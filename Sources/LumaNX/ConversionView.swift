import SwiftUI
import UniformTypeIdentifiers

struct ConversionView:View {
    @EnvironmentObject var store:Store
    @State private var dropTargeted=false
    private var busy:Bool {store.executionBusy || store.importingConversionKeys || !store.queue.isEmpty}
    private var supportedFormats:String {
        ["nsp","xci","nsz","xcz"].filter{store.conversion.mode.extensions.contains($0)}.map{$0.uppercased()}.joined(separator:" / ")
    }
    var body:some View {
        WorkspacePage {
            WorkspaceHeading(title:"文件转换",subtitle:"",symbol:"doc.zipper") {
                StatusPill(title:L("共 \(store.conversion.paths.count) 个文件"),symbol:"doc.on.doc",color:.secondary)
                Menu {
                    Button(L("导入转换密钥…")){store.chooseConversionKeys()}.disabled(busy || store.checkingConverter)
                    Button(L("重新检查"),action:store.checkConverter).disabled(store.checkingConverter)
                } label:{Label(L("更多工具"),systemImage:"ellipsis.circle").labelStyle(.iconOnly)}
                    .menuStyle(.borderlessButton).fixedSize().help(L("更多工具"))
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
                        Text(L("拖入文件，或点击添加文件。")).font(.callout).foregroundStyle(.secondary)
                        Text(L("支持的格式：\(supportedFormats)")).font(.caption).foregroundStyle(.secondary)
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
                    Text(L("请选择同一游戏的本体、更新或 DLC。")).font(.caption).foregroundStyle(.secondary)
                }
                if !store.conversion.paths.isEmpty && !store.conversion.validSelection {
                    Label(L("所选文件格式与转换操作不匹配。"),systemImage:"exclamationmark.circle").font(.caption).foregroundStyle(.orange)
                }
                Divider()
                HStack(alignment:.bottom,spacing:16) {
                    if store.conversion.mode == .convert || store.conversion.mode == .merge {
                        VStack(alignment:.leading,spacing:6) {
                            Text(L("输出格式")).font(.caption).foregroundStyle(.secondary)
                            Picker(L("输出格式"),selection:$store.conversion.target) {Text("NSP").tag("nsp");Text("XCI").tag("xci")}
                                .pickerStyle(.segmented).labelsHidden().controlSize(.large).frame(width:140)
                        }
                    }
                    if store.conversion.mode == .compress {
                        Stepper(L("压缩等级：\(store.conversion.level)"),value:$store.conversion.level,in:1...22).fixedSize()
                        Toggle(L("压缩后校验"),isOn:$store.conversion.verify).toggleStyle(.switch).controlSize(.small)
                    }
                    VStack(alignment:.leading,spacing:6) {
                        Text(L("输出位置")).font(.caption).foregroundStyle(.secondary)
                        Button(action:store.chooseConversionOutput) {
                            HStack(spacing:8) {
                                Image(systemName:"folder").foregroundStyle(WorkspacePalette.accent)
                                Text((store.conversion.outputDirectory as NSString).abbreviatingWithTildeInPath)
                                    .foregroundStyle(.primary).lineLimit(1).truncationMode(.middle)
                                Spacer(minLength:0)
                                Image(systemName:"ellipsis").foregroundStyle(.secondary)
                            }.padding(.horizontal,12).frame(maxWidth:.infinity,minHeight:32,alignment:.leading).glassSurface(12)
                        }.buttonStyle(.plain)
                            .help(store.conversion.outputDirectory)
                            .accessibilityLabel(L("输出位置")).accessibilityValue(store.conversion.outputDirectory)
                    }.frame(minWidth:180,maxWidth:.infinity)
                    Button(L("开始转换")){store.startConversion()}.buttonStyle(.glassProminent).controlSize(.large)
                        .disabled(!store.conversion.validSelection || store.converterStatus?.ready(for:store.conversion.mode) != true || busy)
                }
                Text(L("每次转换会在所选位置新建结果文件夹。")).font(.caption).foregroundStyle(.secondary)
                conversionRequirements
            }.disabled(busy)
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
    @ViewBuilder private var conversionRequirements:some View {
        if store.checkingConverter {
            ProgressView(L("正在检查转换工具…")).controlSize(.small).font(.caption)
        } else if let status=store.converterStatus {
            if !status.keysReady {
                HStack {
                    Label(L("尚未准备转换密钥"),systemImage:"key").font(.caption).foregroundStyle(.orange)
                    Spacer()
                    Button(L("导入转换密钥…")){store.chooseConversionKeys()}.controlSize(.small)
                }
            }
            if !(store.conversion.mode == .compress || store.conversion.mode == .decompress ? status.compressionReady : status.conversionReady) {
                HStack {
                    Label(L("转换工具未就绪"),systemImage:"exclamationmark.circle").font(.caption).foregroundStyle(.orange)
                    Spacer()
                    Button(L("重新检查"),action:store.checkConverter).controlSize(.small)
                }
            }
        }
    }
}
