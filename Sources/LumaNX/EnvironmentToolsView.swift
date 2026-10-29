import SwiftUI

/// One action group shared by Settings and setup; secondary tools live in a menu.
struct EnvironmentToolsView: View {
    @EnvironmentObject var store: Store
    var showsRecheck = true
    @State private var confirmUninstall = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            GlassEffectContainer(spacing:10) {
                HStack(spacing:10) {
                    primaryActions
                    secondaryActions
                }.controlSize(.regular)
            }

            if let task = store.tasks.first(where: {
                $0.id == store.executionTask && ["prepareEngine", "installMetal", "uninstallMetal"].contains($0.operation)
            }) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L(task.stage ?? task.title)).font(.caption)
                    TaskProgressView(task: task, compact: true)
                }
            }
        }.tint(WorkspacePalette.accent)
        .alert(L("卸载 Metal 编译组件？"), isPresented: $confirmUninstall) {
            Button(L("取消"), role: .cancel) {}
            Button(L("卸载组件"), role: .destructive) { store.manageMetal(remove: true) }
        } message: {
            Text(L("这是 Xcode 管理的共享组件，卸载也会影响其他使用它的项目。卸载后无法准备或重新编译游戏，可随时重新安装。游戏文件、密钥和存档会保留。"))
        }
    }

    @ViewBuilder private var primaryActions: some View {
        Button(action: store.chooseXcode) {
            Label(L("选择 Xcode.app…"), systemImage: "folder")
        }.buttonStyle(.glass).disabled(store.checkingEnvironment || store.executionBusy).help(store.preferences.developerDir)
    }

    @ViewBuilder private var secondaryActions: some View {
        if showsRecheck {
            Button {
                store.savePreferences(); store.checkEnvironment()
            } label: {
                Label(L("重新检查"), systemImage: "arrow.clockwise")
            }.buttonStyle(.glass).disabled(store.checkingEnvironment || store.executionBusy)
        }
        Spacer(minLength:0)
        Menu {
            Button(L("修复内置引擎"),action:store.prepareEngine).disabled(!store.canManageToolchain)
            Divider()
            Section("Xcode") {
                Button(L("在 App Store 获取 Xcode"), action: store.openXcodeStore)
                Button(L("打开 Xcode 完成设置")) { store.repairEnvironment("openXcode") }
                    .disabled(!store.xcodeInstalled)
            }
            Section(L("Metal 编译组件")) {
                Button(L("安装 Metal 编译组件")) { store.manageMetal(remove: false) }
                    .disabled(!store.canManageToolchain || !store.xcodeInitialized || store.metalInstalled)
                Button(L("卸载 Metal 编译组件…"), role: .destructive) { confirmUninstall = true }
                    .disabled(!store.canManageToolchain || !store.metalInstalled || !store.canUninstallMetal)
                    .help(store.canUninstallMetal ? L("卸载 Apple 管理的共享组件，可重新安装") : L("当前 Xcode 不支持命令行卸载组件"))
            }
            Divider()
            Button(L("环境安装说明")) { store.openDocumentation(.environment) }
        } label: {
            Label(L("更多工具"), systemImage: "ellipsis.circle")
        }.menuStyle(.borderlessButton).buttonStyle(.glass).fixedSize()
    }
}
