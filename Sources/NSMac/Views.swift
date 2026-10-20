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
                HStack(spacing:10) { BrandMark(); VStack(alignment:.leading,spacing:3) { Text(Brand.name).font(.title2.bold()); Text(Brand.latinName).font(.caption.weight(.medium)).tracking(1.2).foregroundStyle(.secondary) } }.padding(.top,16).padding(.leading,4)
                List(selection:$store.selection) {
                    Label("游戏库",systemImage:"square.grid.2x2").tag("library")
                    Label("准备任务",systemImage:"arrow.triangle.2.circlepath").badge(store.tasks.filter(\.active).count + store.queue.count).tag("tasks")
                    Label("设置",systemImage:"gearshape").tag("settings")
                }.listStyle(.sidebar).scrollContentBackground(.hidden)
                VStack(alignment:.leading,spacing:6) {
                    Label(store.executionBusy ? "任务进行中" : "本地运行",systemImage:store.executionBusy ? "circle.dotted" : "checkmark.shield")
                    Text("游戏与密钥由玩家自行导入").font(.caption).foregroundStyle(.secondary)
                    Text("LumaDock · 0.2").font(.caption2).foregroundStyle(.tertiary)
                }.font(.caption).padding(12).frame(maxWidth:.infinity,alignment:.leading).glassSurface(16).padding(.bottom,16)
            }.padding(.horizontal,12).navigationSplitViewColumnWidth(min:205,ideal:225,max:270)
        } detail: {
            Group {
                switch store.selection {
                case "tasks": TasksView()
                case "settings": SettingsView()
                default: library
                }
            }.background(LibraryBackdrop()).navigationTitle(store.selection=="tasks" ? "准备任务" : store.selection=="settings" ? "设置" : "游戏库")
                .toolbar {
                    ToolbarItemGroup(placement:.primaryAction) {
                        Button(action:store.chooseGames){Label(store.importActionTitle,systemImage:"plus")}.help("先检查环境、选择游戏库并导入 prod.keys，再添加 NSP（⌘O）")
                        Button {store.inputGame=nil;store.editingInput=true} label:{Label("输入映射",systemImage:"keyboard")}.help("设置全局键鼠与手柄映射")
                    }
                }
        }
        .frame(minWidth:1000,minHeight:700)
        .onAppear {store.checkEnvironment()}
        .sheet(isPresented:$store.showOnboarding,onDismiss:store.onboardingDismissed) { OnboardingView().environmentObject(store).interactiveDismissDisabled(!store.preferences.onboardingComplete) }
        .sheet(isPresented:$store.editingInput) { InputEditor(game:store.inputGame, initial:store.input(for:store.inputGame)).environmentObject(store) }
        .alert("操作未完成",isPresented:Binding(get:{!store.showOnboarding && store.error != nil},set:{if !$0 && !store.showOnboarding {store.error=nil}})) { Button("知道了") { store.error=nil }; Button("打开日志") {store.reveal(store.privateRoot.appendingPathComponent("logs"))} } message: {Text(store.error ?? "")}
        .overlay(alignment:.bottom) { if let notice = store.notice { HStack { Image(systemName:"checkmark.circle.fill").foregroundStyle(Brand.accent); Text(notice); Button {store.notice=nil} label:{Image(systemName:"xmark")}.buttonStyle(.plain).accessibilityLabel("关闭提示") }.padding().glassSurface().padding().onAppear {DispatchQueue.main.asyncAfter(deadline:.now()+6){store.notice=nil}} } }
    }
    var library: some View {
        HStack(spacing:16) {
            VStack(alignment:.leading,spacing:18) {
                VStack(alignment:.leading,spacing:6) { Text("随时，开启下一段旅程。").font(.system(size:26,weight:.bold)); Text("让喜爱的游戏，在 Mac 上继续。").foregroundStyle(.secondary) }.padding(.top,8)
                ImportFlowView()
                GlassEffectContainer(spacing:16) {
                    HStack(spacing:12) {
                        LibraryStat(title:"款游戏",value:store.games.count,symbol:"square.stack.3d.up")
                        LibraryStat(title:"可启动",value:store.games.filter{$0.ready==true}.count,symbol:"play.fill")
                        Spacer(minLength:0)
                    }
                }
                HStack(spacing:10) { Image(systemName:"magnifyingglass").foregroundStyle(.secondary); TextField("搜索游戏或 Title ID",text:$search).textFieldStyle(.plain).accessibilityLabel("搜索游戏") }.padding(12).glassSurface(14)
                if store.games.isEmpty {
                    VStack(spacing:16) {
                        BrandMark(size:104)
                        Text("收藏你的第一段旅程").font(.title2.bold())
                        Text(!store.environmentReady ? "先检查系统、Xcode 与 Metal 组件，\n再选择游戏库、导入密钥和游戏。" : store.hasImportedKeys ? "密钥已就绪，添加支持版本的 NSP。\n文件齐全后自动准备，完成后点击启动。" : "先选择游戏库并导入 prod.keys，\n再添加游戏、准备运行文件。").font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                        Button(action:store.chooseGames){Label(store.importActionTitle,systemImage:store.hasImportedKeys ? "plus" : "key")}.buttonStyle(.glassProminent).controlSize(.large)
                        Text("游戏、密钥与固件均需自行提供").font(.caption).foregroundStyle(.tertiary)
                    }.frame(maxWidth:.infinity,maxHeight:.infinity)
                } else {
                    List(selection:$store.selectedGame) {
                        ForEach(store.games.filter {search.isEmpty || $0.name.localizedCaseInsensitiveContains(search) || $0.id.contains(search)}) { game in
                            HStack(spacing:16) {
                                GameCover(game:game).frame(width:76,height:76).clipShape(RoundedRectangle(cornerRadius:12)).accessibilityHidden(true)
                                VStack(alignment:.leading,spacing:8) {
                                    Text(game.name).font(.headline).lineLimit(2)
                                    Text(game.display.isEmpty ? "版本待识别" : game.display).font(.caption).foregroundStyle(.secondary)
                                    Text(game.compatibilityName).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName:game.ready == true ? "checkmark.circle.fill" : "arrow.down.circle").foregroundStyle(game.ready == true ? .teal : .secondary)
                            }.padding(12).padding(.vertical,3).tag(game.id).listRowSeparator(.hidden)
                        }
                        if !search.isEmpty && !store.games.contains(where:{ $0.name.localizedCaseInsensitiveContains(search) || $0.id.contains(search) }) {
                            ContentUnavailableView.search(text:search)
                        }
                    }.listStyle(.inset).scrollContentBackground(.hidden)

                }
            }.frame(minWidth:390)
            if let game = store.selected {GameDetail(game:game).frame(width:320).contentCard(22)}
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
                ForEach(Array(["环境","游戏库","密钥","游戏","准备","启动"].enumerated()),id:\.offset) { i,title in
                    HStack(spacing:4) {
                        Image(systemName:i<current ? "checkmark.circle.fill" : "\(i+1).circle")
                        Text(title).lineLimit(1)
                    }.foregroundStyle(i<=current ? Brand.accent : Color.secondary)
                    if i<5 {Image(systemName:"chevron.right").font(.system(size:9)).foregroundStyle(.tertiary)}
                }
            }.font(.caption.weight(.medium))
            if !store.environmentReady || !store.hasImportedKeys {
                HStack {
                    Text(store.environmentReady ? "先导入 prod.keys，才能读取和添加游戏。" : "先完成环境检查和安装，再导入玩家内容。").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button("继续设置",action:store.openOnboarding).font(.caption)
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
    var body:some View {
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
            if game.compatibility=="startup" {Text("已验证启动；完整游戏流程仍需玩家验证。").font(.caption).foregroundStyle(.secondary)}
            if game.compatibility=="experimental" {Text("已有引擎配置，尚未完成 Mac 实机验收。").font(.caption).foregroundStyle(.secondary)}
            if game.needsPreparation==true {Text("新增内容尚未准备；启动将使用上次成功版本。").font(.caption).foregroundStyle(.orange)}
            if game.ready==true {
                Button {store.launch(game)} label:{Label("启动游戏",systemImage:"play.fill").frame(maxWidth:.infinity)}.buttonStyle(.glassProminent).controlSize(.large).disabled(store.executionBusy || !store.queue.isEmpty)
            }
            Button {store.enqueue(game)} label:{Label(game.ready==true ? "重新检查并准备" : "准备运行文件",systemImage:"hammer").frame(maxWidth:.infinity)}.buttonStyle(.bordered).controlSize(.large).disabled(!game.buildable)
            Button {store.inputGame=game;store.editingInput=true} label:{Label("键鼠与手柄映射",systemImage:"keyboard").frame(maxWidth:.infinity)}.buttonStyle(.bordered).controlSize(.large)
            Divider()
            ScrollView {
                VStack(alignment:.leading,spacing:12) {
                    if !(game.missing ?? []).isEmpty {
                        Label("准备条件未满足",systemImage:"exclamationmark.triangle").font(.headline).foregroundStyle(.orange)
                        ForEach(game.missing ?? [],id:\.self){Text($0).font(.caption)}
                        Divider()
                    }
                    Text("导入内容").font(.headline)
                    ForEach(game.packages){package in
                        VStack(alignment:.leading,spacing:4){
                            HStack{Text(package.kindName);Spacer();Text(package.display.isEmpty ? "v\(package.version)" : package.display)}
                            Text(package.titleId).font(.caption.monospaced()).foregroundStyle(.secondary)
                            Text(ByteCountFormatter.string(fromByteCount:package.size,countStyle:.file)).font(.caption).foregroundStyle(.secondary)
                        }.padding(10).frame(maxWidth:.infinity,alignment:.leading).background(.quaternary,in:RoundedRectangle(cornerRadius:10))
                    }
                }.frame(maxWidth:.infinity,alignment:.leading)
            }
            Divider()
            Button("在访达中查看存档") {
                let url=store.libraryURL.appendingPathComponent("saves/\(game.id)")
                try? FileManager.default.createDirectory(at:url,withIntermediateDirectories:true);store.reveal(url)
            }
            DisclosureGroup("管理游戏") {
                VStack(alignment:.leading,spacing:10) {
                    if game.id=="01007EF00011E000" {Button("迁移已有旷野之息构建…"){store.migrate(game)}}
                    Button("移出游戏库（保留文件与存档）"){store.remove(game)}
                    Button("清理构建缓存…",role:.destructive){cleanKind="cache";confirmClean=true}
                    Button("删除托管 NSP 副本…",role:.destructive){cleanKind="sources";confirmClean=true}
                }.padding(.vertical,8)
            }.disabled(store.executionBusy)
        }.padding(20)
        .alert(cleanKind=="sources" ? "删除托管 NSP 副本？" : "清理构建缓存？",isPresented:$confirmClean) {
            Button("取消",role:.cancel){}
            Button("确认清理",role:.destructive){store.clean(game,kind:cleanKind)}
        } message:{Text("仅处理托管副本；原始文件、存档和上次成功的运行版本保留。")}
    }
}
struct TasksView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack {Text("准备任务").font(.largeTitle.bold());Spacer();Button("打开日志") {store.reveal(store.privateRoot.appendingPathComponent("logs"))}}
            Text("准备队列串行执行；准备游戏时可以继续导入文件和修改映射。").foregroundStyle(.secondary)
            if store.tasks.isEmpty && store.queue.isEmpty { ContentUnavailableView("暂无任务",systemImage:"checklist",description:Text("导入后，文件齐全的游戏会自动加入准备队列；也可在详情中手动准备。")) }
            ScrollView {
                LazyVStack(spacing:14) {
                    ForEach(Array(store.queue.enumerated()),id:\.element) { i,id in HStack { Image(systemName:"clock");Text("排队 \(i+1)：\(store.games.first(where:{$0.id==id})?.name ?? id)");Spacer();Button("移出队列") {store.dequeue(id)} }.padding().background(.quaternary,in:RoundedRectangle(cornerRadius:12)) }
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
            HStack { Label(task.title,systemImage:task.state=="completed" ? "checkmark.circle.fill" : task.state=="failed" ? "exclamationmark.circle" : "circle.dotted").font(.headline); Text(store.games.first(where:{$0.id==task.gameId})?.name ?? "").lineLimit(1);Spacer();Text(task.stateName).foregroundStyle(.secondary) }
            if let stage=task.stage { Text(stage).font(.callout) }
            if task.active {
                if let index=task.stageIndex, let count=task.stageCount, count>0 { ProgressView("整体阶段 \(index)/\(count)",value:Double(max(0,index-1)),total:Double(count)).tint(.teal) }
                if let total=task.total, let done=task.done, total>0 {
                    ProgressView(value:min(done,total),total:total).tint(.teal)
                    HStack {Text(task.unit=="B" ? "\(ByteCountFormatter.string(fromByteCount:Int64(done),countStyle:.file)) / \(ByteCountFormatter.string(fromByteCount:Int64(total),countStyle:.file))" : "\(Int(done)) / \(Int(total))");Spacer();if let elapsed=task.elapsed, elapsed>3, done>0,done<total {Text("预计剩余 \(Int((total-done)*elapsed/done)) 秒")} }.font(.caption).foregroundStyle(.secondary)
                } else { HStack {ProgressView().controlSize(.small);Text("处理中，总量暂不可确定").font(.caption).foregroundStyle(.secondary);if let elapsed=task.elapsed {Text("\(Int(elapsed)) 秒").font(.caption.monospacedDigit())}} }
            }
            if let msg=task.message,!msg.isEmpty {Text(msg).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)}
            HStack {Spacer();if task.active {Button(task.operation=="launch" ? "结束游戏" : "取消任务") {store.cancel(task)}.disabled(task.state=="cancelling")} else if ["failed","interrupted","cancelled"].contains(task.state),task.gameId != nil {Button("重试") {store.retry(task)}.disabled(store.executionBusy)} }
        }.padding(18).contentCard(18)
    }
}
struct SettingsView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        Form {
            Section("游戏库与玩家数据") {
                LabeledContent("存储位置",value:store.preferences.library.isEmpty ? "未选择" : store.preferences.library).textSelection(.enabled)
                Button("选择或切换游戏库…",action:store.chooseLibrary).disabled(store.executionBusy)
                LabeledContent("玩家密钥",value:store.keyStatus);Button("导入 prod.keys…",action:store.importKeys).disabled(store.importingKeys)
                Text("先准备环境，再选择游戏库、导入密钥和游戏。密钥通常只需导入一次，可供多款游戏共用；仅保存在本机私有目录，不随诊断包导出。").font(.caption).foregroundStyle(.secondary)
                Toggle("导入后自动准备支持的游戏",isOn:Binding(get:{store.prepareAfterImport},set:{store.prepareAfterImport=$0}))
                Text("仅将本体、所需更新及构建标识均匹配的游戏加入队列。准备完成后由你点击启动。").font(.caption).foregroundStyle(.secondary)
            }
            Section("Apple 工具链") {
                TextField("Xcode Developer 目录",text:$store.preferences.developerDir).onSubmit {store.savePreferences();store.checkEnvironment()}
                ToolChecks()
                ToolchainActions()
                Text("首次安装需完整 Xcode。打开 Xcode 并完成许可及初始组件安装，再安装 Metal 编译组件。").font(.caption).foregroundStyle(.secondary)
            }
            Section("控制与诊断") {
                Button("设置全局键鼠与手柄映射") {store.inputGame=nil;store.editingInput=true}
                Button("导出诊断包…",action:store.exportDiagnostics)
                Button("重新打开首次运行向导",action:store.openOnboarding)
            }
            Section("关于璃游") {
                LabeledContent("璃游 LumaDock",value:Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "开发版本")
                Text("独立的社区启动器。基于 nxnative；与 Nintendo 无隶属或认可关系。").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Link("上游 nxnative",destination:URL(string:"https://github.com/seedds/nxnative")!)
                    Button("开源许可与版权说明"){store.reveal(store.resources.appendingPathComponent("docs/第三方许可.md"))}
                }
            }
        }.formStyle(.grouped).navigationTitle("设置").onAppear {store.checkEnvironment()}
    }
}
struct ToolChecks: View {
    @EnvironmentObject var store: Store
    var body: some View { ForEach(store.checks) { c in HStack(alignment:.top) {Image(systemName:c.ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill").foregroundStyle(c.ok ? .teal : .orange);VStack(alignment:.leading) {Text(c.name);Text(c.message).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)}} } }
}
struct ToolchainActions: View {
    @EnvironmentObject var store:Store
    @State private var confirmUninstall = false
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            HStack {
                Button("在 App Store 获取 Xcode",action:store.openXcodeStore)
                Button("重新检查") {store.savePreferences();store.checkEnvironment()}.disabled(store.checkingEnvironment || store.executionBusy)
            }
            HStack {
                Button("安装 Metal 编译组件") {store.manageMetal(remove:false)}
                    .disabled(!store.canManageToolchain || !store.xcodeInstalled || store.metalInstalled)
                Button("卸载 Metal 编译组件…",role:.destructive) {confirmUninstall=true}
                    .disabled(!store.canManageToolchain || !store.metalInstalled || !store.canUninstallMetal)
                    .help(store.canUninstallMetal ? "卸载 Apple 管理的共享组件，可重新安装" : "当前 Xcode 不支持命令行卸载组件")
            }
            if let task=store.tasks.first(where:{$0.id==store.executionTask && ["installMetal","uninstallMetal"].contains($0.operation)}) {
                HStack {ProgressView().controlSize(.small);Text(task.title).font(.caption)}
            }
        }
        .alert("卸载 Metal 编译组件？",isPresented:$confirmUninstall) {
            Button("取消",role:.cancel) {}
            Button("卸载组件",role:.destructive) {store.manageMetal(remove:true)}
        } message: {
            Text("这是 Xcode 管理的共享组件，卸载也会影响其他使用它的项目。卸载后无法准备或重新编译游戏，可随时重新安装。游戏文件、密钥和存档会保留。")
        }
    }
}
struct EnvironmentSetupView: View {
    @EnvironmentObject var store:Store
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Text("先准备 Mac 运行环境。需要 Apple Silicon、macOS 26 或更新系统、完整 Xcode 和 Metal 编译组件。检查通过后再导入玩家内容。").foregroundStyle(.secondary)
            if store.checkingEnvironment {ProgressView("正在检查运行环境…").controlSize(.small)}
            ToolChecks()
            Divider()
            Text("缺少环境时，按以下顺序安装：").font(.headline)
            Text("1. 获取完整 Xcode，打开一次，完成许可与初始组件安装。\n2. 在下方填写 Xcode 的 Developer 目录并重新检查。\n3. 缺少 Metal 时点击安装；其余构建依赖已随应用提供。").font(.callout).foregroundStyle(.secondary)
            TextField("Xcode Developer 目录",text:$store.preferences.developerDir).textFieldStyle(.roundedBorder)
                .onChange(of:store.preferences.developerDir) { _,_ in store.checks=[] }
                .onSubmit {store.savePreferences();store.checkEnvironment()}
            ToolchainActions()
            if store.environmentReady {Label("环境已就绪，可以继续选择游戏库。",systemImage:"checkmark.circle.fill").foregroundStyle(.teal)}
        }
    }
}
struct OnboardingView: View {
    @EnvironmentObject var store: Store
    private var step:Int { store.onboardingStep }
    let titles=["检查并安装环境","选择游戏库","导入 prod.keys","添加游戏"]
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack(spacing:16) {
                BrandMark(size:64)
                VStack(alignment:.leading,spacing:5) {
                    Text("欢迎使用璃游").font(.largeTitle.bold())
                    Text("先准备环境，再导入密钥和游戏。").foregroundStyle(.secondary)
                }
            }
            HStack {
                ForEach(0..<4) { i in
                    HStack {
                        Text("\(i+1)").font(.caption.bold()).frame(width:24,height:24).background(i<=step ? Color.teal : Color.secondary.opacity(0.2),in:Circle()).foregroundStyle(i<=step ? .white : .secondary)
                        Text(titles[i]).font(.caption)
                        if i<3 {Image(systemName:"chevron.right").foregroundStyle(.tertiary)}
                    }
                }
            }
            Divider()
            Text(titles[step]).font(.title2.bold())
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    if step==0 {
                        EnvironmentSetupView()
                    } else if step==1 {
                        Text("游戏文件会复制到此位置，支持外置硬盘。请为大型游戏预留充足空间。璃游不附带游戏、密钥或固件，所有内容均由玩家自行导入。").foregroundStyle(.secondary)
                        Button("选择游戏库文件夹…",action:store.chooseLibrary).buttonStyle(.borderedProminent).tint(.teal)
                        Text(store.preferences.library.isEmpty ? "尚未选择" : store.preferences.library).font(.callout).textSelection(.enabled)
                    } else if step==2 {
                        Text("先导入 prod.keys，应用才能读取游戏内容。通常只需导入一次，多款游戏可共用这份密钥集合。").foregroundStyle(.secondary)
                        Button("导入 prod.keys…",action:store.importKeys).buttonStyle(.borderedProminent).tint(.teal).disabled(store.importingKeys)
                        if store.importingKeys {ProgressView("正在检查并导入密钥…").controlSize(.small)}
                        Label(store.keyStatus,systemImage:store.hasImportedKeys ? "checkmark.circle.fill" : "key").foregroundStyle(store.hasImportedKeys ? Color.teal : .secondary)
                        Text("导入时检查格式，首次读取游戏时验证解密能力。密钥仅保存在本机私有目录，源文件保持原样。").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Label("密钥已就绪，可以添加游戏",systemImage:"checkmark.circle.fill").foregroundStyle(.teal)
                        Text("选择支持版本的 NSP 本体、更新及可选 DLC，或扫描所在文件夹。导入时会验证密钥和文件内容，缺少版本会明确提示。").foregroundStyle(.secondary)
                        Toggle("导入后自动准备支持的游戏",isOn:Binding(get:{store.prepareAfterImport},set:{store.prepareAfterImport=$0}))
                        Text("文件齐全后加入准备队列；完成后由你点击“启动游戏”。可在设置中关闭自动准备。").font(.caption).foregroundStyle(.secondary)
                        Label("环境检查已通过，导入后会再次检查准备条件。",systemImage:"checkmark.shield").font(.caption).foregroundStyle(.secondary)
                    }
                }.frame(maxWidth:.infinity,alignment:.leading)
            }
            Spacer()
            Divider()
            HStack {
                if step>0 {Button("上一步"){store.onboardingStep-=1}}
                if step==3 {Button("稍后添加"){store.finishOnboarding(addGames:false)}}
                else if store.preferences.onboardingComplete {Button("关闭"){store.showOnboarding=false}}
                Spacer()
                Button(step==3 ? "添加游戏…" : "继续") {
                    if step<3 {store.onboardingStep+=1}
                    else {store.finishOnboarding(addGames:true)}
                }.buttonStyle(.borderedProminent).tint(.teal).disabled(!store.environmentReady || step==1 && store.preferences.library.isEmpty || step>=2 && (!store.hasImportedKeys || store.importingKeys))
            }
        }.padding(32).frame(width:780,height:600).background(LibraryBackdrop())
        .onAppear {if store.checks.isEmpty && !store.checkingEnvironment {store.checkEnvironment()}}
        .onChange(of:store.hasImportedKeys) { _,ready in if !ready && step==3 {store.onboardingStep=2} }
        .alert("操作未完成",isPresented:Binding(get:{store.error != nil},set:{if !$0 {store.error=nil}})) {
            Button("知道了") {store.error=nil}
            Button("打开日志") {store.reveal(store.privateRoot.appendingPathComponent("logs"))}
        } message:{Text(store.error ?? "")}
    }
}
