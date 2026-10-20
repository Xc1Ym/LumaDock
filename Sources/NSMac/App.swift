import SwiftUI
import AppKit
@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var store: Store?
    func applicationShouldTerminate(_ sender:NSApplication)->NSApplication.TerminateReply {store?.terminate();return .terminateNow}
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {false}
}
@main struct NSMacApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject var store = Store()
    var body: some Scene {
        WindowGroup("璃游 LumaDock") {ContentView().environmentObject(store).onAppear{delegate.store=store
            // App-local appearance override for screenshot and accessibility checks.
            let args=CommandLine.arguments
            if let index=args.firstIndex(of:"--appearance"),index+1<args.count {
                NSApp.appearance=args[index+1]=="dark" ? NSAppearance(named:.darkAqua) : args[index+1]=="light" ? NSAppearance(named:.aqua) : nil
            }
            if CommandLine.arguments.contains("--layout-check") {
                for delay in [0.5,2.0,5.0] { DispatchQueue.main.asyncAfter(deadline:.now()+delay) {
                    let rows=NSApp.windows.map {w in ["title":w.title,"frame":NSStringFromRect(w.frame),"content":NSStringFromRect(w.contentView?.bounds ?? .zero)]}
                    if let data=try? JSONSerialization.data(withJSONObject:rows,options:.prettyPrinted){try? data.write(to:store.privateRoot.appendingPathComponent("layout-check.json"),options:.atomic)}
                } }
            }}.tint(Brand.accent)}
        .defaultSize(width:1240,height:800)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing:.newItem) {Button("导入密钥…",action:store.importKeys);Button("添加游戏…",action:store.chooseGames).keyboardShortcut("o")}
            CommandGroup(after:.appInfo){Button("导出诊断包…",action:store.exportDiagnostics)}
        }
    }
}
