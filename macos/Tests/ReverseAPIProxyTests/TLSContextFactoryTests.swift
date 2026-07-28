import XCTest
@testable import ReverseAPIProxy

final class TLSContextFactoryTests: XCTestCase {
    func testReturnsSameInstanceOnSecondCall() async throws {
        let root = try CertificateAuthority.generateRoot()
        let leaf = try LeafCertificateFactory(root: root)
        let factory = TLSContextFactory(leafFactory: leaf)
        let first = try await factory.serverContext(for: "example.com")
        let second = try await factory.serverContext(for: "example.com")
        XCTAssertTrue(first === second)
    }

    func testDeduplicatesConcurrentCallsForSameHost() async throws {
        let root = try CertificateAuthority.generateRoot()
        let leaf = try LeafCertificateFactory(root: root)
        let factory = TLSContextFactory(leafFactory: leaf)
        async let a = factory.serverContext(for: "concurrent.example.com")
        async let b = factory.serverContext(for: "concurrent.example.com")
        async let c = factory.serverContext(for: "concurrent.example.com")
        let (ra, rb, rc) = try await (a, b, c)
        XCTAssertTrue(ra === rb)
        XCTAssertTrue(rb === rc)
        let hosts = await factory.cachedHosts()
        XCTAssertEqual(hosts.filter { $0 == "concurrent.example.com" }.count, 1)
    }

    func testDifferentHostsGetDifferentContexts() async throws {
        let root = try CertificateAuthority.generateRoot()
        let leaf = try LeafCertificateFactory(root: root)
        let factory = TLSContextFactory(leafFactory: leaf)
        let a = try await factory.serverContext(for: "a.example.com")
        let b = try await factory.serverContext(for: "b.example.com")
        XCTAssertFalse(a === b)
    }
}
