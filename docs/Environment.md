# Runtime and build environment

The first setup step and **Settings → Runtime and build environment** use the same live checklist. Every item has an **Installation and repair** disclosure. Checks run locally, use disposable original test programs, and never read games or keys, install software, or accept Apple's license automatically.

| Requirement | How it is provided or installed | What LumaDock verifies | Needed for |
| --- | --- | --- | --- |
| Apple Silicon, macOS 26+ | Use an Apple Silicon Mac; update in System Settings → General → Software Update | Native arm64 process and OS version; Rosetta is unsupported | Preparation and launch |
| System Metal graphics device | Included with macOS; use a local desktop session | The system can create an actual Metal device | Preparation and launch |
| Full Xcode | Click **Get Xcode on the App Store**, install it, open it once, accept its license and finish initial component installation | Selected app contains the Mac platform, reports its Xcode version, and passes `-checkFirstLaunchStatus` | Preparation |
| macOS SDK, clang, make, ar, codesign | Included with full Xcode; click **Select Xcode.app…** for an installation outside `/Applications/Xcode.app` | SDK 26+, actual arm64 compilation/linking against the host's system frameworks, a signed test executable, make, and static archive creation | Preparation |
| Metal compiler and metallib | Click **Install Metal compiler** after Xcode setup finishes | Actually compiles an original test shader and links a macOS `.metallib`; finding a tool path alone is insufficient | Preparation |
| Bundled Python 3.14 | Included inside the complete LumaDock app | Interpreter starts in isolated mode, matches the component manifest, runs natively, loads required standard modules, and uses the bundled prefix | Preparation and launch |
| capstone, lz4, fontTools | Bundled Python extensions | Actual import, exact manifest versions, sample arm64 disassembly, LZ4 round trip, and font library loading | Preparation |
| .NET 10 runtime | Included with LumaDock; no SDK required on a player's Mac | Correct runtime version loads from the bundled runtime directory | Preparation |
| NSP reader and LibHac | Included with LumaDock | Reader starts and displays usage without reading any player content | Import and preparation |
| Shader translator | Included with the pinned engine | Executable starts and its embedded source fingerprint matches the engine; required DLLs exist | Preparation |
| SPIRV-Cross and Zstandard | Included with LumaDock | Both executables actually start and report their identity | Preparation |
| Library storage | Choose a writable local or external library folder and keep it connected | Correct library identity, writable scratch files, ability to execute from that volume, free space | Preparation and launch |

The generic storage check requires at least 5 GB free. Preparation checks the selected game's source sizes again; large games commonly need 40–80 GB or more. No single generic number guarantees enough space.

## Installing Apple components

1. Install full Xcode through the App Store button. Command Line Tools alone are not the supported installation for LumaDock.
2. Open Xcode using **Open Xcode to finish setup**. The user completes Apple's license and initial component setup in Xcode.
3. Select the actual Xcode app if its path differs from the default, then click **Check again**. LumaDock sets `DEVELOPER_DIR` for its own processes and does not change the system-wide `xcode-select` setting.
4. Click **Install Metal compiler**. LumaDock uses Apple's `xcodebuild -downloadComponent MetalToolchain` command and checks actual compilation after the operation finishes. See [Apple's component installation instructions](https://developer.apple.com/documentation/xcode/downloading-and-installing-additional-xcode-components).
5. Each failed item includes a repair method and applicable action. Raw tool diagnostics are available in its disclosure. A timeout or missing executable becomes a failed check rather than an indefinitely running check.

Only the macOS SDK/compiler is used by this pipeline. No simulator runtime, `xcodegen`, separate Vulkan SDK, Homebrew, system Python, or .NET SDK installation is required for players. Apple frameworks, libvpx, libdeflate and Vulkan headers come from macOS/Xcode or the bundled engine source.

## Repairing an incomplete app

Do not try to repair the bundled Python with `pip` or copy executables between apps. Download a complete DMG from the [official LumaDock releases](https://github.com/Xc1Ym/LumaDock/releases/latest), copy the full app into Applications, reopen it and check again. Keep the existing library and private player data. A packaged app never silently falls back to Homebrew Python; missing Python is reported by the native launcher even when the Worker cannot start.

Existing prepared games can launch without Xcode, Metal compiler, .NET or build-only Python extensions, as long as their runtime files are intact and all launch checks pass. Python is still needed to supervise the game process. Preparing, updating or rebuilding a game requires the complete build checklist. Source development and release packaging have additional maintainer dependencies listed separately in the README.
