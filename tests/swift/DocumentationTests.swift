import XCTest
@testable import LumaNX

final class DocumentationTests:XCTestCase {
    private var root:URL {URL(fileURLWithPath:#filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()}
    func testGuideLocationsFollowTheAppAndLanguage() throws {
        for resources in [URL(fileURLWithPath:"/Applications/LumaNX.app/Contents/Resources"),URL(fileURLWithPath:"/Volumes/中文 磁盘/Moved App.app/Contents/Resources")] {
            for guide in [AppGuide.environment,.licenses] {
                for language in ["en","zh-Hans"] {
                    XCTAssertTrue(guide.url(resources:resources,language:language).path.hasPrefix(resources.path+"/docs/"))
                    let source=guide.url(resources:root,language:language)
                    XCTAssertTrue(FileManager.default.isReadableFile(atPath:source.path))
                    let blocks=GuideBlock.parse(try String(contentsOf:source,encoding:.utf8))
                    XCTAssertFalse(blocks.isEmpty)
                }
            }
        }
    }
    func testEnvironmentTablesPreserveEveryInstallationMethod() throws {
        for language in ["en","zh-Hans"] {
            let source=AppGuide.environment.url(resources:root,language:language)
            let blocks=GuideBlock.parse(try String(contentsOf:source,encoding:.utf8))
            let tables=blocks.compactMap { block -> ([String],[[String]])? in if case let .table(headers,rows)=block {return (headers,rows)};return nil }
            XCTAssertEqual(tables.count,1);XCTAssertEqual(tables[0].0.count,4)
            XCTAssertEqual(tables[0].1.count,12)
            XCTAssertTrue(tables[0].1.contains{$0[0].contains("Python")})
            XCTAssertTrue(tables[0].1.allSatisfy{$0.count==4 && $0.allSatisfy{!$0.isEmpty}})
        }
    }
    func testMarkdownHeadingsListsLinksAndCodeArePreserved() {
        let text="# Title\n\nRead [Apple](https://developer.apple.com).\n\n1. Install Xcode\n- Check Python\n\n```sh\nhello\n```\n\n---"
        XCTAssertEqual(GuideBlock.parse(text),[.heading(1,"Title"),.paragraph("Read [Apple](https://developer.apple.com)."),.list("1. Install Xcode"),.list("- Check Python"),.code("hello"),.rule])
        XCTAssertFalse(GuideBlock.parse("|\n| --- |\n").contains {if case .table = $0{return true};return false})
    }
}
