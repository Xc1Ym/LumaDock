# LumaDock 0.2.13

## Changes

- **Compact utility pages.** Refresh Settings, Conversion, Tasks, first-run setup, input mapping, and save recovery with compact Liquid Glass cards. Keep current progress, failed tasks and warnings visible while collapsing history and advanced details.
- **Clearer environment tools.** Share the setup and Settings action group, group Xcode and Metal actions under More Tools, and improve button contrast and pressed feedback. Preserve disabled conditions and the Metal uninstall confirmation.
- **Reliable package protection tests.** Compile a small native helper for the running-app test instead of copying a macOS platform binary. App replacement protection and packaging behavior remain unchanged.

## Installation and validation

Download **LumaDock-0.2.13-arm64.dmg** and verify the SHA-256 below. Quit LumaDock and active tasks before replacing the app in Applications. Requires Apple Silicon and macOS 26+. Uses **ad-hoc signing and is not notarized**. Game preparation requires full Xcode with Metal; IPA export also requires the iOS platform and XcodeGen.

The reviewed changes passed 65 Swift tests and 192 Python tests locally. Both PR workflows passed their complete build and package checks before merging. The release tag workflow rebuilds and validates the combined source, signatures, distribution boundaries and runtime relocation before publishing the DMG.

Validation uses synthetic fixtures and compile checks; it does not establish real-game compatibility, physical-controller behavior, iOS device behavior, power-loss recovery or removable-media disconnect handling. No games, keys, firmware or player data are included. Bundled dependencies retain their licenses.

---

## 中文说明

- **精简辅助页面。** 设置、转换、任务、首次运行向导、输入映射及存档恢复统一为紧凑的液态玻璃卡片。当前进度、失败任务及警告保持可见，历史记录和高级信息默认折叠。
- **整理环境工具。** 设置与向导共用操作组件，Xcode 和 Metal 操作归入“更多工具”，改善按钮对比度和按下反馈，保留禁用条件及 Metal 卸载确认。
- **稳定打包保护测试。** 运行中应用测试改用现场编译的原生助手，避免复制 macOS 系统二进制造成不稳定；应用替换保护及打包行为保持不变。

下载 **LumaDock-0.2.13-arm64.dmg**，按下方 SHA-256 校验，退出应用及任务后替换“应用程序”中的副本。要求 Apple Silicon、macOS 26 及以上；采用临时签名，尚未公证。准备游戏需完整 Xcode 与 Metal，导出 IPA 另需 iOS 平台与 XcodeGen。

已审查改动在本机通过 65 项 Swift 测试及 192 项 Python 测试；两个 PR 的完整构建与打包 CI 均在合并前通过。标签流水线重新构建并校验合并后的源码、签名、分发边界和运行库搬移后发布 DMG。

验证使用合成数据和编译检查，不代表真实游戏、实体手柄、iOS 真机、断电或外置盘断开验收。不附带游戏、密钥、固件或玩家数据，内置依赖保留各自许可。
