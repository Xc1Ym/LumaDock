# LumaDock 0.2.7

LumaDock is a game launcher for Apple Silicon Macs running macOS 26 or later, using a player-selected external [nxnative](https://github.com/seedds/nxnative) engine.

## Changes

- **Bundled file conversion.** Convert NSP/XCI (including NSZ/XCZ inputs), compress or decompress NSZ/XCZ, and merge one game's base, update and DLC packages. The new File conversion page uses bundled tools adapted from [SAK-Mac](https://github.com/ggaoph-lab/SAK-Mac), with NSC_BUILDER, nsz and pinned dependencies. Conversion needs your own valid keys; it does not need a separate Python, Xcode or nxnative installation. Generated NSPs can be imported into the library. (#8)
- **Protected inputs and outputs.** Conversion runs with private input/backend copies, separate conversion keys, progress, cancellation/retry, task history and log actions. Validated results are exported into a new folder without replacing existing output. Upstream licenses, dependency notices and corresponding GPL/MPL component sources are included.
- **DLC preparation fix.** Pass the engine source directory to the upstream seven-argument `extract_aoc` interface. This fixes `TypeError: extract_aoc() missing 1 required positional argument: 'logs'` during Mac preparation and IPA export. The reported exception was caused by an incorrect call; it did not establish a console/firmware version mismatch. (#9, #10)

## Installation and validation

Download **LumaDock-0.2.7-arm64.dmg**, verify `SHA256SUMS`, and drag **LumaDock.app** into Applications. Packages use **ad-hoc signing and are not notarized**. Game preparation still requires full Xcode, Metal and a compatible external engine; IPA export also requires the iOS platform and XcodeGen.

The combined changes passed **98 Python tests and 51 Swift Release tests**, real macOS/iOS Metal success/failure checks, and original unsigned UIKit IPA packaging/validation. DLC regression coverage includes Mac/iOS calls, multiple DLC packages, no DLC, cache reuse and failure/retry. Conversion success tests use original containers and backend protocol fixtures; real bundled backends are checked for startup, relocation and invalid-key rejection. These checks do not establish commercial-game conversion, in-game DLC behavior or physical iPhone/iPad compatibility.

**No engine, games, updates, DLC, firmware, player keys, game artwork, saves or player caches are included.** Import only content you are authorized to use. The project is not affiliated with Nintendo or any game publisher. Thanks to nxnative, MacNativeGames, d2r-mobile, SAK-Mac and their contributors; full notices remain in the bundled documentation.

---

## 中文说明

璃游 0.2.7 面向 Apple Silicon Mac、macOS 26 及以上，使用玩家自行提供的外部 nxnative 引擎。

- **内置文件转换。** 新增“文件转换”页面，支持 NSP/XCI 转换（可输入 NSZ/XCZ）、压缩解压及同一游戏本体、更新和 DLC 合并。内置参考 SAK-Mac 的调度逻辑、NSC_BUILDER、nsz 和固定版本依赖；导入自己的有效密钥即可使用，无需另装 Python、Xcode 或 nxnative。生成的 NSP 可直接入库。（#8）
- **保护原文件和已有输出。** 使用私有输入与后端副本、独立转换密钥，提供进度、取消重试、任务历史、日志和结果入口。校验后导出至新文件夹，不覆盖旧结果；保留上游许可、依赖声明及 GPL/MPL 组件对应源码。
- **修复 DLC 准备失败。** 补齐 `extract_aoc` 所需的引擎源码目录参数，修复 Mac 准备和 IPA 导出时的 `missing 1 required positional argument: 'logs'`。此异常来自调用参数错误，现有日志没有证明主机或固件版本不匹配。（#9、#10）

下载 **LumaDock-0.2.7-arm64.dmg**，核对 `SHA256SUMS` 后拖入“应用程序”。安装包采用 **ad-hoc 签名，尚未公证**。游戏准备仍需要完整 Xcode、Metal 和兼容的外部引擎；IPA 导出还需要 iOS 平台与 XcodeGen。

组合版本通过 **98 项 Python、51 项 Swift Release 测试**、真实 macOS/iOS Metal 成功与失败检查，以及原创 UIKit 未签名 IPA 构建校验。DLC 回归覆盖 Mac/iOS、多 DLC、无 DLC、缓存复用和失败重试。转换成功测试使用原创容器和后端协议夹具；真实内置后端检查覆盖启动、搬移和无效密钥拒绝。尚未验证商业游戏转换、游戏内 DLC 加载或实体 iPhone/iPad 兼容性。

项目不附带引擎、游戏、更新、DLC、固件、玩家密钥、游戏封面、存档或玩家缓存；仅导入有权使用的内容。项目与 Nintendo 及游戏发行商无隶属或认可关系。感谢 nxnative、MacNativeGames、d2r-mobile、SAK-Mac 及贡献者；完整致谢和许可保留在随包文档中。
