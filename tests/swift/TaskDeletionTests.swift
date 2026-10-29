import XCTest
@testable import LumaNX

@MainActor final class TaskDeletionTests:XCTestCase {
    private func fixture() throws -> (URL,Store) {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-task-delete-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
        return (root,Store(privateRoot:root,resources:root))
    }
    func testDeletingFinishedRecordSurvivesReloadAndPreservesLogsAndOutputs() throws {
        let (root,store)=try fixture()
        defer {try? FileManager.default.removeItem(at:root)}
        let log=root.appendingPathComponent("logs/finished.log")
        let output=root.appendingPathComponent("results/output.txt")
        for url in [log,output] {
            try FileManager.default.createDirectory(at:url.deletingLastPathComponent(),withIntermediateDirectories:true)
            try Data("synthetic fixture".utf8).write(to:url)
        }
        let task=TaskRecord(id:"finished",operation:"convertFiles",state:"completed",outputPath:output.deletingLastPathComponent().path)
        let other=TaskRecord(id:"other",operation:"convertFiles",state:"failed")
        store.tasks=[task,other];store.persistTask(task);store.persistTask(other)
        store.deleteTask(task)
        XCTAssertEqual(store.tasks.map(\.id),[other.id])
        XCTAssertFalse(FileManager.default.fileExists(atPath:root.appendingPathComponent("jobs/finished.json").path))
        for url in [log,output] {XCTAssertEqual(try Data(contentsOf:url),Data("synthetic fixture".utf8))}
        let restored=Store(privateRoot:root,resources:root)
        XCTAssertEqual(restored.tasks.map(\.id),[other.id])
        store.persistTask(task)
        store.event(["schema":1,"taskId":task.id,"type":"result","state":"failed","operation":"convertFiles"],visible:true)
        XCTAssertFalse(store.tasks.contains{$0.id==task.id})
        XCTAssertFalse(FileManager.default.fileExists(atPath:root.appendingPathComponent("jobs/finished.json").path))
    }
    func testRunningQueuedAndExecutingTasksCannotBeDeletedThroughStaleRecords() throws {
        let (root,store)=try fixture()
        defer {try? FileManager.default.removeItem(at:root)}
        let stale=TaskRecord(id:"protected",operation:"build",state:"failed")
        for state in ["running","cancelling","queued","completed"] {
            var current=stale;current.state=state
            store.tasks=[current];store.persistTask(current)
            store.executionTask=state=="completed" ? current.id : nil
            XCTAssertFalse(store.canDeleteTask(stale))
            store.deleteTask(stale)
            XCTAssertEqual(store.tasks.first?.state,state)
            XCTAssertTrue(FileManager.default.fileExists(atPath:root.appendingPathComponent("jobs/protected.json").path))
        }
    }
    func testInvalidTaskIDCannotDeleteOutsideTheJobsDirectory() throws {
        let (root,store)=try fixture()
        defer {try? FileManager.default.removeItem(at:root)}
        let sentinel=root.appendingPathComponent("sentinel.json")
        try Data("keep".utf8).write(to:sentinel)
        let task=TaskRecord(id:"../sentinel",operation:"build",state:"failed")
        store.tasks=[task];store.deleteTask(task)
        XCTAssertEqual(store.tasks.count,1)
        XCTAssertEqual(try Data(contentsOf:sentinel),Data("keep".utf8))
    }
    func testStaleCatalogResponseCannotRestoreDeletedTask() async throws {
        let (root,store)=try fixture()
        defer {store.terminate();try? FileManager.default.removeItem(at:root)}
        let python=root.appendingPathComponent("Runtime/python/bin")
        let worker=root.appendingPathComponent("Worker")
        try FileManager.default.createDirectory(at:python,withIntermediateDirectories:true)
        try FileManager.default.createDirectory(at:worker,withIntermediateDirectories:true)
        try FileManager.default.createSymbolicLink(atPath:python.appendingPathComponent("python3").path,withDestinationPath:"/usr/bin/python3")
        try #"""
import json,pathlib,sys
r=json.loads(pathlib.Path(sys.argv[2]).read_text())
result={'jobs':[{'id':'finished','operation':'build','state':'failed'}]}
print(json.dumps({'schema':1,'taskId':r['taskId'],'type':'result','state':'completed','result':result}),flush=True)
"""#.write(to:worker.appendingPathComponent("main.py"),atomically:true,encoding:.utf8)
        let task=TaskRecord(id:"finished",operation:"build",state:"failed")
        store.tasks=[task];store.persistTask(task);store.deleteTask(task)
        store.preferences.library=root.appendingPathComponent("library").path
        store.refresh()
        let deadline=Date().addingTimeInterval(8)
        while store.catalogWorkers>0,Date()<deadline {try await Task.sleep(nanoseconds:50_000_000)}
        XCTAssertEqual(store.catalogWorkers,0)
        XCTAssertFalse(store.tasks.contains{$0.id==task.id})
    }
}
