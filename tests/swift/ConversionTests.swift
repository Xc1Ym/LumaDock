import XCTest
@testable import NSMac

@MainActor final class ConversionTests:XCTestCase {
    private func fixture() throws -> (URL,Store) {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("lumadock-conversion-"+UUID().uuidString)
        let resources=root.appendingPathComponent("resources")
        let worker=resources.appendingPathComponent("Worker")
        let python=resources.appendingPathComponent("Runtime/python/bin")
        try FileManager.default.createDirectory(at:worker,withIntermediateDirectories:true)
        try FileManager.default.createDirectory(at:python,withIntermediateDirectories:true)
        try FileManager.default.createSymbolicLink(atPath:python.appendingPathComponent("python3").path,withDestinationPath:"/usr/bin/python3")
        try #"""
import json,pathlib,sys,time
r=json.loads(pathlib.Path(sys.argv[2]).read_text())
root=pathlib.Path(r['resources']).parent
with (root/'operations.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
result={}
if r['operation']=='convertFiles':
    result={'outputPath':str(root/'output'),'outputFiles':[str(root/'output/done.nsp')]}
elif r['operation'] in ('converterStatus','conversionKeys'):
    result={'path':str(pathlib.Path(r['resources'])/'Runtime/converter'),'conversionReady':True,'compressionReady':True,'keysReady':True,'keySource':'使用转换专用密钥'}
print(json.dumps({'schema':1,'taskId':r['taskId'],'type':'result','state':'completed','result':result}),flush=True)
"""#.write(to:worker.appendingPathComponent("main.py"),atomically:true,encoding:.utf8)
        return (root,Store(privateRoot:root.appendingPathComponent("private"),resources:resources))
    }
    private func operations(_ root:URL)->[[String:Any]] {
        guard let text=try? String(contentsOf:root.appendingPathComponent("operations.jsonl"),encoding:.utf8) else {return []}
        return text.split(separator:"\n").compactMap{try? JSONSerialization.jsonObject(with:Data($0.utf8)) as? [String:Any]}
    }
    private func waitUntil(_ condition:()->Bool) async throws {
        let end=Date().addingTimeInterval(8)
        while !condition(),Date()<end {try await Task.sleep(nanoseconds:50_000_000)}
        XCTAssertTrue(condition())
    }
    private func cleanup(_ root:URL,_ store:Store) async {
        store.terminate();try? await Task.sleep(nanoseconds:250_000_000);try? FileManager.default.removeItem(at:root)
    }
    func testExplicitConverterAcceptsCompressedAndCartridgeInputWithoutSetupOrAutomaticWork() async throws {
        let (root,store)=try fixture()
        XCTAssertFalse(store.environmentReady)
        store.addConversionFiles([root.appendingPathComponent("中文's.xcz"),root.appendingPathComponent("base.nsp")])
        XCTAssertEqual(store.selection,"conversion");XCTAssertFalse(store.showOnboarding)
        XCTAssertEqual(store.conversion.paths.count,2)
        XCTAssertTrue(operations(root).isEmpty)
        store.addConversionFiles([root.appendingPathComponent("中文's.xcz")])
        XCTAssertEqual(store.conversion.paths.count,2)
        await cleanup(root,store)
    }
    func testConversionIsIndependentOfEngineXcodeAndLibraryAndRetainsOutputActions() async throws {
        let (root,store)=try fixture()
        store.preferences.libraryId="offline-library"
        store.conversion.paths=[root.appendingPathComponent("base.xci").path]
        store.startConversion()
        try await waitUntil {operations(root).count==1 && !store.executionBusy}
        let request=try XCTUnwrap(operations(root).first)
        XCTAssertEqual(request["operation"] as? String,"convertFiles")
        XCTAssertEqual(request["libraryId"] as? String,"")
        XCTAssertEqual(request["storageLibraryId"] as? String,"offline-library")
        XCTAssertFalse(store.environmentReady);XCTAssertFalse(store.hasImportedKeys)
        XCTAssertEqual(store.tasks.first?.outputFiles,[root.appendingPathComponent("output/done.nsp").path])
        XCTAssertNotNil(store.latestConversion)
        await cleanup(root,store)
    }
    func testRetryKeepsOriginalConversionOptionsAndNeverStartsGameBuild() async throws {
        let (root,store)=try fixture()
        var options=ConversionJob();options.mode = .compress;options.level=22;options.verify=false
        options.paths=[root.appendingPathComponent("base.nsp").path];options.outputDirectory=root.appendingPathComponent("other output").path
        let record=TaskRecord(id:"failed",operation:"convertFiles",state:"failed",conversion:options)
        store.retry(record)
        try await waitUntil {operations(root).count==1 && !store.executionBusy}
        let request=try XCTUnwrap(operations(root).first)
        XCTAssertEqual(request["operation"] as? String,"convertFiles")
        XCTAssertEqual(Store.decode(ConversionJob.self,request["conversion"]),options)
        XCTAssertEqual(store.tasks.first?.conversion,options)
        await cleanup(root,store)
    }
    func testRunningGameAndQueuedPreparationPreventConversion() async throws {
        let (root,store)=try fixture();store.conversion.paths=[root.appendingPathComponent("base.nsp").path]
        store.executionTask="game";store.startConversion();XCTAssertTrue(operations(root).isEmpty)
        store.executionTask=nil;store.queue=["queued"];store.startConversion();XCTAssertTrue(operations(root).isEmpty)
        store.queue=[];store.tasks=[TaskRecord(id:"keys",operation:"conversionKeys",state:"running")];store.startConversion();XCTAssertTrue(operations(root).isEmpty)
        XCTAssertNotNil(store.error)
        await cleanup(root,store)
    }
    func testHistoryRecoversConversionWithoutALibraryAndLegacySettingsStillDecode() async throws {
        let (root,store)=try fixture()
        var options=ConversionJob();options.paths=[root.appendingPathComponent("base.nsp").path]
        store.persistTask(TaskRecord(id:"interrupted",operation:"convertFiles",state:"running",conversion:options))
        store.preferences.conversionOutput=root.appendingPathComponent("custom output").path;store.savePreferences()
        let restored=Store(privateRoot:store.privateRoot,resources:store.resources)
        XCTAssertEqual(restored.tasks.first?.state,"interrupted")
        XCTAssertEqual(restored.tasks.first?.conversion,options)
        XCTAssertEqual(restored.conversion.outputDirectory,store.preferences.conversionOutput)
        let legacy=try JSONDecoder().decode(Preferences.self,from:Data(#"{"library":"","libraryId":"","developerDir":"","onboardingComplete":false}"#.utf8))
        XCTAssertNil(legacy.conversionOutput)
        await cleanup(root,store)
    }
    func testConverterStatusAndSeparateKeyImportDoNotStartOnboardingOrChangeLibraryKeyState() async throws {
        let (root,store)=try fixture()
        store.checkConverter();try await waitUntil {!store.checkingConverter && store.converterStatus != nil}
        store.chooseConversionKeys(source:root.appendingPathComponent("my.keys"))
        try await waitUntil {operations(root).count==2 && !store.importingConversionKeys}
        XCTAssertTrue(store.converterStatus?.keysReady == true)
        XCTAssertFalse(store.hasImportedKeys);XCTAssertFalse(store.environmentReady)
        XCTAssertEqual(operations(root).map{$0["operation"] as? String},["converterStatus","conversionKeys"])
        await cleanup(root,store)
    }
}
