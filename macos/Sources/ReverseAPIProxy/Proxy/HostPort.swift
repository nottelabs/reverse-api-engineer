import Foundation

public struct HostPort: Sendable, Hashable {
    public static let validPortRange = 1...65535

    public let host: String
    public let port: Int

    public init(host: String, port: Int) {
        self.host = host
        self.port = port
    }

    public static func parseAuthority(_ string: String, defaultPort: Int = 443) -> HostPort? {
        if string.hasPrefix("[") {
            guard let close = string.firstIndex(of: "]") else { return nil }
            let host = String(string[string.index(after: string.startIndex)..<close])
            guard !host.isEmpty else { return nil }
            let rest = string[string.index(after: close)...]
            if rest.isEmpty { return HostPort(host: host, port: defaultPort) }
            guard rest.first == ":" else { return nil }
            let portString = rest.dropFirst()
            guard let port = Int(portString), validPortRange.contains(port) else { return nil }
            return HostPort(host: host, port: port)
        }
        let parts = string.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        guard let hostPart = parts.first, !hostPart.isEmpty else { return nil }
        if parts.count == 1 {
            return HostPort(host: String(hostPart), port: defaultPort)
        }
        guard let port = Int(parts[1]), validPortRange.contains(port) else { return nil }
        return HostPort(host: String(hostPart), port: port)
    }

    public static func parseAbsoluteURI(_ uri: String) -> (HostPort, String, CapturedFlow.Scheme)? {
        guard let scheme = ["http://", "https://"].first(where: { uri.hasPrefix($0) }) else {
            return nil
        }
        let captured: CapturedFlow.Scheme = scheme == "https://" ? .https : .http
        let defaultPort = captured == .https ? 443 : 80
        let withoutScheme = uri.dropFirst(scheme.count)

        let delimiters = [
            withoutScheme.firstIndex(of: "/"),
            withoutScheme.firstIndex(of: "?"),
            withoutScheme.firstIndex(of: "#"),
        ].compactMap { $0 }
        let authorityEnd = delimiters.min() ?? withoutScheme.endIndex
        let authority = String(withoutScheme[..<authorityEnd])
        let suffix = authorityEnd == withoutScheme.endIndex ? "" : String(withoutScheme[authorityEnd...])
        let path: String
        if suffix.isEmpty {
            path = "/"
        } else if suffix.hasPrefix("/") {
            path = suffix
        } else {
            path = "/" + suffix
        }

        guard let hp = HostPort.parseAuthority(authority, defaultPort: defaultPort) else {
            return nil
        }
        return (hp, path, captured)
    }
}
