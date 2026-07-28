import Foundation
import NIOCore
import NIOFoundationCompat
import NIOHTTP1
import NIOSSL

final class ProxyHandler: ChannelInboundHandler, RemovableChannelHandler, @unchecked Sendable {
    typealias InboundIn = HTTPServerRequestPart
    typealias OutboundOut = HTTPServerResponsePart

    enum Mode {
        case entry
        case bumped(host: String, port: Int)
    }

    private enum Phase {
        case idle
        case buffering(InflightRequest)
        case bumping
        case rejected
    }

    static let defaultMaxBodyBytes = 32 * 1024 * 1024

    private let context: ProxyContext
    private let mode: Mode
    private let maxBodyBytes: Int
    private var phase: Phase = .idle

    init(context: ProxyContext, mode: Mode, maxBodyBytes: Int = ProxyHandler.defaultMaxBodyBytes) {
        self.context = context
        self.mode = mode
        self.maxBodyBytes = max(1024, maxBodyBytes)
    }

    func channelRead(context channelContext: ChannelHandlerContext, data: NIOAny) {
        let part = unwrapInboundIn(data)
        switch part {
        case .head(let head):
            onHead(channelContext: channelContext, head: head)
        case .body(let buffer):
            onBody(channelContext: channelContext, buffer: buffer)
        case .end(let trailers):
            onEnd(channelContext: channelContext, trailers: trailers)
        }
    }

    func errorCaught(context: ChannelHandlerContext, error: Error) {
        self.context.logger.error("proxy handler error: \(error)")
        context.close(promise: nil)
    }

    private func onHead(channelContext: ChannelHandlerContext, head: HTTPRequestHead) {
        switch mode {
        case .entry:
            if head.method == .CONNECT {
                beginBump(channelContext: channelContext, head: head)
                return
            }
            guard let parsed = HostPort.parseAbsoluteURI(head.uri) else {
                respondError(channelContext: channelContext, status: .badRequest)
                return
            }
            let (target, path, scheme) = parsed
            phase = .buffering(InflightRequest(head: head, scheme: scheme, host: target.host, port: target.port, path: path))
        case .bumped(let host, let port):
            phase = .buffering(InflightRequest(head: head, scheme: .https, host: host, port: port, path: head.uri))
        }
    }

    private func onBody(channelContext: ChannelHandlerContext, buffer: ByteBuffer) {
        guard case .buffering(var inflight) = phase else { return }
        inflight.appendBody(buffer)
        // Reject + close immediately on overflow. Waiting for `.end`
        // lets a hostile client keep streaming past the limit and
        // grow the buffer arbitrarily.
        if inflight.body.readableBytes > maxBodyBytes {
            phase = .rejected
            respondError(channelContext: channelContext, status: .payloadTooLarge)
            return
        }
        phase = .buffering(inflight)
    }

    private func onEnd(channelContext: ChannelHandlerContext, trailers: HTTPHeaders?) {
        // `.rejected` already wrote the 413 + closed in `onBody`; just
        // drop any trailing parts the client may still be sending.
        if case .rejected = phase { return }
        guard case .buffering(var inflight) = phase else { return }
        inflight.appendTrailers(trailers)
        phase = .idle
        dispatch(channelContext: channelContext, inflight: inflight)
    }

    private func dispatch(channelContext: ChannelHandlerContext, inflight: InflightRequest) {
        let proxyContext = self.context
        let channel = channelContext.channel
        let eventLoop = channelContext.eventLoop

        var headersForUpstream = inflight.head.headers
        sanitizeRequestHeaders(&headersForUpstream)
        let flow = makeFlow(from: inflight)

        Task {
            await proxyContext.bus.emit(.started(flow))
            do {
                let response = try await proxyContext.upstream.send(
                    scheme: inflight.scheme,
                    host: inflight.host,
                    port: inflight.port,
                    method: inflight.head.method,
                    uri: inflight.path,
                    headers: headersForUpstream,
                    body: inflight.body
                )
                var captured = flow
                captured.responseStatus = Int(response.status.code)
                captured.responseHeaders = response.headers.map { HTTPHeader($0.name, $0.value) }
                captured.responseBody = Data(buffer: response.body)
                captured.finishedAt = Date()
                await proxyContext.bus.emit(.finished(captured))

                eventLoop.execute {
                    var head = HTTPResponseHead(version: response.version, status: response.status, headers: response.headers)
                    head.headers.replaceOrAdd(name: "Connection", value: "close")
                    head.headers.remove(name: "Transfer-Encoding")
                    head.headers.replaceOrAdd(name: "Content-Length", value: String(response.body.readableBytes))

                    channel.write(HTTPServerResponsePart.head(head), promise: nil)
                    if response.body.readableBytes > 0 {
                        channel.write(HTTPServerResponsePart.body(.byteBuffer(response.body)), promise: nil)
                    }
                    channel.writeAndFlush(HTTPServerResponsePart.end(nil)).whenComplete { _ in
                        channel.close(promise: nil)
                    }
                }
            } catch {
                var failed = flow
                failed.error = "\(error)"
                failed.finishedAt = Date()
                await proxyContext.bus.emit(.finished(failed))
                proxyContext.logger.error("upstream \(inflight.host):\(inflight.port) failed: \(error)")
                eventLoop.execute { channel.close(promise: nil) }
            }
        }
    }

    private func beginBump(channelContext: ChannelHandlerContext, head: HTTPRequestHead) {
        guard let target = HostPort.parseAuthority(head.uri) else {
            respondError(channelContext: channelContext, status: .badRequest)
            return
        }
        phase = .bumping
        let proxyContext = self.context
        let channel = channelContext.channel
        let eventLoop = channelContext.eventLoop

        Task {
            do {
                let tlsContext = try await proxyContext.tlsContexts.serverContext(for: target.host)
                try await eventLoop.submit {
                    var okHead = HTTPResponseHead(version: .http1_1, status: .ok)
                    okHead.headers.add(name: "Content-Length", value: "0")
                    channel.write(HTTPServerResponsePart.head(okHead), promise: nil)
                    channel.writeAndFlush(HTTPServerResponsePart.end(nil), promise: nil)

                    let pipeline = channel.pipeline.syncOperations
                    _ = pipeline.removeHandler(self)
                    _ = pipeline.removeHandler(name: PipelineNames.encoder)
                    _ = pipeline.removeHandler(name: PipelineNames.decoder)

                    let sslHandler = NIOSSLServerHandler(context: tlsContext)
                    try pipeline.addHandler(sslHandler, name: PipelineNames.tls, position: .first)
                    try pipeline.addHandler(
                        ByteToMessageHandler(HTTPRequestDecoder(leftOverBytesStrategy: .forwardBytes)),
                        name: PipelineNames.decoder
                    )
                    try pipeline.addHandler(HTTPResponseEncoder(), name: PipelineNames.encoder)
                    try pipeline.addHandler(
                        ProxyHandler(context: proxyContext, mode: .bumped(host: target.host, port: target.port)),
                        name: PipelineNames.proxy
                    )
                }.get()
            } catch {
                proxyContext.logger.error("bump install failed for \(target.host): \(error)")
                eventLoop.execute { channel.close(promise: nil) }
            }
        }
    }

    private func respondError(channelContext: ChannelHandlerContext, status: HTTPResponseStatus) {
        var headers = HTTPHeaders()
        headers.add(name: "Content-Length", value: "0")
        headers.add(name: "Connection", value: "close")
        let head = HTTPResponseHead(version: .http1_1, status: status, headers: headers)
        channelContext.write(wrapOutboundOut(.head(head)), promise: nil)
        channelContext.writeAndFlush(wrapOutboundOut(.end(nil))).whenComplete { _ in
            channelContext.close(promise: nil)
        }
    }

    private func sanitizeRequestHeaders(_ headers: inout HTTPHeaders) {
        headers.remove(name: "Proxy-Connection")
        headers.remove(name: "Proxy-Authorization")
        headers.replaceOrAdd(name: "Connection", value: "close")
    }

    private func makeFlow(from inflight: InflightRequest) -> CapturedFlow {
        var flow = CapturedFlow(
            scheme: inflight.scheme,
            method: inflight.head.method.rawValue,
            host: inflight.host,
            port: inflight.port,
            path: inflight.path
        )
        flow.requestHeaders = inflight.head.headers.map { HTTPHeader($0.name, $0.value) }
        flow.requestBody = Data(buffer: inflight.body)
        return flow
    }
}

enum PipelineNames {
    static let tls = "tls"
    static let decoder = "http-request-decoder"
    static let encoder = "http-response-encoder"
    static let proxy = "proxy-handler"
}

struct InflightRequest {
    let head: HTTPRequestHead
    let scheme: CapturedFlow.Scheme
    let host: String
    let port: Int
    let path: String
    var body: ByteBuffer = ByteBufferAllocator().buffer(capacity: 0)
    var trailers: HTTPHeaders?

    mutating func appendBody(_ buffer: ByteBuffer) {
        var b = buffer
        body.writeBuffer(&b)
    }

    mutating func appendTrailers(_ headers: HTTPHeaders?) {
        trailers = headers
    }
}
