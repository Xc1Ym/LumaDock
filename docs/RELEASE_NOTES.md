# LumaDock 0.2.9

## Changes

- **Restore Add games (#13).** Fix the #8 regression that sent XCI/NSZ/XCZ selections to the independent File conversion page. Adding files or scanning a mixed-format folder now continues through library import and automatic preparation when required content is available and automatic preparation is enabled.
- **Read XCI directly.** NSP and XCI are passed directly to the compatible nxnative reader. Managed copies retain their original container extension; XCI is not repacked into NSP. Only NSZ/XCZ archives are automatically decompressed into temporary NSP/XCI files before import, using the library key.
- **Preserve task controls.** Automatic decompression reports progress, can wait for an active build or game to finish, and supports cancellation and retry. Temporary output is cleaned up. Independent file conversion keeps its own settings and keys.

## Installation and validation

Download **LumaDock-0.2.9-arm64.dmg**, verify `SHA256SUMS`, and drag **LumaDock.app** into Applications. Requires Apple Silicon and macOS 26+. Packages use **ad-hoc signing and are not notarized**. Preparation requires full Xcode, Metal and a compatible external nxnative engine; IPA export also requires the iOS platform and XcodeGen.

The import fix passed **122 Python tests and 60 Swift Release tests**, plus the PR's complete CI build, real Metal diagnostics, unsigned UIKit IPA validation, package/signature checks and runtime relocation. An isolated app verified that a synthetic mixed XCI/XCZ folder proceeds from import to preparation and a ready library entry. The tag workflow rebuilds and validates all assets before publishing them.

**Validation limits:** UI and import tests use synthetic containers with metadata/compiler test doubles. They do not establish successful commercial-game decryption, compilation, gameplay or physical iOS compatibility. The previously documented newer-nxnative NVN IPA C1 inputs-stamp issue is not addressed by this update.

No engine, games, updates, DLC, firmware, player keys, game artwork, saves or player caches are included. Thanks to nxnative, MacNativeGames, d2r-mobile, SAK-Mac, S2Arm and their contributors; full notices remain in the bundled documentation.

---

## 中文说明

- **恢复添加游戏流程（#13）。** 修复 #8 将 XCI/NSZ/XCZ 选择直接转交独立“文件转换”页的问题。添加文件或扫描混合格式文件夹后继续入库；所需内容齐全且开启自动准备时，自动开始编译。
- **直接读取 XCI。** NSP、XCI 直接交给兼容的 nxnative 读取器，托管副本保留原容器扩展名，不将 XCI 重新封装为 NSP。仅 NSZ/XCZ 使用游戏库密钥自动解压为临时 NSP/XCI 后导入。
- **保留任务控制。** 自动解压显示进度，可等待已有构建或游戏结束，支持取消、重试及临时产物清理。独立文件转换保留自己的设置和密钥。

下载 **LumaDock-0.2.9-arm64.dmg**，核对 `SHA256SUMS` 后拖入“应用程序”。需要 Apple Silicon、macOS 26 及以上。安装包采用 **ad-hoc 签名，尚未公证**。游戏准备仍需完整 Xcode、Metal 和兼容的外部引擎；IPA 导出还需 iOS 平台与 XcodeGen。

导入修复通过 **122 项 Python、60 项 Swift Release 测试**，以及 PR 的完整 CI 构建、真实 Metal 诊断、原创 UIKit 未签名 IPA 校验、安装包和签名校验、运行时搬移检查。独立测试应用实际验证合成 XCI/XCZ 混合目录从导入自动进入准备，最终游戏库显示可启动。版本标签流水线会在公开附件前重新执行完整构建与校验。

**验证范围：** 界面和导入测试使用原创合成容器，元数据读取及编译由测试替身提供，不代表商业游戏解密、编译、游玩或实体 iOS 兼容性验收。本版未处理此前记录的新版 nxnative NVN IPA C1 inputs 标记兼容问题。

项目不附带引擎、游戏、更新、DLC、固件、玩家密钥、游戏封面、存档或玩家缓存。感谢 nxnative、MacNativeGames、d2r-mobile、SAK-Mac、S2Arm 及贡献者；完整致谢与许可保留在随包文档中。
