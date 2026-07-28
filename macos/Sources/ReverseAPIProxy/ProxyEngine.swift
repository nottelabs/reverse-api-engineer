import Foundation
import NIOCore
import NIOPosix
import NIOHTTP1

public final class ProxyEngine: @unchecked Sendable {
    public let port: Int
    public let bus: FlowBus
    public let root: RootCertificate

    private let leafFactory: LeafCertificateFactory
    private let tlsContexts: TLSContextFactory
    private let upstream: UpstreamPump
    private let logger = AppLogger("proxy.engine")
    private let group: MultiThreadedEventLoopGroup

    private var serverChannel: Channel?

    public init(root: RootCertificate, port: Int = 8888, bus: FlowBus = FlowBus()) throws {
        self.root = root
        self.port = port
        self.bus = bus
        self.leafFactory = try LeafCertificateFactory(root: root)
        self.tlsContexts = TLSContextFactory(leafFactory: leafFactory)
        self.group = MultiThreadedEventLoopGroup(numberOfThreads: System.coreCount)
        self.upstream = UpstreamPump(group: group, logger: AppLogger("proxy.upstream"))
    }

    public var isRunning: Bool { serverChannel != nil }

    public func start(host: String = "127.0.0.1") async throws {
        guard serverChannel == nil else { return }
        let proxyContext = ProxyContext(tlsContexts: tlsContexts, upstream: upstream, bus: bus, logger: AppLogger("proxy.handler"))

        let bootstrap = ServerBootstrap(group: group)
            .serverChannelOption(ChannelOptions.backlog, value: 256)
            .serverChannelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)
            .childChannelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)
            .childChannelOption(ChannelOptions.allowRemoteHalfClosure, value: true)
            .childChannelInitializer { channel in
                let decoder = ByteToMessageHandler(HTTPRequestDecoder(leftOverBytesStrategy: .forwardBytes))
                let encoder = HTTPResponseEncoder()
                let proxy = ProxyHandler(context: proxyContext, mode: .entry)
                do {
                    try channel.pipeline.syncOperations.addHandler(decoder, name: PipelineNames.decoder)
                    try channel.pipeline.syncOperations.addHandler(encoder, name: PipelineNames.encoder)
                    try channel.pipeline.syncOperations.addHandler(proxy, name: PipelineNames.proxy)
                    return channel.eventLoop.makeSucceededVoidFuture()
                } catch {
                    return channel.eventLoop.makeFailedFuture(error)
                }
            }

        let channel = try await bootstrap.bind(host: host, port: port).get()
        serverChannel = channel
        logger.info("proxy listening on \(host):\(port)")
    }

    public func stop() async throws {
        // Always shutdown the event-loop group, even when the channel
        // close fails — otherwise NIO threads leak on every restart.
        var closeError: Error?
        if let channel = serverChannel {
            serverChannel = nil
            do {
                try await channel.close().get()
            } catch ChannelError.alreadyClosed {
                logger.info("proxy channel already closed")
            } catch {
                closeError = error
            }
        }
        do {
            try await group.shutdownGracefully()
        } catch {
            logger.error("event-loop shutdown failed: \(error)")
            // Re-throw the shutdown failure if we don't already have
            // a more specific channel error to surface.
            if closeError == nil { throw error }
        }
        if let closeError { throw closeError }
        logger.info("proxy stopped")
    }
}
