import XCTest
@testable import ReverseAPIProxy

final class FlowBusTests: XCTestCase {
    func testMultipleSubscribersReceiveEvent() async {
        let bus = FlowBus(bufferLimit: 16)
        let s1 = await bus.subscribe()
        let s2 = await bus.subscribe()
        let flow = CapturedFlow(scheme: .https, method: "GET", host: "h", port: 443, path: "/")
        let received1 = expectation(description: "s1 receives")
        let received2 = expectation(description: "s2 receives")
        Task {
            for await event in s1 {
                if case .started(let f) = event, f.id == flow.id {
                    received1.fulfill()
                    return
                }
            }
        }
        Task {
            for await event in s2 {
                if case .started(let f) = event, f.id == flow.id {
                    received2.fulfill()
                    return
                }
            }
        }
        try? await Task.sleep(for: .milliseconds(50))
        await bus.emit(.started(flow))
        await fulfillment(of: [received1, received2], timeout: 2)
    }

    func testUnsubscribeOnStreamTermination() async {
        let bus = FlowBus(bufferLimit: 16)
        var stream: AsyncStream<FlowEvent>? = await bus.subscribe()
        let initialCount = await bus.subscriberCount()
        XCTAssertEqual(initialCount, 1)
        stream = nil
        _ = stream
        try? await Task.sleep(for: .milliseconds(100))
        let count = await bus.subscriberCount()
        XCTAssertEqual(count, 0)
    }

    func testBoundedBufferDropsOldestWhenSlowConsumer() async {
        let bus = FlowBus(bufferLimit: 2)
        let stream = await bus.subscribe()
        let f1 = CapturedFlow(scheme: .http, method: "GET", host: "a", port: 80, path: "/1")
        let f2 = CapturedFlow(scheme: .http, method: "GET", host: "a", port: 80, path: "/2")
        let f3 = CapturedFlow(scheme: .http, method: "GET", host: "a", port: 80, path: "/3")
        let f4 = CapturedFlow(scheme: .http, method: "GET", host: "a", port: 80, path: "/4")
        await bus.emit(.started(f1))
        await bus.emit(.started(f2))
        await bus.emit(.started(f3))
        await bus.emit(.started(f4))
        var collected: [String] = []
        for await event in stream {
            if case .started(let flow) = event {
                collected.append(flow.path)
            }
            if collected.count == 2 { break }
        }
        XCTAssertEqual(collected.count, 2)
        XCTAssertEqual(collected.last, "/4", "bufferingNewest must retain the latest events")
    }

    func testDefaultBufferLimitIsPositive() {
        XCTAssertGreaterThan(FlowBus.defaultBufferLimit, 0)
    }
}
