## New in 0.2.4

- Clarify Xcode setup recovery: if setup is already complete, check again or quit and reopen LumaDock first. Review the actual diagnostics before using a manual initialization command.
- Keep the in-app English/Chinese repair instructions and offline environment guides consistent. Environment checks still run once at startup, with manual rechecks and verification after toolchain/library changes.

Local validation: 43 Python tests, 24 Swift Release tests, and app/DMG/source/signature/checksum and bundled-runtime relocation checks passed. No games were run or Apple components installed, removed or licensed during validation. A reported recovery after reopening does not establish a specific root cause or a new gameplay test result. GitHub Actions publishes the release only after its own checks pass; local validation does not confirm the remote run.

### 0.2.4 更新

- 明确 Xcode 设置恢复步骤：若已完成设置，先重新检查或退出后重开璃游；仍失败时查看实际诊断，确认需要后再使用手动初始化命令。
- 应用内英文、中文提示与离线环境说明保持一致。保留每次启动检查一次、手动检查及工具链或游戏库变化后的验证。

本地通过 43 项 Python 测试、24 项 Swift Release 测试，以及应用、DMG、源码包、签名、校验和与内置运行库搬移检查。本次未运行游戏，未安装、卸载 Apple 组件或接受许可。用户重开后恢复的反馈不代表已确定根因，也不增加游戏游玩验证结论。CI 自身检查通过才会公开 Release；本地通过不代表远端已完成。

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
