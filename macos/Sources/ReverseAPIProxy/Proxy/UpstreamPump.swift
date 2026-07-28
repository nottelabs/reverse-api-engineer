import Foundation
import NIOConcurrencyHelpers
import NIOCore
import NIOPosix
import NIOHTTP1
import NIOSSL

struct UpstreamResponse: Sendable {
    let status: HTTPResponseStatus
    let version: HTTPVersion
    let headers: HTTPHeaders
    let body: ByteBuffer
}

enum UpstreamError: Error {
    case connectionClosed
    case missingResponse
    case unexpected(String)
}

actor UpstreamPump {
    private let group: EventLoopGroup
    private let logger: AppLogger

    init(group: EventLoopGroup, logger: AppLogger) {
        self.group = group
        self.logger = logger
    }

    func send(
        scheme: CapturedFlow.Scheme,
        host: String,
        port: Int,
        method: HTTPMethod,
        uri: String,
        headers: HTTPHeaders,
        body: ByteBuffer
    ) async throws -> UpstreamResponse {
        let collector = ResponseCollector()
        let resultTask = Task { try await collector.awaitResponse() }

        let bootstrap = ClientBootstrap(group: group)
            .channelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)

        let channel: Channel
        do {
            channel = try await bootstrap.connect(host: host, port: port).get()
        } catch {
            collector.cancel(with: error)
            resultTask.cancel()
            throw error
        }

        do {
            if scheme == .https {
                try await channel.eventLoop.submit {
                    var clientConfig = TLSConfiguration.makeClientConfiguration()
                    clientConfig.applicationProtocols = ["http/1.1"]
                    let sslContext = try NIOSSLContext(configuration: clientConfig)
                    let sslHandler = try NIOSSLClientHandler(context: sslContext, serverHostname: host)
                    try channel.pipeline.syncOperations.addHandler(sslHandler, position: .first)
                }.get()
            }

            try await channel.pipeline.addHTTPClientHandlers().get()
            try await channel.pipeline.addHandler(collector).get()

            var requestHeaders = headers
            requestHeaders.replaceOrAdd(name: "Host", value: hostHeaderValue(host: host, port: port, scheme: scheme))
            requestHeaders.replaceOrAdd(name: "Connection", value: "close")
            requestHeaders.remove(name: "Proxy-Connection")

            let head = HTTPRequestHead(
                version: .http1_1,
                method: method,
                uri: uri,
                headers: requestHeaders
            )

            channel.write(HTTPClientRequestPart.head(head), promise: nil)
            if body.readableBytes > 0 {
                channel.write(HTTPClientRequestPart.body(.byteBuffer(body)), promise: nil)
            }
            try await channel.writeAndFlush(HTTPClientRequestPart.end(nil)).get()
        } catch {
            collector.cancel(with: error)
            try? await channel.close().get()
            throw error
        }

        do {
            let response = try await resultTask.value
            try? await channel.close().get()
            return response
        } catch {
            try? await channel.close().get()
            throw error
        }
    }

    private func hostHeaderValue(host: String, port: Int, scheme: CapturedFlow.Scheme) -> String {
        let bracketed = host.contains(":") && !host.hasPrefix("[") ? "[\(host)]" : host
        switch (scheme, port) {
        case (.http, 80), (.https, 443): return bracketed
        default: return "\(bracketed):\(port)"
        }
    }
}

private final class ResponseCollector: ChannelInboundHandler, @unchecked Sendable {
    typealias InboundIn = HTTPClientResponsePart

    private struct State {
        var head: HTTPResponseHead?
        var body: ByteBuffer = ByteBufferAllocator().buffer(capacity: 0)
        var continuation: CheckedContinuation<UpstreamResponse, Error>?
        var result: Result<UpstreamResponse, Error>?
        var settled = false
    }

    private let lock = NIOLockedValueBox<State>(State())

    func awaitResponse() async throws -> UpstreamResponse {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<UpstreamResponse, Error>) in
            let pending: Result<UpstreamResponse, Error>? = lock.withLockedValue { state in
                if state.settled, let result = state.result {
                    return result
                }
                state.continuation = continuation
                return nil
            }
            if let pending {
                switch pending {
                case .success(let value): continuation.resume(returning: value)
                case .failure(let error): continuation.resume(throwing: error)
                }
            }
        }
    }

    func cancel(with error: Error) {
        finish(.failure(error))
    }

    func channelRead(context: ChannelHandlerContext, data: NIOAny) {
        switch unwrapInboundIn(data) {
        case .head(let head):
            lock.withLockedValue { state in
                state.head = head
            }
        case .body(let buffer):
            lock.withLockedValue { state in
                var copy = buffer
                state.body.writeBuffer(&copy)
            }
        case .end:
            let response = lock.withLockedValue { state -> UpstreamResponse in
                let head = state.head ?? HTTPResponseHead(version: .http1_1, status: .internalServerError)
                return UpstreamResponse(status: head.status, version: head.version, headers: head.headers, body: state.body)
            }
            finish(.success(response))
        }
    }

    func errorCaught(context: ChannelHandlerContext, error: Error) {
        finish(.failure(error))
        context.close(promise: nil)
    }

    func channelInactive(context: ChannelHandlerContext) {
        finish(.failure(UpstreamError.connectionClosed))
    }

    private func finish(_ result: Result<UpstreamResponse, Error>) {
        let pending: CheckedContinuation<UpstreamResponse, Error>? = lock.withLockedValue { state in
            if state.settled { return nil }
            state.settled = true
            state.result = result
            let cont = state.continuation
            state.continuation = nil
            return cont
        }
        switch result {
        case .success(let value): pending?.resume(returning: value)
        case .failure(let error): pending?.resume(throwing: error)
        }
    }
}
