import Foundation

public struct RootCertificateStore: Sendable {
    public let directory: URL
    public let certificateURL: URL
    public let privateKeyURL: URL

    /// Serialises `loadOrCreate` across the process. The previous
    /// check-then-create pattern could let two concurrent callers
    /// both miss the file existence check, both generate fresh roots,
    /// and race to overwrite each other — leaving one writer holding
    /// an in-memory `RootCertificate` whose private key no longer
    /// matches what's on disk.
    private static let loadOrCreateLock = NSLock()

    public init(directory: URL) {
        self.directory = directory
        self.certificateURL = directory.appendingPathComponent("reverseapi-root.pem")
        self.privateKeyURL = directory.appendingPathComponent("reverseapi-root-key.pem")
    }

    public static func defaultDirectory(fileManager: FileManager = .default) throws -> URL {
        guard let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            throw CocoaError(.fileNoSuchFile)
        }
        return appSupport.appendingPathComponent("ReverseAPI", isDirectory: true)
    }

    public static func `default`() throws -> RootCertificateStore {
        try RootCertificateStore(directory: defaultDirectory())
    }

    public func loadOrCreate(commonName: String = "ReverseAPI Local Root") throws -> RootCertificate {
        Self.loadOrCreateLock.lock()
        defer { Self.loadOrCreateLock.unlock() }

        let fileManager = FileManager.default
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        try fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)

        if fileManager.fileExists(atPath: certificateURL.path), fileManager.fileExists(atPath: privateKeyURL.path) {
            let certificatePEM = try String(contentsOf: certificateURL, encoding: .utf8)
            let privateKeyPEM = try String(contentsOf: privateKeyURL, encoding: .utf8)
            return try CertificateAuthority.loadRoot(certificatePEM: certificatePEM, privateKeyPEM: privateKeyPEM)
        }

        let root = try CertificateAuthority.generateRoot(commonName: commonName)
        try save(root)
        return root
    }

    public func save(_ root: RootCertificate) throws {
        let fileManager = FileManager.default
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        try fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)

        try root.pem().write(to: certificateURL, atomically: true, encoding: .utf8)
        try root.privateKeyPEM().write(to: privateKeyURL, atomically: true, encoding: .utf8)
        try fileManager.setAttributes([.posixPermissions: 0o644], ofItemAtPath: certificateURL.path)
        try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: privateKeyURL.path)
    }
}
