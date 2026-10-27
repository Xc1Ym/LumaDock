import XCTest
@testable import LumaNX

@MainActor final class RecoveryTests: XCTestCase {
    private func fixture() throws -> (URL,Store,Game) {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-recovery-ui-"+UUID().uuidString)
        let resources=root.appendingPathComponent("resources")
        let worker=resources.appendingPathComponent("Worker")
        let python=resources.appendingPathComponent("Runtime/python/bin")
        try FileManager.default.createDirectory(at:worker,withIntermediateDirectories:true)
        try FileManager.default.createDirectory(at:python,withIntermediateDirectories:true)
        try FileManager.default.createSymbolicLink(atPath:python.appendingPathComponent("python3").path,withDestinationPath:"/usr/bin/python3")
        try #"""
import json, pathlib, sys
r=json.loads(pathlib.Path(sys.argv[2]).read_text())
with (pathlib.Path(r['resources']).parent/'operations.jsonl').open('a') as f:
    f.write(json.dumps(r)+'\n')
result={'backups':[],'releases':[]} if r['operation']=='listRecovery' else {}
print(json.dumps({'schema':1,'taskId':r['taskId'],'type':'result','state':'completed','result':result}),flush=True)
"""#.write(to:worker.appendingPathComponent("main.py"),atomically:true,encoding:.utf8)
        let store=Store(privateRoot:root.appendingPathComponent("private"),resources:resources)
        store.preferences.library=root.appendingPathComponent("library").path
        store.preferences.libraryId="library-a"
        let game=Game(id:"0100000000010000",name:"Synthetic game",display:"2.0",packages:[],hidden:false,runtimeVersion:"1.0")
        store.games=[game]
        return (root,store,game)
    }
    private func waitUntil(_ condition:()->Bool) async throws {
        let deadline=Date().addingTimeInterval(8)
        while !condition(),Date()<deadline {try await Task.sleep(nanoseconds:30_000_000)}
        XCTAssertTrue(condition())
    }
    private func cleanup(_ root:URL,_ store:Store) async {
        store.terminate()
        try? await Task.sleep(nanoseconds:150_000_000)
        try? FileManager.default.removeItem(at:root)
    }
    func testRecoveryDecodesLegacyGamesAndVersionMetadata() throws {
        let legacy=Data(#"{"id":"g","name":"game","display":"2.0","packages":[],"hidden":false}"#.utf8)
        XCTAssertNil(try JSONDecoder().decode(Game.self,from:legacy).runtimeVersion)
        let report=Data(#"{"backups":[{"id":"b","created":1,"reason":"beforeRestore","size":12}],"releases":[{"id":"r","created":2,"version":"1.0","engine":"abc","current":true}]}"#.utf8)
        let value=try JSONDecoder().decode(RecoveryReport.self,from:report)
        XCTAssertEqual(value.backups[0].size,12)
        XCTAssertTrue(value.releases[0].current)
        XCTAssertEqual(value.releases[0].version,"1.0")
    }
    func testRecoveryIsBlockedWhileGameRunsOrPreparationIsQueued() async throws {
        let (root,store,game)=try fixture()
        store.executionTask="running-game"
        store.performRecovery("restoreSave",game:game,extra:["backupId":"b"])
        XCTAssertTrue(store.tasks.isEmpty)
        XCTAssertNotNil(store.error)
        store.executionTask=nil;store.queue=[game.id]
        store.performRecovery("activateRelease",game:game,extra:["releaseId":"r"])
        XCTAssertTrue(store.tasks.isEmpty)
        store.queue=[]
        await cleanup(root,store)
    }
    func testRetryKeepsRestoreIdentifierAndDoesNotEnqueueBuild() async throws {
        let (root,store,game)=try fixture()
        let task=TaskRecord(id:"old",operation:"restoreSave",state:"failed",gameId:game.id,backupId:"backup-fixture",libraryId:"library-a")
        store.retry(task)
        XCTAssertEqual(store.tasks.first?.operation,"restoreSave")
        XCTAssertEqual(store.tasks.first?.backupId,"backup-fixture")
        XCTAssertEqual(store.tasks.first?.libraryId,"library-a")
        XCTAssertTrue(store.queue.isEmpty)
        try await waitUntil {store.executionTask == nil}
        let log=try String(contentsOf:root.appendingPathComponent("operations.jsonl"),encoding:.utf8)
        let calls=try log.split(separator:"\n").map {try JSONSerialization.jsonObject(with:Data($0.utf8)) as! [String:Any]}
        let restore=calls.first {$0["operation"] as? String == "restoreSave"}
        XCTAssertEqual(restore?["backupId"] as? String,"backup-fixture")
        XCTAssertFalse(calls.contains {$0["operation"] as? String == "build"})
        await cleanup(root,store)
    }
    func testRetryCannotRunInAnotherLibraryAndStaleReportsAreIgnored() async throws {
        let (root,store,game)=try fixture()
        store.retry(TaskRecord(id:"old",operation:"backupSave",state:"failed",gameId:game.id,libraryId:"another-library"))
        XCTAssertTrue(store.tasks.isEmpty)
        XCTAssertNotNil(store.error)
        store.error=nil
        var delivered=false
        store.loadRecovery(game) {_ in delivered=true}
        store.preferences.libraryId="library-b"
        try await waitUntil {store.processes.isEmpty}
        XCTAssertFalse(delivered)
        await cleanup(root,store)
    }
}
