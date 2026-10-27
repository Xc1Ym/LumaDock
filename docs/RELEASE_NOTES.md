# LumaNX 0.2.15

## Changes

- **Renamed to LumaNX (previously LumaDock).** The project, application, executable, packages and documentation now use the LumaNX name, and the bilingual screenshots have been refreshed. The original icon is unchanged.
- **In-place upgrade for existing installs.** The application identifier (`org.nsmac.launcher`), application-support data directory, game libraries, saves, settings and prepared caches are all retained; replacing the old app is enough. New conversion jobs default to a `LumaNX Conversions` output folder.
- **No engine or functional changes.** The bundled nxnative engine and the launcher's behavior are identical to 0.2.14; this release only changes names, branding and documentation.

## Installation and validation

Download **LumaNX-0.2.15-arm64.dmg** and verify the SHA-256 below. Quit the app and active tasks before replacing it in Applications. Because the bundle identifier is unchanged, LumaNX replaces LumaDock in place; keep your library, saves and successful caches.

Requires Apple Silicon and macOS 26+. Uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

This version passed the complete CI workflow before entering main: Python and Swift regression tests, native controller and engine checks, Metal diagnostics, unsigned synthetic iOS packaging, portable runtime bundling, app signing, DMG validation, source audits and runtime relocation. The release tag workflow repeats these checks before publishing this version's DMG.

Validation uses synthetic fixtures and compile checks; it does not establish real-game compatibility, physical-controller behavior, iOS device behavior, power-loss recovery or removable-media disconnect handling. No games, keys, firmware or player data are included. Bundled dependencies retain their licenses.

---

## 中文说明

- **更名为 LumaNX（原名 LumaDock）。** 项目、应用、可执行文件、安装包与文档统一改用 LumaNX 名称，并更新双语界面截图；原创图标保持不变。
- **老用户原地升级。** 应用标识（`org.nsmac.launcher`）、应用数据目录、游戏库、存档、设置与已准备缓存全部保留，直接替换旧应用即可；新任务的转换输出默认改用 `LumaNX Conversions` 目录。
- **无引擎或功能变更。** 内置 nxnative 引擎与启动器行为与 0.2.14 完全一致，本版本仅调整名称、品牌与文档。

下载 **LumaNX-0.2.15-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换“应用程序”中的副本。应用标识未变化，LumaNX 会原地替换 LumaDock；保留游戏库、存档和成功缓存。

要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

本版本已通过完整 CI 后进入 main：包括 Python 与 Swift 回归、原生手柄和引擎检查、Metal 诊断、合成未签名 iOS 包、可搬移运行库封装、应用签名、DMG 校验、源码清单审计及运行库搬移。版本标签流水线将再次完成这些检查后发布当前版本 DMG。

验证使用合成数据和编译检查，不代表真实游戏、实体手柄、iOS 真机、断电或外置盘断开验收。不附带游戏、密钥、固件或玩家数据，内置依赖保留各自许可。
