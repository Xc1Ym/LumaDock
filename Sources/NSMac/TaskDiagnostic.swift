import Foundation

struct TaskDiagnostic: Codable, Identifiable, Equatable {
    var code: String
    var severity: String
    var summary: String
    var suggestion: String
    var detail: String
    var stage: String?
    var logPath: String?
    var component: String?
    var exitCode: Int?
    var id: String { code + "|" + (logPath ?? "") + "|" + (stage ?? "") + "|" + summary }
    var isWarning: Bool { severity == "warning" }
    static func redact(_ text: String, paths: [(String,String)]) -> String {
        var result=text.replacingOccurrences(of:#"(?i)(authorization\s*:\s*(?:bearer|basic|token)\s+)\S+"#,with:"$1[REDACTED]",options:.regularExpression)
        result=result.replacingOccurrences(of:#"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"#,with:"$1[REDACTED]@",options:.regularExpression)
        result=result.replacingOccurrences(of:#"(?i)([\w-]*(?:key|secret|token|password)[\w-]*\s*[=:]\s*)["']?[^\s,;"']+"#,with:"$1[REDACTED]",options:.regularExpression)
        result=result.replacingOccurrences(of:#"\b[0-9a-fA-F]{64,}\b"#,with:"[REDACTED]",options:.regularExpression)
        for (path,label) in paths where !path.isEmpty {result=result.replacingOccurrences(of:path,with:label)}
        return String(result.suffix(3000))
    }
    var reportText: String {
        var lines = [L(summary), L("错误代码：") + code]
        if let stage, !stage.isEmpty { lines.append(L("失败阶段：") + L(stage)) }
        if let component { lines.append(L("组件：") + component) }
        if let exitCode { lines.append(L("退出码：") + String(exitCode)) }
        lines.append(L("建议处理：") + L(suggestion))
        if !detail.isEmpty { lines.append(detail) }
        return lines.joined(separator:"\n")
    }
}
