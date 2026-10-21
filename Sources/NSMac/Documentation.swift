import SwiftUI
import Foundation

enum AppGuide {
    case environment, licenses
    var title:String { self == .environment ? L("环境安装说明") : L("开源许可与版权说明") }
    func fileName(language:String)->String {
        switch self {
        case .environment:return language == "en" ? "Environment.md" : "环境要求.md"
        case .licenses:return language == "en" ? "Third-party-licenses.md" : "第三方许可.md"
        }
    }
    func url(resources:URL,language:String)->URL { resources.appendingPathComponent("docs").appendingPathComponent(fileName(language:language)) }
}

/// The bundled guides use headings, paragraphs, lists, code blocks and tables.
/// Inline Markdown uses Foundation; links remain ordinary clickable SwiftUI links.
enum GuideBlock:Equatable {
    case heading(Int,String), paragraph(String), list(String), code(String), table([String],[[String]]), rule
    private static func cells(_ line:String)->[String] {
        var values=line.split(separator:"|",omittingEmptySubsequences:false).map { $0.trimmingCharacters(in:.whitespaces) }
        if values.first == "" {values.removeFirst()};if values.last == "" {values.removeLast()}
        return values
    }
    static func parse(_ markdown:String)->[GuideBlock] {
        let lines=markdown.components(separatedBy:.newlines);var blocks:[GuideBlock]=[];var index=0
        func special(_ line:String)->Bool {line.hasPrefix("#") || line.hasPrefix("- ") || line.hasPrefix("```") || line == "---" || line.range(of:#"^\d+\. "#,options:.regularExpression) != nil}
        while index<lines.count {
            let line=lines[index].trimmingCharacters(in:.whitespaces)
            if line.isEmpty {index+=1;continue}
            if line.hasPrefix("```") {
                index+=1;var code:[String]=[]
                while index<lines.count && !lines[index].hasPrefix("```") {code.append(lines[index]);index+=1}
                blocks.append(.code(code.joined(separator:"\n")));index+=1;continue
            }
            if line == "---" {blocks.append(.rule);index+=1;continue}
            if line.hasPrefix("#") {
                let level=line.prefix(while:{$0=="#"}).count
                blocks.append(.heading(level,String(line.dropFirst(level)).trimmingCharacters(in:.whitespaces)));index+=1;continue
            }
            if line.contains("|"),index+1<lines.count {
                let separators=cells(lines[index+1])
                if !separators.isEmpty && separators.count == cells(line).count && separators.allSatisfy({$0.range(of:#"^:?-{3,}:?$"#,options:.regularExpression) != nil}) {
                    let headers=cells(line);var rows:[[String]]=[];index+=2
                    while index<lines.count && lines[index].contains("|") && !lines[index].trimmingCharacters(in:.whitespaces).isEmpty {
                        var row=cells(lines[index]);row=Array((row+Array(repeating:"",count:headers.count)).prefix(headers.count));rows.append(row);index+=1
                    }
                    blocks.append(.table(headers,rows));continue
                }
            }
            if line.hasPrefix("- ") || line.range(of:#"^\d+\. "#,options:.regularExpression) != nil {
                blocks.append(.list(line));index+=1;continue
            }
            var paragraph=[line];index+=1
            while index<lines.count {
                let next=lines[index].trimmingCharacters(in:.whitespaces)
                if next.isEmpty || special(next) || next.contains("|") {break}
                paragraph.append(next);index+=1
            }
            blocks.append(.paragraph(paragraph.joined(separator:" ")))
        }
        return blocks
    }
}

struct GuideInline:View {
    let text:String
    var body:some View {
        Text((try? AttributedString(markdown:text,options:.init(interpretedSyntax:.inlineOnlyPreservingWhitespace))) ?? AttributedString(text))
            .textSelection(.enabled).fixedSize(horizontal:false,vertical:true)
    }
}

struct DocumentationView:View {
    @EnvironmentObject var store:Store
    let guide:AppGuide
    @State private var blocks:[GuideBlock]=[]
    @State private var failed=false
    private var file:URL {guide.url(resources:store.resources,language:Localization.language)}
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            HStack {
                VStack(alignment:.leading,spacing:5) {
                    Text(guide.title).font(.title.bold())
                    Text(L("随应用提供，可离线阅读")).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button(L("在 Finder 中显示")){store.reveal(file)}.disabled(failed)
            }.padding(24)
            Divider()
            if failed {
                ContentUnavailableView {
                    Label(L("无法读取说明文件"),systemImage:"doc.questionmark")
                } description: {
                    Text(L("说明文件缺失或损坏，请重新安装完整应用。"))
                } actions: {
                    Button(L("下载完整应用")){store.repairEnvironment("reinstall")}
                }.frame(maxWidth:.infinity,maxHeight:.infinity)
            } else {
                ScrollView {
                    VStack(alignment:.leading,spacing:16) {
                        ForEach(Array(blocks.enumerated()),id:\.offset) { _,block in
                            switch block {
                            case let .heading(level,text):GuideInline(text:text).font(level==1 ? .title2.bold() : .title3.bold()).padding(.top,8)
                            case let .paragraph(text),let .list(text):GuideInline(text:text)
                            case let .code(text):Text(text).font(.callout.monospaced()).textSelection(.enabled).padding(12).frame(maxWidth:.infinity,alignment:.leading).background(.quaternary,in:RoundedRectangle(cornerRadius:10))
                            case .rule:Divider()
                            case let .table(headers,rows):
                                // Render wide documentation tables as readable native cards.
                                ForEach(Array(rows.enumerated()),id:\.offset) { _,row in
                                    VStack(alignment:.leading,spacing:10) {
                                        GuideInline(text:row[0]).font(.headline)
                                        ForEach(Array(headers.indices.dropFirst()),id:\.self) { column in
                                            VStack(alignment:.leading,spacing:3) {
                                                Text(headers[column]).font(.caption.bold()).foregroundStyle(.secondary)
                                                GuideInline(text:row[column])
                                            }
                                        }
                                    }.padding(16).frame(maxWidth:.infinity,alignment:.leading).background(.quaternary.opacity(0.6),in:RoundedRectangle(cornerRadius:12))
                                }
                            }
                        }
                    }.frame(maxWidth:1000,alignment:.leading).frame(maxWidth:.infinity,alignment:.center).padding(24)
                }
            }
        }.frame(minWidth:650,minHeight:480).tint(Brand.accent)
            .task(id:file) {
                do {blocks=GuideBlock.parse(try String(contentsOf:file,encoding:.utf8));failed=false}
                catch {blocks=[];failed=true}
            }
    }
}
