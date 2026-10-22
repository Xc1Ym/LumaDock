import XCTest
@testable import NSMac

@MainActor final class ProgressTests: XCTestCase {
    func testProgressUsesMeasuredCountersAndClampsOutOfRangeValues() {
        var task=TaskRecord(id:"build",operation:"build",state:"running",stageIndex:2,stageCount:4,done:50,total:100)
        XCTAssertEqual(task.progressFraction,0.5);XCTAssertEqual(task.stageFraction,0.375)
        task.done=150;XCTAssertEqual(task.progressFraction,1)
        task.total=0;XCTAssertNil(task.progressFraction)
        task.total=nil;XCTAssertNil(task.progressFraction)
        task.total=100;task.done=Double.infinity;XCTAssertNil(task.progressFraction)
    }
    func testMessagesAndDiagnosticsKeepProgressButNewStageResetsIt() {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumadock-progress-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        store.tasks=[.init(id:"build",operation:"build",state:"running",done:40,total:100,unit:"B")]
        for type in ["message","diagnostic","heartbeat"] {
            store.event(["schema":1,"taskId":"build","type":type,"message":"fixture"],visible:true)
            XCTAssertEqual(store.tasks[0].done,40);XCTAssertEqual(store.tasks[0].total,100)
        }
        store.event(["schema":1,"taskId":"build","type":"stage","stage":"next","stageIndex":2,"stageCount":3],visible:true)
        XCTAssertNil(store.tasks[0].done);XCTAssertNil(store.tasks[0].total)
        store.event(["schema":1,"taskId":"build","type":"progress","done":4,"unit":"files"],visible:true)
        XCTAssertEqual(store.tasks[0].done,4);XCTAssertNil(store.tasks[0].progressFraction)
        store.event(["schema":1,"taskId":"build","type":"progress","resetProgress":true],visible:true)
        XCTAssertNil(store.tasks[0].done)
    }
    func testGlobalProgressCoversLongOperationsAndExcludesRunningGamesAndQueue() {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumadock-active-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        let operations=["import","prepareEngine","build","exportIPA","preflight","installMetal","uninstallMetal","diagnostics","clean","keys","setup"]
        store.tasks=operations.map{TaskRecord(id:$0,operation:$0,state:"running")}
        store.tasks.append(.init(id:"game",operation:"launch",state:"running"))
        store.tasks.append(.init(id:"queued",operation:"build",state:"queued"))
        XCTAssertEqual(Set(store.activeTasks.map(\.operation)),Set(operations))
    }
    func testNativeFailurePersistsItsDiagnostic() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumadock-native-"+UUID().uuidString)
        defer {try? FileManager.default.removeItem(at:root)}
        let store=Store(privateRoot:root)
        let diagnostic=store.nativeDiagnostic(code:"worker_start_failed",summary:"failed",detail:root.path)
        let task=TaskRecord(id:"failed",operation:"build",state:"failed",diagnostics:[diagnostic])
        store.persistTask(task)
        let saved=try JSONDecoder().decode(TaskRecord.self,from:Data(contentsOf:root.appendingPathComponent("jobs/failed.json")))
        XCTAssertEqual(saved.diagnostics,[diagnostic]);XCTAssertFalse(diagnostic.detail.contains(root.path))
    }
}
