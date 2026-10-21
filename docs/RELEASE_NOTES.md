# LumaDock 0.2.5

LumaDock is a Mac game launcher for Apple Silicon and macOS 26 or later, built to work with [nxnative](https://github.com/seedds/nxnative).

## Changes

- **External engine only.** The app, DMG and source archive no longer include nxnative sources, the NSP reader or shader translator. Obtain a complete compatible nxnative source directory yourself, select its root in setup or Settings, then choose **Prepare engine tools**. There is no engine download action. The initial tool build requires the **.NET 10 SDK for macOS Arm64** and may restore NuGet dependencies. Builds use private copies and leave your original source directory unchanged. Generic Python/.NET runtimes and conversion tools remain bundled.
- **Game language ([#2](https://github.com/Xc1Ym/LumaDock/issues/2)).** Fix the invalid hardcoded `zhHans` code to `zh-Hans`. Choose **Launch language** in game details, or a **Default game language** in Settings. Per-game choices persist independently of the interface language and apply on the next launch without rebuilding or importing firmware. The game and engine must support the selected language.
- **Setup exit ([#1](https://github.com/Xc1Ym/LumaDock/issues/1)).** Leave incomplete setup with **Set up later / Esc**, or quit normally with **Quit LumaDock / ⌘Q**, including when environment checks fail or are running. Required checks still gate imports and preparation.
- Validate external source interfaces and fingerprints, isolate private tool caches, and preserve the previous successful runtime after failures. Custom mappings require an external engine implementing `DM_INPUT_CONFIG`; otherwise the editor explains that the engine's own controls apply.
- Update English/Chinese guides and light-mode screenshots without game content. CI builds the standalone launcher without downloading nxnative.

## Installation and validation

Download **LumaDock-0.2.5-arm64.dmg**, check `SHA256SUMS`, and drag **LumaDock.app** into Applications. The community build uses **ad-hoc signing and is not notarized**. Preparing games also requires full Xcode and Apple's Metal compiler component; the setup assistant checks their actual state and explains installation.

Local validation passed **55 Python tests and 34 Swift Release tests**, actual English/Chinese menu checks, package/signature checks and release-artifact verification. No commercial games were run for this release, so these checks do not establish gameplay or in-game language compatibility with arbitrary external engines. GitHub Actions independently verifies and publishes the tag's DMG, source archive and checksums; local results do not confirm the remote run.

**No games, updates, DLC, firmware, player keys, game artwork, saves or player caches are included.** Import only content you are authorized to use. Experimental native execution can crash, stutter or lose saves; back up important data. The project is not affiliated with or endorsed by Nintendo or any game publisher. Special thanks to **nxnative**, MacNativeGames, d2r-mobile and their contributors; upstream acknowledgements and third-party licenses remain in the README and bundled documentation.

---

## 中文说明

璃游 0.2.5 面向 Apple Silicon、macOS 26 及以上。

- **改为外部引擎。** 应用、DMG 和源码包不再内置 nxnative 源码、NSP 读取器或着色器翻译器，也没有引擎下载按钮。请自行获取兼容的完整源码，在向导或设置中选择包含 `dm` 和 `scripts` 的根目录，再点击“准备引擎工具”。首次需要 **.NET 10 SDK（macOS Arm64）**，可能恢复 NuGet 依赖。所有构建及适配在私有副本中完成，原目录保持不变；通用 Python/.NET 运行时及转换工具仍随应用提供。
- **修复游戏语言（[#2](https://github.com/Xc1Ym/LumaDock/issues/2)）。** 将错误的 `zhHans` 改为 `zh-Hans`。游戏详情新增“启动语言”，设置新增“默认游戏语言”；每游戏选择独立保存，与界面语言无关，下次启动生效，无需重新准备或导入固件。实际语言取决于游戏和引擎支持。
- **修复向导退出（[#1](https://github.com/Xc1Ym/LumaDock/issues/1)）。** 环境失败或检查进行中，也可通过“稍后设置 / Esc”离开，或通过“退出璃游 / ⌘Q”正常退出；必要检查仍会限制导入和准备。
- 增加外部引擎接口、源码指纹和工具完整性检查，隔离缓存并保留上次成功的运行版本。自定义映射需要引擎提供 `DM_INPUT_CONFIG`；不支持时明确提示并使用引擎默认操作。更新中英文说明及不含游戏内容的浅色截图，CI 不下载 nxnative。

下载 **LumaDock-0.2.5-arm64.dmg**，核对校验和后拖入“应用程序”。安装包采用本地 ad-hoc 签名，**尚未公证**；准备游戏还需要完整 Xcode 和 Metal 编译组件，向导会检查实际状态并提供安装方法。

本地通过 **55 项 Python、34 项 Swift Release 测试**，以及中英文实际菜单、应用签名与发行产物校验。本次未运行商业游戏，不能据此声称任意外部引擎的游玩或游戏内语言验收通过。标签流水线独立校验并发布 DMG、源码包和校验和；本地结果不代表远端已成功。

项目不附带游戏、更新、DLC、固件、玩家密钥、游戏封面、存档或玩家缓存；仅导入有权使用的内容。实验性运行可能崩溃、卡顿或丢失存档，请备份重要数据。项目与 Nintendo 及游戏发行商无隶属或认可关系。特别感谢 nxnative、MacNativeGames、d2r-mobile 及其贡献者；README 与随包文档保留上游致谢、风险及第三方许可。
