import Foundation
import Crypto
import X509
import SwiftASN1
import NIOSSL

public actor LeafCertificateFactory {
    public struct Materials: Sendable {
        public let certificate: NIOSSLCertificate
        public let privateKey: NIOSSLPrivateKey
        public let rootCertificate: NIOSSLCertificate
    }

    public static let defaultCacheLimit = 256

    private let root: RootCertificate
    private let rootSSL: NIOSSLCertificate
    private let rootKeyIdentifier: ArraySlice<UInt8>
    private let cacheLimit: Int
    private var cache: [String: Materials] = [:]
    private var order: [String] = []

    public init(root: RootCertificate, cacheLimit: Int = LeafCertificateFactory.defaultCacheLimit) throws {
        self.root = root
        var serializer = DER.Serializer()
        try serializer.serialize(root.certificate)
        self.rootSSL = try NIOSSLCertificate(bytes: serializer.serializedBytes, format: .der)
        self.rootKeyIdentifier = SubjectKeyIdentifier(hash: root.privateKey.publicKey).keyIdentifier
        self.cacheLimit = max(1, cacheLimit)
    }

    public func materials(for host: String) throws -> Materials {
        if let cached = cache[host] {
            touch(host)
            return cached
        }
        let minted = try mint(host: host)
        insert(host: host, materials: minted)
        return minted
    }

    public func cacheCount() -> Int {
        cache.count
    }

    private func insert(host: String, materials: Materials) {
        cache[host] = materials
        order.removeAll(where: { $0 == host })
        order.append(host)
        while order.count > cacheLimit {
            let evict = order.removeFirst()
            cache.removeValue(forKey: evict)
        }
    }

    private func touch(_ host: String) {
        if let idx = order.firstIndex(of: host) {
            order.remove(at: idx)
            order.append(host)
        }
    }

    private func mint(host: String) throws -> Materials {
        let leafSigning = P256.Signing.PrivateKey()
        let leafPrivateKey = Certificate.PrivateKey(leafSigning)

        let subject = try DistinguishedName {
            CommonName(host)
            OrganizationName("ReverseAPI")
        }

        let now = Date()
        let notValidAfter = now.addingTimeInterval(397 * 24 * 60 * 60)

        let extensions = try Certificate.Extensions {
            Critical(BasicConstraints.notCertificateAuthority)
            Critical(KeyUsage(digitalSignature: true, keyEncipherment: true))
            try ExtendedKeyUsage([.serverAuth, .clientAuth])
            subjectAlternativeNames(for: host)
            SubjectKeyIdentifier(hash: leafPrivateKey.publicKey)
            AuthorityKeyIdentifier(keyIdentifier: rootKeyIdentifier)
        }

        let certificate = try Certificate(
            version: .v3,
            serialNumber: Certificate.SerialNumber(),
            publicKey: leafPrivateKey.publicKey,
            notValidBefore: now.addingTimeInterval(-60),
            notValidAfter: notValidAfter,
            issuer: root.certificate.subject,
            subject: subject,
            signatureAlgorithm: .ecdsaWithSHA256,
            extensions: extensions,
            issuerPrivateKey: root.privateKey
        )

        var certSerializer = DER.Serializer()
        try certSerializer.serialize(certificate)
        let certBytes = certSerializer.serializedBytes
        let nioCert = try NIOSSLCertificate(bytes: certBytes, format: .der)

        let keyPEM = try leafPrivateKey.serializeAsPEM().pemString
        let nioKey = try NIOSSLPrivateKey(bytes: Array(keyPEM.utf8), format: .pem)

        return Materials(certificate: nioCert, privateKey: nioKey, rootCertificate: rootSSL)
    }

    private func subjectAlternativeNames(for host: String) -> SubjectAlternativeNames {
        if let bytes = ipv4Bytes(host) {
            return SubjectAlternativeNames([.ipAddress(ASN1OctetString(contentBytes: ArraySlice(bytes)))])
        }
        if let bytes = ipv6Bytes(host) {
            return SubjectAlternativeNames([.ipAddress(ASN1OctetString(contentBytes: ArraySlice(bytes)))])
        }
        return SubjectAlternativeNames([.dnsName(host)])
    }
}

private func ipv4Bytes(_ host: String) -> [UInt8]? {
    let parts = host.split(separator: ".")
    guard parts.count == 4 else { return nil }
    var bytes = [UInt8]()
    for part in parts {
        guard let value = UInt8(part) else { return nil }
        bytes.append(value)
    }
    return bytes
}

private func ipv6Bytes(_ host: String) -> [UInt8]? {
    guard host.contains(":") else { return nil }
    var hints = addrinfo()
    hints.ai_family = AF_INET6
    hints.ai_flags = AI_NUMERICHOST
    var result: UnsafeMutablePointer<addrinfo>?
    let status = getaddrinfo(host, nil, &hints, &result)
    guard status == 0, let info = result else { return nil }
    defer { freeaddrinfo(info) }
    guard let sockaddr = info.pointee.ai_addr else { return nil }
    return sockaddr.withMemoryRebound(to: sockaddr_in6.self, capacity: 1) { ptr in
        var addr = ptr.pointee.sin6_addr
        return withUnsafeBytes(of: &addr) { Array($0) }
    }
}
