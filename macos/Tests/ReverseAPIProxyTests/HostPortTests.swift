import XCTest
@testable import ReverseAPIProxy

final class HostPortTests: XCTestCase {
    // MARK: - parseAuthority

    func testParsesHostnameWithoutPort() {
        let hp = HostPort.parseAuthority("example.com")
        XCTAssertEqual(hp?.host, "example.com")
        XCTAssertEqual(hp?.port, 443)
    }

    func testParsesHostnameWithPort() {
        let hp = HostPort.parseAuthority("example.com:8080")
        XCTAssertEqual(hp?.host, "example.com")
        XCTAssertEqual(hp?.port, 8080)
    }

    func testParsesAuthorityWithCustomDefaultPort() {
        let hp = HostPort.parseAuthority("example.com", defaultPort: 80)
        XCTAssertEqual(hp?.port, 80)
    }

    func testParsesIPv4() {
        let hp = HostPort.parseAuthority("127.0.0.1:9090")
        XCTAssertEqual(hp?.host, "127.0.0.1")
        XCTAssertEqual(hp?.port, 9090)
    }

    func testParsesBracketedIPv6WithoutPort() {
        let hp = HostPort.parseAuthority("[::1]", defaultPort: 80)
        XCTAssertEqual(hp?.host, "::1")
        XCTAssertEqual(hp?.port, 80)
    }

    func testParsesBracketedIPv6WithPort() {
        let hp = HostPort.parseAuthority("[2001:db8::1]:8443")
        XCTAssertEqual(hp?.host, "2001:db8::1")
        XCTAssertEqual(hp?.port, 8443)
    }

    func testRejectsEmptyBrackets() {
        XCTAssertNil(HostPort.parseAuthority("[]:80"))
    }

    func testRejectsBracketedHostWithoutColonBeforePort() {
        XCTAssertNil(HostPort.parseAuthority("[::1]8080"))
    }

    func testRejectsPortZero() {
        XCTAssertNil(HostPort.parseAuthority("example.com:0"))
    }

    func testRejectsNegativePort() {
        XCTAssertNil(HostPort.parseAuthority("example.com:-1"))
    }

    func testRejectsPortBeyondMax() {
        XCTAssertNil(HostPort.parseAuthority("example.com:99999"))
    }

    func testRejectsNonNumericPort() {
        XCTAssertNil(HostPort.parseAuthority("example.com:abc"))
    }

    func testRejectsEmptyHost() {
        XCTAssertNil(HostPort.parseAuthority(""))
        XCTAssertNil(HostPort.parseAuthority(":80"))
    }

    // MARK: - parseAbsoluteURI

    func testParsesAbsoluteHTTPWithDefaultPort() {
        guard let (hp, path, scheme) = HostPort.parseAbsoluteURI("http://example.com/foo") else {
            return XCTFail("expected parse to succeed")
        }
        XCTAssertEqual(hp.host, "example.com")
        XCTAssertEqual(hp.port, 80)
        XCTAssertEqual(path, "/foo")
        XCTAssertEqual(scheme, .http)
    }

    func testParsesAbsoluteHTTPSWithDefaultPort() {
        guard let (hp, path, scheme) = HostPort.parseAbsoluteURI("https://api.example.com/v1/users") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.host, "api.example.com")
        XCTAssertEqual(hp.port, 443)
        XCTAssertEqual(path, "/v1/users")
        XCTAssertEqual(scheme, .https)
    }

    func testParsesAbsoluteHTTPSWithExplicitPort() {
        guard let (hp, _, _) = HostPort.parseAbsoluteURI("https://example.com:8443/x") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.port, 8443)
    }

    func testParsesIPv6HTTPDefaultsTo80NotTo443() {
        guard let (hp, _, _) = HostPort.parseAbsoluteURI("http://[::1]/path") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.host, "::1")
        XCTAssertEqual(hp.port, 80, "IPv6 HTTP URL must default to port 80, not 443")
    }

    func testParsesIPv6HTTPSDefaultsTo443() {
        guard let (hp, _, _) = HostPort.parseAbsoluteURI("https://[::1]/path") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.port, 443)
    }

    func testParsesIPv6WithExplicitPort() {
        guard let (hp, _, _) = HostPort.parseAbsoluteURI("https://[2001:db8::1]:9000/x") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.host, "2001:db8::1")
        XCTAssertEqual(hp.port, 9000)
    }

    func testParsesURIWithQueryStringNoSlash() {
        guard let (hp, path, _) = HostPort.parseAbsoluteURI("http://example.com?q=1") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.host, "example.com")
        XCTAssertEqual(path, "/?q=1")
    }

    func testParsesURIWithFragmentNoSlash() {
        guard let (hp, path, _) = HostPort.parseAbsoluteURI("http://example.com#section") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.host, "example.com")
        XCTAssertEqual(path, "/#section")
    }

    func testParsesURIWithoutPathDefaultsToSlash() {
        guard let (hp, path, _) = HostPort.parseAbsoluteURI("http://example.com") else {
            return XCTFail()
        }
        XCTAssertEqual(hp.host, "example.com")
        XCTAssertEqual(path, "/")
    }

    func testParsesURIWithPathAndQuery() {
        guard let (_, path, _) = HostPort.parseAbsoluteURI("https://example.com/users?id=42&name=hi") else {
            return XCTFail()
        }
        XCTAssertEqual(path, "/users?id=42&name=hi")
    }

    func testRejectsURIWithUnknownScheme() {
        XCTAssertNil(HostPort.parseAbsoluteURI("ftp://example.com/x"))
    }

    func testRejectsURIWithInvalidPort() {
        XCTAssertNil(HostPort.parseAbsoluteURI("http://example.com:abc/x"))
        XCTAssertNil(HostPort.parseAbsoluteURI("http://example.com:99999/x"))
    }
}
