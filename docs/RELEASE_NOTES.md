# LumaDock 0.2.6

LumaDock is a game launcher for Apple Silicon Macs running macOS 26 or later, using a player-selected external [nxnative](https://github.com/seedds/nxnative) source directory.

## Changes

- **Actionable errors.** Build failures show the failed stage, error code, suggested repair, redacted compiler output and a link to the specific log. Copy a redacted summary from the alert or task. Diagnostics cover missing Metal/SDK components, shader translation/compilation errors, shader-chain mismatches, disk/permission errors and possible memory exhaustion. Worker startup failures and unexpected exits are also retained.
- **Shader warnings stay visible.** A shader tool returning success with incomplete shader results produces a warning; no usable shaders stops the build. Warnings survive checkpoint reuse instead of disappearing on retry. A completed build does not guarantee correct graphics in every scene.
- **Progress across long operations.** A shared linear progress display covers imports, source/copy/cache verification, engine preparation, game/shader builds, IPA export, environment checks, Metal component management, cleanup and diagnostics export. Tasks show measured bytes/files/shaders and percentages when a real total is known; otherwise they show an indeterminate bar, current phase and elapsed time. Progress remains visible outside Tasks and inside setup/Settings. Pure Python work has heartbeats; ordinary messages no longer clear counters.
- **Generate IPA.** Choose **Generate IPA…** in game details to export an unsigned iPhone/iPad game package. Mac and iOS builds have separate cache identities; iOS shaders are checked before packaging. Export validates archive structure/CRCs and preserves the previous IPA after failure or cancellation. Xcode's iOS platform, Metal compiler and XcodeGen are required. Sign the IPA with your installation tool before installing it.
- Keep English/Chinese UI and guides synchronized. CI additionally compiles original Metal samples for macOS/iOS, checks real compiler error redaction and builds/validates a small unsigned UIKit fixture IPA. No engine or player content is fetched for these checks.

## Installation and validation

Download **LumaDock-0.2.6-arm64.dmg**, verify `SHA256SUMS`, and drag **LumaDock.app** into Applications. Packages use **ad-hoc signing and are not notarized**. Preparing games requires full Xcode, Metal and your own compatible external engine. IPA export additionally needs the iOS platform and XcodeGen (`brew install xcodegen`).

Local validation passed **78 Python tests and 45 Swift Release tests**, plus English/Chinese UI checks of progress, cancellation/retry, warning/error actions, mapping save and synthetic IPA export. Regression coverage includes library/import/setup flows, keys and source isolation, engine/tool caches, cancellation/retry, input mappings, language/appearance, diagnostics, progress, IPA export and distribution data boundaries. Real Apple tools validate macOS/iOS Metal success and failure paths and a synthetic iOS app archive. These checks do not establish commercial-game preparation, gameplay or physical iPhone/iPad compatibility. See the bundled validation record for the exact scope.

**No games, updates, DLC, firmware, player keys, game artwork, saves or player caches are included.** Import only content you are authorized to use. Back up important saves. The project is not affiliated with Nintendo or any game publisher. Thanks to nxnative, MacNativeGames, d2r-mobile and their contributors; acknowledgements and third-party licenses remain in the README and bundled guides.

---

## 中文说明

璃游 0.2.6 面向 Apple Silicon Mac、macOS 26 及以上，继续使用玩家自行提供的外部 nxnative 源码。

- **具体报错与修复建议。** 显示失败阶段、错误代码、处理建议和脱敏编译器输出，直接定位对应日志，也可复制错误摘要。区分 Metal/SDK 缺失、着色器转换或编译失败、缓存链不匹配、空间/权限问题及可能的内存不足；工作进程启动失败和异常退出也会保存诊断。
- **保留着色器警告。** 进程返回成功但着色器结果不完整时显示警告，没有可用着色器时停止构建；缓存复用后仍显示警告。“准备完成”不代表所有场景画面正常。
- **补齐耗时操作的进度条。** 覆盖导入、源文件/副本/缓存校验、引擎准备、游戏与着色器构建、IPA 导出、环境检查、Metal 组件管理、清理和诊断导出。可计数时显示实际字节、文件、着色器数量和百分比；总量未知时使用线形不定进度条，并显示阶段及已用时间。其他页面、设置及向导中也能查看进度，普通消息不会清空计数，纯 Python 任务持续发送心跳。
- **一键生成 IPA。** 游戏详情点击“生成 IPA…”即可导出未签名 iPhone/iPad 游戏包。Mac/iOS 缓存隔离，检查 iOS 着色器、IPA 结构及 CRC；失败或取消保留上次 IPA。需要 Xcode iOS 平台、Metal 组件和 XcodeGen；安装到设备前仍需自行签名。
- 同步中英文界面和文档；CI 新增 macOS/iOS 实际 Metal 成功/失败诊断及原创 UIKit 样例 IPA 构建校验，不下载引擎或玩家内容。

下载 **LumaDock-0.2.6-arm64.dmg**，核对 `SHA256SUMS` 后拖入“应用程序”。安装包采用 **ad-hoc 签名，尚未公证**。本地通过 **78 项 Python、45 项 Swift Release 测试**，以及中英文进度、取消/重试、错误/警告、映射保存及合成 IPA 导出的实际界面检查。回归检查覆盖启动器各工作流程、取消与重试、设置、进度、诊断及数据边界，并使用真实 Apple 编译器与合成 iOS 应用验证；不代表商业游戏准备、游玩或 iPhone/iPad 真机兼容性验收。具体范围见随包验收记录。

项目不附带游戏、更新、DLC、固件、玩家密钥、游戏封面、存档或玩家缓存；仅导入有权使用的内容，并备份重要存档。项目与 Nintendo 及游戏发行商无隶属或认可关系。感谢 nxnative、MacNativeGames、d2r-mobile 及贡献者；README 与随包文档保留上游致谢和第三方许可。
