# LumaDock 0.2.11

## Changes

- **Save backups and runtime rollback.** Create verified save snapshots, restore a selected backup, and switch between prepared runtime versions. Restore and version switching back up current saves first; version switching does not restore old saves automatically. Recovery is serialized with gameplay and preparation, and retries stay bound to their original library.
- **Safe shared-file cleanup.** Keep managed containers referenced by other games, including hidden entries. Cache cleanup refuses symbolic links that could reach saves or backups.
- **Bundled nxnative and native controllers.** Include nxnative revision `c4b74a62f926e1c5bff71b50d7fae9d6340ddf08`, its translator, metadata reader and third-party notices. Packaged apps prepare the bundled tools offline without installing the .NET SDK. Native GameController input maps Switch Pro A / Xbox A / PlayStation cross to game A on Mac and iOS. Prepare existing games again to apply the new host.
- **Compact game details and environment checks.** Use smaller import cards, keep the launch-language selector on one line, and show IPA requirements on hover. Failed checks remain visible; passed checks are collapsed by default.
- **Tested daily engine synchronization.** Import upstream sources daily at 03:00 Asia/Shanghai, reapply controller rules, and update the repository only after full CI passes. Interface changes, failures or a changed main branch retain the previous engine. Daily synchronization does not publish a Release.

## Installation and validation

Download **LumaDock-0.2.11-arm64.dmg** and verify its SHA-256 below. Quit LumaDock and active tasks before replacing the app in Applications. Requires Apple Silicon and macOS 26+. The app uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

After upgrading, choose **Prepare engine tools** in Settings, then prepare existing games again for the new controller behavior. Save backups and runtime versions are available from game details.

The combined changes pass **190 Python tests**. Release validation also covers Swift Release tests, native controller snapshots, engine host tests and compilation, iOS source compilation, real Metal diagnostics, unsigned synthetic IPA packaging, signatures, distribution boundaries and runtime relocation. The tag workflow rebuilds and validates the DMG before publishing it; public Release assets contain only the DMG.

**Validation limits:** synthetic input and compile checks do not establish physical-controller behavior, real-game compatibility, iOS device behavior, power-loss recovery or removable-media disconnect handling. No games, updates, DLC, firmware, player keys, artwork, saves, backups or player caches are included. The bundled engine and dependencies retain their licenses.

---

## 中文说明

- **存档备份与运行版本回退。** 创建并校验存档快照，恢复指定备份，或切换已准备的运行版本。恢复和版本切换前自动备份当前存档；切换运行版本不会自动回退存档。恢复与游戏运行、准备任务互斥，重试限定在原游戏库内。
- **安全清理共享文件。** 保留其他游戏（含隐藏条目）仍引用的托管容器；拒绝通过符号链接清理存档或备份。
- **内置引擎与原生手柄。** 内置 nxnative 固定版本 `c4b74a62f926e1c5bff71b50d7fae9d6340ddf08`、翻译器、读取器及第三方许可。安装包可离线准备工具，无需另装 .NET SDK。Mac/iOS 共用原生 GameController 规则：Switch Pro A / Xbox A / PS 叉键对应游戏 A。已有游戏需重新准备一次以更新宿主。
- **精简界面。** 压缩导入内容卡片，启动语言保持单行，IPA 要求移至悬停提示。异常环境检查直接显示，通过项默认折叠。
- **每日同步并验证引擎。** 每天北京时间 03:00 导入上游源码、重新应用手柄规则，通过完整 CI 后才更新仓库。接口变化、验证失败或 main 已变化时保留旧引擎。每日同步不发布 Release。

下载 **LumaDock-0.2.11-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换“应用程序”中的副本。要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

升级后在设置中选择“准备引擎工具”，再为已有游戏重新准备以应用手柄规则。游戏详情提供存档备份与运行版本管理。

整合后通过 **190 项 Python 测试**。发行验证还覆盖 Swift Release、原生手柄快照、引擎宿主测试与编译、iOS 源码编译、实际 Metal 诊断、合成未签名 IPA、签名、分发边界及运行库搬移。标签流水线重新构建并验证后才发布 DMG；Release 只附带 DMG。

**验证范围：** 合成输入和编译检查不代表实体手柄、真实游戏、iOS 真机、断电或外置盘断开验收。不附带游戏、更新、DLC、固件、玩家密钥、封面、存档、备份或玩家缓存，内置引擎及依赖保留各自许可。
