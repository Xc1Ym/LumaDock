# LumaNX 0.2.14

## Changes

- **Updated bundled engine.** Synchronize nxnative from `c484b13c` to `40e6baede556acd454169ac75b33d1686063f528`, retaining LumaNX's native controller mapping. Includes fixes for unaligned NVN vertex streams on Metal, separation of scripted and physical controller input, and audio layout detection, plus updated engine profiles and regression tools.
- **Shader compatibility follow-up (#20).** This build includes the returning IGN image-atomic and native texture-atomic support already present in 0.2.13. These address limitations reported with the older 0.2.12 translator. The latest sync does not itself prove that both shaders reported in #20 now build; the reporter's game data has not been tested here, and unsupported TRAP or predicate semantics can still fail.

## Installation and validation

Download **LumaNX-0.2.14-arm64.dmg** and verify the SHA-256 below. Quit LumaNX and active tasks before replacing the app in Applications. In Settings, select **Prepare engine tools**, then prepare affected games again to apply the updated engine. Keep your library, saves and successful caches.

Requires Apple Silicon and macOS 26+. Uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

The synchronized engine passed the complete CI workflow before entering main: Python and Swift regression tests, native controller and engine checks, Metal diagnostics, unsigned synthetic iOS packaging, portable runtime bundling, app signing, DMG validation, source audits and runtime relocation. The release tag workflow repeats these checks before publishing this version's DMG.

Validation uses synthetic fixtures and compile checks; it does not establish real-game compatibility, physical-controller behavior, iOS device behavior, power-loss recovery or removable-media disconnect handling. No games, keys, firmware or player data are included. Bundled dependencies retain their licenses.

---

## 中文说明

- **同步上游引擎。** nxnative 从 `c484b13c` 更新至 `40e6baede556acd454169ac75b33d1686063f528`，保留璃游的原生手柄映射。包含 Metal 上未对齐 NVN 顶点流处理、脚本输入与实体手柄状态分离、音频布局检测等修复，并更新引擎配置和回归工具。
- **跟进着色器兼容性（#20）。** 本版本包含 v0.2.13 已引入的带返回值 IGN image atomics 及原生纹理原子操作支持，针对 v0.2.12 旧转换器的相关限制。本次同步不代表已确认 #20 报告的两个着色器均可构建：尚未使用报告者的游戏数据复测，不支持的 TRAP 或谓词语义仍可能失败。

下载 **LumaNX-0.2.14-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换“应用程序”中的副本。在设置中执行“准备引擎工具”，再重新准备受影响的游戏，以应用新引擎。保留游戏库、存档和成功缓存。

要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

同步引擎已通过完整 CI 后进入 main：包括 Python 与 Swift 回归、原生手柄和引擎检查、Metal 诊断、合成未签名 iOS 包、可搬移运行库封装、应用签名、DMG 校验、源码清单审计及运行库搬移。版本标签流水线将再次完成这些检查后发布当前版本 DMG。

验证使用合成数据和编译检查，不代表真实游戏、实体手柄、iOS 真机、断电或外置盘断开验收。不附带游戏、密钥、固件或玩家数据，内置依赖保留各自许可。
