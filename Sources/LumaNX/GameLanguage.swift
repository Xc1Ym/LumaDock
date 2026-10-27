import Foundation

// Switch language codes passed unchanged to nxnative's GetDesiredLanguage hook.
// Keep these separate from AppLanguage, which controls only the launcher UI.
enum GameLanguage: String, CaseIterable, Identifiable {
    case simplifiedChinese = "zh-Hans", traditionalChinese = "zh-Hant"
    case englishUS = "en-US", englishUK = "en-GB", japanese = "ja", korean = "ko"
    case french = "fr", frenchCanadian = "fr-CA", german = "de", italian = "it"
    case spanish = "es", spanishLatinAmerica = "es-419", dutch = "nl"
    case portuguese = "pt", portugueseBrazilian = "pt-BR", russian = "ru"
    case chineseChina = "zh-CN", chineseTaiwan = "zh-TW"
    var id: String { rawValue }
    var name: String {
        switch self {
        case .simplifiedChinese: return L("简体中文")
        case .traditionalChinese: return L("繁體中文")
        case .englishUS: return L("英语（美国）")
        case .englishUK: return L("英语（英国）")
        case .japanese: return L("日语")
        case .korean: return L("韩语")
        case .french: return L("法语")
        case .frenchCanadian: return L("法语（加拿大）")
        case .german: return L("德语")
        case .italian: return L("意大利语")
        case .spanish: return L("西班牙语")
        case .spanishLatinAmerica: return L("西班牙语（拉丁美洲）")
        case .dutch: return L("荷兰语")
        case .portuguese: return L("葡萄牙语")
        case .portugueseBrazilian: return L("葡萄牙语（巴西）")
        case .russian: return L("俄语")
        case .chineseChina: return L("中文（中国，旧版代码）")
        case .chineseTaiwan: return L("中文（台湾，旧版代码）")
        }
    }
}
