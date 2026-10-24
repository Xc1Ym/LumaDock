import SwiftUI
import UniformTypeIdentifiers

struct ConversionView:View {
    @EnvironmentObject var store:Store
    private var busy:Bool {store.executionBusy || store.importingConversionKeys || !store.queue.isEmpty}
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:20) {
                Text(L("文件转换")).font(.largeTitle.bold())
                Text(L("转换 NSP / XCI，压缩或解压 NSZ / XCZ，也可合并同一游戏的本体、更新和 DLC。")).foregroundStyle(.secondary)
                backend
                VStack(alignment:.leading,spacing:14) {
                    Picker(L("转换操作"),selection:$store.conversion.mode) {
                        ForEach(ConversionMode.allCases){Text($0.title).tag($0)}
                    }.pickerStyle(.segmented)
                    HStack {
                        Button(L("添加文件…"),action:store.chooseConversionFiles)
                        Button(L("清空文件")){store.conversion.paths=[]}.disabled(store.conversion.paths.isEmpty)
                        Spacer()
                        Text(L("共 \(store.conversion.paths.count) 个文件")).font(.caption).foregroundStyle(.secondary)
                    }
                    if store.conversion.paths.isEmpty {
                        Text(L("拖入文件，或点击添加文件。原始文件不会被修改。")).foregroundStyle(.secondary).frame(maxWidth:.infinity,minHeight:95)
                    } else {
                        ForEach(store.conversion.paths,id:\.self) {path in
                            HStack {
                                Image(systemName:"doc.zipper")
                                VStack(alignment:.leading) {
                                    Text(URL(fileURLWithPath:path).lastPathComponent).lineLimit(2)
                                    Text(path).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                                }
                                Spacer()
                                Button {store.conversion.paths.removeAll{$0==path}} label:{Image(systemName:"minus.circle")}.buttonStyle(.plain).accessibilityLabel(L("移除文件"))
                            }
                        }
                    }
                    if store.conversion.mode == .convert || store.conversion.mode == .merge {
                        Picker(L("输出格式"),selection:$store.conversion.target) {Text("NSP").tag("nsp");Text("XCI").tag("xci")}.pickerStyle(.segmented).frame(maxWidth:260)
                    }
                    if store.conversion.mode == .compress {
                        Stepper(L("压缩等级：\(store.conversion.level)"),value:$store.conversion.level,in:1...22)
                        Toggle(L("压缩后校验"),isOn:$store.conversion.verify)
                    }
                    if store.conversion.mode == .merge {Text(L("一次选择同一游戏的文件；同一内容有多个版本时由后端保留最新版本。")).font(.caption).foregroundStyle(.secondary)}
                    if !store.conversion.paths.isEmpty && !store.conversion.validSelection {Text(L("所选文件格式与转换操作不匹配。")).font(.caption).foregroundStyle(.orange)}
                    HStack {
                        Button(L("输出文件夹…"),action:store.chooseConversionOutput)
                        Text(store.conversion.outputDirectory).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    }
                    Text(L("结果写入新的独立文件夹，不覆盖已有输出；转换成功不代表游戏可运行。")).font(.caption).foregroundStyle(.secondary)
                    Button(L("开始转换")){store.startConversion()}.buttonStyle(.glassProminent).controlSize(.large)
                        .disabled(!store.conversion.validSelection || store.converterStatus?.ready(for:store.conversion.mode) != true || busy)
                }.padding(20).contentCard(18).disabled(busy)
                if let task=store.tasks.first(where:{$0.id==store.executionTask && $0.operation=="convertFiles"}) {TaskCard(task:task)}
                if let task=store.latestConversion,task.id != store.executionTask {TaskCard(task:task)}
                Text(L("转换功能参考 SAK-Mac，内置 NSC_BUILDER / nsz；第三方来源与许可可在设置中查看。")).font(.caption).foregroundStyle(.secondary)
            }.padding(28).frame(maxWidth:1000,alignment:.leading).frame(maxWidth:.infinity)
        }
        .onAppear(perform:store.checkConverter)
        .onDrop(of:[UTType.fileURL],isTargeted:nil) {providers in
            guard !busy else {return false}
            let group=DispatchGroup();let urls=DroppedURLs()
            for provider in providers {group.enter();_ = provider.loadObject(ofClass:URL.self){url,_ in if let url{urls.append(url)};group.leave()}}
            group.notify(queue:.main){store.addConversionFiles(urls.result())};return true
        }
    }
    private var backend:some View {
        VStack(alignment:.leading,spacing:10) {
            HStack {
                Text(L("转换工具")).font(.headline)
                Spacer()
                if store.checkingConverter {ProgressView().controlSize(.small)}
                Button(L("重新检查"),action:store.checkConverter).disabled(store.checkingConverter)
            }
            Text(L("SAK-Mac 转换后端与依赖已内置，无需额外安装 Python、Xcode 或 nxnative。导入自己的密钥后即可转换。")).font(.callout).foregroundStyle(.secondary)
            HStack {
                Label(L(store.converterStatus?.conversionReady == true ? "格式转换就绪" : "格式转换后端未就绪"),systemImage:store.converterStatus?.conversionReady == true ? "checkmark.circle" : "exclamationmark.circle")
                Label(L(store.converterStatus?.compressionReady == true ? "压缩解压就绪" : "压缩解压后端未就绪"),systemImage:store.converterStatus?.compressionReady == true ? "checkmark.circle" : "exclamationmark.circle")
            }.font(.caption)
            HStack {
                Link(L("SAK-Mac 项目"),destination:URL(string:"https://github.com/ggaoph-lab/SAK-Mac")!)
                Spacer()
                Text(L(store.converterStatus?.keysReady == true ? store.converterStatus?.keySource ?? "" : "尚未准备转换密钥")).font(.caption).foregroundStyle(.secondary)
                Button(L("导入转换密钥…")){store.chooseConversionKeys()}.disabled(busy || store.checkingConverter)
            }
        }.padding(20).contentCard(18)
    }
}
