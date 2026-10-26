import SwiftUI
import UniformTypeIdentifiers

struct ConversionView:View {
    @EnvironmentObject var store:Store
    @State private var dropTargeted=false
    private var busy:Bool {store.executionBusy || store.importingConversionKeys || !store.queue.isEmpty}
    var body:some View {
        WorkspacePage {
            WorkspaceHeading(title:"文件转换",subtitle:"转换、压缩与合并，在一处完成。",symbol:"doc.zipper") {
                StatusPill(title:L("共 \(store.conversion.paths.count) 个文件"),symbol:"doc.on.doc",color:.secondary)
            }
            GlassPanel {
                Picker(L("转换操作"),selection:$store.conversion.mode) {
                    ForEach(ConversionMode.allCases){Text($0.title).tag($0)}
                }.pickerStyle(.segmented)
                HStack {
                    Text(L("待转换文件")).font(.headline)
                    Spacer()
                    if !store.conversion.paths.isEmpty {
                        Button(L("清空文件")){store.conversion.paths=[]}.controlSize(.small)
                        Button(L("添加文件…"),action:store.chooseConversionFiles).controlSize(.small)
                    }
                }
                if store.conversion.paths.isEmpty {
                    VStack(spacing:10) {
                        Image(systemName:"doc.badge.plus").font(.system(size:32,weight:.light)).foregroundStyle(WorkspacePalette.accent)
                        Text(L("拖入文件，或点击添加文件。原始文件不会被修改。")).font(.callout).foregroundStyle(.secondary)
                        Button(L("添加文件…"),action:store.chooseConversionFiles).buttonStyle(.glass)
                    }.frame(maxWidth:.infinity,minHeight:170)
                        .background(WorkspacePalette.accent.opacity(dropTargeted ? 0.12 : 0.035),in:RoundedRectangle(cornerRadius:14))
                        .overlay(RoundedRectangle(cornerRadius:14).strokeBorder(WorkspacePalette.accent.opacity(dropTargeted ? 0.7 : 0.2),style:StrokeStyle(lineWidth:1,dash:[5,4])))
                } else {
                    ScrollView {
                        LazyVStack(spacing:6) {
                            ForEach(store.conversion.paths,id:\.self) {path in
                                HStack(spacing:10) {
                                    Image(systemName:"doc.zipper").foregroundStyle(WorkspacePalette.accent).frame(width:28)
                                    Text(URL(fileURLWithPath:path).lastPathComponent).font(.callout).lineLimit(1).truncationMode(.middle).help(path)
                                    Spacer()
                                    Button {store.conversion.paths.removeAll{$0==path}} label:{Image(systemName:"xmark.circle.fill")}
                                        .buttonStyle(.plain).foregroundStyle(.secondary).accessibilityLabel(L("移除文件"))
                                }.padding(10).contentCard(10)
                            }
                        }
                    }.frame(height:min(230,CGFloat(store.conversion.paths.count)*48))
                }
                if store.conversion.mode == .merge {
                    Text(L("一次选择同一游戏的文件；同一内容有多个版本时由后端保留最新版本。")).font(.caption).foregroundStyle(.secondary)
                }
                if !store.conversion.paths.isEmpty && !store.conversion.validSelection {
                    Label(L("所选文件格式与转换操作不匹配。"),systemImage:"exclamationmark.circle").font(.caption).foregroundStyle(.orange)
                }
                Divider()
                HStack(spacing:16) {
                    if store.conversion.mode == .convert || store.conversion.mode == .merge {
                        Text(L("输出格式")).font(.callout).foregroundStyle(.secondary)
                        Picker(L("输出格式"),selection:$store.conversion.target) {Text("NSP").tag("nsp");Text("XCI").tag("xci")}
                            .pickerStyle(.segmented).labelsHidden().frame(width:160)
                    }
                    if store.conversion.mode == .compress {
                        Stepper(L("压缩等级：\(store.conversion.level)"),value:$store.conversion.level,in:1...22).fixedSize()
                        Toggle(L("压缩后校验"),isOn:$store.conversion.verify).toggleStyle(.switch).controlSize(.small)
                    }
                    Spacer(minLength:0)
                    Button(L("开始转换")){store.startConversion()}.buttonStyle(.glassProminent).controlSize(.large)
                        .disabled(!store.conversion.validSelection || store.converterStatus?.ready(for:store.conversion.mode) != true || busy)
                }
                CompactDisclosure(title:"输出位置与说明",subtitle:URL(fileURLWithPath:store.conversion.outputDirectory).lastPathComponent,symbol:"folder") {
                    HStack {
                        Text(store.conversion.outputDirectory).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        Spacer()
                        Button(L("输出文件夹…"),action:store.chooseConversionOutput).controlSize(.small)
                    }
                    Text(L("结果写入新的独立文件夹，不覆盖已有输出；转换成功不代表游戏可运行。")).font(.caption).foregroundStyle(.secondary)
                }
            }.disabled(busy)
            backend
            if let task=store.tasks.first(where:{$0.id==store.executionTask && $0.operation=="convertFiles"}) {TaskCard(task:task)}
            if let task=store.latestConversion,task.id != store.executionTask {
                GlassPanel {
                    CompactDisclosure(title:"最近转换",subtitle:task.stateName,symbol:"clock.arrow.circlepath") {TaskCard(task:task,embedded:true)}
                }
            }
        }
        .onAppear(perform:store.checkConverter)
        .onDrop(of:[UTType.fileURL],isTargeted:$dropTargeted) {providers in
            guard !busy else {return false}
            let group=DispatchGroup();let urls=DroppedURLs()
            for provider in providers {group.enter();_ = provider.loadObject(ofClass:URL.self){url,_ in if let url{urls.append(url)};group.leave()}}
            group.notify(queue:.main){store.addConversionFiles(urls.result())};return true
        }
    }
    private var backend:some View {
        GlassPanel {
            HStack(spacing:10) {
                Image(systemName:"key").foregroundStyle(WorkspacePalette.accent)
                Text(L(store.converterStatus?.keysReady == true ? "转换密钥已就绪" : "尚未准备转换密钥")).font(.callout)
                Spacer()
                if store.checkingConverter {ProgressView().controlSize(.small)}
                Button(L("导入转换密钥…")){store.chooseConversionKeys()}.disabled(busy || store.checkingConverter).controlSize(.small)
            }
            CompactDisclosure(title:"转换工具",subtitle:"NSC_BUILDER · nsz",symbol:"shippingbox") {
                HStack {
                    StatusPill(title:store.converterStatus?.conversionReady == true ? "格式转换就绪" : "格式转换后端未就绪",symbol:store.converterStatus?.conversionReady == true ? "checkmark.circle" : "exclamationmark.circle",color:store.converterStatus?.conversionReady == true ? WorkspacePalette.accent : .orange)
                    StatusPill(title:store.converterStatus?.compressionReady == true ? "压缩解压就绪" : "压缩解压后端未就绪",symbol:store.converterStatus?.compressionReady == true ? "checkmark.circle" : "exclamationmark.circle",color:store.converterStatus?.compressionReady == true ? WorkspacePalette.accent : .orange)
                    Spacer()
                    Button(L("重新检查"),action:store.checkConverter).disabled(store.checkingConverter).controlSize(.small)
                }
                Text(L("SAK-Mac 转换后端与依赖已内置，无需额外安装 Python、Xcode 或 nxnative。导入自己的密钥后即可转换。")).font(.caption).foregroundStyle(.secondary)
                if store.converterStatus?.keysReady == true {Text(L(store.converterStatus?.keySource ?? "")).font(.caption).foregroundStyle(.secondary)}
                Text(L("转换功能参考 SAK-Mac，内置 NSC_BUILDER / nsz；第三方来源与许可可在设置中查看。")).font(.caption).foregroundStyle(.secondary)
                Link(L("SAK-Mac 项目"),destination:URL(string:"https://github.com/ggaoph-lab/SAK-Mac")!)
            }
            if let status=store.converterStatus,!(store.conversion.mode == .compress || store.conversion.mode == .decompress ? status.compressionReady : status.conversionReady) {
                Label(L("当前转换工具未就绪，请展开检查。"),systemImage:"exclamationmark.circle").font(.caption).foregroundStyle(.orange)
            }
        }
    }
}
