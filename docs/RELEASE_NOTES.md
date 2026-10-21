## New in 0.2.3

- Check the environment automatically once per app launch. Settings and reopened setup reuse the current result, including failures; manual rechecks and verification after toolchain/library changes remain available.
- Explain Xcode initial setup failures with the selected Developer path, the status command, error output and exit status even when the command returns no text. Distinguish missing Xcode, a reported license error, timeout and other initialization/status failures. A copyable repair command uses the selected Xcode; the user runs it manually after reviewing and agreeing to Apple's license. LumaDock does not execute privileged initialization or accept licenses automatically.
- Open English/Chinese environment instructions and third-party notices in an offline reader inside the app, including from the setup assistant.
- Show bundled component versions first, with full installation paths in an expandable section. Locate Python, extensions and .NET from the current app bundle.
- Remove leftover Homebrew runtime search paths and reject external native dependencies/symlinks during packaging. CI verifies actual bundled tool startup after renaming and moving the app into a path containing Chinese characters and spaces.
- An incomplete packaged app reports its own missing resources instead of falling back to a developer checkout.

Local validation: 43 Python tests, 24 Swift tests, native runtime load-path audits, real UI navigation/offline-guide checks, relocation tests, and DMG/source/signature/checksum verification passed on macOS 27.0.1 with Xcode 27.1. No games were run. The reported initialization failure on another Mac cannot be diagnosed from its old screenshot alone; use the updated diagnostics. Physical macOS 26 testing remains outstanding. GitHub Actions builds and publishes this release only after its checks pass; local results do not confirm the remote run.

### 0.2.3 更新

- 每次启动自动检查一次；切换设置或重新打开向导复用本次结果，包括失败结果。手动检查、工具链或游戏库变更后的验证保留。
- Xcode 初始设置失败时显示所选 Developer 路径、检查命令、错误输出及退出码；命令无输出也不会只显示通用说明。区分缺少 Xcode、命令报告的许可错误、超时及其他初始化或状态检查失败。修复命令按实际 Xcode 路径生成，由玩家阅读并同意 Apple 许可后手动执行；应用不自动执行管理员初始化或接受许可。
- 环境安装说明与第三方许可改为应用内离线阅读，支持中英文，首次运行向导内也能打开。
- 内置组件默认显示版本，完整位置可展开；Python、扩展及 .NET 根据当前应用包位置定位。
- 清除 Homebrew 备用搜索目录，打包时拒绝外部原生依赖和符号链接；CI 实际验证应用改名、移动至中文和空格目录后仍能启动内置工具。
- 应用包缺少资源时报告本包错误，不回退到开发者源码目录。

本地通过 43 项 Python 测试、24 项 Swift 测试、运行库审计、真实界面切换及离线说明检查、搬移验证，以及 DMG、源码、签名和校验和检查。测试系统为 macOS 27.0.1 / Xcode 27.1；本次没有运行游戏，也未在对方 Mac 上确认初始化失败的具体原因。macOS 26 真机验证仍待补充。CI 全部通过才会公开 Release，本地通过不代表此次远程构建已成功。

LumaDock is a native Mac launcher built on [nxnative](https://github.com/seedds/nxnative), for Apple Silicon and macOS 26 or later.

- Guided setup: check the environment, choose a library, import your own `prod.keys`, then add NSP games.
- Automatic preparation with progress, cancellation, validated caches, and keyboard/mouse/controller configuration.
- Direct Mac runtime generation, a Liquid Glass interface, and Xcode / Metal component management.
- Tested titles: **Breath of the Wild 1.9.0** (build and startup passed) and **Super Mario Odyssey 1.4.1** (player gameplay test passed). These are limited test results, not full-game completion claims; see the README and validation record.

Download the ARM64 DMG and drag LumaDock into Applications. Packages use local ad-hoc signing and are **not notarized**. A full Xcode installation and the Metal compiler component are needed to prepare games.

**No games, updates, DLC, firmware, keys, game artwork, or player caches are included.** Import only content you are authorized to use. This project is not affiliated with Nintendo. Thanks to nxnative, MacNativeGames, d2r-mobile, and their contributors; third-party licenses and notices are preserved.

The release DMG and source archive are built and checked by GitHub Actions; verify them with `SHA256SUMS`.

---

璃游是基于 nxnative 的原生 Mac 游戏启动器，面向 Apple Silicon、macOS 26 及以上。先检查环境，再选择游戏库、导入玩家密钥及 NSP，支持自动准备、进度显示、缓存复用与键鼠/手柄映射。

历史记录中《旷野之息》1.9.0 构建及启动通过，《奥德赛》1.4.1 玩家游玩测试通过，均不代表全流程验证。《奥德赛》的较长游玩记录使用此前的 10b33338 引擎；更新固定引擎不会扩大这一证据范围。安装包采用本地 ad-hoc 签名，尚未公证；准备游戏需要完整 Xcode 与 Metal 编译组件。

项目不附带游戏、更新、DLC、固件、密钥或玩家缓存，与 Nintendo 没有隶属关系。感谢 nxnative 等上游项目及贡献者。安装包和源码包由 GitHub Actions 生成并校验，可用 SHA256SUMS 核对。
