import XCTest
@testable import LumaNX

@MainActor final class DiagnosticsTests: XCTestCase {
    private func diagnostic(severity: String = "error", path: String? = nil) -> TaskDiagnostic {
        .init(code:"shader_compile_failed",severity:severity,summary:"Metal 着色器编译失败。",suggestion:"在设置中安装 Metal 编译组件，完成后重新检查环境并重试。",detail:"sample.metal:7: error: unknown type",stage:"转换并编译 Metal 着色器",logPath:path,component:"dmsh_build.py",exitCode:1)
    }
    func testFailureEventKeepsDiagnosticLogAndActionableAlert() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-errors-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        let log=root.appendingPathComponent("logs/shader.log").path
        let value=diagnostic(path:log)
        let object=try JSONSerialization.jsonObject(with:JSONEncoder().encode(value))
        store.tasks=[.init(id:"build",operation:"build",state:"running")]
        store.event(["schema":1,"taskId":"build","type":"diagnostic","diagnostic":object],visible:true)
        store.event(["schema":1,"taskId":"build","type":"result","state":"failed","message":value.summary],visible:true)
        XCTAssertEqual(store.tasks[0].diagnostics,[value]);XCTAssertEqual(store.errorDiagnostic,value)
        XCTAssertTrue(store.failureMessage.contains("shader_compile_failed"))
        XCTAssertTrue(store.failureMessage.contains(L(value.suggestion)))
        XCTAssertEqual(store.diagnosticLogURL(value).path,URL(fileURLWithPath:log).resolvingSymlinksInPath().path)
        store.showFailedTask();XCTAssertEqual(store.selection,"tasks");XCTAssertNil(store.errorDiagnostic)
    }
    func testResultCanRestoreDiagnosticsWithoutEarlierStreamingEvent() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-result-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root);let value=diagnostic(severity:"warning")
        let object=try JSONSerialization.jsonObject(with:JSONEncoder().encode([value]))
        store.tasks=[.init(id:"build",operation:"build",state:"running")]
        store.event(["schema":1,"taskId":"build","type":"result","state":"completed","diagnostics":object],visible:true)
        XCTAssertTrue(store.tasks[0].hasWarnings);XCTAssertEqual(store.tasks[0].stateName,L("完成（有警告）"))
        XCTAssertNil(store.error)
    }
    func testLegacyJobsDecodeAndLogLinksStayWithinManagedLogLocations() throws {
        let legacy=try JSONDecoder().decode(TaskRecord.self,from:Data(#"{"id":"old","operation":"build","state":"failed"}"#.utf8))
        XCTAssertNil(legacy.diagnostics)
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-log-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        let fallback=root.appendingPathComponent("logs")
        XCTAssertEqual(store.diagnosticLogURL(diagnostic(path:"/etc/hosts")),fallback)
        XCTAssertEqual(store.diagnosticLogURL(diagnostic(path:root.appendingPathComponent("logs/../keys/prod.keys").path)),fallback)
        XCTAssertFalse(diagnostic(path:"/private/secret.log").reportText.contains("/private/secret.log"))
    }
    func testNativeErrorsAreRedactedBeforeCopying() {
        let secret=String(repeating:"a",count:64)
        let raw="header_key = \(secret) password=privatepass /Users/player/library/game.nsp\nAuthorization: Bearer bearer-secret\nhttps://user:linkpass@example.invalid"
        let result=TaskDiagnostic.redact(raw,paths:[("/Users/player/library","[LIBRARY]")])
        XCTAssertFalse(result.contains(secret));XCTAssertFalse(result.contains("privatepass"))
        XCTAssertFalse(result.contains("bearer-secret"));XCTAssertFalse(result.contains("linkpass"))
        XCTAssertTrue(result.contains("[LIBRARY]"));XCTAssertTrue(result.contains("[REDACTED]"))
    }
}
