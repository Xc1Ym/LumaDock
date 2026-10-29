# LumaNX 0.2.18

## Changes

- **A calmer Liquid Glass interface.** The game library, conversion and settings pages now share one set of glass controls. The library drops the preparation-flow banner and places library counts and search on one capsule row; game details are expanded by default above **Manage game**, with tighter version and import-content layout.
- **Conversion on one row.** Output format, output location and the start button share a row. Supported input formats follow the selected operation; key import and recheck move into a **More tools** menu, and prompts appear only when a prerequisite is missing.
- **Delete finished task records.** Task cards are narrower, diagnostics are collapsed by default, and details, log and copy actions sit on one row. A new **Delete** button removes only the record of a finished task — logs and generated files are kept — and stale catalog responses or late events cannot restore a deleted record. Running, queued or cancelling tasks stay protected.
- **Settings in one layer.** Environment checks flatten to a single expandable section, the manual Xcode path field is removed (pick Xcode.app or run **Recheck** instead), the first-run wizard sits next to recheck, keyboard/mouse and controller mapping get their own panel, and About plus open-source licenses are shown directly.
- **Reduced-transparency fallback preserved** for every new glass surface, and all new wording ships with English translations.
- **Updated bundled engine.** Includes nxnative `8325eefbc68a935c5f684d4fbdff571e2540b4b4`, with worker support for the upstream split Metal tool lock interface.

## Installation and validation

Download **LumaNX-0.2.18-arm64.dmg** and verify the SHA-256 below. Quit the app and active tasks before replacing the application. The application identifier and existing libraries, saves and settings are retained.

Requires Apple Silicon and macOS 26+. Uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

The release workflow runs Python and Swift regression tests, native controller and engine checks, Metal diagnostics, unsigned synthetic iOS packaging, portable runtime bundling, app signing, DMG/source audits and runtime relocation before publishing the DMG. These checks do not establish full-game or iOS-device compatibility. This release does not include the separate upstream Chinese-language compatibility PR. No games, keys, firmware or player data are included; bundled dependencies retain their licenses.

---

## 中文说明

- **更安静的液态玻璃界面。** 游戏库、转换和设置页统一一套玻璃控件。游戏库移除准备流程条，统计数量与搜索共用一行胶囊；游戏详情默认展开、置于“管理游戏”上方，版本与导入内容排版更紧凑。
- **转换操作一行完成。** 输出格式、输出位置和开始按钮同行排列；按所选操作显示支持的输入格式；密钥导入与重新检查收进“更多工具”菜单，仅在缺少条件时提示。
- **可删除已结束的任务记录。** 任务卡片更窄，诊断默认折叠，详情、日志与复制操作同行。新增“删除”按钮仅移除已结束任务的记录，保留日志与生成文件；旧目录响应或迟到事件无法恢复已删除的记录，运行中、排队与取消中的任务仍受保护。
- **设置压成一层。** 环境检查合并为单个可展开区域，移除手工 Xcode 路径输入（改用“选择 Xcode.app…”与“重新检查”），首次运行向导与重新检查并列，键鼠与手柄映射独立成栏，关于与开源许可直接展示。
- **保留减少透明度回退。** 所有新增玻璃表面在“减少透明度”下保持非透明回退，新增文案均附英文翻译。
- **同步内置引擎。** 包含 nxnative `8325eefbc68a935c5f684d4fbdff571e2540b4b4`，工作进程已适配上游拆分后的 Metal 工具锁接口。

下载 **LumaNX-0.2.18-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换应用。应用标识、现有游戏库、存档与设置保持兼容。

要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

标签流水线在发布前完成 Python/Swift 回归、原生手柄与引擎检查、Metal 诊断、合成未签名 iOS 包、运行库封装、应用签名、DMG/源码审计及搬移校验。这些检查不代表完整游戏或 iOS 真机验收。本次不包含单独提交给上游的中文语言兼容 PR。不附带游戏、密钥、固件或玩家数据，内置依赖保留各自许可。
