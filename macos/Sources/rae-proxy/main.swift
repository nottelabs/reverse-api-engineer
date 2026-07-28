import Foundation
import ReverseAPIProxy
import Darwin

@main
struct RAEProxyCLI {
    static func main() async {
        let logger = AppLogger("cli")
        do {
            let options = try CLIOptions.parse()
            let store = RootCertificateStore(directory: try options.dataDirectory())
            let root = try store.loadOrCreate()

            let engine = try ProxyEngine(root: root, port: options.port)
            try await engine.start()
            // Try to enable the system proxy but don't make it fatal —
            // automatic networksetup can fail under sandboxing,
            // network-config locked by MDM, or missing privileges. Drop
            // back to manual-proxy mode so the user can still point
            // their own client at us.
            let systemProxy = options.systemProxy ? SystemProxyManager(port: options.port) : nil
            var systemProxyActive = false
            if let systemProxy {
                do {
                    try systemProxy.apply()
                    systemProxyActive = true
                    installTerminationHandlers {
                        systemProxy.restore()
                    }
                } catch {
                    logger.error("system proxy setup failed, continuing without it: \(error)")
                    fputs(
                        "warning: could not enable the system proxy (\(error)). "
                        + "Falling back to manual mode — point your client at "
                        + "http://127.0.0.1:\(options.port).\n",
                        stderr
                    )
                }
            }
            defer {
                if systemProxyActive { systemProxy?.restore() }
            }

            print("Proxy listening on 127.0.0.1:\(options.port)")
            if systemProxyActive {
                print("System HTTP/HTTPS proxy enabled. It will be restored on exit.")
            } else if options.systemProxy {
                print("System proxy unavailable — configure your client manually with HTTP/HTTPS proxy = 127.0.0.1:\(options.port).")
            } else {
                print("System proxy disabled. Configure clients manually or omit --no-system-proxy.")
            }
            print("CA stored at:", store.certificateURL.path)
            if !options.trustCA {
                print("HTTPS body capture requires trusting the CA. Use --trust-ca if you want full HTTPS interception.")
            }
            print("Curl smoke test:", "curl -k -x http://127.0.0.1:\(options.port) https://example.com")
            print("Press Ctrl-C to stop.")
            fflush(stdout)

            if options.trustCA {
                Task.detached {
                    trustRoot(at: store.certificateURL)
                }
            }
            if options.launchChrome {
                launchChrome(port: options.port, dataDirectory: store.directory)
            } else {
                print("Chrome launch disabled. Pass --launch-chrome to open an isolated capture profile.")
            }

            let bus = engine.bus
            Task {
                for await event in await bus.subscribe() {
                    switch event {
                    case .started(let flow):
                        print("→ \(flow.method) \(flow.url)")
                    case .updated:
                        break
                    case .finished(let flow):
                        let status = flow.responseStatus.map(String.init) ?? "ERR"
                        let bytes = flow.responseBody.count
                        if let error = flow.error {
                            print("✗ \(flow.method) \(flow.url) — \(error)")
                        } else {
                            print("← \(status) \(flow.method) \(flow.url) (\(bytes) B)")
                        }
                    }
                }
            }

            try await Task.sleep(for: .seconds(60 * 60 * 24 * 365))
            try await engine.stop()
        } catch {
            logger.error("fatal: \(error)")
            fputs("fatal: \(error)\n", stderr)
            exit(1)
        }
    }

    private static func trustRoot(at certificateURL: URL) {
        #if os(macOS)
        let home = FileManager.default.homeDirectoryForCurrentUser
        let keychain = home.appendingPathComponent("Library/Keychains/login.keychain-db")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        process.arguments = [
            "add-trusted-cert",
            "-d",
            "-r",
            "trustRoot",
            "-k",
            keychain.path,
            certificateURL.path,
        ]
        process.standardOutput = Pipe()
        process.standardError = Pipe()

        do {
            try process.run()
            DispatchQueue.global().asyncAfter(deadline: .now() + .seconds(10)) {
                if process.isRunning {
                    process.terminate()
                }
            }
            process.waitUntilExit()
            if process.terminationStatus == 0 {
                print("Root CA trusted in login keychain.")
            } else {
                print("Could not trust the Root CA in the login keychain.")
            }
        } catch {
            print("Could not trust the Root CA: \(error)")
        }
        #else
        print("CA trust installation is only supported on macOS.")
        #endif
    }

    private static func launchChrome(port: Int, dataDirectory: URL) {
        #if os(macOS)
        guard let chromeURL = chromeExecutableURL() else {
            print("Chrome not found. Install Google Chrome or pass --no-launch-chrome and configure your own client.")
            return
        }

        let profileURL = dataDirectory.appendingPathComponent("ChromeProfile", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: profileURL, withIntermediateDirectories: true)
        } catch {
            print("Could not create Chrome profile directory: \(error)")
            return
        }

        let process = Process()
        process.executableURL = chromeURL
        process.arguments = [
            "--user-data-dir=\(profileURL.path)",
            "--proxy-server=http://127.0.0.1:\(port)",
            "--no-first-run",
            "--no-default-browser-check",
            "https://example.com",
        ]

        do {
            try process.run()
            print("Opened isolated Chrome capture profile.")
        } catch {
            print("Could not launch Chrome: \(error)")
        }
        #else
        print("Chrome auto-launch is only supported on macOS.")
        #endif
    }

    private static func chromeExecutableURL() -> URL? {
        let fileManager = FileManager.default
        let candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "\(NSHomeDirectory())/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        return candidates.map { URL(fileURLWithPath: $0) }.first { fileManager.isExecutableFile(atPath: $0.path) }
    }
}

private struct CLIOptions {
    var port: Int
    var trustCA: Bool
    var launchChrome: Bool
    var systemProxy: Bool
    var dataDirectoryOverride: URL?

    static func parse(
        arguments: [String] = Array(ProcessInfo.processInfo.arguments.dropFirst()),
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) throws -> CLIOptions {
        var port = environment["RAE_PROXY_PORT"].flatMap(Int.init) ?? 8888
        var trustCA = environment["RAE_PROXY_TRUST_CA"].map(isTruthy) ?? false
        var launchChrome = environment["RAE_PROXY_LAUNCH_CHROME"].map(isTruthy) ?? false
        var systemProxy = environment["RAE_PROXY_SYSTEM_PROXY"].map(isTruthy) ?? true
        var dataDirectory = environment["RAE_PROXY_DATA_DIR"].map { URL(fileURLWithPath: $0, isDirectory: true) }

        var iterator = arguments.makeIterator()
        while let argument = iterator.next() {
            switch argument {
            case "--trust-ca":
                trustCA = true
            case "--no-trust-ca":
                trustCA = false
            case "--launch-chrome":
                launchChrome = true
            case "--no-launch-chrome":
                launchChrome = false
            case "--system-proxy":
                systemProxy = true
            case "--no-system-proxy":
                systemProxy = false
            case "--port":
                guard let value = iterator.next(), let parsed = Int(value), HostPort.validPortRange.contains(parsed) else {
                    throw CLIError.invalidOption("--port requires a value from 1 to 65535")
                }
                port = parsed
            case "--data-dir":
                guard let value = iterator.next(), !value.isEmpty else {
                    throw CLIError.invalidOption("--data-dir requires a path")
                }
                dataDirectory = URL(fileURLWithPath: value, isDirectory: true)
            default:
                throw CLIError.invalidOption("unknown option \(argument)")
            }
        }

        guard HostPort.validPortRange.contains(port) else {
            throw CLIError.invalidOption("port must be from 1 to 65535")
        }

        return CLIOptions(
            port: port,
            trustCA: trustCA,
            launchChrome: launchChrome,
            systemProxy: systemProxy,
            dataDirectoryOverride: dataDirectory
        )
    }

    func dataDirectory() throws -> URL {
        if let dataDirectoryOverride {
            return dataDirectoryOverride
        }
        return try RootCertificateStore.defaultDirectory()
    }

    private static func isTruthy(_ value: String) -> Bool {
        ["1", "true", "yes", "on"].contains(value.lowercased())
    }
}

private enum CLIError: Error, CustomStringConvertible {
    case invalidOption(String)

    var description: String {
        switch self {
        case .invalidOption(let message):
            return message
        }
    }
}

private final class SystemProxyManager: @unchecked Sendable {
    private struct Snapshot {
        let service: String
        let kind: ProxyKind
        let enabled: Bool
        let server: String
        let port: Int
    }

    private enum ProxyKind: CaseIterable {
        case web
        case secureWeb

        var getCommand: String {
            switch self {
            case .web: return "-getwebproxy"
            case .secureWeb: return "-getsecurewebproxy"
            }
        }

        var setCommand: String {
            switch self {
            case .web: return "-setwebproxy"
            case .secureWeb: return "-setsecurewebproxy"
            }
        }

        var setStateCommand: String {
            switch self {
            case .web: return "-setwebproxystate"
            case .secureWeb: return "-setsecurewebproxystate"
            }
        }
    }

    private let port: Int
    private let lock = NSLock()
    private var snapshots: [Snapshot] = []
    private var applied = false

    init(port: Int) {
        self.port = port
    }

    func apply() throws {
        lock.lock()
        guard !applied else {
            lock.unlock()
            return
        }
        applied = true
        lock.unlock()

        do {
            let services = try activeNetworkServices()
            for service in services {
                for kind in ProxyKind.allCases {
                    let currentSnapshot = try snapshot(service: service, kind: kind)
                    lock.lock()
                    snapshots.append(currentSnapshot)
                    lock.unlock()
                    try runNetworkSetup([kind.setCommand, service, "127.0.0.1", String(port)])
                    try runNetworkSetup([kind.setStateCommand, service, "on"])
                }
            }
        } catch {
            restore()
            throw error
        }
    }

    func restore() {
        lock.lock()
        let currentSnapshots = snapshots
        snapshots = []
        let shouldRestore = applied
        applied = false
        lock.unlock()

        guard shouldRestore else { return }
        for snapshot in currentSnapshots.reversed() {
            do {
                if snapshot.enabled {
                    try runNetworkSetup([snapshot.kind.setCommand, snapshot.service, snapshot.server, String(snapshot.port)])
                    try runNetworkSetup([snapshot.kind.setStateCommand, snapshot.service, "on"])
                } else {
                    try runNetworkSetup([snapshot.kind.setStateCommand, snapshot.service, "off"])
                }
            } catch {
                fputs("warning: failed to restore proxy for \(snapshot.service): \(error)\n", stderr)
            }
        }
    }

    private func activeNetworkServices() throws -> [String] {
        let output = try runNetworkSetup(["-listallnetworkservices"])
        return output
            .split(separator: "\n")
            .dropFirst()
            .map(String.init)
            .filter { !$0.hasPrefix("*") && !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }

    private func snapshot(service: String, kind: ProxyKind) throws -> Snapshot {
        let output = try runNetworkSetup([kind.getCommand, service])
        let fields = Dictionary(
            uniqueKeysWithValues: output.split(separator: "\n").compactMap { line -> (String, String)? in
                let parts = line.split(separator: ":", maxSplits: 1)
                guard parts.count == 2 else { return nil }
                return (
                    String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines),
                    String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
                )
            }
        )
        return Snapshot(
            service: service,
            kind: kind,
            enabled: fields["Enabled"] == "Yes",
            server: fields["Server"] ?? "",
            port: Int(fields["Port"] ?? "") ?? 0
        )
    }

    @discardableResult
    private func runNetworkSetup(_ arguments: [String]) throws -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/networksetup")
        process.arguments = arguments

        let output = Pipe()
        let error = Pipe()
        process.standardOutput = output
        process.standardError = error

        try process.run()
        process.waitUntilExit()

        let data = output.fileHandleForReading.readDataToEndOfFile()
        let errorData = error.fileHandleForReading.readDataToEndOfFile()
        if process.terminationStatus != 0 {
            let message = String(data: errorData, encoding: .utf8) ?? "networksetup failed"
            throw CLIError.invalidOption(message.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return String(data: data, encoding: .utf8) ?? ""
    }
}

private var signalSources: [DispatchSourceSignal] = []

private func installTerminationHandlers(_ cleanup: @escaping @Sendable () -> Void) {
    for signalNumber in [SIGINT, SIGTERM] {
        signal(signalNumber, SIG_IGN)
        let source = DispatchSource.makeSignalSource(signal: signalNumber, queue: .main)
        source.setEventHandler {
            cleanup()
            exit(0)
        }
        source.resume()
        signalSources.append(source)
    }
}
