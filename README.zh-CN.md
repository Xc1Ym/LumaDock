<p align="center">
  <img src="Assets/LumaDock.png" width="128" alt="璃游图标">
</p>
<h1 align="center">璃游 · LumaDock</h1>
<p align="center">让你的游戏，在 Mac 上继续。</p>
<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong></p>
<p align="center">Apple Silicon · macOS 26+ · SwiftUI / Liquid Glass</p>
<p align="center"><a href="https://github.com/Xc1Ym/LumaDock/releases/latest">下载 Mac 版</a> · <a href="https://github.com/Xc1Ym/LumaDock/actions/workflows/ci.yml">构建状态</a></p>

璃游是面向 Apple Silicon Mac 的原生 Switch 游戏启动器。使用自备的 **[nxnative 引擎](https://github.com/seedds/nxnative)**、有权使用的 NSP/XCI 文件和 `prod.keys`，即可在图形界面中导入、准备并启动游戏，或导出未签名的 iPhone / iPad IPA。

nxnative 提供原生执行和 Metal 图形能力，璃游负责游戏库与图形化操作流程。**项目不附带或提供引擎、游戏、更新、DLC、固件、密钥、游戏封面及玩家缓存的下载。**

## 主要功能

- **游戏库管理** — 添加 NSP/XCI/NSZ/XCZ 或扫描文件夹，NSP/XCI 直接导入，压缩格式自动解压，再准备游戏。
- **自动构建** — 完成代码、着色器和运行文件准备，支持缓存校验、取消和重试。
- **存档保护与版本回滚** — 手动备份、校验恢复，切换运行版本前自动备份存档，支持选择历史运行版本。
- **文件转换** — 内置参考 [SAK-Mac](https://github.com/ggaoph-lab/SAK-Mac) 的转换工具，转换 NSP/XCI、压缩解压 NSZ/XCZ、合并文件；生成的 NSP 可导入游戏库。
- **IPA 导出** — 在游戏详情中生成未签名的 iPhone / iPad 安装包。
- **进度与错误提示** — 显示实际进度、分阶段步骤与参考估时，提供着色器警告、修复建议、对应日志与脱敏错误摘要。
- **原生 Mac 体验** — 中英双语、浅色 / 深色外观、游戏语言设置，以及所选引擎支持的输入映射。

## 快速开始

**环境要求：** Apple Silicon、macOS 26+。准备游戏还需完整 Xcode 及 Metal 组件，以及兼容的外部 nxnative 源码目录。首次编译引擎工具还需要 **.NET 10 SDK（macOS Arm64）**。通用运行依赖随应用提供。

1. 下载最新版 **ARM64 DMG**，核对 `SHA256SUMS`，将 **LumaDock.app** 拖入“应用程序”。当前版本采用 **ad-hoc 签名，尚未公证**。
2. 按向导检查环境，选择 nxnative 源码根目录，点击“准备引擎工具”。
3. 选择游戏库，导入自己的 `prod.keys`，再添加本体、更新和 DLC 的 NSP、XCI、NSZ 或 XCZ 文件。
4. 准备完成后点击“启动游戏”，或在详情中点击“生成 IPA…”。任务页显示进度，支持取消和重试。

IPA 导出额外需要 Xcode 的 **iOS 平台**和 **XcodeGen**（`brew install xcodegen`）。导出后需使用自己的安装工具签名，再安装到设备。

兼容性取决于所选引擎和游戏版本；准备成功不保证完整可玩，iOS 真机兼容性尚未验收。**升级或试验性运行前，请备份存档。**

## 界面预览

浅色外观与空游戏库，不含玩家数据或游戏内容。

<img src="docs/screenshots/library-zh.jpg" width="1000" alt="璃游游戏库">

<details>
<summary>首次设置与设置页面</summary>

<img src="docs/screenshots/setup-zh.jpg" width="1000" alt="璃游首次运行向导">
<img src="docs/screenshots/settings-zh.jpg" width="1000" alt="璃游设置">

</details>

## 文档与帮助

| 文档 | 内容 |
| --- | --- |
| [使用说明](docs/使用说明.md) | 首次设置、IPA 导出、输入、语言与数据管理 |
| [环境要求与修复](docs/环境要求.md) | 依赖、安装步骤与工具链排错 |
| [开发说明](docs/开发说明.md) | 测试、本地构建与 CI 发布 |
| [更新说明](docs/RELEASE_NOTES.md) | 最新版本的中英文变更 |
| [架构说明](docs/架构说明.md) · [引擎接口](docs/引擎修改.md) · [验收记录](docs/验收记录.md) | 技术细节与具体验证范围 |

报错时可打开任务对应日志或复制脱敏错误摘要。[提交 Issue](https://github.com/Xc1Ym/LumaDock/issues) 时，请附应用、芯片、macOS 和 Xcode 版本及复现步骤。分享前检查诊断内容，不要上传游戏、密钥、固件、存档或私人缓存。

## 致谢与许可

特别感谢 **[nxnative](https://github.com/seedds/nxnative)** 提供核心执行与图形能力，以及 **[MacNativeGames](https://github.com/ly05010419/MacNativeGames)**、**[d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile)** 的上游贡献。文件转换参考 **[SAK-Mac](https://github.com/ggaoph-lab/SAK-Mac)**（MIT）的代码实现。引擎由玩家自行提供。同时感谢 Ryujinx / Spv.Generator、LibHac、SPIRV-Cross、CPython、.NET 等依赖项目，详见[完整第三方许可](docs/第三方许可.md)。

启动器代码与原创图标采用 **[MIT License](LICENSE)**，第三方组件保留各自许可。软件按 “AS IS” 提供，仅使用有权使用的内容。Nintendo 及游戏商标归相应权利人所有；本项目与 Nintendo 或游戏发行商没有隶属或认可关系。
