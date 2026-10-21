import Foundation
import SwiftUI
import AppKit

final class WorkerOutput: @unchecked Sendable {
    private let lock = NSLock()
    private var buffer = Data()
    private var errors = Data()
    func append(_ chunk: Data) -> [Data] {
        lock.lock(); defer {lock.unlock()}; buffer.append(chunk)
        var lines: [Data] = []
        while let range = buffer.range(of:Data([10])) {lines.append(buffer.subdata(in:0..<range.lowerBound));buffer.removeSubrange(0..<range.upperBound)}
        return lines
    }
    func error(_ data:Data) {lock.lock();defer{lock.unlock()};if errors.count<32768{errors.append(data)}}
    var errorText:String {lock.lock();defer{lock.unlock()};return String(data:errors,encoding:.utf8) ?? ""}
}

@MainActor final class Store: ObservableObject {
    @Published var preferences = Preferences()
    @Published var games: [Game] = []
    @Published var tasks: [TaskRecord] = []
    @Published var checks: [ToolCheck] = []
    @Published private(set) var checkingEnvironment = false
    @Published var environmentReportComplete = false
    private var environmentCallbacks: [()->Void] = []
    private var lastWorkerEvent: [String:Date] = [:]
    @Published var canUninstallMetal = false
    @Published var profiles: [GameProfile] = []
    @Published var keyStatus = "尚未导入密钥"
    @Published var hasImportedKeys = false
    @Published var error: String?
    @Published var notice: String?
    @Published var selection: String? = "library"
    @Published var selectedGame: String?
    @Published var showOnboarding = false
    @Published var onboardingStep = 0
    private var addGamesAfterOnboarding = false
    @Published var editingInput = false
    @Published var inputGame: Game?
    @Published var globalInput = InputConfig.standard
    @Published var queue: [String] = []
    let privateRoot: URL
    let resources: URL
    var processes: [String:Process] = [:]
    var callbacks: [String:([String:Any])->Void] = [:]
    @Published var executionTask: String?
    var refreshTimer: Timer?
    var libraryURL: URL { URL(fileURLWithPath: preferences.library) }
    var executionBusy: Bool { executionTask != nil }
    var environmentReady: Bool { environmentReportComplete && !checkingEnvironment && !checks.isEmpty && checks.filter{$0.required(for:"prepare")}.allSatisfy(\.ok) }
    var runtimeReady: Bool { environmentReportComplete && !checkingEnvironment && !checks.isEmpty && checks.filter{$0.required(for:"launch")}.allSatisfy(\.ok) }
    var metalInstalled: Bool { checks.contains { $0.name == "Metal 编译组件" && $0.ok } }
    var xcodeInstalled: Bool { checks.contains { $0.name == "Xcode" && $0.ok } }
    var xcodeInitialized: Bool { checks.contains { $0.name == "Xcode 初始设置" && $0.ok } }
    var canManageToolchain: Bool { !executionBusy && queue.isEmpty && !checkingEnvironment }
    var importActionTitle: String { !environmentReady ? "准备环境" : hasImportedKeys ? "添加游戏" : "开始导入" }
    var importingKeys: Bool { tasks.contains { $0.operation == "keys" && $0.active } }
    var prepareAfterImport: Bool {
        get { preferences.prepareAfterImport ?? true }
        set { preferences.prepareAfterImport = newValue; savePreferences() }
    }
    var appearance: AppAppearance {
        get { AppAppearance(rawValue:preferences.appearance ?? "system") ?? .system }
        set { preferences.appearance = newValue.rawValue; applyAppearance(); savePreferences() }
    }
    func applyAppearance() {
        switch appearance {
        case .system: NSApp?.appearance = nil
        case .light: NSApp?.appearance = NSAppearance(named:.aqua)
        case .dark: NSApp?.appearance = NSAppearance(named:.darkAqua)
        }
    }
    var language: AppLanguage {
        get { AppLanguage(rawValue:preferences.language ?? "system") ?? .system }
        set {
            Localization.preference = newValue
            preferences.language = newValue.rawValue
            savePreferences()
        }
    }
    var selected: Game? { games.first { $0.id == selectedGame } }
    init(privateRoot overrideRoot: URL? = nil, resources overrideResources: URL? = nil) {
        let args = CommandLine.arguments
        if let overrideRoot { privateRoot = overrideRoot }
        else if let i = args.firstIndex(of:"--data-root"), args.count > i+1 { privateRoot = URL(fileURLWithPath:args[i+1]) }
        else { privateRoot = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("NSMac") }
        if let overrideResources { resources = overrideResources }
        else if let r = Bundle.main.resourceURL, FileManager.default.fileExists(atPath:r.appendingPathComponent("Worker/main.py").path) { resources = r }
        else { resources = URL(fileURLWithPath:#filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent() }
        try? FileManager.default.createDirectory(at:privateRoot,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        if let data = try? Data(contentsOf:privateRoot.appendingPathComponent("preferences.json")), let p = try? JSONDecoder().decode(Preferences.self,from:data) { preferences = p }
        if let data = try? Data(contentsOf:privateRoot.appendingPathComponent("default-input.json")), let p = try? JSONDecoder().decode(InputConfig.self,from:data) { globalInput = p }
        if let i = args.firstIndex(of:"--language"), args.count > i+1, let language = AppLanguage(rawValue:args[i+1]) {
            preferences.language = language.rawValue
        }
        Localization.preference = language
        if let i = args.firstIndex(of:"--appearance"), args.count > i+1, let appearance = AppAppearance(rawValue:args[i+1]) {
            preferences.appearance = appearance.rawValue
        }
        applyAppearance()
        recoverTasks()
        showOnboarding = !preferences.onboardingComplete
        if !preferences.library.isEmpty { refresh() }
    }
    func recoverTasks() {
        let paths = (try? FileManager.default.contentsOfDirectory(at:privateRoot.appendingPathComponent("jobs"),includingPropertiesForKeys:nil)) ?? []
        for path in paths where path.pathExtension == "json" {
            guard let data = try? Data(contentsOf:path), var obj = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any], let state = obj["state"] as? String else { continue }
            if ["running","cancelling","queued"].contains(state) {
                obj["state"] = "interrupted"; obj["message"] = "上次运行被中断，可验证已有阶段后重试。"
                if let d = try? JSONSerialization.data(withJSONObject:obj) { try? d.write(to:path,options:.atomic) }
            }
        }
    }
    func savePreferences() { if let d = try? JSONEncoder().encode(preferences) { try? d.write(to:privateRoot.appendingPathComponent("preferences.json"),options:.atomic) } }
    func chooseLibrary() {
        let panel = NSOpenPanel(); panel.title = L("选择游戏库（首次请选择空文件夹）"); panel.canChooseFiles = false; panel.canChooseDirectories = true; panel.canCreateDirectories = true; panel.prompt = L("选择")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        worker("setup",extra:["library":url.path,"libraryId":""]) { result in
            self.preferences.library = result["library"] as? String ?? url.path; self.preferences.libraryId = result["libraryId"] as? String ?? ""; self.savePreferences(); self.refresh(); self.checkEnvironment()
        }
    }
    func checkEnvironment(completion: (() -> Void)? = nil) {
        if let completion { environmentCallbacks.append(completion) }
        guard !checkingEnvironment else { return }
        checkingEnvironment = true; environmentReportComplete = false; checks = []; canUninstallMetal = false
        let developerDir=preferences.developerDir,libraryId=preferences.libraryId
        worker("preflight") { r in
        if self.preferences.developerDir != developerDir || self.preferences.libraryId != libraryId {
            self.checkingEnvironment=false;self.checkEnvironment();return
        }
        if let checks = Self.decode([ToolCheck].self,r["checks"]) { self.checks = checks;self.environmentReportComplete=true }
        self.canUninstallMetal = r["canUninstallMetal"] as? Bool == true
        self.checkingEnvironment = false
        let callbacks = self.environmentCallbacks; self.environmentCallbacks = []
        callbacks.forEach { $0() }
        if self.environmentReady { self.startNext() }
    } }
    func pythonExecutable() throws -> URL {
        let bundled = resources.appendingPathComponent("Runtime/python/bin/python3")
        if FileManager.default.isExecutableFile(atPath:bundled.path) { return bundled }
        // Source checkout support is explicit; installed apps never borrow a system Python.
        let developer = resources.appendingPathComponent("work/Runtime/python/bin/python3")
        if FileManager.default.fileExists(atPath:resources.appendingPathComponent("Package.swift").path), FileManager.default.isExecutableFile(atPath:developer.path) { return developer }
        throw NSError(domain:"LumaDock",code:1,userInfo:[NSLocalizedDescriptionKey:L("内置 Python 缺失或不可执行，请重新安装完整应用。")])
    }
    func failEnvironmentBootstrap(_ detail:String) {
        checkingEnvironment = false; environmentReportComplete = false; environmentCallbacks = []
        checks = [.init(name:"内置 Python",ok:false,message:"内置 Python 无法启动环境检查",help:"Python 随完整应用提供，无需另装系统 Python。请从官方 Release 重新下载 DMG，将完整应用复制到“应用程序”后重新检查。",action:"reinstall",group:"bundled",requiredFor:["prepare","launch"],detail:detail)]
    }
    private func watchEnvironmentWorker(_ id:String) {
        DispatchQueue.main.asyncAfter(deadline:.now()+45) { [weak self] in
            guard let self,let process=self.processes[id],process.isRunning,self.checkingEnvironment else {return}
            if Date().timeIntervalSince(self.lastWorkerEvent[id] ?? .distantPast) >= 40 {
                process.terminate();self.failEnvironmentBootstrap("工具检查超时，请重新检查或修复对应组件。")
            } else { self.watchEnvironmentWorker(id) }
        }
    }
    func repairEnvironment(_ action:String) {
        switch action {
        case "xcodeStore": openXcodeStore()
        case "openXcode":
            let app = URL(fileURLWithPath:preferences.developerDir).deletingLastPathComponent().deletingLastPathComponent()
            guard app.pathExtension == "app", FileManager.default.fileExists(atPath:app.path) else { openXcodeStore(); return }
            NSWorkspace.shared.open(app)
        case "installMetal": manageMetal(remove:false)
        case "reinstall": NSWorkspace.shared.open(URL(string:"https://github.com/Xc1Ym/LumaDock/releases/latest")!)
        case "systemUpdate": NSWorkspace.shared.open(URL(string:"x-apple.systempreferences:com.apple.Software-Update-Settings.extension")!)
        case "library": chooseLibrary()
        default: break
        }
    }
    func chooseXcode() {
        let panel=NSOpenPanel();panel.title=L("选择完整 Xcode.app");panel.canChooseFiles=true;panel.canChooseDirectories=false;panel.allowedContentTypes=[.application]
        guard panel.runModal() == .OK,let app=panel.url else {return}
        preferences.developerDir=app.appendingPathComponent("Contents/Developer").path
        savePreferences();checkEnvironment()
    }
    func openXcodeStore() {
        if !NSWorkspace.shared.open(URL(string:"macappstore://apps.apple.com/app/xcode/id497799835?mt=12")!) {
            NSWorkspace.shared.open(URL(string:"https://apps.apple.com/app/xcode/id497799835")!)
        }
    }
    func manageMetal(remove: Bool) {
        guard canManageToolchain else { error = "请等待游戏、准备队列和工具链任务结束后再管理组件。"; return }
        guard xcodeInstalled, remove || xcodeInitialized else { error = "请先安装完整 Xcode 并完成初始设置。"; return }
        guard !remove || metalInstalled && canUninstallMetal else { error = "未检测到可卸载的 Metal 组件，或当前 Xcode 不支持卸载。"; return }
        savePreferences()
        checks = []
        executionTask = worker(remove ? "uninstallMetal" : "installMetal",extra:remove ? ["confirmed":true] : [:]) { _ in
            self.notice = remove ? "Metal 编译组件已卸载，可随时重新安装。" : "Metal 编译组件已安装。"
        }
    }
    func openOnboarding() {
        onboardingStep = !environmentReady ? 0 : preferences.library.isEmpty ? 1 : hasImportedKeys ? 3 : 2
        showOnboarding = true
    }
    func importPrerequisitesReady() -> Bool {
        guard environmentReady else { onboardingStep = 0; showOnboarding = true; checkEnvironment(); return false }
        guard !preferences.library.isEmpty else { onboardingStep = 1; showOnboarding = true; return false }
        guard hasImportedKeys, FileManager.default.isReadableFile(atPath:privateRoot.appendingPathComponent("keys/prod.keys").path) else {
            hasImportedKeys = false; keyStatus = "请先导入 prod.keys，再添加游戏"; onboardingStep = 2; showOnboarding = true; return false
        }
        return true
    }
    func finishOnboarding(addGames: Bool) {
        guard importPrerequisitesReady() else { return }
        preferences.onboardingComplete = true; savePreferences()
        addGamesAfterOnboarding = addGames; showOnboarding = false
    }
    func onboardingDismissed() {
        if addGamesAfterOnboarding { addGamesAfterOnboarding = false; chooseGames() }
    }
    func importKeys() {
        guard environmentReady else { onboardingStep = 0; showOnboarding = true; checkEnvironment(); return }
        guard !preferences.library.isEmpty else { onboardingStep = 1; showOnboarding = true; return }
        guard !importingKeys else { return }
        let p = NSOpenPanel(); p.title = L("导入玩家自己的 prod.keys"); p.allowsMultipleSelection = false
        guard p.runModal() == .OK, let url = p.url else { return }
        worker("keys",extra:["path":url.path]) { r in self.hasImportedKeys = true; self.keyStatus = r["message"] as? String ?? "已导入"; self.refresh() }
    }
    func chooseGames() {
        guard importPrerequisitesReady() else { return }
        let p = NSOpenPanel(); p.title = L("添加 NSP 文件或扫描文件夹"); p.allowsMultipleSelection = true; p.canChooseDirectories = true; p.canChooseFiles = true
        if p.runModal() == .OK { addGames(p.urls) }
    }
    func addGames(_ urls: [URL]) {
        guard importPrerequisitesReady(), !urls.isEmpty else { return }
        let libraryId = preferences.libraryId
        let prepare = prepareAfterImport
        worker("import",extra:["paths":urls.map(\.path)]) { result in
            guard libraryId == self.preferences.libraryId else { return }
            let ids = Set((result["imports"] as? [[String:Any]] ?? []).compactMap { item in item["duplicate"] as? Bool == false ? item["id"] as? String : nil })
            self.refresh {
                guard libraryId == self.preferences.libraryId else { return }
                let imported = self.games.filter { ids.contains($0.id) }
                if let first = imported.first { self.selectedGame = first.id }
                self.notice = "导入完成，源文件保持原样。"
                let candidates = imported.filter { $0.buildable && ($0.ready != true || $0.needsPreparation == true) }
                guard prepare, !candidates.isEmpty else { return }
                self.checkEnvironment {
                    guard libraryId == self.preferences.libraryId else { return }
                    guard !self.checks.isEmpty, self.checks.allSatisfy(\.ok) else {
                        self.selection = "settings"; self.notice = "游戏已导入，请完成工具链检查后准备运行文件。"; return
                    }
                    candidates.forEach { self.enqueue($0) }
                    self.notice = "导入完成，文件齐全的游戏已加入准备队列；完成后可启动。"
                }
            }
        }
    }
    func refresh(completion: (() -> Void)? = nil) {
        guard !preferences.library.isEmpty else { return }
        let libraryId = preferences.libraryId
        worker("catalog",visible:false) { r in
            guard libraryId == self.preferences.libraryId else { return }
            if let games = Self.decode([Game].self,r["games"]) { self.games = games.filter { !$0.hidden } }
            if let profiles = Self.decode([GameProfile].self,r["profiles"]) { self.profiles = profiles }
            let keys = r["keys"] as? [String:Any] ?? [:]
            self.hasImportedKeys = keys["ready"] as? Bool == true
            self.keyStatus = keys["message"] as? String ?? "尚未导入 prod.keys"
            if let records = Self.decode([TaskRecord].self,r["jobs"]) {
                for rec in records where ["import","build","launch","migrate","keys","installMetal","uninstallMetal"].contains(rec.operation) {
                    if !self.tasks.contains(where: { $0.id == rec.id }) { self.tasks.append(rec) }
                }
                self.tasks.sort { ($0.started ?? 0) > ($1.started ?? 0) }
            }
            if self.selectedGame == nil { self.selectedGame = self.games.first?.id }
            completion?()
        }
    }
    static func decode<T:Decodable>(_ type: T.Type, _ obj: Any?) -> T? {
        guard let obj, JSONSerialization.isValidJSONObject(obj), let d = try? JSONSerialization.data(withJSONObject:obj) else { return nil }
        return try? JSONDecoder().decode(type,from:d)
    }
    @discardableResult func worker(_ operation: String, extra: [String:Any] = [:], visible: Bool = true, completion: (([String:Any])->Void)? = nil) -> String {
        let id = UUID().uuidString.lowercased()
        var req: [String:Any] = ["schema":1,"taskId":id,"operation":operation,"privateRoot":privateRoot.path,"resources":resources.path,"library":preferences.library.isEmpty ? privateRoot.appendingPathComponent("unconfigured").path : preferences.library,"libraryId":preferences.libraryId,"developerDir":preferences.developerDir,"parentPid":ProcessInfo.processInfo.processIdentifier]
        extra.forEach { req[$0] = $1 }
        // Environment setup must remain available when an old library drive is offline.
        if ["preflight","installMetal","uninstallMetal"].contains(operation) {
            req["libraryId"] = ""
            req["storageLibraryId"] = preferences.libraryId
        }
        let dir = privateRoot.appendingPathComponent("requests"); try? FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700]); let file = dir.appendingPathComponent(id+".json")
        do {
            let data = try JSONSerialization.data(withJSONObject:req); try data.write(to:file,options:.atomic); try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:file.path)
            let python = try pythonExecutable()
            let process = Process(); process.executableURL = python; process.arguments = ["-B","-I",resources.appendingPathComponent("Worker/main.py").path,"--request",file.path]
            var env = ProcessInfo.processInfo.environment; env["PYTHONUNBUFFERED"] = "1"; env["PYTHONDONTWRITEBYTECODE"] = "1"; env["PYTHONNOUSERSITE"] = "1"; env.removeValue(forKey:"PYTHONPATH"); env.removeValue(forKey:"PYTHONHOME"); process.environment = env
            let pipe = Pipe(); process.standardOutput = pipe; let err = Pipe(); process.standardError = err
            let output = WorkerOutput()
            pipe.fileHandleForReading.readabilityHandler = { handle in
                let chunk = handle.availableData
                if chunk.isEmpty { return }
                let lines = output.append(chunk)
                for line in lines {
                    guard let e = (try? JSONSerialization.jsonObject(with:line)) as? [String:Any] else { continue }
                    DispatchQueue.main.async { self.event(e,visible:visible) }
                }
            }
            // Drain stderr so a failed Python bootstrap cannot block the child.
            err.fileHandleForReading.readabilityHandler = { h in output.error(h.availableData) }
            process.terminationHandler = { p in
                pipe.fileHandleForReading.readabilityHandler = nil; err.fileHandleForReading.readabilityHandler = nil
                DispatchQueue.main.asyncAfter(deadline:.now()+0.15) {
                    self.processes[id] = nil; try? FileManager.default.removeItem(at:file)
                    self.lastWorkerEvent[id] = nil
                    if let i = self.tasks.firstIndex(where:{$0.id == id}), self.tasks[i].active {
                        self.tasks[i].state = p.terminationStatus == 130 ? "cancelled" : "interrupted"; self.tasks[i].message = "工作进程已退出。可重试并验证完成阶段。"
                        if operation == "preflight" { self.failEnvironmentBootstrap(output.errorText.isEmpty ? "工作进程已退出。可重试并验证完成阶段。" : output.errorText) }
                    }
                    self.callbacks[id] = nil
                    if self.executionTask == id {
                        self.executionTask = nil
                        if !["installMetal","uninstallMetal"].contains(operation) { self.startNext() }
                    }
                    if ["installMetal","uninstallMetal"].contains(operation) { self.checkEnvironment() }
                    if visible { self.refresh() }
                }
            }
            if visible { tasks.insert(.init(id:id,operation:operation,state:"running",gameId:extra["gameId"] as? String,started:Date().timeIntervalSince1970),at:0) }
            callbacks[id] = completion; processes[id] = process
            try process.run()
            if operation == "preflight" {lastWorkerEvent[id]=Date();watchEnvironmentWorker(id)}
        } catch {
            self.error = "无法启动本地组件：\(error.localizedDescription)"; processes[id] = nil; callbacks[id] = nil
            if let i=tasks.firstIndex(where:{$0.id==id}) { tasks[i].state="failed";tasks[i].message=self.error }
            try? FileManager.default.removeItem(at:file)
            if operation == "preflight" { failEnvironmentBootstrap(error.localizedDescription) }
            DispatchQueue.main.async {if self.executionTask==id {self.executionTask=nil;self.startNext()}}
        }
        return id
    }
    func event(_ e: [String:Any], visible: Bool) {
        guard e["schema"] as? Int == 1, let id = e["taskId"] as? String else { return }
        if lastWorkerEvent[id] != nil {lastWorkerEvent[id]=Date()}
        if e["type"] as? String == "check", tasks.contains(where:{$0.id==id && $0.operation=="preflight"}), let check=Self.decode(ToolCheck.self,e["check"]) {
            if let index=checks.firstIndex(where:{$0.id==check.id}) {checks[index]=check} else {checks.append(check)}
        }
        if let i = tasks.firstIndex(where:{$0.id == id}) {
            tasks[i].stage = e["stage"] as? String; tasks[i].stageIndex = e["stageIndex"] as? Int; tasks[i].stageCount = e["stageCount"] as? Int
            if e["type"] as? String != "heartbeat" {tasks[i].done = e["done"] as? Double; tasks[i].total = e["total"] as? Double; tasks[i].unit = e["unit"] as? String}; tasks[i].elapsed = e["elapsed"] as? Double
            if let msg = e["message"] as? String, !msg.isEmpty { tasks[i].message = msg }
            if let state = e["state"] as? String { tasks[i].state = state }
        }
        if e["type"] as? String == "result" {
            let state = e["state"] as? String
            if state == "completed" { callbacks[id]?(e["result"] as? [String:Any] ?? [:]) }
            else if state == "failed" {
                error = e["message"] as? String ?? "操作失败，请查看任务日志。"
                if tasks.contains(where:{$0.id==id && $0.operation=="preflight"}) {checkingEnvironment=false;environmentCallbacks=[]}
            }
        }
    }
    func enqueue(_ game: Game) {
        guard importPrerequisitesReady() else { return }
        guard game.buildable else { error = (game.missing ?? []).joined(separator:"\n"); return }
        guard !queue.contains(game.id), !tasks.contains(where: { $0.operation == "build" && $0.gameId == game.id && $0.active && !$0.id.hasPrefix("queued-") }) else { return }
        queue.append(game.id)
        let rec = TaskRecord(id:"queued-"+game.id,operation:"build",state:"queued",gameId:game.id,started:Date().timeIntervalSince1970)
        if let d = try? JSONEncoder().encode(rec) {try? d.write(to:privateRoot.appendingPathComponent("jobs/\(rec.id).json"),options:.atomic)}
        selection = "tasks"; startNext()
    }
    func dequeue(_ id:String) {
        queue.removeAll {$0==id}
        let path=privateRoot.appendingPathComponent("jobs/queued-\(id).json")
        if let d=try? Data(contentsOf:path),var record=try? JSONDecoder().decode(TaskRecord.self,from:d){record.state="cancelled";record.message="已从队列移除";if let data=try? JSONEncoder().encode(record){try? data.write(to:path,options:.atomic)}}
    }
    func startNext() {
        guard !executionBusy, environmentReady, !queue.isEmpty else { return }
        let id = queue.removeFirst(); try? FileManager.default.removeItem(at:privateRoot.appendingPathComponent("jobs/queued-\(id).json")); executionTask = worker("build",extra:["gameId":id]) { _ in self.notice = "游戏已准备完成，可以启动。" }
    }
    func launch(_ game: Game) {
        guard !executionBusy, queue.isEmpty else { error = "构建与游戏运行互斥，请等待当前任务结束。"; return }
        guard runtimeReady else {
            checkEnvironment {
                if self.runtimeReady {self.launch(game)}
                else {self.onboardingStep=0;self.showOnboarding=true}
            }
            return
        }
        executionTask = worker("launch",extra:["gameId":game.id])
    }
    func migrate(_ game: Game) {
        guard !executionBusy else { return }
        let p = NSOpenPanel(); p.title = L("选择原 BreathOfTheWild 构建文件夹"); p.canChooseDirectories = true; p.canChooseFiles = false
        guard p.runModal() == .OK, let url = p.url else { return }
        selection = "tasks"; executionTask = worker("migrate",extra:["gameId":game.id,"path":url.path])
    }
    func cancel(_ task: TaskRecord) {
        if let i = tasks.firstIndex(where:{$0.id == task.id}) { tasks[i].state = "cancelling" }
        processes[task.id]?.terminate()
    }
    func retry(_ task: TaskRecord) {
        guard let game = games.first(where:{$0.id == task.gameId}) else { return }
        if task.operation == "launch" { launch(game) } else { enqueue(game) }
    }
    func remove(_ game: Game) { worker("remove",extra:["gameId":game.id]) { _ in self.refresh() } }
    func clean(_ game: Game, kind: String) { worker("clean",extra:["gameId":game.id,"kind":kind]) { _ in self.refresh() } }
    func reveal(_ url: URL) { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    func exportDiagnostics() {
        let p = NSSavePanel(); p.prompt = L("保存"); p.nameFieldStringValue = L("NSMac-诊断.zip"); guard p.runModal() == .OK, let url = p.url else { return }
        worker("diagnostics",extra:["path":url.path]) { _ in self.reveal(url) }
    }
    func input(for game: Game?) -> InputConfig {
        if let game, let d = try? Data(contentsOf:libraryURL.appendingPathComponent("mappings/\(game.id).json")), let config = try? JSONDecoder().decode(InputConfig.self,from:d) { return config }
        return globalInput
    }
    func saveInput(_ config: InputConfig, for game: Game?) {
        guard config.conflicts.isEmpty, let d = try? JSONEncoder().encode(config), let obj = try? JSONSerialization.jsonObject(with:d) else { return }
        var extra: [String:Any] = ["config":obj]; if let game { extra["gameId"] = game.id }
        worker("saveInput",extra:extra,visible:false) { _ in
            if game == nil { self.globalInput = config }; self.notice = "映射已保存，下次启动游戏时生效，无需重新编译。"; self.editingInput = false
        }
    }
    func terminate() { processes.values.forEach { if $0.isRunning { $0.terminate() } } }
}
