import Foundation
import AppKit
import SwiftUI

struct NSPPackage: Codable, Identifiable {
    var id: String { sha256 }
    var titleId: String; var baseId: String; var version: Int; var type: String; var name: String; var display: String
    var path: String; var size: Int64; var sha256: String; var builds: [String:String]
    var kindName: String { ["base":L("本体"),"update":L("更新"),"dlc":"DLC"][type] ?? L("未知内容") }
}
struct Game: Codable, Identifiable {
    var id: String; var name: String; var display: String; var packages: [NSPPackage]; var hidden: Bool
    var compatibility: String?; var missing: [String]?; var cover: String?; var ready: Bool?; var needsPreparation: Bool?
    var compatibilityName: String { ["startup":L("仅验证启动"),"verified":L("Mac 已验证"),"experimental":L("实验性"),"unsupported":L("暂不支持")][compatibility ?? "unsupported"] ?? L("实验性") }
    var buildable: Bool { compatibility != "unsupported" && (missing ?? []).isEmpty }
}
struct TaskRecord: Codable, Identifiable {
    var id: String; var operation: String; var state: String; var gameId: String?; var stage: String?; var message: String?
    var stageIndex: Int?; var stageCount: Int?; var started: Double?; var ended: Double?
    var done: Double?; var total: Double?; var elapsed: Double?; var unit: String?
    var stateName: String { ["queued":L("排队"),"running":L("运行中"),"cancelling":L("取消中"),"cancelled":L("已取消"),"failed":L("失败"),"interrupted":L("中断"),"completed":L("完成")][state] ?? state }
    var active: Bool { ["running","queued","cancelling"].contains(state) }
    var title: String { ["import":L("导入游戏"),"build":L("准备游戏"),"migrate":L("迁移构建"),"launch":L("运行游戏"),"keys":L("导入密钥"),"preflight":L("环境检查"),"installMetal":L("安装 Metal 编译组件"),"uninstallMetal":L("卸载 Metal 编译组件")][operation] ?? operation }
}
struct ToolCheck: Decodable, Identifiable {
    var id: String { name }; var name: String; var ok: Bool; var message: String
    var help: String?; var action: String?; var group: String?; var requiredFor: [String]?; var detail: String?; var location:String?; var repairCommand:String?
    func required(for scope:String) -> Bool { requiredFor?.contains(scope) ?? true }
}
struct GameProfile: Decodable, Identifiable { var id: String; var name: String; var compatibility: String; var version: String }
struct KeyBinding: Codable, Equatable { var code: Int; var modifiers: Int = 0 }
struct AxisBinding: Codable, Equatable { var source: String; var invert: Bool = false }
struct MouseOptions: Codable, Equatable {
    var mode = "camera"; var sensitivityX = 1.0; var sensitivityY = 1.0; var invertX = false; var invertY = false; var recenter = true
}
struct InputConfig: Codable, Equatable {
    var schema = 1; var keyboard: [String:KeyBinding]; var mouse: [String:Int]; var gamepad: [String:String]; var axes: [String:AxisBinding]; var mouseOptions: MouseOptions = .init(); var deadzone = 0.15
    static let targets = ["A","B","X","Y","LS","RS","L","R","ZL","ZR","PLUS","MINUS","LEFT","UP","RIGHT","DOWN","LS_UP","LS_DOWN","LS_LEFT","LS_RIGHT","RS_UP","RS_DOWN","RS_LEFT","RS_RIGHT"]
    static let padCodes = ["east","south","north","west","leftStick","rightStick","leftShoulder","rightShoulder","leftTrigger","rightTrigger","menu","options","dpadLeft","dpadUp","dpadRight","dpadDown"]
    static var standard: InputConfig {
        let keys = ["A":14,"B":56,"X":49,"L":12,"R":5,"ZR":15,"LS":59,"RS":8,"PLUS":48,"MINUS":46,"LEFT":123,"UP":126,"RIGHT":124,"DOWN":125,"LS_UP":13,"LS_DOWN":1,"LS_LEFT":0,"LS_RIGHT":2]
        return .init(keyboard: keys.mapValues { KeyBinding(code:$0) }, mouse:["Y":0,"ZL":1], gamepad:Dictionary(uniqueKeysWithValues:zip(targets.prefix(16),padCodes).map { ($0,$1) }), axes:["LX":.init(source:"leftX"),"LY":.init(source:"leftY"),"RX":.init(source:"rightX"),"RY":.init(source:"rightY")])
    }
    var conflicts: [String] {
        var out: [String] = []; var seen: [String:String] = [:]
        for (t,b) in keyboard { let key = "k\(b.code):\(b.modifiers)"; if let old = seen[key] { out.append(L("键盘：\(old) 与 \(t) 重复")) }; seen[key] = t }
        seen = [:]; for (t,b) in mouse { let k = String(b); if let old = seen[k] { out.append(L("鼠标：\(old) 与 \(t) 重复")) }; seen[k] = t }
        seen = [:]; for (t,b) in gamepad { if let old = seen[b] { out.append(L("手柄：\(old) 与 \(t) 重复")) }; seen[b] = t }
        seen = [:]; for (t,b) in axes { if let old = seen[b.source] { out.append(L("手柄轴：\(old) 与 \(t) 重复")) }; seen[b.source] = t }
        return out
    }
}
struct Preferences: Codable { var library: String = ""; var libraryId: String = ""; var developerDir = "/Applications/Xcode.app/Contents/Developer"; var onboardingComplete = false; var prepareAfterImport: Bool?; var language: String?; var appearance: String? }

func keyName(_ b: KeyBinding?) -> String {
    guard let b else { return L("未绑定") }
    let keys: [Int:String] = [0:"A",1:"S",2:"D",3:"F",4:"H",5:"G",6:"Z",7:"X",8:"C",9:"V",11:"B",12:"Q",13:"W",14:"E",15:"R",16:"Y",17:"T",18:"1",19:"2",20:"3",21:"4",22:"6",23:"5",24:"=",25:"9",26:"7",27:"-",28:"8",29:"0",30:"]",31:"O",32:"U",33:"[",34:"I",35:"P",36:"Return",37:"L",38:"J",39:"'",40:"K",41:";",42:"\\",43:",",44:"/",45:"N",46:"M",47:".",48:"Tab",49:L("空格"),50:"`",51:L("删除"),53:"Esc",56:"Shift",58:"Option",59:"Ctrl",123:"←",124:"→",125:"↓",126:"↑"]
    return (b.modifiers & 1 != 0 ? "⇧" : "") + (b.modifiers & 2 != 0 ? "⌃" : "") + (b.modifiers & 4 != 0 ? "⌥" : "") + (keys[b.code] ?? L("键码 \(b.code)"))
}
func targetName(_ t: String) -> String {
    ["LS":L("左摇杆按下"),"RS":L("右摇杆按下"),"PLUS":"＋","MINUS":"－","LEFT":L("十字键左"),"UP":L("十字键上"),"RIGHT":L("十字键右"),"DOWN":L("十字键下"),"LS_UP":L("左摇杆上"),"LS_DOWN":L("左摇杆下"),"LS_LEFT":L("左摇杆左"),"LS_RIGHT":L("左摇杆右"),"RS_UP":L("右摇杆上"),"RS_DOWN":L("右摇杆下"),"RS_LEFT":L("右摇杆左"),"RS_RIGHT":L("右摇杆右")][t] ?? t
}

func padName(_ code:String) -> String {
    ["east":L("右侧按钮"),"south":L("下侧按钮"),"north":L("上侧按钮"),"west":L("左侧按钮"),"leftStick":L("左摇杆按下"),"rightStick":L("右摇杆按下"),"leftShoulder":L("左肩键"),"rightShoulder":L("右肩键"),"leftTrigger":L("左扳机"),"rightTrigger":L("右扳机"),"menu":L("菜单（＋）"),"options":L("选项（－）"),"dpadLeft":L("方向键左"),"dpadUp":L("方向键上"),"dpadRight":L("方向键右"),"dpadDown":L("方向键下")][code] ?? code
}
func axisName(_ code:String) -> String {
    ["LX":L("左摇杆横向"),"LY":L("左摇杆纵向"),"RX":L("右摇杆横向"),"RY":L("右摇杆纵向"),"leftX":L("左摇杆横向"),"leftY":L("左摇杆纵向"),"rightX":L("右摇杆横向"),"rightY":L("右摇杆纵向")][code] ?? code
}
