import Foundation
import Crypto
import X509
import SwiftASN1

public struct RootCertificate: Sendable {
    public let certificate: Certificate
    public let privateKey: Certificate.PrivateKey

    public func derBytes() throws -> [UInt8] {
        var serializer = DER.Serializer()
        try serializer.serialize(certificate)
        return serializer.serializedBytes
    }

    public func pem() throws -> String {
        let pemDoc = PEMDocument(type: "CERTIFICATE", derBytes: try derBytes())
        return pemDoc.pemString
    }

    public func privateKeyPEM() throws -> String {
        try privateKey.serializeAsPEM().pemString
    }
}

public enum CertificateAuthority {
    public static func generateRoot(commonName: String = "ReverseAPI Local Root") throws -> RootCertificate {
        let signingKey = P256.Signing.PrivateKey()
        let privateKey = Certificate.PrivateKey(signingKey)

        let name = try DistinguishedName {
            CommonName(commonName)
            OrganizationName("ReverseAPI")
        }

        let now = Date()
        let notValidAfter = now.addingTimeInterval(10 * 365 * 24 * 60 * 60)

        let extensions = try Certificate.Extensions {
            Critical(BasicConstraints.isCertificateAuthority(maxPathLength: 0))
            Critical(KeyUsage(keyCertSign: true, cRLSign: true))
            SubjectKeyIdentifier(hash: privateKey.publicKey)
        }

        let certificate = try Certificate(
            version: .v3,
            serialNumber: Certificate.SerialNumber(),
            publicKey: privateKey.publicKey,
            notValidBefore: now.addingTimeInterval(-60),
            notValidAfter: notValidAfter,
            issuer: name,
            subject: name,
            signatureAlgorithm: .ecdsaWithSHA256,
            extensions: extensions,
            issuerPrivateKey: privateKey
        )

        return RootCertificate(certificate: certificate, privateKey: privateKey)
    }

    public static func loadRoot(certificatePEM: String, privateKeyPEM: String) throws -> RootCertificate {
        let certificate = try Certificate(pemEncoded: certificatePEM)
        let privateKey = try Certificate.PrivateKey(pemEncoded: privateKeyPEM)
        // Reject mismatched pairs at load time. Without this, a
        // de-synced cert/key on disk (concurrent writes, manual edit,
        // partial restore) silently breaks every TLS interception
        // until the next regen — and the breakage looks like an
        // upstream cert error, not a local config issue.
        guard privateKey.publicKey == certificate.publicKey else {
            throw CertificateAuthorityError.keyPairMismatch
        }
        return RootCertificate(certificate: certificate, privateKey: privateKey)
    }
}

public enum CertificateAuthorityError: Error, Equatable {
    case keyPairMismatch
}
