import XCTest
@testable import LumaNX

@MainActor final class ImportFlowTests: XCTestCase {
    private func fixture(toolchainReady: Bool = true) throws -> (URL, Store) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("lumanx-flow-"+UUID().uuidString)
        let resources = root.appendingPathComponent("resources")
        let worker = resources.appendingPathComponent("Worker")
        try FileManager.default.createDirectory(at:worker,withIntermediateDirectories:true)
        let python = resources.appendingPathComponent("Runtime/python/bin")
        try FileManager.default.createDirectory(at:python,withIntermediateDirectories:true)
        try FileManager.default.createSymbolicLink(atPath:python.appendingPathComponent("python3").path,withDestinationPath:"/usr/bin/python3")
        // This transport fixture exercises Store's real process/event/queue handling.
        // It never reads commercial games, keys, or invokes a compiler.
        try #"""
import json, pathlib, sys
r=json.loads(pathlib.Path(sys.argv[2]).read_text())
root=pathlib.Path(r['resources']).parent
with (root/'operations.jsonl').open('a') as f:
    f.write(json.dumps({'operation':r['operation'],'gameId':r.get('gameId'),'paths':r.get('paths'),'confirmed':r.get('confirmed'),'engineDir':r.get('engineDir'),'gameLanguage':r.get('gameLanguage'),'outputPath':r.get('outputPath')})+'\n')
if r['operation']=='catalog':
    result=json.loads((root/'catalog.json').read_text())
elif r['operation']=='import':
    result={'imports':json.loads((root/'imports.json').read_text())}
elif r['operation']=='preflight':
    result={'checks':[{'name':'Fixture tools','ok':json.loads((root/'tools.json').read_text()),'message':'fixture'}]}
    if (root/'automatic-engine.json').exists():
        result={'checks':[{'name':'NSP 读取组件','ok':(root/'engine-initialized').exists(),'message':'fixture','action':'prepareEngine'}]}
elif r['operation']=='prepareEngine':
    if (root/'automatic-engine.json').exists() and json.loads((root/'automatic-engine.json').read_text()):
        (root/'engine-initialized').write_text('fixture ready')
    result={}
else:
    result={}
print(json.dumps({'schema':1,'taskId':r['taskId'],'type':'result','state':'completed','result':result}),flush=True)
"""#.write(to:worker.appendingPathComponent("main.py"),atomically:true,encoding:.utf8)
        try JSONSerialization.data(withJSONObject:toolchainReady,options:.fragmentsAllowed).write(to:root.appendingPathComponent("tools.json"))
        let store = Store(privateRoot:root.appendingPathComponent("private"),resources:resources)
        store.checks = [.init(name:"Fixture tools",ok:true,message:"fixture")]
        store.environmentReportComplete = true
        store.preferences.library = root.appendingPathComponent("中文 游戏库").path
        store.preferences.libraryId = "fixture-library"
        try FileManager.default.createDirectory(at:store.privateRoot.appendingPathComponent("keys"),withIntermediateDirectories:true)
        try Data("not-a-real-key; transport fixture only".utf8).write(to:store.privateRoot.appendingPathComponent("keys/prod.keys"))
        return (root,store)
    }
    private func game(_ id:String, missing:[String]=[], ready:Bool=false) -> [String:Any] {
        ["id":id,"name":id,"display":"1.0","packages":[],"hidden":false,"compatibility":"startup","missing":missing,"ready":ready]
    }
    private func configure(_ root:URL, games:[[String:Any]], imports:[[String:Any]]) throws {
        try JSONSerialization.data(withJSONObject:["games":games,"profiles":[],"jobs":[],"keys":["ready":true,"verified":false,"message":"fixture ready"]]).write(to:root.appendingPathComponent("catalog.json"))
        try JSONSerialization.data(withJSONObject:imports).write(to:root.appendingPathComponent("imports.json"))
    }
    private func operations(_ root:URL) -> [[String:Any]] {
        guard let text=try? String(contentsOf:root.appendingPathComponent("operations.jsonl"),encoding:.utf8) else {return []}
        return text.split(separator:"\n").compactMap { try? JSONSerialization.jsonObject(with:Data($0.utf8)) as? [String:Any] }
    }
    private func waitUntil(_ condition:()->Bool) async throws {
        let deadline=Date().addingTimeInterval(8)
        while !condition(),Date()<deadline {try await Task.sleep(nanoseconds:50_000_000)}
        XCTAssertTrue(condition(),"Workflow did not reach expected state")
    }
    private func cleanup(_ root:URL,_ store:Store) async {
        store.terminate()
        try? await Task.sleep(nanoseconds:250_000_000)
        try? FileManager.default.removeItem(at:root)
    }
    func testMissingAndDeletedKeysRouteToKeyStepBeforeImport() async throws {
        let (root,store)=try fixture()
        store.chooseGames()
        XCTAssertTrue(store.showOnboarding);XCTAssertEqual(store.onboardingStep,2)
        XCTAssertTrue(operations(root).isEmpty)
        store.showOnboarding=false;store.hasImportedKeys=true
        try FileManager.default.removeItem(at:store.privateRoot.appendingPathComponent("keys/prod.keys"))
        store.addGames([root.appendingPathComponent("中文 游戏.nsp")])
        XCTAssertFalse(store.hasImportedKeys);XCTAssertEqual(store.onboardingStep,2)
        XCTAssertTrue(operations(root).isEmpty)
        await cleanup(root,store)
    }
    func testIPARetryKeepsExportOperationAndDestination() async throws {
        let (root,store)=try fixture();store.hasImportedKeys=true
        try configure(root,games:[game("g1")],imports:[])
        store.games=[Store.decode(Game.self,game("g1"))!]
        let output=root.appendingPathComponent("中文 游戏.ipa").path
        let task=TaskRecord(id:"failed-ipa",operation:"exportIPA",state:"failed",gameId:"g1",outputPath:output)
        store.retry(task)
        XCTAssertEqual(store.selection,"tasks")
        XCTAssertEqual(store.tasks.first?.operation,"exportIPA")
        XCTAssertEqual(store.tasks.first?.outputPath,output)
        try await waitUntil {self.operations(root).contains{$0["operation"] as? String == "exportIPA"} && !store.executionBusy}
        let exports=operations(root).filter{$0["operation"] as? String == "exportIPA"}
        XCTAssertEqual(exports.count,1)
        XCTAssertEqual(exports.first?["outputPath"] as? String,output)
        XCTAssertFalse(operations(root).contains{$0["operation"] as? String == "build"})
        await cleanup(root,store)
    }
    func testLibraryRefreshProgressEndsOnSuccessAndBootstrapFailure() async throws {
        let (root,store)=try fixture()
        try configure(root,games:[game("g1")],imports:[])
        store.refresh();XCTAssertTrue(store.refreshingLibrary)
        try await waitUntil {!store.refreshingLibrary && store.games.count==1}
        try FileManager.default.removeItem(at:store.resources.appendingPathComponent("Runtime/python/bin/python3"))
        store.refresh();XCTAssertFalse(store.refreshingLibrary);XCTAssertNotNil(store.error)
        XCTAssertTrue(store.tasks.contains{$0.operation=="catalog" && $0.state=="failed" && $0.diagnostics?.isEmpty==false})
        await cleanup(root,store)
    }
    func testIPAExportWaitsForGameAndPreparationQueue() async throws {
        let (root,store)=try fixture();store.hasImportedKeys=true
        let selected=Store.decode(Game.self,game("g1"))!
        store.executionTask="running-game"
        store.generateIPA(selected,destination:root.appendingPathComponent("test.ipa"))
        XCTAssertTrue(store.tasks.isEmpty)
        store.executionTask=nil;store.queue=["g2"]
        store.generateIPA(selected,destination:root.appendingPathComponent("test.ipa"))
        XCTAssertTrue(store.tasks.isEmpty)
        XCTAssertTrue(operations(root).isEmpty)
        await cleanup(root,store)
    }
    func testImportQueuesCompleteNewGamesOnceAndDoesNotLaunch() async throws {
        let (root,store)=try fixture();store.hasImportedKeys=true
        store.tasks=[.init(id:"queued-g1",operation:"build",state:"queued",gameId:"g1")]
        try configure(root,games:[game("g1"),game("g2",missing:["missing update"]),game("g3"),game("g4",ready:true),game("g5")],imports:[
            ["id":"g1","duplicate":false],["id":"g1","duplicate":false],
            ["id":"g2","duplicate":false],["id":"g3","duplicate":true],
            ["id":"g4","duplicate":false],["id":"g5","duplicate":false]])
        store.addGames([root.appendingPathComponent("中文 游戏.nsp")])
        try await waitUntil {self.operations(root).filter{$0["operation"] as? String == "build"}.count==2 && !store.executionBusy}
        let ops=operations(root)
        XCTAssertEqual(Set(ops.filter{$0["operation"] as? String == "build"}.compactMap{$0["gameId"] as? String}),Set(["g1","g5"]))
        XCTAssertFalse(ops.contains{$0["operation"] as? String == "launch"})
        XCTAssertTrue(store.hasImportedKeys)
        await cleanup(root,store)
    }
    func testAutomaticPreparationCanBeDisabledAndPersists() async throws {
        let (root,store)=try fixture();store.hasImportedKeys=true;store.prepareAfterImport=false
        try configure(root,games:[game("g1")],imports:[["id":"g1","duplicate":false]])
        store.addGames([root.appendingPathComponent("game.nsp")])
        try await waitUntil {store.games.count==1 && store.processes.isEmpty}
        XCTAssertFalse(operations(root).contains{$0["operation"] as? String == "build"})
        let saved=try JSONDecoder().decode(Preferences.self,from:Data(contentsOf:store.privateRoot.appendingPathComponent("preferences.json")))
        XCTAssertEqual(saved.prepareAfterImport,false)
        await cleanup(root,store)
    }
    func testMixedFormatsStayInImportFlowAndAutomaticallyPrepare() async throws {
        let (root,store)=try fixture();store.hasImportedKeys=true
        try configure(root,games:[game("g1")],imports:[["id":"g1","duplicate":false]])
        let files=["base.XCI","update.NSZ","dlc.xcz","extra.nsp"].map {root.appendingPathComponent($0)}
        store.conversion.mode = .compress;store.conversion.target="xci"
        store.conversion.paths=["unrelated.nsp"]
        store.addGames(files)
        XCTAssertEqual(store.selection,"tasks")
        XCTAssertEqual(store.tasks.first?.operation,"import")
        XCTAssertEqual(store.tasks.first?.importPaths,files.map(\.path))
        XCTAssertTrue(store.executionBusy)
        store.launch(Store.decode(Game.self,game("g1",ready:true))!)
        try await waitUntil {self.operations(root).contains{$0["operation"] as? String == "build"} && !store.executionBusy}
        XCTAssertEqual(operations(root).first?["paths"] as? [String],files.map(\.path))
        XCTAssertFalse(operations(root).contains {["convertFiles","launch"].contains($0["operation"] as? String ?? "")})
        XCTAssertEqual(store.conversion.paths,["unrelated.nsp"])
        XCTAssertEqual(store.conversion.mode,.compress)
        await cleanup(root,store)
    }
    func testImportRetryRetainsSourcePathsAfterTaskPersistence() async throws {
        let (root,store)=try fixture();store.hasImportedKeys=true;store.prepareAfterImport=false
        try configure(root,games:[game("g1")],imports:[["id":"g1","duplicate":false]])
        let paths=[root.appendingPathComponent("base.xcz").path]
        let failed=TaskRecord(id:"failed-import",operation:"import",state:"failed",importPaths:paths)
        store.persistTask(failed)
        let saved=try JSONDecoder().decode(TaskRecord.self,from:Data(contentsOf:store.privateRoot.appendingPathComponent("jobs/failed-import.json")))
        store.retry(saved)
        try await waitUntil {store.games.count==1 && store.processes.isEmpty}
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String == "import"}.first?["paths"] as? [String],paths)
        XCTAssertFalse(operations(root).contains {$0["operation"] as? String == "build"})
        XCTAssertEqual(store.selection,"tasks")
        await cleanup(root,store)
    }
    func testCompressedInputCannotBypassImportPrerequisites() async throws {
        let (root,store)=try fixture()
        store.addGames([root.appendingPathComponent("base.xci")])
        XCTAssertTrue(store.showOnboarding);XCTAssertEqual(store.onboardingStep,2)
        XCTAssertNotEqual(store.selection,"conversion")
        XCTAssertTrue(operations(root).isEmpty);XCTAssertTrue(store.conversion.paths.isEmpty)
        await cleanup(root,store)
    }
    func testMissingToolchainKeepsImportedGameWithoutBuilding() async throws {
        let (root,store)=try fixture(toolchainReady:false);store.hasImportedKeys=true
        try configure(root,games:[game("g1")],imports:[["id":"g1","duplicate":false]])
        store.addGames([root.appendingPathComponent("game.nsp")])
        try await waitUntil {store.selection=="settings"}
        XCTAssertEqual(store.games.count,1)
        XCTAssertFalse(operations(root).contains{$0["operation"] as? String == "build"})
        await cleanup(root,store)
    }
    func testLegacyPreferencesRemainReadable() throws {
        let data=Data(#"{"library":"/volume/games","libraryId":"old-id","developerDir":"/Applications/Xcode.app/Contents/Developer","onboardingComplete":true}"#.utf8)
        let prefs=try JSONDecoder().decode(Preferences.self,from:data)
        XCTAssertEqual(prefs.libraryId,"old-id");XCTAssertTrue(prefs.onboardingComplete)
        XCTAssertNil(prefs.prepareAfterImport)
        XCTAssertNil(prefs.engineDir)
        XCTAssertNil(prefs.gameLanguage)
        XCTAssertNil(prefs.gameLanguages)
    }
    func testLaunchSendsTheEffectiveLanguageWithoutPreparingAgain() async throws {
        let (root,store)=try fixture()
        try configure(root,games:[game("g1",ready:true)],imports:[])
        let g=try XCTUnwrap(Store.decode(Game.self,game("g1",ready:true)))
        store.language = .english
        store.launch(g)
        try await waitUntil {store.processes.isEmpty}
        store.setGameLanguage(.englishUK,for:g.id)
        store.launch(g)
        try await waitUntil {store.processes.isEmpty}
        store.setGameLanguage(nil,for:g.id)
        store.defaultGameLanguage = .japanese
        store.launch(g)
        try await waitUntil {store.processes.isEmpty}
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String == "launch"}.compactMap{$0["gameLanguage"] as? String},["zh-Hans","en-GB","ja"])
        XCTAssertFalse(operations(root).contains{$0["operation"] as? String == "build"})
        XCTAssertEqual(store.language,.english)
        XCTAssertTrue(store.queue.isEmpty)
        await cleanup(root,store)
    }
    func testExternalEngineSelectionPersistsAndIsPassedToWorkersAsData() async throws {
        let (root,store)=try fixture()
        try configure(root,games:[],imports:[])
        let source=root.appendingPathComponent("下载 中文's nxnative")
        store.selectEngine(source)
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        let saved=try JSONDecoder().decode(Preferences.self,from:Data(contentsOf:store.privateRoot.appendingPathComponent("preferences.json")))
        XCTAssertEqual(saved.engineDir,source.path)
        XCTAssertEqual(operations(root).first?["engineDir"] as? String,source.path)
        store.prepareEngine()
        try await waitUntil {self.operations(root).contains{$0["operation"] as? String=="prepareEngine"} && store.processes.isEmpty}
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String=="preflight"}.count,2)
        XCTAssertFalse(store.executionBusy)
        await cleanup(root,store)
    }
    func testChangingOrPreparingExternalEngineIsBlockedWhileQueueOrGameIsActive() async throws {
        let (root,store)=try fixture()
        store.preferences.engineDir="/existing/engine"
        for queued in [false,true] {
            store.executionTask=queued ? nil : "active-game"
            store.queue=queued ? ["pending-game"] : []
            store.selectEngine(root.appendingPathComponent("other"));store.prepareEngine()
            XCTAssertEqual(store.preferences.engineDir,"/existing/engine")
            XCTAssertTrue(operations(root).isEmpty)
        }
        store.executionTask=nil;store.queue=[]
        await cleanup(root,store)
    }
    func testEnvironmentMustPassBeforeAnyGameImport() async throws {
        let (root,store)=try fixture(toolchainReady:false);store.hasImportedKeys=true
        try configure(root,games:[],imports:[])
        store.checks=[]
        store.addGames([root.appendingPathComponent("game.nsp")])
        XCTAssertTrue(store.showOnboarding);XCTAssertEqual(store.onboardingStep,0)
        try await waitUntil {self.operations(root).contains{$0["operation"] as? String == "preflight"}}
        XCTAssertFalse(operations(root).contains{$0["operation"] as? String == "import"})
        await cleanup(root,store)
    }
    func testDeferringFailedSetupKeepsPrerequisitesAndResumesAfterRelaunch() async throws {
        let (root,store)=try fixture(toolchainReady:false)
        try configure(root,games:[],imports:[])
        store.savePreferences()
        let saved=try Data(contentsOf:store.privateRoot.appendingPathComponent("preferences.json"))
        let key=try Data(contentsOf:store.privateRoot.appendingPathComponent("keys/prod.keys"))
        store.checkEnvironmentAtStartup()
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        XCTAssertTrue(store.showOnboarding);XCTAssertFalse(store.environmentReady)

        store.deferOnboarding();store.onboardingDismissed()
        XCTAssertFalse(store.showOnboarding)
        XCTAssertFalse(store.preferences.onboardingComplete)
        XCTAssertEqual(try Data(contentsOf:store.privateRoot.appendingPathComponent("preferences.json")),saved)
        XCTAssertEqual(try Data(contentsOf:store.privateRoot.appendingPathComponent("keys/prod.keys")),key)
        XCTAssertFalse(operations(root).contains{$0["operation"] as? String == "import"})

        store.openOnboarding()
        XCTAssertTrue(store.showOnboarding);XCTAssertEqual(store.onboardingStep,0)
        store.deferOnboarding()
        XCTAssertFalse(store.importPrerequisitesReady())
        XCTAssertTrue(store.showOnboarding);XCTAssertEqual(store.onboardingStep,0)
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        store.finishOnboarding(addGames:false)
        XCTAssertFalse(store.preferences.onboardingComplete)
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}

        let nextSession=Store(privateRoot:store.privateRoot,resources:store.resources)
        XCTAssertTrue(nextSession.showOnboarding)
        XCTAssertFalse(nextSession.preferences.onboardingComplete)
        try await waitUntil {nextSession.processes.isEmpty}
        nextSession.terminate()
        await cleanup(root,store)
    }
    func testDeferringSetupDuringCheckDoesNotReopenItOrStartAnotherCheck() async throws {
        let (root,store)=try fixture(toolchainReady:false)
        store.checkEnvironmentAtStartup()
        XCTAssertTrue(store.checkingEnvironment)
        store.deferOnboarding();store.onboardingDismissed()
        store.checkEnvironmentAtStartup()
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        XCTAssertFalse(store.showOnboarding);XCTAssertFalse(store.preferences.onboardingComplete)
        XCTAssertFalse(store.environmentReady)
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String=="preflight"}.count,1)
        await cleanup(root,store)
    }
    func testDeferringSetupWhenPythonIsMissingDoesNotBypassImportGate() async throws {
        let (root,store)=try fixture()
        try FileManager.default.removeItem(at:root.appendingPathComponent("resources/Runtime/python/bin/python3"))
        store.checkEnvironmentAtStartup()
        XCTAssertNotNil(store.error)
        store.error=nil // Acknowledge the bootstrap error, as in the UI.
        store.deferOnboarding();store.onboardingDismissed()
        XCTAssertFalse(store.showOnboarding);XCTAssertFalse(store.preferences.onboardingComplete)
        store.chooseGames()
        XCTAssertTrue(store.showOnboarding);XCTAssertEqual(store.onboardingStep,0)
        XCTAssertFalse(store.environmentReady);XCTAssertTrue(operations(root).isEmpty)
        await cleanup(root,store)
    }
    func testQuitFromIncompleteSetupWaitsForSheetDismissalAndDoesNotFinishSetup() async throws {
        let (root,store)=try fixture(toolchainReady:false)
        var terminations=0
        store.quitApplication {terminations+=1}
        XCTAssertFalse(store.showOnboarding)
        XCTAssertEqual(terminations,0,"AppKit must receive quit only after the sheet has detached")
        XCTAssertFalse(store.preferences.onboardingComplete)
        store.onboardingDismissed()
        XCTAssertEqual(terminations,1)
        store.onboardingDismissed()
        XCTAssertEqual(terminations,1,"Dismissal must consume the pending quit request")
        XCTAssertTrue(operations(root).isEmpty)
        store.quitApplication {terminations+=1}
        XCTAssertEqual(terminations,2,"Without a sheet, quit is immediate")
        await cleanup(root,store)
    }
    func testQuitFromGameToolsWaitsForSheetDismissal() async throws {
        let (root,store)=try fixture()
        store.showOnboarding=false
        var terminations=0
        for recovery in [false,true] {
            store.editingInput = !recovery
            store.showingRecovery = recovery
            let previous=terminations
            store.quitApplication {terminations+=1}
            XCTAssertFalse(store.editingInput)
            XCTAssertFalse(store.showingRecovery)
            XCTAssertEqual(terminations,previous,"Quit must wait until the game tools sheet detaches")
            store.applicationSheetDismissed()
            XCTAssertEqual(terminations,previous+1)
            store.applicationSheetDismissed()
            XCTAssertEqual(terminations,previous+1,"Dismissal must consume the pending quit request")
        }
        await cleanup(root,store)
    }
    func testBundledEngineInitializesAutomaticallyOnceAndRechecksBeforeCompleting() async throws {
        for succeeds in [true,false] {
            let (root,store)=try fixture(toolchainReady:false)
            try configure(root,games:[],imports:[])
            let reader=root.appendingPathComponent("resources/Engine/reader")
            try FileManager.default.createDirectory(at:reader,withIntermediateDirectories:true)
            try Data("{}".utf8).write(to:reader.appendingPathComponent("manifest.json"))
            try JSONSerialization.data(withJSONObject:succeeds,options:.fragmentsAllowed).write(to:root.appendingPathComponent("automatic-engine.json"))
            var completions=0
            store.checkEnvironment {completions+=1}
            try await waitUntil {completions==1 && !store.checkingEnvironment && !store.executionBusy}
            XCTAssertEqual(store.environmentReady,succeeds)
            XCTAssertEqual(operations(root).filter{$0["operation"] as? String == "prepareEngine"}.count,1)
            store.checkEnvironment {completions+=1}
            try await waitUntil {completions==2 && !store.checkingEnvironment}
            XCTAssertEqual(operations(root).filter{$0["operation"] as? String == "prepareEngine"}.count,1,"A broken bundle must not trigger an initialization loop")
            await cleanup(root,store)
        }
    }
    func testMetalRemovalIsBlockedWhileBusyAndRechecksAfterMockRemoval() async throws {
        let (root,store)=try fixture()
        try configure(root,games:[],imports:[])
        store.checks=[.init(name:"Xcode",ok:true,message:"fixture"),.init(name:"Metal 编译组件",ok:true,message:"fixture")]
        store.canUninstallMetal=true;store.executionTask="active-game"
        store.manageMetal(remove:true)
        XCTAssertNotNil(store.error);XCTAssertTrue(operations(root).isEmpty)
        store.executionTask=nil;store.queue=["pending-game"];store.error=nil
        store.manageMetal(remove:true)
        XCTAssertNotNil(store.error);XCTAssertTrue(operations(root).isEmpty)
        store.queue=[];store.error=nil;store.canUninstallMetal=false
        store.manageMetal(remove:true)
        XCTAssertNotNil(store.error);XCTAssertTrue(operations(root).isEmpty)
        store.error=nil;store.canUninstallMetal=true
        store.manageMetal(remove:true)
        try await waitUntil {self.operations(root).contains{$0["operation"] as? String == "preflight"} && store.processes.isEmpty}
        let removal=operations(root).filter{$0["operation"] as? String == "uninstallMetal"}
        XCTAssertEqual(removal.count,1);XCTAssertEqual(removal.first?["confirmed"] as? Bool,true)
        XCTAssertNil(store.executionTask)
        await cleanup(root,store)
    }
    func testMissingBundledPythonNeverFallsBackToHomebrew() async throws {
        let (root,store)=try fixture()
        try FileManager.default.removeItem(at:root.appendingPathComponent("resources/Runtime/python/bin/python3"))
        store.checkEnvironmentAtStartup()
        XCTAssertFalse(store.checkingEnvironment);XCTAssertFalse(store.environmentReady)
        XCTAssertFalse(store.runtimeReady);XCTAssertTrue(store.processes.isEmpty)
        XCTAssertEqual(store.checks.first?.name,"内置 Python")
        XCTAssertEqual(store.checks.first?.action,"reinstall")
        store.error=nil
        store.checkEnvironmentAtStartup()
        XCTAssertNil(store.error,"Reappearing views must not retry a failed startup check")
        XCTAssertTrue(operations(root).isEmpty)
        await cleanup(root,store)
    }
    func testStartupCheckRunsOnceAcrossAppearancesAndAgainInNewSession() async throws {
        let (root,store)=try fixture()
        store.checkEnvironmentAtStartup()
        store.checkEnvironmentAtStartup()
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        let firstTasks=store.tasks.filter{$0.operation=="preflight"}.map(\.id)
        for _ in 0..<3 {store.checkEnvironmentAtStartup()}
        XCTAssertTrue(store.environmentReady)
        XCTAssertTrue(store.processes.isEmpty)
        XCTAssertEqual(firstTasks.count,1)
        XCTAssertEqual(store.tasks.filter{$0.operation=="preflight"}.map(\.id),firstTasks)
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String=="preflight"}.count,1)

        let nextSession=Store(privateRoot:store.privateRoot,resources:store.resources)
        nextSession.checkEnvironmentAtStartup()
        try await waitUntil {!nextSession.checkingEnvironment && nextSession.processes.isEmpty}
        XCTAssertTrue(nextSession.environmentReady)
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String=="preflight"}.count,2)
        nextSession.terminate()
        await cleanup(root,store)
    }
    func testFailedStartupCheckIsReusedUntilExplicitRecheck() async throws {
        let (root,store)=try fixture(toolchainReady:false)
        store.checkEnvironmentAtStartup()
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        XCTAssertFalse(store.environmentReady)
        store.checkEnvironmentAtStartup()
        XCTAssertTrue(store.processes.isEmpty)
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String=="preflight"}.count,1)

        try JSONSerialization.data(withJSONObject:true,options:.fragmentsAllowed).write(to:root.appendingPathComponent("tools.json"))
        store.checkEnvironment()
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        XCTAssertTrue(store.environmentReady)
        store.checkEnvironmentAtStartup()
        XCTAssertTrue(store.processes.isEmpty)
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String=="preflight"}.count,2)
        await cleanup(root,store)
    }
    func testPythonBootstrapCrashLeavesAnActionableCheckAndDoesNotRemainChecking() async throws {
        let (root,store)=try fixture()
        let executable=root.appendingPathComponent("resources/Runtime/python/bin/python3")
        try FileManager.default.removeItem(at:executable)
        try "#!/bin/sh\nexit 9\n".write(to:executable,atomically:true,encoding:.utf8)
        try FileManager.default.setAttributes([.posixPermissions:0o700],ofItemAtPath:executable.path)
        store.checkEnvironment()
        try await waitUntil {!store.checkingEnvironment && store.processes.isEmpty}
        XCTAssertFalse(store.environmentReady);XCTAssertEqual(store.checks.first?.action,"reinstall")
        await cleanup(root,store)
    }
    func testPartialChecksAndConcurrentRequestsCannotPrematurelyEnableContinue() async throws {
        let (root,store)=try fixture()
        try configure(root,games:[],imports:[])
        var callbacks=0
        store.checkEnvironment {callbacks+=1}
        store.checkEnvironment {callbacks+=1}
        let id=try XCTUnwrap(store.tasks.first(where:{$0.operation=="preflight"})?.id)
        store.event(["schema":1,"taskId":id,"type":"check","check":["name":"partial","ok":true,"message":"fixture"]],visible:true)
        XCTAssertFalse(store.environmentReady)
        try await waitUntil {callbacks==2 && store.processes.isEmpty}
        XCTAssertEqual(operations(root).filter{$0["operation"] as? String=="preflight"}.count,1)
        XCTAssertTrue(store.environmentReady)
        await cleanup(root,store)
    }
    func testPreparedGameCanLaunchWhenOnlyCompileToolsAreUnavailable() async throws {
        let (root,store)=try fixture()
        try configure(root,games:[],imports:[])
        store.checks=[.init(name:"Python",ok:true,message:"fixture",requiredFor:["prepare","launch"]),.init(name:"Xcode",ok:false,message:"fixture",requiredFor:["prepare"])]
        XCTAssertFalse(store.environmentReady);XCTAssertTrue(store.runtimeReady)
        let game=try XCTUnwrap(Store.decode(Game.self,game("g",ready:true)))
        store.launch(game)
        try await waitUntil {self.operations(root).contains{$0["operation"] as? String=="launch"} && store.processes.isEmpty}
        XCTAssertFalse(operations(root).contains{$0["operation"] as? String=="build"})
        await cleanup(root,store)
    }
}
