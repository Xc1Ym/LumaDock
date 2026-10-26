import SwiftUI
import AppKit
import UniformTypeIdentifiers

final class DroppedURLs: @unchecked Sendable {
    private let lock=NSLock();private var urls:[URL]=[]
    func append(_ u:URL){lock.lock();urls.append(u);lock.unlock()}
    func result()->[URL]{lock.lock();defer{lock.unlock()};return urls}
}
struct ContentView: View {
    @EnvironmentObject var store: Store
    @State private var search = ""
    var body: some View {
        NavigationSplitView {
            VStack(alignment:.leading,spacing:20) {
                HStack(spacing:10) { BrandMark(); VStack(alignment:.leading,spacing:3) { Text(Brand.name).font(.title2.bold()); Text(L("Mac 游戏启动器")).font(.caption.weight(.medium)).tracking(1.2).foregroundStyle(.secondary) } }.padding(.top,16).padding(.leading,4)
                List(selection:$store.selection) {
                    Label(L("游戏库"),systemImage:"square.grid.2x2").tag("library")
                    Label(L("文件转换"),systemImage:"doc.zipper").tag("conversion")
                    Label(L("准备任务"),systemImage:"arrow.triangle.2.circlepath").badge(store.tasks.filter(\.active).count + store.queue.count).tag("tasks")
                    Label(L("设置"),systemImage:"gearshape").tag("settings")
                }.listStyle(.sidebar).scrollContentBackground(.hidden)
                VStack(alignment:.leading,spacing:6) {
                    Label(store.executionBusy ? L("任务进行中") : L("本地运行"),systemImage:store.executionBusy ? "circle.dotted" : "checkmark.shield")
                    Text(L("游戏与密钥由玩家自行导入")).font(.caption).foregroundStyle(.secondary)
                    Text("LumaDock · " + (Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "0.2.7")).font(.caption2).foregroundStyle(.tertiary)
                }.font(.caption).padding(12).frame(maxWidth:.infinity,alignment:.leading).glassSurface(16).padding(.bottom,16)
            }.padding(.horizontal,12).navigationSplitViewColumnWidth(min:205,ideal:225,max:270)
        } detail: {
            Group {
                switch store.selection {
                case "conversion": ConversionView()
                case "tasks": TasksView()
                case "settings": SettingsView()
                default: library
                }
            }
                .safeAreaInset(edge:.bottom,spacing:0) {
                    if !store.showOnboarding,store.selection != "tasks",!store.activeTasks.isEmpty {
                        ActiveTaskBanner()
                    }
                }
                .background(LibraryBackdrop())
                .navigationTitle(store.selection=="conversion" ? L("文件转换") : store.selection=="tasks" ? L("准备任务") : store.selection=="settings" ? L("设置") : L("游戏库"))
                .toolbar {
                    ToolbarItemGroup(placement:.primaryAction) {
                        Button(action:store.chooseGames){Label(L(store.importActionTitle),systemImage:"plus")}.help(L("先检查环境、选择游戏库并导入 prod.keys，再添加游戏（⌘O）"))
                    }
                }
        }
        .frame(minWidth:1100,minHeight:720)
        .onAppear {store.checkEnvironmentAtStartup()}
        .sheet(isPresented:$store.showOnboarding,onDismiss:store.onboardingDismissed) { OnboardingView().environmentObject(store) }
        .sheet(isPresented:$store.editingInput) { InputEditor(game:store.inputGame, initial:store.input(for:store.inputGame)).environmentObject(store) }
        .alert(L("操作未完成"),isPresented:Binding(get:{!store.showOnboarding && store.error != nil},set:{if !$0 && !store.showOnboarding {store.error=nil}})) {
            let diagnostic=store.errorDiagnostic
            Button(L("知道了"),role:.cancel) {store.error=nil}
            if let diagnostic {
                Button(L("查看失败任务")) {store.showFailedTask()}
                Button(L("复制错误摘要")) {store.copyDiagnostic(diagnostic)}
            } else {Button(L("打开日志")) {store.reveal(store.diagnosticLogURL(nil))}}
        } message: {Text(store.failureMessage)}
        .overlay(alignment:.top) { if let notice = store.notice { HStack { Image(systemName:"checkmark.circle.fill").foregroundStyle(Brand.accent); Text(L(notice)); Button {store.notice=nil} label:{Image(systemName:"xmark")}.buttonStyle(.plain).accessibilityLabel(L("关闭提示")) }.padding().glassSurface().padding().onAppear {DispatchQueue.main.asyncAfter(deadline:.now()+6){store.notice=nil}} } }
    }
    var library: some View {
        HStack(spacing:16) {
            VStack(alignment:.leading,spacing:18) {
                VStack(alignment:.leading,spacing:6) { Text(L("随时，开启下一段旅程。")).font(.system(size:26,weight:.bold)); Text(L("让喜爱的游戏，在 Mac 上继续。")).foregroundStyle(.secondary) }.padding(.top,8)
                if store.refreshingLibrary {ProgressView(L("正在读取游戏库…")).progressViewStyle(.linear)}
                ImportFlowView()
                GlassEffectContainer(spacing:16) {
                    HStack(spacing:12) {
                        LibraryStat(title:L("款游戏"),value:store.games.count,symbol:"square.stack.3d.up")
                        LibraryStat(title:L("可启动"),value:store.games.filter{$0.ready==true}.count,symbol:"play.fill")
                        Spacer(minLength:0)
                    }
                }
                HStack(spacing:10) { Image(systemName:"magnifyingglass").foregroundStyle(.secondary); TextField(L("搜索游戏或 Title ID"),text:$search).textFieldStyle(.plain).accessibilityLabel(L("搜索游戏")) }.padding(12).glassSurface(14)
                if store.games.isEmpty {
                    VStack(spacing:16) {
                        BrandMark(size:104)
                        Text(L("收藏你的第一段旅程")).font(.title2.bold())
                        Text(!store.environmentReady ? L("先检查系统、Xcode 与 Metal 组件，\n再选择游戏库、导入密钥和游戏。") : store.hasImportedKeys ? L("添加 NSP、XCI、NSZ 或 XCZ 游戏文件。\n压缩文件自动解压，文件齐全后自动准备。") : L("先选择游戏库并导入 prod.keys，\n再添加游戏、准备运行文件。")).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                        Button(action:store.chooseGames){Label(L(store.importActionTitle),systemImage:store.hasImportedKeys ? "plus" : "key")}.buttonStyle(.glassProminent).controlSize(.large)
                        Text(L("游戏、密钥与固件均需自行提供")).font(.caption).foregroundStyle(.tertiary)
                    }.frame(maxWidth:.infinity,maxHeight:.infinity)
                } else {
                    List(selection:$store.selectedGame) {
                        ForEach(store.games.filter {search.isEmpty || $0.name.localizedCaseInsensitiveContains(search) || $0.id.contains(search)}) { game in
                            HStack(spacing:16) {
                                GameCover(game:game).frame(width:76,height:76).clipShape(RoundedRectangle(cornerRadius:12)).accessibilityHidden(true)
                                VStack(alignment:.leading,spacing:8) {
                                    Text(game.name).font(.headline).lineLimit(2)
                                    Text(game.display.isEmpty ? L("版本待识别") : game.display).font(.caption).foregroundStyle(.secondary)
                                    Text(game.compatibilityName).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName:game.ready == true ? "checkmark.circle.fill" : "arrow.down.circle").foregroundStyle(game.ready == true ? .teal : .secondary)
                            }.padding(12).padding(.vertical,3).tag(game.id).listRowSeparator(.hidden)
                        }
                        if !search.isEmpty && !store.games.contains(where:{ $0.name.localizedCaseInsensitiveContains(search) || $0.id.contains(search) }) {
                            ContentUnavailableView.search(text:search)
                        }
                    }.id(Localization.language).listStyle(.inset).scrollContentBackground(.hidden)

                }
            }.frame(minWidth:390)
            if let game = store.selected {GameDetail(game:game).frame(width:360).contentCard(22)}
        }.padding(24).onDrop(of:[UTType.fileURL],isTargeted:nil) { providers in
            let group=DispatchGroup();let urls=DroppedURLs();for provider in providers {group.enter();_ = provider.loadObject(ofClass:URL.self){url,_ in if let url{urls.append(url)};group.leave()}};group.notify(queue:.main){store.addGames(urls.result())};return true
        }
    }
}
struct ImportFlowView: View {
    @EnvironmentObject var store:Store
    private var current:Int {
        if !store.environmentReady { return 0 }
        if store.preferences.library.isEmpty { return 1 }
        if !store.hasImportedKeys { return 2 }
        if store.games.isEmpty { return 3 }
        return store.selected?.ready == true ? 5 : 4
    }
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            HStack(spacing:5) {
                ForEach(Array([L("环境"),L("游戏库"),L("密钥"),L("游戏"),L("准备"),L("启动")].enumerated()),id:\.offset) { i,title in
                    HStack(spacing:4) {
                        Image(systemName:i<current ? "checkmark.circle.fill" : "\(i+1).circle")
                        Text(L(title)).lineLimit(1)
                    }.foregroundStyle(i<=current ? Brand.accent : Color.secondary)
                    if i<5 {Image(systemName:"chevron.right").font(.system(size:9)).foregroundStyle(.tertiary)}
                }
            }.font(.caption.weight(.medium))
            if !store.environmentReady || !store.hasImportedKeys {
                HStack {
                    Text(store.environmentReady ? L("先导入 prod.keys，才能读取和添加游戏。") : L("先完成环境检查和安装，再导入玩家内容。")).font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button(L("继续设置"),action:store.openOnboarding).font(.caption)
                }
            }
        }.padding(12).frame(maxWidth:.infinity,alignment:.leading).glassSurface(14)
    }
}
struct GameCover: View {
    let game:Game
    var body:some View {
        if let path=game.cover,let ns=NSImage(contentsOfFile:path),let cg=ns.cgImage(forProposedRect:nil,context:nil,hints:nil) {
            Image(decorative:cg,scale:1).resizable().scaledToFit()
        } else {ZStack{Color.teal.opacity(0.12);Image(systemName:"gamecontroller.fill").font(.system(size:36)).foregroundStyle(.teal)}}
    }
}
struct GameDetail: View {
    @EnvironmentObject var store:Store
    let game:Game
    @State private var cleanKind="cache"
    @State private var confirmClean=false
    @State private var showingRecovery=false
    var body:some View {
        ScrollView {
        VStack(alignment:.leading,spacing:14) {
            HStack(alignment:.top,spacing:12) {
                GameCover(game:game).frame(width:76,height:76).clipShape(RoundedRectangle(cornerRadius:12)).accessibilityHidden(true)
                VStack(alignment:.leading,spacing:6) {
                    Text(game.name).font(.headline).lineLimit(3).fixedSize(horizontal:false,vertical:true)
                    Text(game.display).font(.callout).foregroundStyle(.secondary)
                    Text(game.compatibilityName).font(.caption.bold()).foregroundStyle(.orange)
                }
            }
            Text(game.id).font(.caption.monospaced()).foregroundStyle(.secondary)
            if game.needsPreparation==true {Text(L("新增内容或引擎更新尚未准备；启动将使用上次成功版本。")).font(.caption).foregroundStyle(.orange)}
            GameLanguagePicker(gameId:game.id)
            Text(L("下次启动生效，无需重新准备。所选语言需游戏自身支持。")).font(.caption).foregroundStyle(.secondary)
            if game.ready==true {
                LabeledContent(L("当前运行版本"),value:game.runtimeVersion?.isEmpty == false ? game.runtimeVersion! : L("版本待识别"))
                Button {store.launch(game)} label:{Label(L("启动游戏"),systemImage:"play.fill").frame(maxWidth:.infinity)}.buttonStyle(.glassProminent).controlSize(.large).disabled(store.executionBusy || !store.queue.isEmpty)
            }
            Button {store.enqueue(game)} label:{Label(game.ready==true ? L("重新检查并准备") : L("准备运行文件"),systemImage:"hammer").frame(maxWidth:.infinity)}.buttonStyle(.bordered).controlSize(.large).disabled(!game.buildable)
            Button {store.generateIPA(game)} label:{Label(L("生成 IPA…"),systemImage:"iphone.and.arrow.forward").frame(maxWidth:.infinity)}.buttonStyle(.bordered).controlSize(.large).disabled(!game.buildable || store.executionBusy || !store.queue.isEmpty)
                .help(L("导出 iPhone / iPad 未签名包；需 Xcode iOS 平台及 XcodeGen。"))
            Button {store.inputGame=game;store.editingInput=true} label:{Label(L("键鼠与手柄映射"),systemImage:"keyboard").frame(maxWidth:.infinity)}.buttonStyle(.bordered).controlSize(.large)
            Divider()
                VStack(alignment:.leading,spacing:8) {
                    if !(game.missing ?? []).isEmpty {
                        Label(L("准备条件未满足"),systemImage:"exclamationmark.triangle").font(.headline).foregroundStyle(.orange)
                        ForEach(game.missing ?? [],id:\.self){Text(L($0)).font(.caption)}
                        Text(L("当前 nxnative 配置要求指定版本及着色器素材；这与 DLC 或本体是否完整无关。")).font(.caption).foregroundStyle(.secondary)
                        Divider()
                    }
                    Text(L("导入内容")).font(.subheadline.bold())
                    ForEach(game.packages){package in
                        VStack(alignment:.leading,spacing:3){
                            HStack(spacing:8){
                                Text(package.kindName).font(.subheadline.weight(.medium))
                                Spacer(minLength:8)
                                Text(package.display.isEmpty ? "v\(package.version)" : package.display).font(.caption.monospacedDigit())
                            }
                            HStack(spacing:8){
                                Text(package.titleId).font(.caption2.monospaced()).textSelection(.enabled)
                                Spacer(minLength:8)
                                Text(ByteCountFormatter.string(fromByteCount:package.size,countStyle:.file)).font(.caption2).fixedSize()
                            }.foregroundStyle(.secondary)
                        }.padding(.horizontal,10).padding(.vertical,7).frame(maxWidth:.infinity,alignment:.leading).background(.quaternary,in:RoundedRectangle(cornerRadius:8))
                    }
                }.frame(maxWidth:.infinity,alignment:.leading)
                .id(Localization.language)
            Divider()
            Button(L("存档备份与版本回滚…")) {showingRecovery=true}
            Button(L("在访达中查看存档")) {
                let url=store.libraryURL.appendingPathComponent("saves/\(game.id)")
                try? FileManager.default.createDirectory(at:url,withIntermediateDirectories:true);store.reveal(url)
            }
            DisclosureGroup(L("管理游戏")) {
                VStack(alignment:.leading,spacing:10) {
                    if game.id=="01007EF00011E000" {Button(L("迁移已有旷野之息构建…")){store.migrate(game)}}
                    Button(L("移出游戏库（保留文件与存档）")){store.remove(game)}
                    Button(L("清理构建缓存…"),role:.destructive){cleanKind="cache";confirmClean=true}
                    Button(L("删除托管 NSP 副本…"),role:.destructive){cleanKind="sources";confirmClean=true}
                }.padding(.vertical,8)
            }.disabled(store.executionBusy)
        }.padding(20)
        }
        .sheet(isPresented:$showingRecovery) {GameRecoveryView(game:game).environmentObject(store)}
        .alert(cleanKind=="sources" ? L("删除托管 NSP 副本？") : L("清理构建缓存？"),isPresented:$confirmClean) {
            Button(L("取消"),role:.cancel){}
            Button(L("确认清理"),role:.destructive){store.clean(game,kind:cleanKind)}
        } message:{Text(L("仅处理托管副本；原始文件、存档和上次成功的运行版本保留。其他游戏仍在引用的共享文件会保留。"))}
    }
}
struct TasksView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack {Text(L("准备任务")).font(.largeTitle.bold());Spacer();Button(L("打开日志")) {store.reveal(store.privateRoot.appendingPathComponent("logs"))}}
            Text(L("准备队列串行执行；准备游戏时可以继续导入文件和修改映射。")).foregroundStyle(.secondary)
            if store.tasks.isEmpty && store.queue.isEmpty { ContentUnavailableView(L("暂无任务"),systemImage:"checklist",description:Text(L("导入后，文件齐全的游戏会自动加入准备队列；也可在详情中手动准备。"))) }
            ScrollView {
                LazyVStack(spacing:14) {
                    ForEach(Array(store.queue.enumerated()),id:\.element) { i,id in HStack { Image(systemName:"clock");Text(L("排队 \(i+1)：\(store.games.first(where:{$0.id==id})?.name ?? id)"));Spacer();Button(L("移出队列")) {store.dequeue(id)} }.padding().background(.quaternary,in:RoundedRectangle(cornerRadius:12)) }
                    ForEach(store.tasks) { task in TaskCard(task:task) }
                }
            }
        }.padding(28)
    }
}
struct TaskCard: View {
    @EnvironmentObject var store: Store
    let task: TaskRecord
    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack { Label(task.title,systemImage:task.state=="failed" || task.hasWarnings ? "exclamationmark.triangle.fill" : task.state=="completed" ? "checkmark.circle.fill" : "circle.dotted").font(.headline); Text(store.games.first(where:{$0.id==task.gameId})?.name ?? "").lineLimit(1);Spacer();Text(task.stateName).foregroundStyle(task.hasWarnings ? .orange : .secondary) }
            let milestoneLabel=task.active ? task.milestones?.first(where:{$0.id==task.milestone})?.label:nil
            if let stage=task.stage,stage != milestoneLabel { Text(L(stage)).font(.callout) }
            if task.active {TaskProgressView(task:task)}
            if let msg=task.message,!msg.isEmpty,msg != task.stage,msg != milestoneLabel,!(task.diagnostics ?? []).contains(where:{$0.summary==msg}) {Text(L(msg)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)}
            ForEach(task.diagnostics ?? []) {diagnostic in TaskDiagnosticCard(diagnostic:diagnostic)}
            if task.operation=="exportIPA",task.state=="completed",let path=task.outputPath {
                Button(L("在访达中查看 IPA")) {store.reveal(URL(fileURLWithPath:path))}
            }
            if task.operation=="convertFiles",task.state=="completed",let path=task.outputPath {
                HStack {
                    Button(L("查看转换结果")){store.reveal(URL(fileURLWithPath:path))}
                    if (task.outputFiles ?? []).contains(where:{URL(fileURLWithPath:$0).pathExtension.lowercased()=="nsp"}) {Button(L("导入生成的 NSP")){store.importConverted(task)}}
                }
            }
            HStack {Spacer();if task.active {Button(task.operation=="launch" ? L("结束游戏") : L("取消任务")) {store.cancel(task)}.disabled(task.state=="cancelling")} else if ["failed","interrupted","cancelled"].contains(task.state),task.gameId != nil || task.conversion != nil || task.importPaths != nil {Button(L("重试")) {store.retry(task)}.disabled(store.executionBusy)} }
        }.padding(18).contentCard(18)
    }
}
struct TaskDiagnosticCard: View {
    @EnvironmentObject var store: Store
    let diagnostic: TaskDiagnostic
    var body: some View {
        VStack(alignment:.leading,spacing:10) {
            Label(L(diagnostic.summary),systemImage:diagnostic.isWarning ? "exclamationmark.triangle" : "xmark.octagon")
                .font(.callout.bold()).foregroundStyle(diagnostic.isWarning ? .orange : .red)
            Text(L(diagnostic.suggestion)).font(.callout).textSelection(.enabled)
            if let stage=diagnostic.stage,!stage.isEmpty {Text(L("失败阶段：")+L(stage)).font(.caption).foregroundStyle(.secondary)}
            Text(diagnostic.code).font(.caption.monospaced()).foregroundStyle(.secondary)
            if !diagnostic.detail.isEmpty {
                DisclosureGroup(L("编译器输出（已脱敏）")) {
                    ScrollView {Text(diagnostic.detail).font(.caption.monospaced()).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading)}.frame(maxHeight:160)
                }
            }
            HStack {
                Button(L("打开对应日志")) {store.reveal(store.diagnosticLogURL(diagnostic))}
                Button(L("复制错误摘要")) {store.copyDiagnostic(diagnostic)}
            }
        }.padding(12).frame(maxWidth:.infinity,alignment:.leading)
            .background(diagnostic.isWarning ? Color.orange.opacity(0.08) : Color.red.opacity(0.06),in:RoundedRectangle(cornerRadius:10))
    }
}
struct SettingsView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        Form {
            Section(L("语言与外观")) { LanguagePicker(); AppearancePicker(); Text(L("界面语言立即生效；系统文件对话框的内置按钮跟随 macOS 语言。")).font(.caption).foregroundStyle(.secondary) }
            Section(L("游戏语言")) {
                GameLanguagePicker()
                Text(L("与界面语言独立；可在游戏详情中单独设置启动语言。下次启动生效，无需重新准备或导入固件。所选语言需游戏自身支持。")).font(.caption).foregroundStyle(.secondary)
            }
            Section(L("游戏库与玩家数据")) {
                LabeledContent(L("存储位置"),value:store.preferences.library.isEmpty ? L("未选择") : store.preferences.library).textSelection(.enabled)
                Button(L("选择或切换游戏库…"),action:store.chooseLibrary).disabled(store.executionBusy)
                LabeledContent(L("玩家密钥"),value:L(store.keyStatus));Button(L("导入 prod.keys…"),action:store.importKeys).disabled(store.importingKeys)
                Text(L("先准备环境，再选择游戏库、导入密钥和游戏。密钥通常只需导入一次，可供多款游戏共用；仅保存在本机私有目录，不随诊断包导出。")).font(.caption).foregroundStyle(.secondary)
                Toggle(L("导入后自动准备支持的游戏"),isOn:Binding(get:{store.prepareAfterImport},set:{store.prepareAfterImport=$0}))
                Text(L("仅将本体、所需更新及构建标识均匹配的游戏加入队列。准备完成后由你点击启动。")).font(.caption).foregroundStyle(.secondary)
            }
            Section(L("运行与构建环境")) {
                EngineSettingsView()
                TextField(L("Xcode Developer 目录"),text:$store.preferences.developerDir).onSubmit {store.savePreferences();store.checkEnvironment()}
                    .onChange(of:store.preferences.developerDir) {_,_ in store.checks=[]}
                EnvironmentSummary()
                ToolChecks()
                ToolchainActions()
                Text(L("准备游戏需要完整工具链；启动已准备好的游戏只需要标有“启动”的项目。首次安装请先完成全部检查。")).font(.caption).foregroundStyle(.secondary)
            }
            Section(L("控制与诊断")) {
                Button(L("设置全局键鼠与手柄映射")) {store.inputGame=nil;store.editingInput=true}
                Button(L("导出诊断包…"),action:store.exportDiagnostics)
                Button(L("重新打开首次运行向导"),action:store.openOnboarding)
            }
            Section(L("关于璃游")) {
                LabeledContent(L("璃游 LumaDock"),value:Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? L("开发版本"))
                Text(L("独立的社区启动器。基于 nxnative；与 Nintendo 无隶属或认可关系。")).font(.caption).foregroundStyle(.secondary)
                HStack {
                    Text(L("运行引擎由玩家自行提供。"))
                    Button(L("开源许可与版权说明")){store.openDocumentation(.licenses)}
                }
            }
        }.formStyle(.grouped).navigationTitle(L("设置"))
    }
}
struct ToolChecks: View {
    @EnvironmentObject var store: Store
    @State private var showPassed=false
    private let groups=[("system","Mac 与图形"),("apple","Apple 工具链"),("engine","外部引擎"),("bundled","应用内置组件"),("storage","游戏库存储")]
    var body: some View {
        let passed=store.checks.filter(\.ok)
        VStack(alignment:.leading,spacing:18) {
            checkGroups(store.checks.filter{!$0.ok})
            if !passed.isEmpty {
                DisclosureGroup(isExpanded:$showPassed) {
                    VStack(alignment:.leading,spacing:18) {checkGroups(passed)}.padding(.top,8)
                } label: {
                    Label(L("已通过的检查（\(passed.count) 项）"),systemImage:"checkmark.circle.fill")
                        .font(.callout).foregroundStyle(.teal)
                }
            }
        }.id(Localization.language)
            .onChange(of:store.checkingEnvironment) {_,checking in if checking {showPassed=false}}
    }
    @ViewBuilder private func checkGroups(_ checks:[ToolCheck])->some View {
        ForEach(groups,id:\.0) { group,title in
            let items=checks.filter {
                let key=$0.group ?? "system"
                return (groups.contains(where:{$0.0==key}) ? key : "system")==group
            }
            if !items.isEmpty {
                VStack(alignment:.leading,spacing:12) {
                    Text(L(title)).font(.headline)
                    ForEach(items) {check in EnvironmentCheckRow(check:check)}
                }
            }
        }
    }
}
struct EnvironmentCheckRow: View {
    @EnvironmentObject var store: Store
    let check: ToolCheck
    private var actionTitle:String {
        switch check.action {
        case "chooseEngine":return "选择 nxnative 目录…"
        case "prepareEngine":return "准备引擎工具"
        case "xcodeStore":return "获取 Xcode"
        case "openXcode":return "打开 Xcode 完成设置"
        case "installMetal":return "安装 Metal 编译组件"
        case "reinstall":return "下载完整应用"
        case "systemUpdate":return "打开软件更新"
        case "library":return "选择游戏库"
        default:return ""
        }
    }
    var body:some View {
        HStack(alignment:.top,spacing:10) {
            Image(systemName:check.ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill").foregroundStyle(check.ok ? .teal : .orange).padding(.top,2)
            VStack(alignment:.leading,spacing:5) {
                HStack {
                    Text(L(check.name)).fontWeight(.medium)
                    Spacer()
                    Text(L(check.required(for:"launch") ? "准备与启动" : check.required(for:"prepare") ? "准备时需要" : "首次准备工具时需要")).font(.caption2).foregroundStyle(.secondary)
                }
                Text(L(check.message)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                if let location=check.location {
                    DisclosureGroup(L("组件位置")) {
                        VStack(alignment:.leading,spacing:4) {
                            Text(L(check.group == "engine" ? "外部引擎或其私有工具缓存的当前位置。" : "随应用安装位置动态解析，以下是当前完整路径。")).font(.caption).foregroundStyle(.secondary)
                            Text(location).font(.caption.monospaced()).textSelection(.enabled)
                        }.padding(.top,4)
                    }.font(.caption)
                }
                if let help=check.help {
                    DisclosureGroup(L("安装与修复方法")) {
                        VStack(alignment:.leading,spacing:8) {
                            Text(L(help)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                            if !actionTitle.isEmpty,let action=check.action {
                                Button(L(actionTitle)){store.repairEnvironment(action)}
                                    .disabled(store.checkingEnvironment || store.executionBusy || action=="installMetal" && (!store.xcodeInitialized || store.metalInstalled) || action=="library" && !store.queue.isEmpty)
                            }
                            if let detail=check.detail,!detail.isEmpty {Text(detail).font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)}
                            if let command=check.repairCommand,!command.isEmpty {
                                Text(command).font(.caption.monospaced()).textSelection(.enabled)
                                Button(L("复制修复命令")) {
                                    NSPasteboard.general.clearContents()
                                    NSPasteboard.general.setString(command,forType:.string)
                                    store.notice="已复制修复命令，请在终端中手动执行。"
                                }
                            }
                        }.padding(.top,6)
                    }.font(.caption)
                }
            }
        }
    }
}
struct EnvironmentSummary: View {
    @EnvironmentObject var store:Store
    var body:some View {
        HStack {
            if store.checkingEnvironment {
                VStack(alignment:.leading,spacing:6) {
                    Text(L("正在逐项验证环境，请稍候…"))
                    if let task=store.tasks.first(where:{$0.operation=="preflight" && $0.active}) {TaskProgressView(task:task,compact:true)}
                    else {ProgressView().progressViewStyle(.linear)}
                }
            }
            else if store.environmentReady {Label(L("构建与启动环境均已就绪"),systemImage:"checkmark.shield.fill").foregroundStyle(.teal)}
            else if store.runtimeReady {Label(L("可启动已准备的游戏，构建环境仍需修复"),systemImage:"checkmark.circle").foregroundStyle(.secondary)}
            else {Label(L("完成环境检查后再导入游戏"),systemImage:"wrench.and.screwdriver").foregroundStyle(.secondary)}
        }.font(.callout)
    }
}
struct ToolchainActions: View {
    @EnvironmentObject var store:Store
    @State private var confirmUninstall = false
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Button(L("在 App Store 获取 Xcode"),action:store.openXcodeStore)
                Button(L("选择 Xcode.app…"),action:store.chooseXcode).disabled(store.checkingEnvironment || store.executionBusy)
                Button(L("重新检查")) {store.savePreferences();store.checkEnvironment()}.disabled(store.checkingEnvironment || store.executionBusy)
            }
            Button(L("打开 Xcode 完成设置")){store.repairEnvironment("openXcode")}.disabled(!store.xcodeInstalled)
            Button(L("环境安装说明")){store.openDocumentation(.environment)}
            HStack {
                Button(L("安装 Metal 编译组件")) {store.manageMetal(remove:false)}
                    .disabled(!store.canManageToolchain || !store.xcodeInitialized || store.metalInstalled)
                Button(L("卸载 Metal 编译组件…"),role:.destructive) {confirmUninstall=true}
                    .disabled(!store.canManageToolchain || !store.metalInstalled || !store.canUninstallMetal)
                    .help(store.canUninstallMetal ? L("卸载 Apple 管理的共享组件，可重新安装") : L("当前 Xcode 不支持命令行卸载组件"))
            }
            if let task=store.tasks.first(where:{$0.id==store.executionTask && ["installMetal","uninstallMetal"].contains($0.operation)}) {
                VStack(alignment:.leading) {Text(task.title).font(.caption);TaskProgressView(task:task,compact:true)}
            }
        }
        .alert(L("卸载 Metal 编译组件？"),isPresented:$confirmUninstall) {
            Button(L("取消"),role:.cancel) {}
            Button(L("卸载组件"),role:.destructive) {store.manageMetal(remove:true)}
        } message: {
            Text(L("这是 Xcode 管理的共享组件，卸载也会影响其他使用它的项目。卸载后无法准备或重新编译游戏，可随时重新安装。游戏文件、密钥和存档会保留。"))
        }
    }
}
struct EnvironmentSetupView: View {
    @EnvironmentObject var store:Store
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Text(L("先准备 Mac 运行环境。需要 Apple Silicon、macOS 26 或更新系统、完整 Xcode 和 Metal 编译组件。检查通过后再导入玩家内容。")).foregroundStyle(.secondary)
            EnvironmentSummary()
            EngineSettingsView()
            DisclosureGroup(L("安装其他环境")) {
                VStack(alignment:.leading,spacing:10) {
                    Text(L("1. 获取完整 Xcode，打开一次，完成许可与初始组件安装。\n2. 选择 Xcode.app 并重新检查，缺少 Metal 时点击安装。\n3. 展开每项“安装与修复方法”查看具体步骤，全部通过后继续。")).font(.callout).foregroundStyle(.secondary)
                    Text(L("Python、Python 扩展、.NET 运行时、SPIRV-Cross 和 Zstandard 随应用提供。nxnative 及其读取器、翻译器不内置；首次准备引擎工具还需要 .NET 10 SDK，安装方法见环境说明。")).font(.caption).foregroundStyle(.secondary)
                }
            }
            TextField(L("Xcode Developer 目录"),text:$store.preferences.developerDir).textFieldStyle(.roundedBorder)
                .onChange(of:store.preferences.developerDir) { _,_ in store.checks=[] }
                .onSubmit {store.savePreferences();store.checkEnvironment()}
            ToolchainActions()
            Divider()
            ToolChecks()
            if store.environmentReady {Label(L("环境已就绪，可以继续选择游戏库。"),systemImage:"checkmark.circle.fill").foregroundStyle(.teal)}
        }
    }
}
struct EngineSettingsView: View {
    @EnvironmentObject var store:Store
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            Text(L("外部 nxnative 引擎")).font(.headline)
            Text(L("应用不附带或下载 nxnative。请自行下载并解压完整源码，再选择包含 dm 和 scripts 的根目录。原目录保持不变，构建使用私有副本。")).font(.caption).foregroundStyle(.secondary)
            LabeledContent(L("nxnative 目录"),value:(store.preferences.engineDir ?? "").isEmpty ? L("未选择") : store.preferences.engineDir!).textSelection(.enabled)
            HStack {
                Button(L("选择 nxnative 目录…"),action:store.chooseEngine).disabled(!store.canManageToolchain)
                Button(L("准备引擎工具"),action:store.prepareEngine).disabled(!store.canManageToolchain || (store.preferences.engineDir ?? "").isEmpty)
            }
            if let task=store.tasks.first(where:{$0.id==store.executionTask && $0.operation=="prepareEngine"}) {
                VStack(alignment:.leading) {Text(L(task.stage ?? "准备引擎工具")).font(.caption);TaskProgressView(task:task)}
            }
        }
    }
}
struct OnboardingView: View {
    @EnvironmentObject var store: Store
    private var step:Int { store.onboardingStep }
    let titles=[L("检查并安装环境"),L("选择游戏库"),L("导入 prod.keys"),L("添加游戏")]
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack(spacing:16) {
                BrandMark(size:64)
                VStack(alignment:.leading,spacing:5) {
                    Text(L("欢迎使用璃游")).font(.largeTitle.bold())
                    Text(L("先准备环境，再导入密钥和游戏。")).foregroundStyle(.secondary)
                }
            }
            LanguagePicker().frame(maxWidth:460)
            HStack {
                ForEach(0..<4) { i in
                    HStack {
                        Text("\(i+1)").font(.caption.bold()).frame(width:24,height:24).background(i<=step ? Color.teal : Color.secondary.opacity(0.2),in:Circle()).foregroundStyle(i<=step ? .white : .secondary)
                        Text(L(titles[i])).font(.caption)
                        if i<3 {Image(systemName:"chevron.right").foregroundStyle(.tertiary)}
                    }
                }
            }.id(Localization.language)
            Divider()
            Text(L(titles[step])).font(.title2.bold())
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    if step==0 {
                        EnvironmentSetupView()
                    } else if step==1 {
                        Text(L("游戏文件会复制到此位置，支持外置硬盘。请为大型游戏预留充足空间。璃游不附带游戏、密钥或固件，所有内容均由玩家自行导入。")).foregroundStyle(.secondary)
                        Button(L("选择游戏库文件夹…"),action:store.chooseLibrary).buttonStyle(.borderedProminent).tint(.teal)
                        Text(store.preferences.library.isEmpty ? L("尚未选择") : store.preferences.library).font(.callout).textSelection(.enabled)
                    } else if step==2 {
                        Text(L("先导入 prod.keys，应用才能读取游戏内容。通常只需导入一次，多款游戏可共用这份密钥集合。")).foregroundStyle(.secondary)
                        Button(L("导入 prod.keys…"),action:store.importKeys).buttonStyle(.borderedProminent).tint(.teal).disabled(store.importingKeys)
                        if let task=store.tasks.first(where:{$0.operation=="keys" && $0.active}) {TaskProgressView(task:task,compact:true)}
                        Label(L(store.keyStatus),systemImage:store.hasImportedKeys ? "checkmark.circle.fill" : "key").foregroundStyle(store.hasImportedKeys ? Color.teal : .secondary)
                        Text(L("导入时检查格式，首次读取游戏时验证解密能力。密钥仅保存在本机私有目录，源文件保持原样。")).font(.caption).foregroundStyle(.secondary)
                    } else {
                        Label(L("密钥已就绪，可以添加游戏"),systemImage:"checkmark.circle.fill").foregroundStyle(.teal)
                        Text(L("选择支持版本的 NSP 本体、更新及可选 DLC，或扫描所在文件夹。导入时会验证密钥和文件内容，缺少版本会明确提示。")).foregroundStyle(.secondary)
                        Toggle(L("导入后自动准备支持的游戏"),isOn:Binding(get:{store.prepareAfterImport},set:{store.prepareAfterImport=$0}))
                        Text(L("文件齐全后加入准备队列；完成后由你点击“启动游戏”。可在设置中关闭自动准备。")).font(.caption).foregroundStyle(.secondary)
                        Label(L("环境检查已通过，导入后会再次检查准备条件。"),systemImage:"checkmark.shield").font(.caption).foregroundStyle(.secondary)
                    }
                }.frame(maxWidth:.infinity,alignment:.leading)
            }
            Spacer()
            Divider()
            Text(L("可稍后在设置中继续。环境检查通过后才能导入和准备游戏。"))
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button(L("退出璃游")) { store.quitApplication() }
                    .keyboardShortcut("q",modifiers:.command)
                Button(store.preferences.onboardingComplete ? L("关闭") : L("稍后设置"),action:store.deferOnboarding)
                    .keyboardShortcut(.cancelAction)
                Spacer()
                if step>0 {Button(L("上一步")){store.onboardingStep-=1}}
                if step==3 {Button(L("稍后添加")){store.finishOnboarding(addGames:false)}}
                Button(step==3 ? L("添加游戏…") : L("继续")) {
                    if step<3 {store.onboardingStep+=1}
                    else {store.finishOnboarding(addGames:true)}
                }.buttonStyle(.borderedProminent).tint(.teal).disabled(!store.environmentReady || step==1 && store.preferences.library.isEmpty || step>=2 && (!store.hasImportedKeys || store.importingKeys))
            }
        }.padding(32) .frame(width:900,height:700).background(LibraryBackdrop())
        .onAppear {store.checkEnvironmentAtStartup()}
        .onChange(of:store.hasImportedKeys) { _,ready in if !ready && step==3 {store.onboardingStep=2} }
        .alert(L("操作未完成"),isPresented:Binding(get:{store.error != nil},set:{if !$0 {store.error=nil}})) {
            let diagnostic=store.errorDiagnostic
            Button(L("知道了"),role:.cancel) {store.error=nil}
            if let diagnostic {
                Button(L("查看失败任务")) {store.showFailedTask()}
                Button(L("复制错误摘要")) {store.copyDiagnostic(diagnostic)}
            } else {Button(L("打开日志")) {store.reveal(store.diagnosticLogURL(nil))}}
        } message:{Text(store.failureMessage)}
    }
}

struct LanguagePicker: View {
    @EnvironmentObject var store: Store
    var body: some View {
        Picker(L("语言"),selection:Binding(get:{store.language},set:{store.language=$0})) {
            ForEach(AppLanguage.allCases) { language in Text(language.name).tag(language) }
        }.pickerStyle(.segmented).id("app-language-"+Localization.language)
    }
}

struct GameLanguagePicker: View {
    @EnvironmentObject var store: Store
    var gameId: String? = nil
    private var selection: Binding<String> {
        Binding(get:{
            if let gameId { return store.gameLanguageOverride(for:gameId)?.rawValue ?? "" }
            return store.defaultGameLanguage.rawValue
        },set:{ value in
            if let gameId { store.setGameLanguage(GameLanguage(rawValue:value),for:gameId) }
            else if let language=GameLanguage(rawValue:value) { store.defaultGameLanguage=language }
        })
    }
    private var picker: some View {
        Picker(L(gameId == nil ? "默认游戏语言" : "启动语言"),selection:selection) {
            if gameId != nil { Text(L("跟随默认（\(store.defaultGameLanguage.name)）")).tag("") }
            ForEach(GameLanguage.allCases) { language in Text(language.name).tag(language.rawValue) }
        }.pickerStyle(.menu).id("game-language-"+(gameId ?? "default")+"-"+Localization.language)
    }
    var body: some View {
        if gameId == nil { picker }
        else {
            HStack(spacing:10) {
                Text(L("启动语言")).font(.caption).foregroundStyle(.secondary).fixedSize()
                picker.labelsHidden().frame(minWidth:0,maxWidth:.infinity)
            }
        }
    }
}

struct AppearancePicker: View {
    @EnvironmentObject var store: Store
    var body: some View {
        Picker(L("外观"),selection:Binding(get:{store.appearance},set:{store.appearance=$0})) {
            ForEach(AppAppearance.allCases) { appearance in Text(appearance.name).tag(appearance) }
        }.pickerStyle(.segmented).id("app-appearance-"+Localization.language)
    }
}
