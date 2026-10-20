import XCTest
@testable import NSMac

@MainActor final class LocalizationTests: XCTestCase {
    func testSystemLanguageResolutionAndFallback() {
        XCTAssertEqual(AppLanguage.system.resolved(preferredLanguages:["en-US","zh-Hans-CN"]),"en")
        XCTAssertEqual(AppLanguage.system.resolved(preferredLanguages:["zh_CN","en"]),"zh-Hans")
        XCTAssertEqual(AppLanguage.system.resolved(preferredLanguages:["fr-FR","en-GB"]),"en")
        XCTAssertEqual(AppLanguage.system.resolved(preferredLanguages:["de-DE"]),"en")
        XCTAssertEqual(AppLanguage.system.resolved(preferredLanguages:[]),"en")
        XCTAssertEqual(AppLanguage.english.resolved(preferredLanguages:["zh-Hans"]),"en")
        XCTAssertEqual(AppLanguage.simplifiedChinese.resolved(preferredLanguages:["en"]),"zh-Hans")
    }
    func testCatalogCompletenessAndInterpolation() throws {
        let entries = Localization.entries
        XCTAssertGreaterThan(entries.count,350)
        XCTAssertEqual(Set(entries.map(\.source)).count,entries.count)
        let slots = try NSRegularExpression(pattern:#"\{\d+\}"#)
        for entry in entries {
            XCTAssertFalse(entry.en.isEmpty,entry.source)
            func placeholders(_ s:String)->[String] {
                let ns=s as NSString
                return slots.matches(in:s,range:NSRange(location:0,length:ns.length)).map { ns.substring(with:$0.range) }.sorted()
            }
            XCTAssertEqual(placeholders(entry.source),placeholders(entry.en),entry.source)
            func expand(_ s:String)->String {
                var s=s
                for i in 0..<10 { s=s.replacingOccurrences(of:"{\(i)}",with:"VALUE\(i)") }
                return s
            }
            XCTAssertEqual(Localization.translate(expand(entry.source),language:"en"),expand(entry.en),entry.source)
            XCTAssertEqual(Localization.translate(expand(entry.source),language:"zh-Hans"),expand(entry.source),entry.source)
        }
    }
    func testRecordedWorkerMessagesAndReorderedArguments() {
        XCTAssertEqual(Localization.translate("读取 NSP 元数据（2/3）",language:"en"),"Read NSP metadata (2/3)")
        XCTAssertEqual(Localization.translate("v42 的 main 构建标识与已适配版本不同",language:"en"),"The main build ID in v42 differs from the supported version")
        XCTAssertEqual(Localization.translate("缺少更新 v42（配置指定版本）",language:"en"),"Missing update v42 (version required by profile)")
        XCTAssertEqual(Localization.translate("解包与合并 v0",language:"en"),"Extract and merge v0")
        XCTAssertEqual(Localization.translate("缺少本体 v0；此游戏尚无原生适配配置",language:"en"),"Missing base game v0; This game has no native adaptation profile yet")
        XCTAssertEqual(Localization.translate("Missing update v42 (1.9.0)",language:"zh-Hans"),"缺少更新 v42（1.9.0）")
        XCTAssertEqual(Localization.translate("鼠标位移：1.5, -2.0",language:"en"),"Mouse movement: 1.5, -2.0")
    }
    func testParametersAndRawToolOutputAreNotDamaged() {
        let path="/Volumes/中文 游戏/$1 {0} 100%/工具"
        XCTAssertEqual(Localization.translate("无法启动本地组件："+path,language:"en"),"Unable to start a local component: "+path)
        let raw="[RED] Metal compiler error at /Volumes/中文 游戏/a.metal:17"
        XCTAssertEqual(Localization.translate(raw,language:"en"),raw)
    }
    func testLanguageSettingPersistsAndLegacyPreferencesStillLoad() throws {
        let previous=Localization.preference;defer {Localization.preference=previous}
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumadock-locale-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        XCTAssertEqual(store.language,.system)
        store.language = .english
        XCTAssertEqual(L("游戏库"),"Library")
        let saved=try JSONDecoder().decode(Preferences.self,from:Data(contentsOf:root.appendingPathComponent("preferences.json")))
        XCTAssertEqual(saved.language,"en")
        let restarted=Store(privateRoot:root)
        XCTAssertEqual(restarted.language,.english)
        restarted.language = .simplifiedChinese
        XCTAssertEqual(L("游戏库"),"游戏库")
        restarted.language = .system
        XCTAssertEqual(restarted.preferences.language,"system")
        let legacy=try JSONDecoder().decode(Preferences.self,from:Data(#"{"library":"","libraryId":"","developerDir":"/Applications/Xcode.app/Contents/Developer","onboardingComplete":false}"#.utf8))
        XCTAssertNil(legacy.language)
    }
    func testLanguageChangesOnlyPresentationOfTasksAndControls() throws {
        let previous=Localization.preference;defer {Localization.preference=previous}
        let record=TaskRecord(id:"old",operation:"build",state:"running",stage:"转换并编译 Metal 着色器",message:"已验证并复用完成阶段")
        let encoder=JSONEncoder();encoder.outputFormatting = .sortedKeys
        let config=InputConfig.standard
        let before=try encoder.encode(config)
        Localization.preference = .english
        XCTAssertEqual(record.title,"Prepare game");XCTAssertEqual(record.stateName,"Running")
        XCTAssertEqual(L(record.stage!),"Convert and compile Metal shaders")
        XCTAssertEqual(keyName(.init(code:49)),"Space")
        XCTAssertEqual(targetName("LS"),"Left stick click")
        Localization.preference = .simplifiedChinese
        XCTAssertEqual(record.stateName,"运行中")
        XCTAssertEqual(L(record.message!),"已验证并复用完成阶段")
        XCTAssertEqual(try encoder.encode(config),before)
        XCTAssertTrue(config.conflicts.isEmpty)
    }
}
