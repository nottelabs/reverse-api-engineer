import XCTest
@testable import ReverseAPIProxy

final class CapturedFlowURLTests: XCTestCase {
    func testHTTPDefaultPortOmitsPortSegment() {
        let flow = CapturedFlow(scheme: .http, method: "GET", host: "example.com", port: 80, path: "/x")
        XCTAssertEqual(flow.url, "http://example.com/x")
    }

    func testHTTPSDefaultPortOmitsPortSegment() {
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "example.com", port: 443, path: "/x")
        XCTAssertEqual(flow.url, "https://example.com/x")
    }

    func testHTTPCustomPortShown() {
        let flow = CapturedFlow(scheme: .http, method: "GET", host: "example.com", port: 8080, path: "/x")
        XCTAssertEqual(flow.url, "http://example.com:8080/x")
    }

    func testIPv6HostWrappedInBrackets() {
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "2001:db8::1", port: 443, path: "/x")
        XCTAssertEqual(flow.url, "https://[2001:db8::1]/x")
    }

    func testIPv6HostWithCustomPort() {
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "::1", port: 8443, path: "/")
        XCTAssertEqual(flow.url, "https://[::1]:8443/")
    }

    func testIPv4HostNotBracketed() {
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "127.0.0.1", port: 443, path: "/x")
        XCTAssertEqual(flow.url, "https://127.0.0.1/x")
    }

    func testAlreadyBracketedHostIsNotDoubleWrapped() {
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "[::1]", port: 8443, path: "/")
        XCTAssertEqual(flow.url, "https://[::1]:8443/")
    }
}

final class CapturedFlowInitTests: XCTestCase {
    func testInitProducesNonNilDefaults() {
        let flow = CapturedFlow(scheme: .https, method: "POST", host: "h", port: 1, path: "/")
        XCTAssertTrue(flow.requestHeaders.isEmpty)
        XCTAssertTrue(flow.responseHeaders.isEmpty)
        XCTAssertEqual(flow.requestBody, Data())
        XCTAssertEqual(flow.responseBody, Data())
        XCTAssertNil(flow.responseStatus)
        XCTAssertNil(flow.finishedAt)
        XCTAssertNil(flow.error)
    }
}
