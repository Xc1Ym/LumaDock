# LumaDock 0.2.8

## Changes

- **Shader preparation fix (#12).** Read newer nxnative's shared `dm/gfx/nvn/dmsh_chain.h`, with fallback to the selected game's header for older engines. This fixes the missing-header crash reported in the #9 follow-up, before shader compilation starts. Missing or invalid headers trigger one private engine-workspace rebuild before an actionable error.
- **Milestone progress and time estimates (#11).** Game preparation and IPA export show their steps, purposes, elapsed time, estimated remaining time and completion time in both the task page and global task bar. Successful uncached stages train local median estimates by game, target and toolchain. Initial timings are reference estimates; unknown totals do not produce numeric percentages. Adapted from S2Arm with its attribution and MIT notice retained.
- **Correct iOS shader progress.** Count completed iOS reflection/library pairs instead of the Mac cache, including with older per-game chain headers. A finished Mac cache no longer makes an unfinished iOS shader stage appear complete.

## Installation and validation

Download **LumaDock-0.2.8-arm64.dmg**, verify `SHA256SUMS`, and drag **LumaDock.app** into Applications. Requires Apple Silicon and macOS 26+. Packages use **ad-hoc signing and are not notarized**. Preparation requires full Xcode, Metal and a compatible external nxnative engine; IPA export also requires the iOS platform and XcodeGen.

The combined changes passed **114 Python tests and 57 Swift Release tests**, real macOS/iOS Metal checks, original unsigned UIKit IPA validation, and CI package, signature and runtime-relocation checks. Tests exercise both header layouts through actual synthetic header-generation subprocesses and iOS counting while the Mac cache is complete. The tag workflow repeats the full build and validation before publishing assets.

**Validation limits:** #9's reporter bypassed the missing-file error by copying the header, then reported 0% shader progress. Those logs do not establish successful compilation or a complete game build. Real-game preparation, gameplay and physical iOS devices have not been revalidated. Newer nxnative NVN IPA export has a separate existing C1 table inputs-stamp compatibility issue; this release does not resolve it.

No engine, games, updates, DLC, firmware, player keys, game artwork, saves or player caches are included. Thanks to nxnative, MacNativeGames, d2r-mobile, SAK-Mac, S2Arm and their contributors; full notices remain in the bundled documentation.

---

## 中文说明

- **修复着色器准备崩溃（#12）。** 优先读取新版 nxnative 的共享 `dm/gfx/nvn/dmsh_chain.h`，兼容旧版每游戏头文件，修复 #9 追评中在编译启动前发生的缺失头文件异常。缺失或无效头文件会触发一次私有引擎工作区重建，仍无效时给出明确提示。
- **里程碑进度与耗时估算（#11）。** 游戏准备和 IPA 导出显示阶段、步骤作用、已用时间、预计剩余和完成时刻，任务页与全局底栏同步。成功且未命中缓存的阶段按游戏、目标和工具链积累本机耗时中位数；初始耗时明确为参考估计，未知总量不显示数字百分比。实现参考 S2Arm，保留来源和 MIT 声明。
- **修正 iOS 着色器计数。** IPA 任务读取 iOS 产物，避免 Mac 缓存完成后提前显示 iOS 阶段完成，旧版头文件同样适用。

下载 **LumaDock-0.2.8-arm64.dmg**，核对 `SHA256SUMS` 后拖入“应用程序”。需要 Apple Silicon、macOS 26 及以上。安装包采用 **ad-hoc 签名，尚未公证**。游戏准备仍需完整 Xcode、Metal 和兼容的外部引擎；IPA 导出还需 iOS 平台与 XcodeGen。

组合版本通过 **114 项 Python、57 项 Swift Release 测试**、真实 macOS/iOS Metal 检查、原创 UIKit 未签名 IPA 校验，以及 CI 的安装包、签名与运行时搬移检查。新增回归实际启动原创头文件生成子进程，并确认 Mac 缓存完成时 iOS 进度不会提前完成。版本标签流水线会在公开附件前重新执行完整构建与校验。

**验证范围：** #9 报告者仅确认复制头文件后越过缺失文件异常，随后反馈进度停在 0%；附件不能证明编译或完整游戏准备成功。本次未重验真实游戏准备、游玩或 iOS 真机。新版 nxnative 的 NVN IPA 导出另有既存 C1 表 inputs 标记兼容问题，本版尚未处理。

项目不附带引擎、游戏、更新、DLC、固件、玩家密钥、游戏封面、存档或玩家缓存。感谢 nxnative、MacNativeGames、d2r-mobile、SAK-Mac、S2Arm 及贡献者；完整致谢与许可保留在随包文档中。
