import SwiftUI
import AppKit
@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var store: Store?
    func applicationShouldTerminate(_ sender:NSApplication)->NSApplication.TerminateReply {store?.terminate();return .terminateNow}
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {false}
}
@main struct LumaNXApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject var store = Store()
    var body: some Scene {
        WindowGroup(L("璃游 LumaNX")) {ContentView().environmentObject(store).environment(\.locale,Localization.locale).onAppear{delegate.store=store;store.applyAppearance()
            if CommandLine.arguments.contains("--layout-check") {
                for delay in [0.5,2.0,5.0] { DispatchQueue.main.asyncAfter(deadline:.now()+delay) {
                    let rows=NSApp.windows.map {w in ["title":w.title,"frame":NSStringFromRect(w.frame),"content":NSStringFromRect(w.contentView?.bounds ?? .zero)]}
                    if let data=try? JSONSerialization.data(withJSONObject:rows,options:.prettyPrinted){try? data.write(to:store.privateRoot.appendingPathComponent("layout-check.json"),options:.atomic)}
                } }
            }}.tint(Brand.accent)}
        .defaultSize(width:1240,height:800)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing:.appTermination) {
                Button(L("退出璃游")) {store.quitApplication()}.keyboardShortcut("q",modifiers:.command)
            }
            CommandGroup(replacing:.appSettings) {
                Button(L("设置…")) {store.selection="settings"}.keyboardShortcut(",",modifiers:.command)
                    .disabled(store.showOnboarding || store.editingInput)
            }
            CommandGroup(replacing:.newItem) {
                Button(L("导入密钥…"),action:store.importKeys).keyboardShortcut("k",modifiers:[.command,.shift])
                Button(L("添加游戏…"),action:store.chooseGames).keyboardShortcut("o",modifiers:.command)
                Divider()
                Button(L("刷新游戏库")) {store.refresh()}.keyboardShortcut("r",modifiers:.command)
                    .disabled(store.preferences.library.isEmpty || store.refreshingLibrary)
            }
            CommandGroup(after:.sidebar) {
                Divider()
                Button(L("游戏库")) {store.selection="library"}.keyboardShortcut("1",modifiers:.command)
                Button(L("文件转换")) {store.selection="conversion"}.keyboardShortcut("2",modifiers:.command)
                Button(L("准备任务")) {store.selection="tasks"}.keyboardShortcut("3",modifiers:.command)
            }
            CommandGroup(after:.appInfo){Button(L("导出诊断包…"),action:store.exportDiagnostics)}
        }
    }
}
