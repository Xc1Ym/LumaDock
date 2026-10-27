import Foundation

enum AppLanguage: String, CaseIterable, Identifiable {
    case system, english = "en", simplifiedChinese = "zh-Hans"
    var id: String { rawValue }
    var name: String {
        switch self {
        case .system: return L("跟随系统")
        case .english: return "English"
        case .simplifiedChinese: return "简体中文"
        }
    }
    func resolved(preferredLanguages: [String] = Locale.preferredLanguages) -> String {
        if self != .system { return rawValue }
        for language in preferredLanguages {
            let code = language.lowercased().replacingOccurrences(of: "_", with: "-")
            if code == "zh" || code.hasPrefix("zh-") { return "zh-Hans" }
            if code == "en" || code.hasPrefix("en-") { return "en" }
        }
        return "en"
    }
}

enum AppAppearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var name: String {
        switch self {
        case .system: return L("跟随系统")
        case .light: return L("浅色")
        case .dark: return L("深色")
        }
    }
}

/// Translate presentation only. Worker records retain their canonical messages so
/// old jobs can switch language without changing cache identities or player data.
enum Localization {
    struct Entry: Decodable { let source: String; let en: String }
    private struct Pattern {
        let regex: NSRegularExpression
        let indices: [Int]
        let replacement: String
        init?(_ template: String, replacement: String) {
            let slots = try! NSRegularExpression(pattern: #"\{(\d+)\}"#)
            let ns = template as NSString
            let matches = slots.matches(in: template, range: NSRange(location:0,length:ns.length))
            guard !matches.isEmpty else { return nil }
            var pattern = "\\A", cursor = 0, indices: [Int] = []
            for match in matches {
                pattern += NSRegularExpression.escapedPattern(for: ns.substring(with:NSRange(location:cursor,length:match.range.location-cursor))) + "(.*?)"
                indices.append(Int(ns.substring(with:match.range(at:1)))!)
                cursor = NSMaxRange(match.range)
            }
            pattern += NSRegularExpression.escapedPattern(for:ns.substring(from:cursor)) + "\\z"
            self.regex = try! NSRegularExpression(pattern:pattern,options:.dotMatchesLineSeparators)
            self.indices = indices; self.replacement = replacement
        }
        func apply(_ text: String, language: String, depth: Int) -> String? {
            let ns = text as NSString
            guard let match = regex.firstMatch(in:text,range:NSRange(location:0,length:ns.length)) else { return nil }
            // Substitute from the template rather than replacing in-place: user values
            // may themselves contain braces, dollar signs, percent signs, or newlines.
            var arguments: [Int:String] = [:]
            for (group,index) in indices.enumerated() {
                arguments[index] = Localization.translate(ns.substring(with:match.range(at:group+1)),language:language,depth:depth+1)
            }
            let slots = try! NSRegularExpression(pattern:#"\{(\d+)\}"#)
            let template = replacement as NSString
            var result = "", cursor = 0
            for slot in slots.matches(in:replacement,range:NSRange(location:0,length:template.length)) {
                result += template.substring(with:NSRange(location:cursor,length:slot.range.location-cursor))
                result += arguments[Int(template.substring(with:slot.range(at:1)))!] ?? ""
                cursor = NSMaxRange(slot.range)
            }
            return result + template.substring(from:cursor)
        }
    }
    static var preference = AppLanguage.system
    static var language: String { preference.resolved() }
    static var locale: Locale { Locale(identifier:language) }
    static let entries: [Entry] = {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("LumaNX_LumaNX.bundle")
        let bundle = bundled.flatMap { Bundle(url:$0) } ?? Bundle.module
        guard let path = bundle.url(forResource:"Localizable",withExtension:"json"),
              let data = try? Data(contentsOf:path), let entries = try? JSONDecoder().decode([Entry].self,from:data) else {
            preconditionFailure("LumaNX localization resources are missing")
        }
        return entries
    }()
    private static let english = Dictionary(entries.map { ($0.source,$0.en) }, uniquingKeysWith: { first,_ in first })
    private static let chinese = Dictionary(entries.map { ($0.en,$0.source) }, uniquingKeysWith: { first,_ in first })
    private static func specificity(_ template:String) -> Int {
        template.replacingOccurrences(of:#"\{\d+\}"#,with:"",options:.regularExpression).count
    }
    private static let forward = entries.sorted { specificity($0.source) > specificity($1.source) }.compactMap { Pattern($0.source,replacement:$0.en) }
    private static let reverse = entries.sorted { specificity($0.en) > specificity($1.en) }.compactMap { Pattern($0.en,replacement:$0.source) }
    static func translate(_ text: String, language: String, depth: Int = 0) -> String {
        guard !text.isEmpty, depth < 4 else { return text }
        if language == "en" {
            if let result = english[text] { return result }
            if text.range(of:#"[\p{Han}]"#,options:.regularExpression) == nil { return text }
        } else {
            if english[text] != nil { return text }
            if let result = chinese[text] { return result }
        }
        for pattern in language == "en" ? forward : reverse {
            if let result = pattern.apply(text,language:language,depth:depth) { return result }
        }
        // Requirements and errors may combine several canonical messages.
        for separator in ["\n", "；"] where text.contains(separator) {
            let pieces = text.components(separatedBy:separator)
            let translated = pieces.map { translate($0,language:language,depth:depth+1) }
            if translated != pieces { return translated.joined(separator:separator == "；" && language == "en" ? "; " : separator) }
        }
        return text
    }
}

func L(_ text: String) -> String { Localization.translate(text,language:Localization.language) }
