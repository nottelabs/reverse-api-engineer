import Foundation

public struct HTTPHeader: Sendable, Hashable {
    public var name: String
    public var value: String

    public init(_ name: String, _ value: String) {
        self.name = name
        self.value = value
    }
}

public struct CapturedFlow: Sendable, Identifiable {
    public enum Scheme: String, Sendable {
        case http
        case https
    }

    public let id: UUID
    public let scheme: Scheme
    public let method: String
    public let host: String
    public let port: Int
    public let path: String
    public var requestHeaders: [HTTPHeader]
    public var requestBody: Data
    public var responseStatus: Int?
    public var responseHeaders: [HTTPHeader]
    public var responseBody: Data
    public let startedAt: Date
    public var finishedAt: Date?
    public var error: String?

    public init(
        id: UUID = UUID(),
        scheme: Scheme,
        method: String,
        host: String,
        port: Int,
        path: String,
        requestHeaders: [HTTPHeader] = [],
        startedAt: Date = Date()
    ) {
        self.id = id
        self.scheme = scheme
        self.method = method
        self.host = host
        self.port = port
        self.path = path
        self.requestHeaders = requestHeaders
        self.requestBody = Data()
        self.responseStatus = nil
        self.responseHeaders = []
        self.responseBody = Data()
        self.startedAt = startedAt
        self.finishedAt = nil
        self.error = nil
    }

    public var url: String {
        let bracketed = host.contains(":") && !host.hasPrefix("[") ? "[\(host)]" : host
        let portSegment: String
        switch (scheme, port) {
        case (.http, 80), (.https, 443):
            portSegment = ""
        default:
            portSegment = ":\(port)"
        }
        return "\(scheme.rawValue)://\(bracketed)\(portSegment)\(path)"
    }
}
