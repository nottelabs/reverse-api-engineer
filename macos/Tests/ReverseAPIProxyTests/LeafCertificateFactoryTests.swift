import XCTest
@testable import ReverseAPIProxy

final class LeafCertificateFactoryTests: XCTestCase {
    func testCachesMaterialsPerHost() async throws {
        let root = try CertificateAuthority.generateRoot()
        let factory = try LeafCertificateFactory(root: root)
        let first = try await factory.materials(for: "example.com")
        let second = try await factory.materials(for: "example.com")
        XCTAssertEqual(try first.certificate.toDERBytes(), try second.certificate.toDERBytes())
    }

    func testDifferentHostsProduceDifferentCertificates() async throws {
        let root = try CertificateAuthority.generateRoot()
        let factory = try LeafCertificateFactory(root: root)
        let a = try await factory.materials(for: "a.example.com")
        let b = try await factory.materials(for: "b.example.com")
        XCTAssertNotEqual(try a.certificate.toDERBytes(), try b.certificate.toDERBytes())
    }

    func testCacheRespectsLimit() async throws {
        let root = try CertificateAuthority.generateRoot()
        let factory = try LeafCertificateFactory(root: root, cacheLimit: 2)
        _ = try await factory.materials(for: "a.example.com")
        _ = try await factory.materials(for: "b.example.com")
        _ = try await factory.materials(for: "c.example.com")
        let count = await factory.cacheCount()
        XCTAssertEqual(count, 2, "cache must not exceed declared limit")
    }

    func testCacheEvictsLeastRecentlyUsed() async throws {
        let root = try CertificateAuthority.generateRoot()
        let factory = try LeafCertificateFactory(root: root, cacheLimit: 2)
        _ = try await factory.materials(for: "a.example.com")
        _ = try await factory.materials(for: "b.example.com")
        _ = try await factory.materials(for: "a.example.com")
        _ = try await factory.materials(for: "c.example.com")
        let aFirstDER = try await factory.materials(for: "a.example.com").certificate.toDERBytes()
        _ = try await factory.materials(for: "b.example.com")
        let aSecondDER = try await factory.materials(for: "a.example.com").certificate.toDERBytes()
        XCTAssertEqual(aFirstDER, aSecondDER, "recently used cert should still be cached")
    }

    func testIPv4HostProducesValidCertificate() async throws {
        let root = try CertificateAuthority.generateRoot()
        let factory = try LeafCertificateFactory(root: root)
        let materials = try await factory.materials(for: "127.0.0.1")
        XCTAssertFalse(try materials.certificate.toDERBytes().isEmpty)
    }
}
