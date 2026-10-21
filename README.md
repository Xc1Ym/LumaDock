<p align="center">
  <img src="Assets/LumaDock.png" width="128" alt="LumaDock icon">
</p>
<h1 align="center">LumaDock · 璃游</h1>
<p align="center">Let your games continue on Mac.</p>
<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>
<p align="center">Apple Silicon · macOS 26+ · Native Liquid Glass interface</p>
<p align="center"><a href="https://github.com/Xc1Ym/LumaDock/releases/latest">Download for Mac</a> · <a href="https://github.com/Xc1Ym/LumaDock/actions/workflows/ci.yml">Build status</a></p>

LumaDock is a game launcher exclusively for Apple Silicon Macs, built on **[nxnative](https://github.com/seedds/nxnative)**. Bring your authorized NSP game files and `prod.keys`, then import, prepare, and launch from a graphical interface.

Through nxnative's code rewriting and runtime, the game's code executes natively on Apple Silicon, with graphics rendered through Metal. LumaDock organizes your library and runs the preparation steps, producing runtime files directly for macOS.

**No games, updates, DLC, firmware, keys, game artwork, or player-generated shader caches are included. This project is not affiliated with Nintendo or any game publisher.** The app and README support **English and Simplified Chinese**. The interface follows your macOS language by default; choose System default, English, or 简体中文 in **Settings → Language** or the setup assistant. Changes apply immediately. Built-in system dialog controls and raw compiler logs retain their system/tool language.

Choose **System default, Light, or Dark** in **Settings → Language & appearance** to change LumaDock’s appearance independently of macOS. The choice takes effect immediately and is saved.

## Features

- **One game library.** Import NSPs or scan a folder. Identify base games, updates, and DLC from their content metadata. Drag and drop, multiple selection, Unicode paths, and duplicate checks are supported.
- **Automated preparation.** Extract, merge updates, process DLC, rewrite code, translate and compile shaders, then build the Mac host. Track stages, cancel tasks, validate caches, and retry.
- **A native Mac interface.** SwiftUI / AppKit, Liquid Glass, light and dark appearance, and an opaque fallback for Reduce Transparency.
- **Separate player data.** Original files, managed copies, runtime files, caches, and saves are kept separate. A failed preparation preserves the last successful runtime version.

## Screenshots

All screenshots use Light appearance and an empty library. They contain no game footage, covers, keys, or player data.

**Game library** — An empty library before importing player content.

<img src="docs/screenshots/library-en.jpg" width="1000" alt="LumaDock game library">

**Setup assistant** — Environment checks come before importing keys and games.

<img src="docs/screenshots/setup-en.jpg" width="1000" alt="LumaDock setup assistant">

**Settings** — Switch languages and appearance, and manage the local environment.

<img src="docs/screenshots/settings-en.jpg" width="1000" alt="LumaDock settings">

## Tested games on Mac

**This README lists only games actually tested on Mac.** Tests were recorded on October 20, 2026, using an Apple M5 Pro, macOS 27.0.1, and Xcode 27.1.

| Game | Tested version | Result and scope |
| --- | --- | --- |
| The Legend of Zelda: Breath of the Wild | 1.9.0 | **Build and startup passed:** full preparation with two DLCs and a brief native run; gameplay across the full game has not been verified |
| Super Mario Odyssey | 1.4.1 | **Gameplay test passed:** full preparation and GUI launch passed; the player confirmed normal play during a roughly 23-minute run, and save files were written |

Neither result is a full-game completion claim. Odyssey retains three known geometry-shader conversion gaps affecting thunder effects; those effects and all later scenes have not been fully checked. See the [validation record](docs/验收记录.md) (Chinese) for evidence and remaining test boundaries.

The player gameplay result was recorded with the previous `10b33338` engine baseline. With the updated `4e2dcdc` engine, Odyssey completed full preparation; Breath of the Wild's rebuild was cancelled at the player's request, and new game-startup checks were not performed. Gameplay on the updated engine has not been revalidated, and no compatibility claim is added for other games.

Import the base game, the specified update, and any DLC you want to use. Title IDs and executable build IDs must match the fixed game profile; the app checks requirements before preparation.

## Get started

You need an **Apple Silicon Mac, macOS 26 or later, and a full Xcode installation with the Metal compiler component**. The current tested setup is an M5 Pro running macOS 27.0.1 with Xcode 27.1; the app has not been revalidated on a physical Mac running macOS 26. Allow tens of gigabytes of free space for large games; requirements vary with the game and its caches.

**1. Install LumaDock.** Open `LumaDock-0.2.4-arm64.dmg` and drag `LumaDock.app` into Applications. Current packages use local ad-hoc signing and are not Developer ID signed or notarized. If macOS blocks the first launch, verify the source and `SHA256SUMS` before using the opening procedure offered in Privacy & Security.

**2. Prepare the environment first.** The first setup step checks Apple Silicon, macOS, full Xcode, Metal, bundled components, and available space. The Xcode button opens its [Mac App Store page](https://apps.apple.com/app/xcode/id497799835) directly. Install missing Apple tools using the instructions in the wizard, then recheck; the next step stays locked until checks pass. Metal can be installed using [Apple's supported method](https://developer.apple.com/documentation/xcode/downloading-and-installing-additional-xcode-components). Other runtime dependencies are bundled; players do not need Homebrew, Python, or .NET.

**3. Choose a library, import keys, then add your game.** Follow the wizard in that order. External drives are supported; keep the drive connected while preparing or running games. Import your own `prod.keys` once before adding games; its format is checked locally, and decryption is verified when a game is read. The button, menu, and drag-and-drop entry points return to the missing setup step when needed. Choose **Add games**, select the base, update, and DLC NSPs or their containing folder, or drag them into the library. Identification uses file contents, so no particular filename format is required. Files are copied into the managed library; once copying succeeds, moving the originals does not affect those copies.

**4. Prepare and launch.** By default, newly imported games with all required files and matching versions automatically enter the preparation queue after toolchain checks pass. Missing content is listed in game details; if tools are missing, finish their setup and choose **Prepare game**. Duplicate imports do not trigger preparation. The **Tasks** page shows stages, available counters, and errors. When preparation succeeds, choose **Launch game**; games are not launched automatically. You can disable automatic preparation in Settings or the setup wizard. The first preparation can take a while; retries validate and reuse completed stages.

See the [getting started guide](docs/Getting-started.md) in English. For migration of an existing Breath of the Wild build and further data management details, see the [Chinese user guide](docs/使用说明.md).

The [environment and repair guide](docs/Environment.md) lists every dependency and its installation method. Initial setup verifies the bundled Python interpreter and its extensions, .NET, the NSP reader, shader tools, Xcode initialization, the macOS SDK, actual native/Metal compilation, and library permissions. A missing bundled Python is reported by the native app; a separate system Python is not required. Build-only tools are distinguished from the requirements for launching already prepared games.

Settings also provides Metal component removal when supported by the selected Xcode. Removal uses Apple’s component manager and requires confirmation because the component is shared with other projects. Installation and removal are blocked while a game or preparation queue is active; checks refresh afterward. Removing the compiler does not delete games, keys, or saves, but it must be reinstalled before preparing games again.


## Saves and files

| Path inside your chosen library | Contents |
| --- | --- |
| `sources/` | Managed copies of imported NSPs |
| `games/<Title ID>/current` | Last successfully prepared runtime version |
| `games/<Title ID>/pso_user/` | Reusable runtime graphics pipeline records |
| `cache/` | Build and shader caches |
| `saves/<Title ID>/` | Saves; also accessible through Finder from game details |
| `mappings/` | Per-game input configurations |

Keys and launcher preferences are stored in the private application directory, `~/Library/Application Support/NSMac`. Key files use `0600` permissions. Upgrading from the earlier NS Mac app retains that directory and application identifier; avoid running both versions at once.

Removing a game from the library removes its registration while retaining files and saves. Deleting managed NSP copies and clearing caches require separate confirmation; neither deletes original files or saves. **Back up your saves separately before upgrading, migrating, or experimenting.**

## Known limitations

- No Intel Mac support, XCI / NSZ, general-purpose emulator backend, online play, motion controls, or vibration.
- Entering a new scene may still compile graphics pipelines and cause brief stutters. Offline shader processing cannot eliminate every first-use stall.
- Experimental games may fail to launch, display graphics or audio issues, or crash in later scenes. Successful preparation does not guarantee a fully playable game.
- Preparation runs one game at a time and cannot run alongside a game. Tasks interrupted by restarting the app require a manual retry.

When reporting a problem, include the app version, chip, macOS / Xcode versions, reproduction steps, and a redacted error summary. Diagnostics can be exported from Settings; review them for private paths before sharing. **Do not upload keys, games, firmware, saves, game artwork, or player caches.**

## Development and building

The launcher uses SwiftUI / AppKit with a Python build worker. nxnative is pinned to [`4e2dcdc749668ddd4d61361117ad4a6980fabcf7`](https://github.com/seedds/nxnative/tree/4e2dcdc749668ddd4d61361117ad4a6980fabcf7) and does not automatically follow upstream branches. The [architecture](docs/架构说明.md) and [engine change list](docs/引擎修改.md) document interfaces and local changes (Chinese).

Maintainers need full Xcode, Homebrew, and the [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) on PATH. Run the following from the project root; adjust `DEVELOPER_DIR` if Xcode is installed elsewhere:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
mkdir -p work
brew install python@3.14 spirv-cross zstd
"$(brew --prefix python@3.14)/bin/python3.14" -m venv work/python-venv
work/python-venv/bin/python -m pip install -r requirements-runtime.txt -r requirements-build.txt
work/python-venv/bin/python -B -m unittest discover -s tests -v
swift test --disable-sandbox --cache-path "$PWD/work/spm-cache" -c release
swift scripts/make_icons.swift
work/python-venv/bin/python -B scripts/bundle_runtime.py
work/python-venv/bin/python -B scripts/package.py
work/python-venv/bin/python -B scripts/source_archive.py
work/python-venv/bin/python -B scripts/verify_release.py
```

Outputs are placed in `release/`: the app, DMG, source ZIP, `SHA256SUMS`, and a distribution audit. Building a distribution does not require games or keys. Actual bundled dependency versions are recorded in `Runtime/versions.json` inside the app. Homebrew and toolchain versions depend on the build environment; byte-for-byte reproducibility is not currently guaranteed.

[GitHub CI](.github/workflows/ci.yml) runs on main/master pushes, version tags, pull requests, or manual dispatch. A macOS ARM64 runner tests, builds, ad-hoc signs, and verifies packages. Artifacts are retained for 14 days. A tag matching `product.json` (for example `v0.2.4`) publishes a GitHub Release only after the Mac job and checksum validation succeed. Ordinary branch and pull-request runs do not publish releases. CI does not run commercial games or replace physical hardware validation. See the [release preparation guide](docs/发布准备.md) (Chinese).

Use the ignored `work/` directory for development and private tests. `--data-root <directory>` isolates application data. Do not commit `work/`, `release/`, `Runtime`, or any player data.

## Acknowledgements and origins

**Special thanks to the authors and contributors of [nxnative](https://github.com/seedds/nxnative), LumaDock's direct upstream and the source of its core game execution and graphics capabilities.** We also thank the authors and contributors of MacNativeGames, d2r-mobile, and the dependencies below. Their work makes this launcher possible.

The upstream contributions and their licenses are credited here:

- **[nxnative](https://github.com/seedds/nxnative)** (MIT, Copyright © 2026 jhaizhou) is the direct upstream. It provides native execution, NSO rewriting, the system-service runtime, and graphics translation. LumaDock adds the library, graphical workflow, worker, configurable input, and Mac distribution tools. Upstream source and its license are retained in [`Vendor/nxnative`](Vendor/nxnative/LICENSE).
- **[d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile)** (MIT) is an origin of nxnative's native-execution approach; see [upstream acknowledgements](Vendor/nxnative/README.md#acknowledgements).
- **[MacNativeGames](https://github.com/ly05010419/MacNativeGames)** (MIT) contributed graphics and shader improvements incorporated through nxnative. See the [upstream third-party notes](Vendor/nxnative/dm/third_party/README.md) and [license](Vendor/nxnative/dm/third_party/macnativegames/LICENSE) for scope and terms.
- **Ryujinx / Spv.Generator, [LibHac](https://github.com/Thealexbarney/LibHac), and [SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross)** provide shader translation, NSP content reading, and SPIR-V to Metal conversion through upstream.
- **CPython, .NET, Capstone, lz4, fontTools, Zstandard**, and other upstream components retain their respective licenses in source or bundled runtime files. See [third-party notices](docs/Third-party-licenses.md).

## License, copyright, and risks

New launcher code and original icon artwork use the **[MIT License](LICENSE)**. Third-party code retains its own licenses. The software is provided “AS IS,” without guarantees of compatibility, stability, or fitness for a particular purpose. Experimental execution may cause crashes or save-data loss.

Nintendo, Nintendo Switch, game names, trademarks, artwork, and game content belong to their respective rights holders. This project is not affiliated with, sponsored by, or endorsed by Nintendo or any game publisher. An open-source code license does not grant rights to use or redistribute games, firmware, keys, or trademarks.

Confirm the source and permissions for your input files and follow applicable local laws and platform terms. This project does not provide downloads, key sharing, or acquisition sources for that content. Ownership of hardware or a game should not be treated as authorization for every extraction, use, or redistribution activity.
