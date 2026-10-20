import XCTest
import AppKit
@testable import NSMac

@MainActor final class AppearanceTests: XCTestCase {
    func testSwitchingPersistsAndOnlyOverridesThisApplication() throws {
        let application=NSApplication.shared
        let previous=application.appearance
        let oldLanguage=Localization.preference
        let systemPreference=UserDefaults.standard.string(forKey:"AppleInterfaceStyle")
        defer { application.appearance=previous;Localization.preference=oldLanguage }
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumadock-appearance-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        XCTAssertEqual(store.appearance,.system)
        store.appearance = .dark
        XCTAssertEqual(application.appearance?.name,.darkAqua)
        let restarted=Store(privateRoot:root)
        XCTAssertEqual(restarted.appearance,.dark)
        XCTAssertEqual(application.appearance?.name,.darkAqua)
        restarted.appearance = .light
        XCTAssertEqual(application.appearance?.name,.aqua)
        restarted.appearance = .system
        XCTAssertNil(application.appearance)
        XCTAssertEqual(UserDefaults.standard.string(forKey:"AppleInterfaceStyle"),systemPreference)
        let saved=try JSONDecoder().decode(Preferences.self,from:Data(contentsOf:root.appendingPathComponent("preferences.json")))
        XCTAssertEqual(saved.appearance,"system")
    }
    func testLegacyPreferencesAndUnknownAppearanceUseSystem() throws {
        let previous=NSApp?.appearance;let oldLanguage=Localization.preference
        defer {NSApp?.appearance=previous;Localization.preference=oldLanguage}
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumadock-old-appearance-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        store.preferences.appearance="unknown-future-option"
        XCTAssertEqual(store.appearance,.system)
        store.applyAppearance();XCTAssertNil(NSApp?.appearance)
        let legacy=try JSONDecoder().decode(Preferences.self,from:Data(#"{"library":"","libraryId":"","developerDir":"","onboardingComplete":true}"#.utf8))
        XCTAssertNil(legacy.appearance)
    }
}
