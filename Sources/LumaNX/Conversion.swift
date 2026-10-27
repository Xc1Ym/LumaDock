import Foundation
import AppKit
import UniformTypeIdentifiers

enum ConversionMode: String, Codable, CaseIterable, Identifiable {
    case convert, compress, decompress, merge
    var id:String {rawValue}
    var title:String {
        switch self {
        case .convert: L("格式转换")
        case .compress: L("压缩")
        case .decompress: L("解压")
        case .merge: L("合并")
        }
    }
    var extensions:Set<String> {
        switch self {
        case .compress: ["nsp","xci"]
        case .decompress: ["nsz","xcz"]
        default: ["nsp","xci","nsz","xcz"]
        }
    }
}
struct ConversionJob: Codable, Equatable {
    var mode:ConversionMode = .convert
    var target = "nsp"
    var paths:[String] = []
    var outputDirectory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads/LumaNX Conversions").path
    var level = 18
    var verify = true
    var validSelection:Bool { !paths.isEmpty && (mode != .merge || paths.count>1) && paths.allSatisfy{mode.extensions.contains(URL(fileURLWithPath:$0).pathExtension.lowercased())} }
}
struct ConverterStatus: Decodable {
    var path:String
    var conversionReady:Bool
    var compressionReady:Bool
    var keysReady:Bool
    var keySource:String
    func ready(for mode:ConversionMode)->Bool {keysReady && (mode == .compress || mode == .decompress ? compressionReady : conversionReady)}
}

@MainActor extension Store {
    var latestConversion:TaskRecord? {tasks.first{$0.operation=="convertFiles" && $0.state=="completed" && !($0.outputFiles ?? []).isEmpty}}
    func checkConverter() {
        guard !checkingConverter else {return}
        checkingConverter=true
        worker("converterStatus",visible:false) {result in
            self.converterStatus=Self.decode(ConverterStatus.self,result)
            self.checkingConverter=false
        }
    }
    func chooseConversionKeys(source:URL? = nil) {
        guard !executionBusy,!importingConversionKeys,!checkingConverter else {return}
        let url:URL
        if let source {url=source}
        else {
            let panel=NSOpenPanel();panel.title=L("导入自己的转换密钥 prod.keys")
            guard panel.runModal() == .OK,let selected=panel.url else {return};url=selected
        }
        worker("conversionKeys",extra:["path":url.path]) {result in
            self.converterStatus=Self.decode(ConverterStatus.self,result)
            self.notice="转换密钥已导入，游戏库密钥保持不变。"
        }
    }
    var importingConversionKeys:Bool {tasks.contains{$0.operation=="conversionKeys" && $0.active}}
    func chooseConversionFiles() {
        let panel=NSOpenPanel();panel.title=L("添加 NSP、XCI、NSZ 或 XCZ 文件");panel.allowsMultipleSelection=true
        panel.allowedContentTypes=["nsp","xci","nsz","xcz"].compactMap{UTType(filenameExtension:$0)}
        if panel.runModal() == .OK {addConversionFiles(panel.urls)}
    }
    func addConversionFiles(_ urls:[URL]) {
        let supported:Set<String>=["nsp","xci","nsz","xcz"]
        let incoming=urls.filter{supported.contains($0.pathExtension.lowercased())}.map(\.path)
        guard !incoming.isEmpty else {error="请选择 NSP、XCI、NSZ 或 XCZ 文件。";return}
        for path in incoming where !conversion.paths.contains(path) {conversion.paths.append(path)}
        showOnboarding=false;selection="conversion"
    }
    func chooseConversionOutput() {
        let panel=NSOpenPanel();panel.title=L("选择转换输出文件夹");panel.canChooseFiles=false;panel.canChooseDirectories=true;panel.canCreateDirectories=true
        panel.directoryURL=URL(fileURLWithPath:conversion.outputDirectory)
        guard panel.runModal() == .OK,let url=panel.url else {return}
        conversion.outputDirectory=url.path;preferences.conversionOutput=url.path;savePreferences()
    }
    func startConversion(_ job:ConversionJob? = nil) {
        guard !executionBusy,!importingConversionKeys,queue.isEmpty else {error="构建与游戏运行互斥，请等待当前任务结束。";return}
        let options=job ?? conversion
        guard options.validSelection else {error="所选文件格式与转换操作不匹配。";return}
        do {
            let value=try JSONSerialization.jsonObject(with:JSONEncoder().encode(options))
            conversion=options;selection="conversion"
            executionTask=worker("convertFiles",extra:["conversion":value]) { _ in
                self.notice="转换完成，可在任务中查看或导入生成的 NSP。"
            }
        } catch {self.error=error.localizedDescription}
    }
    func importConverted(_ task:TaskRecord) {
        let paths=(task.outputFiles ?? []).filter{URL(fileURLWithPath:$0).pathExtension.lowercased()=="nsp"}
        guard !paths.isEmpty else {return}
        addGames(paths.map{URL(fileURLWithPath:$0)})
    }
}
