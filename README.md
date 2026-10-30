<p align="center">
  <img src="Assets/LumaNX.png" width="112" alt="LumaNX icon">
</p>
<h1 align="center">LumaNX · 璃游</h1>
<p align="center">A native Mac workspace for building and packaging Switch games.</p>
<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>
<p align="center">
  <a href="https://github.com/Xc1Ym/LumaNX/releases/latest">Download DMG</a> ·
  <a href="docs/Getting-started.md">User guide</a> ·
  <a href="docs/Development.md">Build from source</a> ·
  <a href="https://github.com/Xc1Ym/LumaNX/issues">Report an issue</a>
</p>

LumaNX is a third-party graphical frontend for **[nxnative](https://github.com/seedds/nxnative)** on Apple Silicon Macs. Import your game files, prepare a Mac runtime, launch from your library, or export an unsigned IPA for iPhone and iPad. nxnative provides native execution and Metal graphics; LumaNX brings the workflow into a SwiftUI interface.

<img src="docs/screenshots/library-en.jpg" width="1000" alt="LumaNX 0.2.19 game library in light appearance">

## From files to a ready library

| Workspace | What you can do |
| --- | --- |
| **Game library** | Add NSP/XCI/NSZ/XCZ files or scan folders; manage base games, updates and DLC. Compressed files are decompressed before import. |
| **Game preparation** | Prepare code, shaders and runtime files with validated caches. Follow stage progress, counters and reference time estimates; cancel or retry tasks. |
| **Mac and mobile** | Launch prepared games on Mac, or generate an unsigned iPhone / iPad IPA from game details. |
| **File conversion** | Convert NSP/XCI, compress or decompress NSZ/XCZ, and merge packages using bundled conversion tools. |
| **Save recovery** | Back up and verify saves, restore a backup, or switch prepared runtime versions with an automatic save backup. |
| **Preferences** | Choose English or Simplified Chinese, light or dark appearance, and game language. Configure input where supported by the engine. |

Switch Pro, Xbox and PlayStation controllers connect through Apple's GameController framework. The native button policy maps Switch A / Xbox A / PlayStation cross to game A. Re-prepare existing games after an engine update to apply runtime changes.

## Get started

**You need an Apple Silicon Mac running macOS 26 or later.** Game preparation requires full Xcode and its Metal components. The packaged app includes nxnative, the metadata reader, shader translator and runtime dependencies.

1. Download the ARM64 DMG from [Releases](https://github.com/Xc1Ym/LumaNX/releases/latest), check its SHA-256 against the release notes, and drag **LumaNX.app** into Applications. Packages currently use ad-hoc signing and are not notarized.
2. Open LumaNX. Use the setup assistant to check your environment and **prepare engine tools**.
3. Choose a game library and import your own `prod.keys`. Add game files, updates and DLC that you are authorized to use.
4. Prepare a game, then choose **Launch game**. For mobile, choose **Generate IPA…** in game details.

IPA export also needs Xcode's **iOS platform** and **XcodeGen** (`brew install xcodegen`). Sign the exported IPA with your installation tool before installing it.

Compatibility varies by game, version and engine. Preparation success does not establish full gameplay compatibility; iOS device compatibility has not been validated. Back up saves before upgrading or experimenting.

## Interface

Captured on **2026-10-30** from a **0.2.19 UI preview build**, in light appearance with an isolated, empty data directory. No games, keys or player data are shown. The setup assistant illustrates components needing attention in this preview.

<details>
<summary>Setup assistant and preferences</summary>

<img src="docs/screenshots/setup-en.jpg" width="1000" alt="LumaNX setup assistant">
<img src="docs/screenshots/settings-en.jpg" width="1000" alt="LumaNX preferences">

</details>

## Documentation

| Guide | Contents |
| --- | --- |
| [Getting started](docs/Getting-started.md) | Setup, IPA export, controllers, language and data management |
| [Environment and repair](docs/Environment.md) | Dependencies and toolchain troubleshooting |
| [Development](docs/Development.md) | Tests, local App / DMG builds and CI |
| [Release notes](docs/RELEASE_NOTES.md) | Changes in English and Chinese |
| [Architecture](docs/架构说明.md) · [Engine interface](docs/引擎修改.md) · [Validation record](docs/验收记录.md) | Implementation and recorded validation scope (Chinese) |

For a failure, open the task log or copy its redacted error summary. Include the app, chip, macOS and Xcode versions, plus reproduction steps, in your [issue](https://github.com/Xc1Ym/LumaNX/issues). Review diagnostics before sharing and exclude games, keys, firmware, saves and private caches.

## Development and engine updates

The launcher uses SwiftUI / AppKit and a Python Worker. The pinned nxnative source lives in `Engine/nxnative`; the [development guide](docs/Development.md) covers dependencies, automated tests and packaging.

The daily upstream-sync workflow validates engine updates before publishing them to this repository. Releases provide a DMG on demand. To use a newer synchronized engine before the next release, build the App or DMG from source.

LumaNX was previously called **LumaDock**. The original icon, application identifier, library and settings remain compatible with existing installations.

## Credits and license

Thanks to **[nxnative](https://github.com/seedds/nxnative)** for execution and graphics, and to **[MacNativeGames](https://github.com/ly05010419/MacNativeGames)** and **[d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile)** for upstream contributions. Conversion tools adapt **[SAK-Mac](https://github.com/ggaoph-lab/SAK-Mac)**. See [third-party notices](docs/Third-party-licenses.md) for these components and dependencies including Ryujinx / Spv.Generator, LibHac, SPIRV-Cross, CPython and .NET.

Launcher code and original artwork use the **[MIT License](LICENSE)**. Third-party components retain their own licenses. Games, updates, DLC, firmware, keys, game artwork and player caches are not included. Use only content you are authorized to use. Nintendo and game trademarks belong to their owners; LumaNX is not affiliated with or endorsed by Nintendo or game publishers.
