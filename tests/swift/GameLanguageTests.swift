import XCTest
@testable import LumaNX

@MainActor final class GameLanguageTests: XCTestCase {
    func testDefaultAndOverridesPersistIndependentlyOfInterfaceLanguage() throws {
        let previous=Localization.preference;defer {Localization.preference=previous}
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-game-language-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        XCTAssertEqual(store.defaultGameLanguage,.simplifiedChinese)
        XCTAssertEqual(store.gameLanguage(for:"g1"),.simplifiedChinese)
        store.language = .english
        XCTAssertEqual(store.gameLanguage(for:"g1"),.simplifiedChinese)
        store.defaultGameLanguage = .englishUS
        store.setGameLanguage(.traditionalChinese,for:"g1")
        store.setGameLanguage(.japanese,for:"g2")
        store.defaultGameLanguage = .korean
        XCTAssertEqual(store.language,.english)
        XCTAssertEqual(store.gameLanguage(for:"g1"),.traditionalChinese)
        XCTAssertEqual(store.gameLanguage(for:"g2"),.japanese)
        XCTAssertEqual(store.gameLanguage(for:"g3"),.korean)

        let restarted=Store(privateRoot:root)
        XCTAssertEqual(restarted.gameLanguage(for:"g1"),.traditionalChinese)
        XCTAssertEqual(restarted.gameLanguage(for:"g2"),.japanese)
        XCTAssertEqual(restarted.defaultGameLanguage,.korean)
        restarted.setGameLanguage(nil,for:"g1")
        XCTAssertNil(restarted.gameLanguageOverride(for:"g1"))
        XCTAssertEqual(L(restarted.notice ?? ""),"Launch language set to Use default (Korean). Applies on the next launch.")
        XCTAssertEqual(restarted.gameLanguage(for:"g1"),.korean)
        XCTAssertEqual(Store(privateRoot:root).gameLanguage(for:"g1"),.korean)
        XCTAssertTrue(store.processes.isEmpty)
        XCTAssertTrue(restarted.processes.isEmpty)
        XCTAssertTrue(store.queue.isEmpty)
    }
    func testUnknownStoredCodesFallBackWithoutLosingOtherPreferences() throws {
        let previous=Localization.preference;defer {Localization.preference=previous}
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-game-language-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        store.preferences.gameLanguage="zhHans"
        store.preferences.gameLanguages=["g1":"unknown-language","g2":"en-GB"]
        store.language = .english
        let restarted=Store(privateRoot:root)
        XCTAssertEqual(restarted.language,.english)
        XCTAssertEqual(restarted.gameLanguage(for:"g1"),.simplifiedChinese)
        XCTAssertEqual(restarted.gameLanguage(for:"g2"),.englishUK)
        XCTAssertEqual(restarted.gameLanguage(for:"g3"),.simplifiedChinese)
    }
    func testSwitchLanguageCodesFitTheNativeABIAndHaveLocalizedNames() {
        let previous=Localization.preference;defer {Localization.preference=previous}
        XCTAssertEqual(GameLanguage.allCases.count,18)
        XCTAssertEqual(Set(GameLanguage.allCases.map(\.rawValue)).count,18)
        for language in GameLanguage.allCases {
            XCTAssertLessThanOrEqual(language.rawValue.utf8.count,7)
            Localization.preference = .english
            XCTAssertFalse(language.name.contains(where:{$0.unicodeScalars.contains { $0.value >= 0x4e00 && $0.value <= 0x9fff }}),language.rawValue)
        }
        XCTAssertEqual(GameLanguage.simplifiedChinese.rawValue,"zh-Hans")
        XCTAssertNil(GameLanguage(rawValue:"zhHans"))
    }
}
