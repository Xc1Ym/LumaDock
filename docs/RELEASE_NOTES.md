## New in 0.2.1

- Sync nxnative to `4e2dcdc749668ddd4d61361117ad4a6980fabcf7`, preserving the Mac metadata, packaging, and configurable input patches. Existing working runtimes are retained and marked for re-preparation.
- Independent System / Light / Dark appearance settings, with immediate updates and persistence.
- Refreshed bilingual READMEs with real light-mode app screenshots and no Controls chapter.
- English and Simplified Chinese throughout the app, setup assistant, input editor, progress, and application error messages.
- System language by default, with an immediate, persistent override in Settings and setup. Existing task records translate when displayed; game content and raw tool logs remain unchanged.
- Localized application metadata and bundled translation resources checked during packaging.

Engine validation scope: Odyssey completed preparation with `4e2dcdc`. Breath of the Wild's rebuild was cancelled at the player's request; new startup and gameplay checks were not performed. The longer player gameplay record below belongs to the previous `10b33338` baseline.

### 0.2.1 更新

- 同步 nxnative `4e2dcdc`，保留 Mac 补丁；引擎更新后提示重新准备，旧的成功运行版本保留。
- 新增独立的跟随系统／浅色／深色外观设置，立即生效并持久化。
- 中英文 README 删除操作映射章节，增加真实浅色界面截图。
- 应用、首次运行向导、输入映射、任务进度和应用错误提示支持英文及简体中文。
- 默认跟随系统，可在设置和向导中立即切换并记住选择；已有任务记录按显示语言翻译，游戏内容与原始工具日志保持原样。
- 打包时检查应用语言元数据和翻译资源。

新版引擎的验证范围：《奥德赛》完整准备通过；《旷野之息》重建按玩家要求取消，未执行新版启动及游玩检查。较长时间的玩家游玩记录基于此前的 `10b33338`。

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
