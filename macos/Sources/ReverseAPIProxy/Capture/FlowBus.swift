import Foundation

public enum FlowEvent: Sendable {
    case started(CapturedFlow)
    case updated(CapturedFlow)
    case finished(CapturedFlow)
}

public actor FlowBus {
    public typealias Stream = AsyncStream<FlowEvent>

    public static let defaultBufferLimit = 1024

    private let bufferLimit: Int
    private var subscribers: [UUID: Stream.Continuation] = [:]

    public init(bufferLimit: Int = FlowBus.defaultBufferLimit) {
        self.bufferLimit = max(1, bufferLimit)
    }

    public func subscribe() -> Stream {
        let policy: Stream.Continuation.BufferingPolicy = .bufferingNewest(bufferLimit)
        let (stream, continuation) = Stream.makeStream(bufferingPolicy: policy)
        let token = UUID()
        subscribers[token] = continuation
        continuation.onTermination = { [weak self] _ in
            Task { await self?.unsubscribe(token) }
        }
        return stream
    }

    public func emit(_ event: FlowEvent) {
        for continuation in subscribers.values {
            continuation.yield(event)
        }
    }

    public func subscriberCount() -> Int {
        subscribers.count
    }

    private func unsubscribe(_ token: UUID) {
        subscribers.removeValue(forKey: token)
    }
}
