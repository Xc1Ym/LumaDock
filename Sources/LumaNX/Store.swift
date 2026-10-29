import Foundation
import SwiftUI
import AppKit
import UniformTypeIdentifiers

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
    @Published var conversion = ConversionJob()
    @Published var converterStatus:ConverterStatus?
    @Published var checkingConverter = false
    @Published var checks: [ToolCheck] = []
    @Published private(set) var checkingEnvironment = false
    @Published private(set) var catalogWorkers = 0
    @Published var environmentReportComplete = false
    private var environmentCallbacks: [()->Void] = []
    private var requestedStartupEnvironmentCheck = false
    private var attemptedBundledEngineInitialization = false
    private var lastWorkerEvent: [String:Date] = [:]
    private var deletedTaskIDs = Set<String>()
    private var documentationWindow:NSWindow?
    @Published var canUninstallMetal = false
    @Published var engineSupportsInput = false
    @Published var profiles: [GameProfile] = []
    @Published var keyStatus = "尚未导入密钥"
    @Published var hasImportedKeys = false
    @Published var error: String? { didSet { if error == nil {errorDiagnostic=nil} } }
    @Published var errorDiagnostic: TaskDiagnostic?
    @Published var notice: String?
    @Published var selection: String? = "library"
    @Published var selectedGame: String?
    @Published var showOnboarding = false
    @Published var onboardingStep = 0
    private var addGamesAfterOnboarding = false
    private var quitAfterSheetDismissal: (@MainActor () -> Void)?
    @Published var editingInput = false
    @Published var showingRecovery = false
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
    var executionBusy: Bool { executionTask != nil || tasks.contains { $0.operation == "import" && $0.active } }
    var refreshingLibrary: Bool {catalogWorkers>0}
    var activeTasks: [TaskRecord] {tasks.filter{$0.active && $0.state != "queued" && $0.operation != "launch"}}
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
    var defaultGameLanguage: GameLanguage {
        get { GameLanguage(rawValue:preferences.gameLanguage ?? "") ?? .simplifiedChinese }
        set { preferences.gameLanguage = newValue.rawValue; savePreferences() }
    }
    func gameLanguageOverride(for id:String) -> GameLanguage? {
        preferences.gameLanguages?[id].flatMap(GameLanguage.init(rawValue:))
    }
    func gameLanguage(for id:String) -> GameLanguage {
        gameLanguageOverride(for:id) ?? defaultGameLanguage
    }
    func setGameLanguage(_ language:GameLanguage?, for id:String) {
        guard gameLanguageOverride(for:id) != language else {return}
        var overrides = preferences.gameLanguages ?? [:]
        overrides[id] = language?.rawValue
        preferences.gameLanguages = overrides.isEmpty ? nil : overrides
        savePreferences()
        let name=language?.name ?? L("跟随默认（\(defaultGameLanguage.name)）")
        notice="启动语言已设为\(name)，下次启动生效。"
    }
    var selected: Game? { games.first { $0.id == selectedGame } }
    init(privateRoot overrideRoot: URL? = nil, resources overrideResources: URL? = nil) {
        let args = CommandLine.arguments
        if let overrideRoot { privateRoot = overrideRoot }
        else if let i = args.firstIndex(of:"--data-root"), args.count > i+1 { privateRoot = URL(fileURLWithPath:args[i+1]) }
        // Preserve the pre-rename application data directory for existing installations.
        else { privateRoot = FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("NSMac") }
        if let overrideResources { resources = overrideResources }
        else if let r = Bundle.main.resourceURL, Bundle.main.bundleURL.pathExtension == "app" || FileManager.default.fileExists(atPath:r.appendingPathComponent("Worker/main.py").path) { resources = r }
        else { resources = URL(fileURLWithPath:#filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent() }
        try? FileManager.default.createDirectory(at:privateRoot,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        if let data = try? Data(contentsOf:privateRoot.appendingPathComponent("preferences.json")), let p = try? JSONDecoder().decode(Preferences.self,from:data) { preferences = p }
        if let output=preferences.conversionOutput {conversion.outputDirectory=output}
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
            if obj["operation"] as? String == "convertFiles",let data=try? JSONSerialization.data(withJSONObject:obj),let record=try? JSONDecoder().decode(TaskRecord.self,from:data) {tasks.append(record)}
        }
        tasks.sort{($0.started ?? 0)>($1.started ?? 0)}
    }
    func savePreferences() { if let d = try? JSONEncoder().encode(preferences) { try? d.write(to:privateRoot.appendingPathComponent("preferences.json"),options:.atomic) } }
    func chooseLibrary() {
        let panel = NSOpenPanel(); panel.title = L("选择游戏库（首次请选择空文件夹）"); panel.canChooseFiles = false; panel.canChooseDirectories = true; panel.canCreateDirectories = true; panel.prompt = L("选择")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        worker("setup",extra:["library":url.path,"libraryId":""]) { result in
            self.preferences.library = result["library"] as? String ?? url.path; self.preferences.libraryId = result["libraryId"] as? String ?? ""; self.savePreferences(); self.refresh(); self.checkEnvironment()
        }
    }
    func checkEnvironmentAtStartup() {
        guard !requestedStartupEnvironmentCheck else { return }
        checkEnvironment()
    }
    func checkEnvironment(completion: (() -> Void)? = nil) {
        // Keep this attempt scoped to the Store's app session, including failures.
        // Reappearing windows and onboarding reuse it; explicit checks still refresh.
        requestedStartupEnvironmentCheck = true
        if let completion { environmentCallbacks.append(completion) }
        guard !checkingEnvironment else { return }
        checkingEnvironment = true; environmentReportComplete = false; checks = []; canUninstallMetal = false
        let developerDir=preferences.developerDir,libraryId=preferences.libraryId,engineDir=preferences.engineDir
        worker("preflight") { r in
        if self.preferences.developerDir != developerDir || self.preferences.libraryId != libraryId || self.preferences.engineDir != engineDir {
            self.checkingEnvironment=false;self.checkEnvironment();return
        }
        if let checks = Self.decode([ToolCheck].self,r["checks"]) { self.checks = checks;self.environmentReportComplete=true }
        self.canUninstallMetal = r["canUninstallMetal"] as? Bool == true
        self.engineSupportsInput = (r["engineInfo"] as? [String:Any])?["inputConfig"] as? Bool == true
        self.checkingEnvironment = false
        if !self.attemptedBundledEngineInitialization,!self.executionBusy,
           FileManager.default.isReadableFile(atPath:self.resources.appendingPathComponent("Engine/reader/manifest.json").path),
           self.checks.contains(where:{$0.name=="NSP 读取组件" && !$0.ok && $0.action=="prepareEngine"}) {
            self.attemptedBundledEngineInitialization=true
            self.executionTask=self.worker("prepareEngine")
            return
        }
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
        throw NSError(domain:"LumaNX",code:1,userInfo:[NSLocalizedDescriptionKey:L("内置 Python 缺失或不可执行，请重新安装完整应用。")])
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
        case "chooseEngine": chooseEngine()
        case "prepareEngine": prepareEngine()
        case "xcodeStore": openXcodeStore()
        case "openXcode":
            let app = URL(fileURLWithPath:preferences.developerDir).deletingLastPathComponent().deletingLastPathComponent()
            guard app.pathExtension == "app", FileManager.default.fileExists(atPath:app.path) else { openXcodeStore(); return }
            NSWorkspace.shared.open(app)
        case "installMetal": manageMetal(remove:false)
        case "reinstall": NSWorkspace.shared.open(URL(string:"https://github.com/Xc1Ym/LumaNX/releases/latest")!)
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
    func chooseEngine() {
        guard canManageToolchain else { return }
        let panel=NSOpenPanel();panel.title=L("选择 nxnative 源码根目录");panel.canChooseDirectories=true;panel.canChooseFiles=false
        guard panel.runModal() == .OK,let folder=panel.url else {return}
        selectEngine(folder)
    }
    func selectEngine(_ folder:URL) {
        guard canManageToolchain else { return }
        preferences.engineDir=folder.path;savePreferences()
        checks=[];environmentReportComplete=false;engineSupportsInput=false
        refresh();checkEnvironment()
    }
    func prepareEngine() {
        guard canManageToolchain else {return}
        savePreferences()
        executionTask=worker("prepareEngine") { _ in self.notice="引擎工具已就绪。" }
    }
    func openDocumentation(_ guide:AppGuide) {
        if documentationWindow == nil {
            let window=NSWindow(contentRect:NSRect(x:0,y:0,width:900,height:720),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
            window.isReleasedWhenClosed=false;window.center();documentationWindow=window
        }
        documentationWindow?.title=guide.title
        documentationWindow?.contentView=NSHostingView(rootView:DocumentationView(guide:guide).environmentObject(self))
        documentationWindow?.makeKeyAndOrderFront(nil)
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
    func deferOnboarding() {
        // Dismissing setup never marks prerequisites as satisfied or opens import.
        addGamesAfterOnboarding = false
        quitAfterSheetDismissal = nil
        showOnboarding = false
    }
    func quitApplication(terminate: (@MainActor () -> Void)? = nil) {
        let quit: @MainActor () -> Void = terminate ?? { NSApp.terminate(nil) }
        addGamesAfterOnboarding = false
        // AppKit can ignore terminate while a sheet is attached. Wait for SwiftUI
        // to finish dismissing it, then use the normal delegate/worker shutdown.
        guard showOnboarding || editingInput || showingRecovery else {
            let sheets = NSApp?.windows.compactMap(\.attachedSheet) ?? []
            guard !sheets.isEmpty else { quit(); return }
            for sheet in sheets {sheet.sheetParent?.endSheet(sheet)}
            DispatchQueue.main.async {quit()}
            return
        }
        quitAfterSheetDismissal = quit
        showOnboarding = false
        editingInput = false
        showingRecovery = false
    }
    func applicationSheetDismissed() {
        if let quit = quitAfterSheetDismissal {
            quitAfterSheetDismissal = nil
            quit()
        }
    }
    func onboardingDismissed() {
        if quitAfterSheetDismissal != nil {applicationSheetDismissed();return}
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
        let p = NSOpenPanel(); p.title = L("添加游戏文件或扫描文件夹"); p.allowsMultipleSelection = true; p.canChooseDirectories = true; p.canChooseFiles = true
        p.allowedContentTypes = ["nsp","xci","nsz","xcz"].compactMap { UTType(filenameExtension:$0) }
        if p.runModal() == .OK { addGames(p.urls) }
    }
    func addGames(_ urls: [URL]) {
        guard importPrerequisitesReady(), !urls.isEmpty else { return }
        let libraryId = preferences.libraryId
        let prepare = prepareAfterImport
        selection = "tasks"
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
                    guard self.environmentReady else {
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
                for rec in records where rec.state=="failed" || ["backupSave","restoreSave","activateRelease","setup","clean","remove","diagnostics","prepareEngine","import","build","exportIPA","convertFiles","launch","migrate","keys","installMetal","uninstallMetal"].contains(rec.operation) {
                    if !self.deletedTaskIDs.contains(rec.id),!self.tasks.contains(where: { $0.id == rec.id }) { self.tasks.append(rec) }
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
        if operation=="catalog" {catalogWorkers+=1}
        var req: [String:Any] = ["schema":1,"taskId":id,"operation":operation,"privateRoot":privateRoot.path,"resources":resources.path,"engineDir":preferences.engineDir ?? "","library":preferences.library.isEmpty ? privateRoot.appendingPathComponent("unconfigured").path : preferences.library,"libraryId":preferences.libraryId,"developerDir":preferences.developerDir,"parentPid":ProcessInfo.processInfo.processIdentifier]
        extra.forEach { req[$0] = $1 }
        // Environment setup must remain available when an old library drive is offline.
        if ["preflight","prepareEngine","installMetal","uninstallMetal","converterStatus","conversionKeys","convertFiles"].contains(operation) {
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
                    if operation=="catalog" {self.catalogWorkers=max(0,self.catalogWorkers-1)}
                    if operation=="converterStatus" {self.checkingConverter=false}
                    self.lastWorkerEvent[id] = nil
                    if let i = self.tasks.firstIndex(where:{$0.id == id}), self.tasks[i].active {
                        self.tasks[i].state = p.terminationStatus == 130 ? "cancelled" : "interrupted"; self.tasks[i].message = "工作进程已退出。可重试并验证完成阶段。"
                        if p.terminationStatus != 130 {
                            let log=self.privateRoot.appendingPathComponent("logs/\(id)-bootstrap.log")
                            try? FileManager.default.createDirectory(at:log.deletingLastPathComponent(),withIntermediateDirectories:true)
                            try? output.errorText.write(to:log,atomically:true,encoding:.utf8)
                            self.tasks[i].diagnostics=[self.nativeDiagnostic(code:"worker_interrupted",summary:"工作进程已退出。可重试并验证完成阶段。",detail:output.errorText,logPath:log.path)]
                            self.persistTask(self.tasks[i])
                            self.errorDiagnostic=self.tasks[i].diagnostics?.last
                            self.error=self.tasks[i].message
                        }
                        if operation == "preflight" { self.failEnvironmentBootstrap(output.errorText.isEmpty ? "工作进程已退出。可重试并验证完成阶段。" : output.errorText) }
                    }
                    self.callbacks[id] = nil
                    if self.executionTask == id {
                        self.executionTask = nil
                        if !["prepareEngine","installMetal","uninstallMetal"].contains(operation) { self.startNext() }
                    }
                    if operation == "import" { self.startNext() }
                    if ["prepareEngine","installMetal","uninstallMetal"].contains(operation) { self.checkEnvironment() }
                    if visible { self.refresh() }
                }
            }
            if visible { tasks.insert(.init(id:id,operation:operation,state:"running",gameId:extra["gameId"] as? String,started:Date().timeIntervalSince1970,outputPath:extra["outputPath"] as? String,conversion:Self.decode(ConversionJob.self,extra["conversion"]),importPaths:operation == "import" ? extra["paths"] as? [String] : nil,backupId:extra["backupId"] as? String,releaseId:extra["releaseId"] as? String,libraryId:preferences.libraryId),at:0) }
            callbacks[id] = completion; processes[id] = process
            try process.run()
            if operation == "preflight" {lastWorkerEvent[id]=Date();watchEnvironmentWorker(id)}
        } catch {
            if operation=="converterStatus" {checkingConverter=false}
            if operation=="catalog" {catalogWorkers=max(0,catalogWorkers-1)}
            self.error = "无法启动本地组件：\(error.localizedDescription)"; processes[id] = nil; callbacks[id] = nil
            let diagnostic=nativeDiagnostic(code:"worker_start_failed",summary:self.error ?? "",detail:error.localizedDescription)
            self.errorDiagnostic=diagnostic
            if let i=tasks.firstIndex(where:{$0.id==id}) { tasks[i].state="failed";tasks[i].message=self.error;tasks[i].diagnostics=[diagnostic];persistTask(tasks[i]) }
            else {
                let task=TaskRecord(id:id,operation:operation,state:"failed",gameId:extra["gameId"] as? String,message:self.error,started:Date().timeIntervalSince1970,diagnostics:[diagnostic])
                tasks.insert(task,at:0);persistTask(task)
            }
            try? FileManager.default.removeItem(at:file)
            if operation == "preflight" { failEnvironmentBootstrap(error.localizedDescription) }
            DispatchQueue.main.async {
                if self.executionTask==id {self.executionTask=nil;self.startNext()}
                if operation == "import" {self.startNext()}
            }
        }
        return id
    }
    func event(_ e: [String:Any], visible: Bool) {
        guard e["schema"] as? Int == 1, let id = e["taskId"] as? String,!deletedTaskIDs.contains(id) else { return }
        if e["type"] as? String == "result",e["state"] as? String == "failed",!tasks.contains(where:{$0.id==id}) {
            tasks.insert(.init(id:id,operation:e["operation"] as? String ?? "worker",state:"failed",gameId:e["gameId"] as? String,started:(e["started"] as? NSNumber)?.doubleValue ?? Date().timeIntervalSince1970),at:0)
        }
        if lastWorkerEvent[id] != nil {lastWorkerEvent[id]=Date()}
        if e["type"] as? String == "check", tasks.contains(where:{$0.id==id && $0.operation=="preflight"}), let check=Self.decode(ToolCheck.self,e["check"]) {
            if let index=checks.firstIndex(where:{$0.id==check.id}) {checks[index]=check} else {checks.append(check)}
        }
        if let i = tasks.firstIndex(where:{$0.id == id}) {
            if e["type"] as? String == "plan",let plan=Self.decode([Milestone].self,e["milestones"]),!plan.isEmpty,plan.allSatisfy(\.valid),Set(plan.map(\.id)).count==plan.count {
                tasks[i].milestones=plan;tasks[i].milestone=nil;tasks[i].milestoneStarted=[:]
                tasks[i].done=nil;tasks[i].total=nil;tasks[i].unit=nil
            }
            if let current=e["milestone"] as? String,tasks[i].milestones?.contains(where:{$0.id==current})==true {
                tasks[i].milestone=current
                var starts=tasks[i].milestoneStarted ?? [:]
                if let incoming=e["milestoneStarted"] as? [String:Double] {starts.merge(incoming.filter{$0.value.isFinite}){_,new in new}}
                if starts[current]==nil {starts[current]=Date().timeIntervalSince1970}
                tasks[i].milestoneStarted=starts
            }
            if let cached=e["milestoneCached"] as? [String] {tasks[i].milestoneCached=cached}
            if let stage=e["stage"] as? String {tasks[i].stage=stage}
            if let index=e["stageIndex"] as? Int {tasks[i].stageIndex=index}
            if let count=e["stageCount"] as? Int {tasks[i].stageCount=count}
            if e["type"] as? String == "stage" || e["resetProgress"] as? Bool == true {tasks[i].done=nil;tasks[i].total=nil;tasks[i].unit=nil}
            if e["done"] != nil || e["total"] != nil {tasks[i].done=(e["done"] as? NSNumber)?.doubleValue;tasks[i].total=(e["total"] as? NSNumber)?.doubleValue;tasks[i].unit=e["unit"] as? String}
            if let elapsed=(e["elapsed"] as? NSNumber)?.doubleValue {tasks[i].elapsed=elapsed}
            if let msg = e["message"] as? String, !msg.isEmpty { tasks[i].message = msg }
            if let state = e["state"] as? String { tasks[i].state = state }
            if let diagnostic=Self.decode(TaskDiagnostic.self,e["diagnostic"]) {
                var records=tasks[i].diagnostics ?? []
                if let existing=records.firstIndex(where:{$0.id==diagnostic.id}) {records[existing]=diagnostic}
                else {records.append(diagnostic)}
                tasks[i].diagnostics=Array(records.suffix(24))
            }
            if let diagnostics=Self.decode([TaskDiagnostic].self,e["diagnostics"]) {tasks[i].diagnostics=diagnostics}
            if let result=e["result"] as? [String:Any] {
                if let path=result["outputPath"] as? String {tasks[i].outputPath=path}
                if let files=result["outputFiles"] as? [String] {tasks[i].outputFiles=files}
            }
        }
        if e["type"] as? String == "result" {
            let state = e["state"] as? String
            if state == "completed" { callbacks[id]?(e["result"] as? [String:Any] ?? [:]) }
            else if state == "failed" {
                errorDiagnostic=tasks.first(where:{$0.id==id})?.diagnostics?.last(where:{!$0.isWarning})
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
        executionTask = worker("launch",extra:["gameId":game.id,"gameLanguage":gameLanguage(for:game.id).rawValue])
    }
    func migrate(_ game: Game) {
        guard !executionBusy else { return }
        let p = NSOpenPanel(); p.title = L("选择原 BreathOfTheWild 构建文件夹"); p.canChooseDirectories = true; p.canChooseFiles = false
        guard p.runModal() == .OK, let url = p.url else { return }
        selection = "tasks"; executionTask = worker("migrate",extra:["gameId":game.id,"path":url.path])
    }
    func generateIPA(_ game: Game, destination: URL? = nil) {
        guard !executionBusy, queue.isEmpty else { error = "构建与游戏运行互斥，请等待当前任务结束。"; return }
        guard importPrerequisitesReady() else { return }
        guard game.buildable else { error = (game.missing ?? []).joined(separator:"\n"); return }
        let output: URL
        if let destination { output = destination }
        else {
            let panel = NSSavePanel()
            panel.title = L("生成 IPA")
            panel.message = L("生成用于 iPhone / iPad 的未签名游戏包；安装时需自行签名。")
            panel.prompt = L("生成 IPA")
            panel.allowedContentTypes = [UTType(filenameExtension:"ipa") ?? .data]
            panel.nameFieldStringValue = "LumaNX-\(game.id).ipa"
            guard panel.runModal() == .OK, let url = panel.url else { return }
            output = url
        }
        guard !executionBusy, queue.isEmpty else { return }
        selection = "tasks"
        executionTask = worker("exportIPA",extra:["gameId":game.id,"outputPath":output.path]) { result in
            self.notice = "IPA 已生成；安装到 iPhone / iPad 前需自行签名。"
            self.reveal(URL(fileURLWithPath:result["outputPath"] as? String ?? output.path))
        }
    }
    func cancel(_ task: TaskRecord) {
        if let i = tasks.firstIndex(where:{$0.id == task.id}) { tasks[i].state = "cancelling" }
        processes[task.id]?.terminate()
    }
    func retry(_ task: TaskRecord) {
        if task.operation != "convertFiles",let libraryId=task.libraryId,libraryId != preferences.libraryId {error="请切换回任务所属游戏库后重试。";return}
        if task.operation == "convertFiles",let conversion=task.conversion {startConversion(conversion);return}
        if task.operation == "import",let paths=task.importPaths {addGames(paths.map {URL(fileURLWithPath:$0)});return}
        guard let game = games.first(where:{$0.id == task.gameId}) else { return }
        if task.operation == "backupSave" { performRecovery("backupSave",game:game) }
        else if task.operation == "restoreSave" {
            if let id=task.backupId {performRecovery("restoreSave",game:game,extra:["backupId":id])}
        }
        else if task.operation == "activateRelease" {
            if let id=task.releaseId {performRecovery("activateRelease",game:game,extra:["releaseId":id])}
        }
        else if task.operation == "launch" { launch(game) }
        else if task.operation == "exportIPA" { generateIPA(game,destination:task.outputPath.map { URL(fileURLWithPath:$0) }) }
        else { enqueue(game) }
    }
    func remove(_ game: Game) { worker("remove",extra:["gameId":game.id]) { _ in self.refresh() } }
    func clean(_ game: Game, kind: String) {
        worker("clean",extra:["gameId":game.id,"kind":kind]) { result in
            if (result["retainedShared"] as? Int ?? 0)>0 {self.notice="已移除该游戏的内容登记；其他游戏仍在使用的共享文件已保留。"}
            self.refresh()
        }
    }
    func reveal(_ url: URL) { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    func persistTask(_ task: TaskRecord) {
        guard !deletedTaskIDs.contains(task.id) else {return}
        let folder=privateRoot.appendingPathComponent("jobs")
        let path=folder.appendingPathComponent(task.id+".json")
        try? FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        if let data=try? JSONEncoder().encode(task) {try? data.write(to:path,options:.atomic);try? FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:path.path)}
    }
    func canDeleteTask(_ task:TaskRecord)->Bool {
        guard let current=tasks.first(where:{$0.id==task.id}) else {return false}
        return !current.active && executionTask != current.id && processes[current.id]?.isRunning != true
    }
    func deleteTask(_ task:TaskRecord) {
        guard canDeleteTask(task),task.id.range(of:"^[A-Za-z0-9_-]+$",options:.regularExpression) != nil else {return}
        let path=privateRoot.appendingPathComponent("jobs").appendingPathComponent(task.id+".json")
        do {
            if FileManager.default.fileExists(atPath:path.path) {try FileManager.default.removeItem(at:path)}
            deletedTaskIDs.insert(task.id)
            tasks.removeAll{$0.id==task.id}
        } catch {
            errorDiagnostic=nil
            self.error="无法删除任务记录。"
        }
    }
    func nativeDiagnostic(code: String, summary: String, detail: String, logPath: String? = nil) -> TaskDiagnostic {
        let paths=[(preferences.library,"[LIBRARY]"),(privateRoot.path,"[PRIVATE]"),(preferences.engineDir ?? "","[ENGINE]"),(NSHomeDirectory(),"~")]
        return TaskDiagnostic(code:code,severity:"error",summary:TaskDiagnostic.redact(summary,paths:paths),suggestion:"检查完整应用、磁盘连接和权限后重试；查看对应日志了解工作进程退出原因。",detail:TaskDiagnostic.redact(detail,paths:paths),logPath:logPath)
    }
    var failureMessage: String {
        var message=L(error ?? "")
        if let diagnostic=errorDiagnostic {
            message += "\n\n" + L("建议处理：") + L(diagnostic.suggestion)
            message += "\n\n" + L("错误代码：") + diagnostic.code
        }
        return message
    }
    func diagnosticLogURL(_ diagnostic: TaskDiagnostic?) -> URL {
        if let path=diagnostic?.logPath {
            let url=URL(fileURLWithPath:path).resolvingSymlinksInPath()
            let roots=[privateRoot.appendingPathComponent("logs"),libraryURL.appendingPathComponent("cache")]
            if url.pathExtension == "log",roots.contains(where:{url.path.hasPrefix($0.resolvingSymlinksInPath().path+"/")}) {return url}
        }
        return privateRoot.appendingPathComponent("logs")
    }
    func copyDiagnostic(_ diagnostic: TaskDiagnostic? = nil) {
        let text=(diagnostic ?? errorDiagnostic)?.reportText ?? L(error ?? "")
        NSPasteboard.general.clearContents();NSPasteboard.general.setString(text,forType:.string)
    }
    func showFailedTask() {selection="tasks";showOnboarding=false;error=nil}
    func exportDiagnostics() {
        let p = NSSavePanel(); p.prompt = L("保存"); p.nameFieldStringValue = L("LumaNX-诊断.zip"); guard p.runModal() == .OK, let url = p.url else { return }
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
