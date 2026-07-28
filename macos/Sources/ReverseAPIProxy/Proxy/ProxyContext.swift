import NIOCore

struct ProxyContext: @unchecked Sendable {
    let tlsContexts: TLSContextFactory
    let upstream: UpstreamPump
    let bus: FlowBus
    let logger: AppLogger
}
