# LumaNX 0.2.16

## Changes

- **Updated bundled nxnative engine.** Includes upstream fixes for shader compilation and pipeline archive recovery, texture and geometry handling, shader-cache reuse, controller motion and haptics, audio and presentation. Updated from `40e6baede556` to `76c545320666`; the full revision is recorded in `Engine/nxnative/manifest.json`.
- **Restored daily engine verification (PR #23).** The native controller harness now links IOKit, supplies the motion callbacks and monotonic clock required by the new front end, and checks motion cleanup on focus loss and disconnect. Candidate engines still pass the complete verification workflow before being imported.
- **Existing controller mapping retained.** The LumaNX Nintendo / Xbox / PlayStation face-button policy is reapplied to the updated engine.
- **Kept extraction compatible with the launcher.** New upstream image requests use the reader's supported directory mode for launcher preparation and IPA export; base, update and DLC selection still uses exact content metadata. The reader adapter also accepts the upstream application filter. Regression tests exercise the bundled extraction stages with synthetic data.

## Installation and validation

Download **LumaNX-0.2.16-arm64.dmg** and verify the SHA-256 below. Quit the app and active tasks before replacing the app in Applications. Keep your library, saves and successful caches; prepare the updated engine tools and reprepare affected games to use the new engine.

Requires Apple Silicon and macOS 26+. Uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

The candidate-build and release-tag workflows gate publication on Python and Swift regression tests, native controller and engine checks, Metal diagnostics, unsigned synthetic iOS packaging, portable runtime bundling, app signing, DMG validation, source audits and runtime relocation. The published DMG is taken from the successful release-tag build.

Validation uses synthetic fixtures and compile checks; it does not establish real-game compatibility, physical-controller behavior or iOS device behavior. No games, keys, firmware or player data are included. Bundled dependencies retain their licenses.

---

## 中文说明

- **更新内置 nxnative 引擎。** 纳入上游着色器编译与管线归档恢复、纹理和几何处理、着色器缓存复用、手柄体感与震动、音频及画面呈现等改动。引擎从 `40e6baede556` 更新至 `76c545320666`，完整版本记录在 `Engine/nxnative/manifest.json`。
- **恢复每日引擎验证（PR #23）。** 原生手柄测试补齐 IOKit 链接、体感回调与单调时钟，并检查失焦和断连时的体感清理。候选引擎仍需通过完整验证流程才能同步入库。
- **保留现有手柄映射。** 更新引擎后继续应用 LumaNX 的 Nintendo / Xbox / PlayStation 面键规则。
- **适配新版提取接口。** 启动器准备和 IPA 导出继续使用读取器支持的目录模式，兼容上游的新镜像请求；主游戏、更新和 DLC 仍按准确内容元数据选择。读取器适配同时兼容上游新增的应用类型过滤，并以合成数据调用内置引擎提取阶段进行回归验证。

下载 **LumaNX-0.2.16-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换“应用程序”中的副本。保留游戏库、存档和成功缓存；准备更新后的引擎工具，并重新准备受影响游戏以使用新版引擎。

要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

候选构建和版本标签流水线以 Python / Swift 回归、原生手柄与引擎检查、Metal 诊断、合成未签名 iOS 包、可搬移运行库封装、应用签名、DMG 校验、源码审计及运行库搬移作为发布门禁；公开 DMG 来自成功的版本标签构建。

验证使用合成数据和编译检查，不代表真实游戏、实体手柄或 iOS 真机验收。不附带游戏、密钥、固件或玩家数据，内置依赖保留各自许可。
