import Foundation
import os

public struct AppLogger: Sendable {
    private let logger: Logger

    public init(_ category: String) {
        self.logger = Logger(subsystem: "app.reverseapi", category: category)
    }

    public func debug(_ message: @autoclosure () -> String) {
        let text = message()
        logger.debug("\(text, privacy: .public)")
    }

    public func info(_ message: @autoclosure () -> String) {
        let text = message()
        logger.info("\(text, privacy: .public)")
    }

    public func warn(_ message: @autoclosure () -> String) {
        let text = message()
        logger.warning("\(text, privacy: .public)")
    }

    public func error(_ message: @autoclosure () -> String) {
        let text = message()
        logger.error("\(text, privacy: .public)")
    }
}
