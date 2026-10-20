// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "NSMac", defaultLocalization: "en", platforms: [.macOS("26.0")], products: [.executable(name: "NSMac", targets: ["NSMac"])], targets: [.executableTarget(name: "NSMac", resources: [.process("Resources")], swiftSettings: [.swiftLanguageMode(.v5)]), .testTarget(name: "NSMacTests", dependencies: ["NSMac"], path: "tests/swift", swiftSettings: [.swiftLanguageMode(.v5)])])
