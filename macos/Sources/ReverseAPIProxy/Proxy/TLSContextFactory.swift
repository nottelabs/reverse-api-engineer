import Foundation
import NIOSSL

actor TLSContextFactory {
    private let leafFactory: LeafCertificateFactory
    private var cache: [String: NIOSSLContext] = [:]
    private var inflight: [String: Task<NIOSSLContext, Error>] = [:]

    init(leafFactory: LeafCertificateFactory) {
        self.leafFactory = leafFactory
    }

    func serverContext(for host: String) async throws -> NIOSSLContext {
        if let cached = cache[host] { return cached }
        if let pending = inflight[host] {
            return try await pending.value
        }
        let factory = leafFactory
        let task = Task<NIOSSLContext, Error> {
            let materials = try await factory.materials(for: host)
            var config = TLSConfiguration.makeServerConfiguration(
                certificateChain: [.certificate(materials.certificate)],
                privateKey: .privateKey(materials.privateKey)
            )
            config.minimumTLSVersion = .tlsv12
            config.applicationProtocols = ["http/1.1"]
            return try NIOSSLContext(configuration: config)
        }
        inflight[host] = task
        defer { inflight.removeValue(forKey: host) }
        let context = try await task.value
        cache[host] = context
        return context
    }

    func cachedHosts() -> [String] {
        Array(cache.keys)
    }
}
