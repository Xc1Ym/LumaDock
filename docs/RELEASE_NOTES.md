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

本轮实测《旷野之息》1.9.0 构建及启动通过，《奥德赛》1.4.1 玩家游玩测试通过，均不代表全流程验证。安装包采用本地 ad-hoc 签名，尚未公证；准备游戏需要完整 Xcode 与 Metal 编译组件。

项目不附带游戏、更新、DLC、固件、密钥或玩家缓存，与 Nintendo 没有隶属关系。感谢 nxnative 等上游项目及贡献者。安装包和源码包由 GitHub Actions 生成并校验，可用 SHA256SUMS 核对。
