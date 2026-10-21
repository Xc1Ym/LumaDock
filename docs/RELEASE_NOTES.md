## New in 0.2.2

- Complete environment checklist in setup and Settings: hardware, system Metal device, bundled Python and extensions, .NET 10, NSP reader, shader tools, Xcode initialization, macOS SDK, native compilation/signing, actual Metal compilation, and library permissions/free space.
- English and Chinese installation and repair guidance for every item, with actions to get/select/open Xcode, install Metal, reinstall an incomplete app, or change library storage.
- Isolated bundled Python with no silent Homebrew fallback. Missing Python or a failed Worker bootstrap produces an actionable native check instead of leaving setup stuck.
- Separate preparation and launch requirements. Already prepared games can launch without build-only tools; incomplete or failed checks cannot enable Continue early.
- Mac shader-chain checks only require the macOS SDK. Tool and engine changes continue to invalidate affected build caches.
- Redesigned Retina DMG installer with a light glass-style background, aligned drag-to-Applications icons, bilingual instructions, and organized guides/licenses. Packaging verifies the mounted installer layout and preserves the app signature.

Local validation: 38 Python tests, 19 Swift tests, all 18 packaged environment checks, bilingual UI checks, and DMG/source/signature/checksum verification passed on macOS 27.0.1 with Xcode 27.1. No games were run for this update; the historical gameplay evidence is unchanged. Physical macOS 26 testing remains outstanding.

### 0.2.2 更新

- 首次设置和设置页补齐完整环境检查，实际验证 Python 及扩展、.NET、NSP 读取器、着色器工具、Xcode 初始化、macOS SDK、原生编译与签名、Metal 编译和游戏库存储。
- 每项提供中英文安装与修复方法，可获取、选择或打开 Xcode，安装 Metal、重装完整应用或切换游戏库存储。
- 隔离启动内置 Python，不再自动借用 Homebrew Python。Python 缺失或 Worker 启动失败时，原生界面仍能给出修复入口。
- 区分“准备”和“启动”条件；已准备游戏不依赖仅构建所需的工具，未完成或失败的检查不会提前放行。
- Mac 着色器链只检查 macOS SDK，工具链或引擎变化仍会使对应缓存失效。
- 美化 Retina DMG 安装界面，加入浅色玻璃质感背景、固定图标位置、双语拖拽引导及整理后的文档和许可；验证安装盘布局及应用签名。

本地验证通过：38 项 Python 测试、19 项 Swift 测试、18 项发行应用环境检查、中英文界面检查，以及 DMG、源码、签名与校验和验证。实测系统为 macOS 27.0.1 / Xcode 27.1；本次未运行游戏，不扩大历史游玩结论，macOS 26 真机仍未重新验证。

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
