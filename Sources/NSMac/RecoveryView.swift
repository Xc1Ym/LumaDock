import SwiftUI

struct SaveBackup: Codable, Identifiable {
    var id: String
    var created: Double
    var reason: String
    var size: Int64
    var reasonName: String {
        switch reason {
        case "beforeRestore": return L("恢复前自动备份")
        case "beforeVersionChange": return L("版本切换前自动备份")
        default: return L("手动备份")
        }
    }
}

struct RuntimeRelease: Codable, Identifiable {
    var id: String
    var version: String
    var engine: String
    var created: Double
    var current: Bool
}

struct RecoveryReport: Codable {
    var backups: [SaveBackup]
    var releases: [RuntimeRelease]
}

extension Store {
    func loadRecovery(_ game: Game, completion: @escaping (RecoveryReport) -> Void) {
        let libraryId = preferences.libraryId
        worker("listRecovery", extra:["gameId":game.id], visible:false) { result in
            guard libraryId == self.preferences.libraryId,
                  let report = Self.decode(RecoveryReport.self,result) else { return }
            completion(report)
        }
    }

    func performRecovery(_ operation: String, game: Game, extra: [String:Any] = [:], completion: @escaping () -> Void = {}) {
        guard !executionBusy, queue.isEmpty else { error = "请先结束游戏及准备任务，再管理存档和运行版本。"; return }
        guard ["backupSave","restoreSave","activateRelease"].contains(operation) else { return }
        let libraryId = preferences.libraryId
        var request = extra
        request["gameId"] = game.id
        executionTask = worker(operation,extra:request) { _ in
            guard libraryId == self.preferences.libraryId else { return }
            self.notice = operation == "backupSave" ? "存档备份已保存。" : operation == "restoreSave" ? "存档已恢复，恢复前的存档已自动备份。" : "运行版本已切换，存档未回退。"
            completion()
        }
    }
}

struct GameRecoveryView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    let game: Game
    @State private var report: RecoveryReport?
    @State private var loading = false
    @State private var requestId = UUID()
    @State private var restore: SaveBackup?
    @State private var activate: RuntimeRelease?
    private var busy: Bool { store.executionBusy || !store.queue.isEmpty }

    private func reload() {
        loading = true
        let request = UUID()
        requestId = request
        store.loadRecovery(game) { value in
            guard requestId == request else { return }
            report = value
            loading = false
        }
    }

    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            HStack {
                VStack(alignment:.leading) {
                    Text(L("存档与运行版本")).font(.title2.bold())
                    Text(game.name).foregroundStyle(.secondary)
                }
                Spacer()
                Button(L("刷新"),action:reload).disabled(loading || busy)
                Button(L("关闭")) { dismiss() }.keyboardShortcut(.cancelAction)
            }
            if let notice = store.notice { Text(L(notice)).font(.callout).foregroundStyle(.secondary) }
            if let task = store.activeTasks.first(where: { $0.gameId == game.id && ["backupSave","restoreSave","activateRelease"].contains($0.operation) }) {
                TaskProgressView(task:task,compact:true)
                Button(L("取消任务")) { store.cancel(task) }.disabled(task.state == "cancelling")
            }
            if busy { Text(L("请先结束游戏及准备任务，再管理存档和运行版本。")).font(.caption).foregroundStyle(.secondary) }
            ScrollView {
                VStack(alignment:.leading,spacing:18) {
                    HStack {
                        Text(L("存档备份")).font(.headline)
                        Spacer()
                        Button(L("立即备份")) { store.performRecovery("backupSave",game:game,completion:reload) }.disabled(busy || loading)
                    }
                    if loading { ProgressView().progressViewStyle(.linear) }
                    if let report {
                        if report.backups.isEmpty { Text(L("尚无存档备份。")).foregroundStyle(.secondary) }
                        ForEach(report.backups) { backup in
                            HStack {
                                VStack(alignment:.leading,spacing:4) {
                                    Text(Date(timeIntervalSince1970:backup.created),style:.date)
                                    Text(Date(timeIntervalSince1970:backup.created),style:.time).font(.caption)
                                    Text(backup.reasonName).font(.caption).foregroundStyle(.secondary)
                                    Text(ByteCountFormatter.string(fromByteCount:backup.size,countStyle:.file)).font(.caption)
                                }
                                Spacer()
                                Button(L("恢复此备份…")) { restore = backup }.disabled(busy || loading)
                            }.padding(12).contentCard(12)
                        }
                        Divider()
                        Text(L("运行版本")).font(.headline)
                        Text(L("切换运行版本前会自动备份存档。切换不会自动恢复旧存档；旧版本可能无法读取新版本存档。")).font(.caption).foregroundStyle(.secondary)
                        if report.releases.isEmpty { Text(L("尚无已准备的运行版本。")).foregroundStyle(.secondary) }
                        ForEach(report.releases) { release in
                            HStack {
                                VStack(alignment:.leading,spacing:4) {
                                    Text(release.version.isEmpty ? L("版本待识别") : release.version).font(.headline)
                                    Text(Date(timeIntervalSince1970:release.created),style:.date).font(.caption)
                                    Text(Date(timeIntervalSince1970:release.created),style:.time).font(.caption)
                                    Text(L("引擎标识：") + String(release.engine.prefix(16))).font(.caption.monospaced()).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if release.current { Label(L("当前运行版本"),systemImage:"checkmark.circle.fill").foregroundStyle(.teal) }
                                else { Button(L("切换到此版本…")) { activate = release }.disabled(busy || loading) }
                            }.padding(12).contentCard(12)
                        }
                    }
                }
            }
        }.padding(24).frame(width:650,height:640)
        .onAppear { store.notice = nil; reload() }
        .onChange(of:store.preferences.libraryId) { _,_ in dismiss() }
        .alert(L("恢复所选存档？"),isPresented:Binding(get:{restore != nil},set:{if !$0 {restore = nil}})) {
            Button(L("取消"),role:.cancel) { restore = nil }
            Button(L("恢复存档"),role:.destructive) {
                if let backup = restore { store.performRecovery("restoreSave",game:game,extra:["backupId":backup.id],completion:reload) }
                restore = nil
            }
        } message: { Text(L("将替换当前存档。恢复前会自动备份当前存档；备份校验失败时保留当前存档。")) }
        .alert(L("切换运行版本？"),isPresented:Binding(get:{activate != nil},set:{if !$0 {activate = nil}})) {
            Button(L("取消"),role:.cancel) { activate = nil }
            Button(L("切换版本")) {
                if let release = activate { store.performRecovery("activateRelease",game:game,extra:["releaseId":release.id],completion:reload) }
                activate = nil
            }
        } message: { Text(L("切换前会校验运行文件并备份当前存档。存档不会自动回退。")) }
        .alert(L("操作未完成"),isPresented:Binding(get:{store.error != nil},set:{if !$0 {store.error = nil;loading = false}})) {
            Button(L("知道了"),role:.cancel) { store.error = nil;loading = false }
            Button(L("复制错误摘要")) { store.copyDiagnostic() }
        } message: { Text(store.failureMessage) }
    }
}
