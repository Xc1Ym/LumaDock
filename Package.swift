// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "LumaNX", defaultLocalization: "en", platforms: [.macOS("26.0")], products: [.executable(name: "LumaNX", targets: ["LumaNX"])], targets: [.executableTarget(name: "LumaNX", resources: [.process("Resources")], swiftSettings: [.swiftLanguageMode(.v5)]), .testTarget(name: "LumaNXTests", dependencies: ["LumaNX"], path: "tests/swift", swiftSettings: [.swiftLanguageMode(.v5)])])
