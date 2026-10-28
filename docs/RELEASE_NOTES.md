# LumaNX 0.2.17

## Changes

- **A quieter game sidebar.** Ready games show their running version and launch action. Expand **Manage game** for launch language, keyboard/mouse/controller mapping, save backups and version rollback, the save folder, preparation, IPA export, and cleanup/removal. Technical identifiers, compatibility and imported content are in a separate collapsed **Game details** section.
- **Launch language in one row.** Choosing a language shows a brief confirmation for the next launch. Repeated changes restart the toast timer; reselecting the current value does not save or notify again.
- **macOS keyboard shortcuts.** ⌘Q quits the application, including from setup, mapping and recovery sheets; ⌘, opens Settings; ⌘O adds games; ⇧⌘K imports keys; ⌘R refreshes the library; ⌘1/2/3 switches between Library, File conversion and Preparation tasks.
- **Automatic bundled-engine initialization.** The packaged engine and reader initialize their private cache on first use. Manual repair remains under **More tools → Repair bundled engine**. Failed initialization does not retry in a loop.
- **Native controller build check.** Includes the main-branch correction that links the controller regression harness with its upstream motion dependencies.

## Installation and validation

Download **LumaNX-0.2.17-arm64.dmg** and verify the SHA-256 below. Quit the app and active tasks before replacing the application. The application identifier and existing libraries, saves and settings are retained.

Requires Apple Silicon and macOS 26+. Uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

The release workflow runs Python and Swift regression tests, native controller and engine checks, Metal diagnostics, unsigned synthetic iOS packaging, portable runtime bundling, app signing, DMG/source audits and runtime relocation before publishing the DMG. These checks do not establish full-game or iOS-device compatibility. This release does not include the separate upstream Chinese-language compatibility PR. No games, keys, firmware or player data are included; bundled dependencies retain their licenses.

---

## 中文说明

- **重新设计游戏详情。** 已准备游戏默认显示运行版本和启动按钮；展开“管理游戏”后统一访问启动语言、键鼠与手柄映射、存档备份与版本回滚、存档目录、重新检查并准备、IPA 导出及清理移除。Title ID、兼容性和导入内容收进独立、默认折叠的“游戏详情”。
- **语言选择保持单行。** 修改后通过短暂提示告知下次启动生效，连续修改会重新计时；重复选择当前语言不会再次保存或提示。
- **增加键盘快捷键。** ⌘Q 完全退出，包括向导、映射与恢复窗口；⌘, 打开设置；⌘O 添加游戏；⇧⌘K 导入密钥；⌘R 刷新游戏库；⌘1/2/3 切换游戏库、文件转换和准备任务。
- **内置引擎自动初始化。** 安装包首次使用时自动初始化私有引擎与读取器缓存，手动修复收进“更多工具 → 修复内置引擎”；初始化失败不会循环重试。
- **修复原生手柄构建检查。** 包含主线对手柄回归程序的链接修正，补齐上游运动输入依赖。

下载 **LumaNX-0.2.17-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换应用。应用标识、现有游戏库、存档与设置保持兼容。

要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

标签流水线在发布前完成 Python/Swift 回归、原生手柄与引擎检查、Metal 诊断、合成未签名 iOS 包、运行库封装、应用签名、DMG/源码审计及搬移校验。这些检查不代表完整游戏或 iOS 真机验收。本次不包含单独提交给上游的中文语言兼容 PR。不附带游戏、密钥、固件或玩家数据，内置依赖保留各自许可。
