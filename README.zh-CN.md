<p align="center">
  <img src="Assets/LumaNX.png" width="112" alt="璃游图标">
</p>
<h1 align="center">璃游 · LumaNX</h1>
<p align="center">在 Mac 上，图形化构建与打包 Switch 游戏。</p>
<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong></p>
<p align="center">
  <a href="https://github.com/Xc1Ym/LumaNX/releases/latest">下载 DMG</a> ·
  <a href="docs/使用说明.md">使用指南</a> ·
  <a href="docs/开发说明.md">源码构建</a> ·
  <a href="https://github.com/Xc1Ym/LumaNX/issues">反馈问题</a>
</p>

璃游 LumaNX 是面向 Apple Silicon Mac 的 **[nxnative](https://github.com/seedds/nxnative) 第三方图形界面**。导入游戏文件，准备 Mac 运行版本，从游戏库启动，或导出未签名的 iPhone / iPad IPA。nxnative 提供原生执行与 Metal 图形能力，璃游用 SwiftUI 将这些操作集中到一个工作空间。

<img src="docs/screenshots/library-zh.jpg" width="1000" alt="璃游 0.2.19 浅色外观游戏库">

## 从游戏文件到运行版本

| 工作空间 | 可以做什么 |
| --- | --- |
| **游戏库** | 添加 NSP/XCI/NSZ/XCZ 或扫描文件夹，管理本体、更新与 DLC；压缩文件先解压再导入。 |
| **游戏准备** | 准备代码、着色器与运行文件，校验和复用缓存；查看阶段进度、实际计数与参考估时，取消或重试任务。 |
| **Mac 与移动设备** | 在 Mac 上启动已准备的游戏，或在详情中生成未签名的 iPhone / iPad IPA。 |
| **文件转换** | 使用内置转换工具转换 NSP/XCI、压缩或解压 NSZ/XCZ、合并文件。 |
| **存档恢复** | 备份并校验存档、从备份恢复；切换已准备的运行版本前自动备份存档。 |
| **偏好设置** | 选择中英文、浅色或深色外观、游戏语言，并使用引擎支持的输入配置。 |

Switch Pro、Xbox、PlayStation 手柄通过 Apple GameController 框架接入。原生按键策略将 Switch A / Xbox A / PlayStation 叉键映射为游戏 A。更新引擎后，重新准备已有游戏即可应用运行时变更。

## 开始使用

**需要 Apple Silicon Mac 与 macOS 26 或更新版本。** 准备游戏还需完整 Xcode 及 Metal 组件。安装包内置 nxnative、元数据读取器、着色器翻译器与运行依赖。

1. 从 [Releases](https://github.com/Xc1Ym/LumaNX/releases/latest) 下载 ARM64 DMG，核对发布说明中的 SHA-256，将 **LumaNX.app** 拖入“应用程序”。当前安装包采用 ad-hoc 签名，尚未公证。
2. 打开璃游，按首次设置向导检查环境，并**准备引擎工具**。
3. 选择游戏库，导入自己的 `prod.keys`，添加有权使用的游戏本体、更新与 DLC。
4. 准备完成后点击**启动游戏**；移动设备请选择游戏详情中的**生成 IPA…**。

IPA 导出还需 Xcode 的 **iOS 平台**与 **XcodeGen**（`brew install xcodegen`）。导出后使用自己的安装工具签名，再安装到设备。

兼容性随游戏、版本和引擎而变化。准备成功不代表完整可玩，iOS 真机兼容性尚未验收。升级或试验性运行前，请备份存档。

## 界面预览

截图拍摄于 **2026-10-30**，取自 **0.2.19 界面预览构建**，使用浅色外观与独立空白数据目录，不含游戏、密钥或玩家数据。首次设置展示了此预览构建中组件尚待修复的状态。

<details>
<summary>首次设置与偏好设置</summary>

<img src="docs/screenshots/setup-zh.jpg" width="1000" alt="璃游首次设置向导">
<img src="docs/screenshots/settings-zh.jpg" width="1000" alt="璃游偏好设置">

</details>

## 文档

| 指南 | 内容 |
| --- | --- |
| [使用说明](docs/使用说明.md) | 首次设置、IPA 导出、手柄、语言与数据管理 |
| [环境要求与修复](docs/环境要求.md) | 依赖安装与工具链排错 |
| [开发说明](docs/开发说明.md) | 测试、本地 App / DMG 构建与 CI |
| [更新说明](docs/RELEASE_NOTES.md) | 中英文版本变更 |
| [架构说明](docs/架构说明.md) · [引擎接口](docs/引擎修改.md) · [验收记录](docs/验收记录.md) | 实现细节与已记录的验证范围 |

报错时，打开任务日志或复制脱敏错误摘要。[提交 Issue](https://github.com/Xc1Ym/LumaNX/issues) 请附应用、芯片、macOS、Xcode 版本及复现步骤。分享前检查诊断内容，排除游戏、密钥、固件、存档与私人缓存。

## 开发与引擎更新

启动器由 SwiftUI / AppKit 与 Python Worker 组成，固定版本的 nxnative 源码位于 `Engine/nxnative`。[开发说明](docs/开发说明.md) 包含依赖、自动化测试与打包流程。

每日上游同步工作流会先验证引擎更新，再发布到本仓库。Release 按需提供 DMG；如需在下次发布前使用较新的同步引擎，可从源码构建 App 或 DMG。

璃游原名 **LumaDock**。原有图标、应用标识、游戏库与设置继续兼容已有安装。

## 致谢与许可

感谢 **[nxnative](https://github.com/seedds/nxnative)** 提供执行与图形能力，感谢 **[MacNativeGames](https://github.com/ly05010419/MacNativeGames)** 与 **[d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile)** 的上游贡献。文件转换参考 **[SAK-Mac](https://github.com/ggaoph-lab/SAK-Mac)**。这些组件及 Ryujinx / Spv.Generator、LibHac、SPIRV-Cross、CPython、.NET 等依赖的许可见[第三方声明](docs/第三方许可.md)。

启动器代码与原创图标采用 **[MIT License](LICENSE)**，第三方组件保留各自许可。项目不附带游戏、更新、DLC、固件、密钥、游戏封面或玩家缓存。请仅使用有权使用的内容。Nintendo 及游戏商标归相应权利人所有；璃游与 Nintendo 或游戏发行商没有隶属或认可关系。
