# LumaNX 0.2.19

## Changes

- **Updated bundled engine.** Includes nxnative `710559cf53d2b9037f48b44f515e940f71b51f2b`, which adds Subnautica: Below Zero (`010014C011146000`) — tested on Apple Silicon Mac at 30 fps through the title, menu, new Survival game, hangar opening and the crash site; upstream notes one audio-device stall at the landing — and extends registered-shader decoding: Criterion `bnd2` bundles (Need for Speed: Hot Pursuit Remastered reads its ~2,112 GLSLC outputs from `SHADERS.BNDL`) and refreshed per-game shader tables across 211 profiles.
- **Decoders prepared for registered shader builds.** The conversion worker builds the game decoders a profile registers for its shader toolchain, with regression tests for repeated profile derivation.
- **Stricter daily-sync patch anchors.** The sync's SDK compatibility patch now fails loudly when upstream reformats the guarded phone-motion interface (previously it silently skipped), and worker import search paths are deduplicated across repeated derivations.

## Installation and validation

Download **LumaNX-0.2.19-arm64.dmg** and verify the SHA-256 below. Quit the app and active tasks before replacing the application. The application identifier and existing libraries, saves and settings are retained.

Requires Apple Silicon and macOS 26+. Uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

The release workflow runs Python and Swift regression tests, native controller and engine checks, Metal diagnostics, unsigned synthetic iOS packaging, portable runtime bundling, app signing, DMG/source audits and runtime relocation before publishing the DMG. These checks do not establish full-game or iOS-device compatibility. No games, keys, firmware or player data are included; bundled dependencies retain their licenses.

---

## 中文说明

- **同步内置引擎。** 包含 nxnative `710559cf53d2b9037f48b44f515e940f71b51f2b`：新增 Subnautica: Below Zero（`010014C011146000`），在 Apple Silicon Mac 上以 30 fps 通过标题、菜单、新生存档、机库开场与坠机点实测；上游记录降落阶段有一次音频设备停顿。注册着色器解码扩展：Criterion `bnd2` 包（Need for Speed: Hot Pursuit Remastered 从 `SHADERS.BNDL` 读取约 2,112 个 GLSLC 输出），并刷新 211 个游戏档案的着色器表。
- **转换工作进程按档案构建注册的解码器。** 工作进程为档案注册的着色器工具链构建所需的游戏解码器，重复档案推导带回归测试。
- **每日同步补丁锚点更严格。** 同步的 SDK 兼容补丁在上游改写受保护接口的排版时会明确报错（此前会静默跳过），工作进程的导入搜索路径在重复推导下去重。

下载 **LumaNX-0.2.19-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换应用。应用标识、现有游戏库、存档与设置保持兼容。

要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

标签流水线在发布前完成 Python/Swift 回归、原生手柄与引擎检查、Metal 诊断、合成未签名 iOS 包、运行库封装、应用签名、DMG/源码审计及搬移校验。这些检查不代表完整游戏或 iOS 真机验收。不附带游戏、密钥、固件或玩家数据，内置依赖保留各自许可。
