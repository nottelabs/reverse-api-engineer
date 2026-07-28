// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "ReverseAPI",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "ReverseAPIProxy", targets: ["ReverseAPIProxy"]),
        .executable(name: "rae-proxy", targets: ["rae-proxy"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-nio.git", from: "2.65.0"),
        .package(url: "https://github.com/apple/swift-nio-ssl.git", from: "2.27.0"),
        .package(url: "https://github.com/apple/swift-certificates.git", from: "1.5.0"),
        .package(url: "https://github.com/apple/swift-crypto.git", from: "3.7.0"),
    ],
    targets: [
        .target(
            name: "ReverseAPIProxy",
            dependencies: [
                .product(name: "NIO", package: "swift-nio"),
                .product(name: "NIOCore", package: "swift-nio"),
                .product(name: "NIOHTTP1", package: "swift-nio"),
                .product(name: "NIOPosix", package: "swift-nio"),
                .product(name: "NIOFoundationCompat", package: "swift-nio"),
                .product(name: "NIOConcurrencyHelpers", package: "swift-nio"),
                .product(name: "NIOSSL", package: "swift-nio-ssl"),
                .product(name: "X509", package: "swift-certificates"),
                .product(name: "Crypto", package: "swift-crypto"),
                .product(name: "_CryptoExtras", package: "swift-crypto"),
            ]
        ),
        .executableTarget(
            name: "rae-proxy",
            dependencies: ["ReverseAPIProxy"]
        ),
        .testTarget(
            name: "ReverseAPIProxyTests",
            dependencies: ["ReverseAPIProxy"]
        ),
    ]
)
