import SwiftUI

/// One action group shared by Settings and setup; secondary tools live in a menu.
struct EnvironmentToolsView: View {
    @EnvironmentObject var store: Store
    var showsRecheck = true
    @State private var confirmUninstall = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) { primaryActions; secondaryActions }
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) { primaryActions }
                    HStack(spacing: 10) { secondaryActions }
                }
            }.controlSize(.regular)

            if let task = store.tasks.first(where: {
                $0.id == store.executionTask && ["prepareEngine", "installMetal", "uninstallMetal"].contains($0.operation)
            }) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L(task.stage ?? task.title)).font(.caption)
                    TaskProgressView(task: task, compact: true)
                }
            }

            CompactDisclosure(title: "引擎与高级设置", subtitle: "nxnative · Xcode · Metal", symbol: "slider.horizontal.3") {
                Text(L("引擎随应用提供，无需单独下载。Switch Pro、Xbox 与 PS 手柄自动识别，无需配置按键映射。引擎更新随新版应用发布。"))
                    .font(.caption).foregroundStyle(.secondary)
                TextField(L("Xcode Developer 目录"), text: $store.preferences.developerDir)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { store.savePreferences(); store.checkEnvironment() }
                    .onChange(of: store.preferences.developerDir) { _, _ in store.checks = [] }
                Text(L("准备游戏需要完整工具链；启动已准备好的游戏只需要标有“启动”的项目。首次安装请先完成全部检查。"))
                    .font(.caption).foregroundStyle(.secondary)
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
        Button(action: store.prepareEngine) {
            Label(L("准备引擎工具"), systemImage: "hammer")
        }.buttonStyle(EnvironmentActionStyle(prominent: true)).disabled(!store.canManageToolchain)

        Button(action: store.chooseXcode) {
            Label(L("选择 Xcode.app…"), systemImage: "folder")
        }.buttonStyle(EnvironmentActionStyle()).disabled(store.checkingEnvironment || store.executionBusy)
    }

    @ViewBuilder private var secondaryActions: some View {
        if showsRecheck {
            Button {
                store.savePreferences(); store.checkEnvironment()
            } label: {
                Label(L("重新检查"), systemImage: "arrow.clockwise")
            }.buttonStyle(EnvironmentActionStyle()).disabled(store.checkingEnvironment || store.executionBusy)
        }
        Menu {
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

/// Keep action boundaries and contrast clear even when the window is inactive.
private struct EnvironmentActionStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorScheme) private var colorScheme
    var prominent = false

    private var foreground: Color {
        guard isEnabled else { return .secondary }
        return prominent ? (colorScheme == .dark ? .black : .white) : .primary
    }

    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.callout.weight(.semibold))
            .foregroundStyle(foreground)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(
                isEnabled ? WorkspacePalette.accent.opacity(prominent ? 1 : 0.10) : Color.secondary.opacity(0.08),
                in: RoundedRectangle(cornerRadius: 10)
            )
            .glassSurface(10)
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(
                isEnabled ? WorkspacePalette.accent.opacity(prominent ? 0.7 : 0.35) : Color.secondary.opacity(0.15)
            ))
            .opacity(isEnabled ? (configuration.isPressed ? 0.75 : 1) : 0.55)
    }
}
