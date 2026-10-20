import SwiftUI
import AppKit
import GameController

@MainActor final class ControllerMonitor: ObservableObject {
    @Published var name = L("未连接手柄")
    @Published var value = L("等待输入")
    var observers: [NSObjectProtocol] = []
    init() {
        for n in [NSNotification.Name.GCControllerDidConnect, .GCControllerDidDisconnect] { observers.append(NotificationCenter.default.addObserver(forName:n,object:nil,queue:.main) { [weak self] _ in Task { @MainActor in self?.refresh() } }) }
        refresh()
    }
    func refresh() {
        for c in GCController.controllers() {c.extendedGamepad?.valueChangedHandler=nil}
        guard let c = GCController.controllers().first,let pad=c.extendedGamepad else {name=L("未连接手柄");value=L("所有输入已清空");return}
        name=c.vendorName ?? L("已连接手柄")
        pad.valueChangedHandler = { [weak self] p,_ in DispatchQueue.main.async {
            guard let self else {return}
            self.value=String(format:L("左摇杆 %.2f, %.2f · 右摇杆 %.2f, %.2f · L2 %.2f · R2 %.2f"),p.leftThumbstick.xAxis.value,p.leftThumbstick.yAxis.value,p.rightThumbstick.xAxis.value,p.rightThumbstick.yAxis.value,p.leftTrigger.value,p.rightTrigger.value)
            if p.buttonA.isPressed {self.value += " · south"};if p.buttonB.isPressed{self.value += " · east"};if p.buttonX.isPressed{self.value += " · west"};if p.buttonY.isPressed{self.value += " · north"}
        } }
    }
    deinit {for o in observers {NotificationCenter.default.removeObserver(o)}}
}
struct InputEditor: View {
    @EnvironmentObject var store: Store
    let game: Game?
    @State var config: InputConfig
    @State private var recording: String?
    @State private var test = false
    @State private var testText = L("点击“开始输入测试”后按键或移动鼠标")
    @State private var tab = "bindings"
    @StateObject private var controller = ControllerMonitor()
    init(game:Game?,initial:InputConfig) { self.game=game;_config=State(initialValue:initial) }
    var body: some View {
        VStack(alignment:.leading,spacing:16) {
            HStack {VStack(alignment:.leading) {Text(game == nil ? L("全局输入映射") : L("\(game!.name) · 输入映射")).font(.title2.bold());Text(L("保存后在下次启动游戏时生效，无需重新编译。")).foregroundStyle(.secondary)};Spacer();Button(L("关闭")){store.editingInput=false}}
            Picker(L("配置"),selection:$tab) {Text(L("按键映射")).tag("bindings");Text(L("鼠标与摇杆")).tag("options");Text(L("输入测试")).tag("test")}.pickerStyle(.segmented)
            if tab=="bindings" { bindings }
            else if tab=="options" { options }
            else { inputTest }
            if !config.conflicts.isEmpty { Text(config.conflicts.joined(separator:L("；"))).font(.callout).foregroundStyle(.red) }
            Divider()
            HStack {
                Button(L("恢复默认")) {config = .standard}
                if game != nil {Button(L("复制全局配置")) {config=store.globalInput}}
                Spacer();Button(L("保存配置")) {store.saveInput(config,for:game)}.buttonStyle(.borderedProminent).tint(.teal).disabled(!config.conflicts.isEmpty || recording != nil)
            }
        }.padding(24).frame(width:1040,height:790).background(LibraryBackdrop())
        .background(EventRecorder(recording:recording != nil,test:test && tab=="test",onKey:{ b in
            if let t=recording {if b.code != 53 {config.keyboard[t]=b};recording=nil}
            else {if b.code==53 {test=false;testText=L("输入测试已结束")} else {testText=L("键盘：\(keyName(b))")}}
        },onMouse:{v in testText=v}))
    }
    var bindings: some View {
        ScrollView {
            Grid(alignment:.leading,horizontalSpacing:18,verticalSpacing:9) {
                GridRow {Text(L("Switch 输入")).bold();Text(L("键盘（点击录入）")).bold();Text(L("鼠标")).bold();Text(L("手柄物理位置")).bold()}
                Divider().gridCellColumns(4)
                ForEach(InputConfig.targets,id:\.self) { target in
                    GridRow {
                        Text(targetName(target)).frame(width:155,alignment:.leading)
                        HStack {Button(recording==target ? L("请按键…（Esc 取消）") : keyName(config.keyboard[target])) {test=false;recording=target}.frame(width:205);Button {config.keyboard[target]=nil} label:{Image(systemName:"xmark.circle")}.accessibilityLabel(L("解除绑定")).buttonStyle(.plain).foregroundStyle(.secondary)}
                        Picker("",selection:Binding(get:{config.mouse[target] ?? -1},set:{config.mouse[target]=$0<0 ? nil : $0})) {Text(L("未绑定")).tag(-1);Text(L("左键")).tag(0);Text(L("右键")).tag(1);Text(L("中键")).tag(2);Text(L("侧键 1")).tag(3);Text(L("侧键 2")).tag(4)}.labelsHidden().frame(width:140)
                        Picker("",selection:Binding(get:{config.gamepad[target] ?? ""},set:{config.gamepad[target]=$0.isEmpty ? nil : $0})) {Text(L("未绑定")).tag("");ForEach(InputConfig.padCodes,id:\.self){Text(padName($0)).tag($0)}}.labelsHidden().frame(width:190)
                    }
                }
            }.padding(.trailing,10).id(Localization.language)
        }
    }
    var options: some View {
        Form {
            Section(L("鼠标")) {
                Picker(L("模式"),selection:$config.mouseOptions.mode) {Text(L("转动视角（Esc 切换捕获）")).tag("camera");Text(L("触屏指针")).tag("touch")}
                HStack {Text(L("横向灵敏度"));Slider(value:$config.mouseOptions.sensitivityX,in:0.1...10);Text(String(format:"%.1f",config.mouseOptions.sensitivityX)).monospacedDigit()}
                HStack {Text(L("纵向灵敏度"));Slider(value:$config.mouseOptions.sensitivityY,in:0.1...10);Text(String(format:"%.1f",config.mouseOptions.sensitivityY)).monospacedDigit()}
                Toggle(L("横向反转"),isOn:$config.mouseOptions.invertX);Toggle(L("纵向反转"),isOn:$config.mouseOptions.invertY);Toggle(L("停止移动后摇杆回中"),isOn:$config.mouseOptions.recenter)
                Text(L("失焦、最小化或系统输入框出现时会释放鼠标并清空输入。")).font(.caption).foregroundStyle(.secondary)
            }
            Section(L("手柄")) {
                Label(L(controller.name),systemImage:"gamecontroller")
                HStack {Text(L("摇杆死区"));Slider(value:$config.deadzone,in:0...0.8);Text(String(format:"%.0f%%",config.deadzone*100)).monospacedDigit()}
                ForEach(["LX","LY","RX","RY"],id:\.self){target in
                    HStack {Text(axisName(target)).frame(width:100);Picker(L("来源"),selection:Binding(get:{config.axes[target]?.source ?? "leftX"},set:{config.axes[target]=AxisBinding(source:$0,invert:config.axes[target]?.invert ?? false)})){ForEach(["leftX","leftY","rightX","rightY"],id:\.self){Text(axisName($0)).tag($0)}};Toggle(L("反转"),isOn:Binding(get:{config.axes[target]?.invert ?? false},set:{config.axes[target]?.invert=$0}))}
                }
                Text(L("默认按 Switch 物理位置映射；单玩家。断开手柄立即清空该设备输入。")).font(.caption).foregroundStyle(.secondary)
            }
        }.formStyle(.grouped).id(Localization.language)
    }
    var inputTest: some View {
        VStack(alignment:.leading,spacing:20) {
            Label(L(controller.name),systemImage:"gamecontroller.fill").font(.headline)
            Text(L(controller.value)).font(.system(.callout,design:.monospaced))
            Divider();Toggle(L("开始输入测试"),isOn:$test).onChange(of:test){_,v in if v {recording=nil}}
            Text(L(testText)).font(.title3.monospaced()).frame(maxWidth:.infinity,minHeight:130).background(.quaternary,in:RoundedRectangle(cornerRadius:16))
            Text(L("测试只在此窗口接收输入，不会启动游戏。Esc 结束键盘测试。")).foregroundStyle(.secondary)
            Spacer()
        }.padding(20)
    }
}
struct EventRecorder: NSViewRepresentable {
    var recording: Bool; var test: Bool; var onKey: (KeyBinding)->Void; var onMouse: (String)->Void
    func makeCoordinator()->Coordinator { Coordinator(self) }
    func makeNSView(context:Context)->NSView {let v=NSView();context.coordinator.install(v);return v}
    func updateNSView(_ view:NSView,context:Context) {context.coordinator.parent=self}
    static func dismantleNSView(_ view:NSView,coordinator:Coordinator){coordinator.remove()}
    final class Coordinator {
        var parent:EventRecorder; var monitor:Any?; weak var view:NSView?
        init(_ p:EventRecorder){parent=p}
        func install(_ v:NSView){view=v;monitor=NSEvent.addLocalMonitorForEvents(matching:[.keyDown,.keyUp,.flagsChanged,.mouseMoved,.leftMouseDown,.rightMouseDown,.otherMouseDown]){[weak self] e in
            guard let self,(self.parent.recording || self.parent.test),NSApp.isActive,self.view?.window?.isKeyWindow == true else{return e}
            if [.mouseMoved,.leftMouseDown,.rightMouseDown,.otherMouseDown].contains(e.type){if self.parent.test {self.parent.onMouse(e.type == .mouseMoved ? String(format:L("鼠标位移：%.1f, %.1f"),e.deltaX,e.deltaY) : L("鼠标按钮：\(e.buttonNumber)"))};return e}
            if e.type == .keyUp {if self.parent.test {self.parent.onMouse(L("键盘已松开：\(keyName(.init(code:Int(e.keyCode))))"))};return self.parent.recording ? nil : e}
            let code = [60:56,62:59,61:58][Int(e.keyCode)] ?? Int(e.keyCode)
            var mods=(e.modifierFlags.contains(.shift) ? 1 : 0)|(e.modifierFlags.contains(.control) ? 2 : 0)|(e.modifierFlags.contains(.option) ? 4 : 0)
            if e.modifierFlags.contains(.command){return e}
            if e.type == .flagsChanged {let bit=code==56 ? 1 : code==59 ? 2 : code==58 ? 4 : 0;if bit==0 || mods & bit == 0{if self.parent.test {self.parent.onMouse(L("修饰键已松开"))};return e};mods=0}
            self.parent.onKey(.init(code:code,modifiers:mods));return nil
        }}
        func remove(){if let monitor {NSEvent.removeMonitor(monitor)};monitor=nil}
    }
}
