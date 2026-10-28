# Environment and repair guide

Setup and Settings use the same checks. They run once per app launch; opening Settings reuses the result. **Check again**, selecting a different engine/Xcode/library, and finishing component management refresh the checks. You can leave setup with **Set up later** / Esc or quit with **Quit LumaNX** / ⌘Q, including after a failure.

## Bundled nxnative engine

nxnative sources, the shader translator and a compiled LibHac metadata reader are included in the app. The app verifies and initializes its private engine cache automatically on first use. If initialization fails, choose **More tools → Repair bundled engine** and check again. Packaged apps need no engine download, .NET SDK or NuGet restore. Source builds still require the .NET 10 SDK on the builder.

The source manifest records the upstream commit and file hashes. Old external-directory preferences are superseded by the bundled engine. App updates change the engine identity; prepare games again to build a new host, while previously successful runtimes remain available. Source and app resources stay read-only.

Switch Pro A / Xbox A / PS cross automatically produce game A through GameController. Nintendo retains its printed A/B/X/Y layout; Xbox retains its letters; PS cross/circle/square/triangle produce A/B/X/Y. This does not require `DM_INPUT_CONFIG`; the optional mapping editor still requires that separate engine interface.

nxnative is synchronized daily in the repository only after CI succeeds. Build your own App/DMG for the latest snapshot; Releases are provided on demand.

## Required tools

| Tool | Installation / source | Verification | Needed for |
| --- | --- | --- | --- |
| Apple Silicon, macOS 26+ and Metal device | Mac hardware and macOS | Native arm64 process, OS version and actual Metal device creation | Preparation and launch |
| Full Xcode | Mac App Store / full Xcode | Install from the Mac App Store, open it and finish its license and components. Select the actual Xcode.app; Command Line Tools alone are insufficient | Preparation |
| macOS SDK, clang, make, ar, codesign | Selected Xcode installation | Supplied by Xcode; compile/link an original arm64 program, create a static library and verify local signing | Preparation |
| Metal compiler and metallib | Apple’s component manager | Install using the app's Apple component action after Xcode setup. Check by compiling an original test shader | Preparation |
| Bundled nxnative | Included engine snapshot | Upstream revision, manifest, API/profile validation and source fingerprint | Import and preparation |
| .NET 10 SDK | Microsoft macOS Arm64 SDK installer | Builder only; verify `--list-sdks` | Building the App/DMG from source |
| Engine reader / LibHac | Compiled on the app builder and included | Content fingerprint and hashes checked before private copy | Import and preparation |
| Shader translator | Bundled engine snapshot | Executable/source fingerprint and required DLLs checked | Preparation |
| Python, capstone, lz4, fontTools | Bundled generic runtime | Bundled generic interpreter/extensions; isolated startup, versions, arm64 disassembly, compression round trip and font library loading | Python: preparation/launch; extensions: preparation |
| .NET 10 runtime | Bundled generic runtime | Bundled generic runtime, with version and load-path verification | Reader and translator execution |
| SPIRV-Cross and Zstandard | Bundled generic tools | Bundled generic tools, checked by actual execution | Preparation |
| Library storage | Player-selected volume | Connected, writable, executable volume with matching identity and enough space | Preparation and launch |

The generic free-space threshold is 5 GB; individual game builds check their actual source sizes again and can need 40–80 GB or more. No generic number guarantees enough space for every build.

## Xcode and Metal installation

Use **Get Xcode on the App Store**, open Xcode and finish Apple's license/initial components yourself. If Xcode is elsewhere, select it and check again. LumaNX sets its processes' `DEVELOPER_DIR` without changing global `xcode-select`.

Use **Install Metal compiler** after Xcode setup. This invokes Apple's `xcodebuild -downloadComponent MetalToolchain`; removal, when supported, uses the Apple component manager and requires confirmation. See [Apple's component instructions](https://developer.apple.com/documentation/xcode/downloading-and-installing-additional-xcode-components). No engine download occurs.

If initial setup still fails, expand **Installation and repair** to see the selected path, actual command and diagnostic. If Xcode setup is already complete, check again or quit and reopen LumaNX first. The optional manual repair command installs initial components and accepts the Xcode license; read and agree to the license before running it yourself. LumaNX never executes that administrator command automatically.

## Bundled dependencies and offline help

Generic runtimes are resolved relative to the current app at `Contents/Resources/Runtime`. Full paths printed by .NET describe the current installation, rather than a fixed developer path. Moving or renaming the complete app does not require reinstalling Python/.NET. Native dependency paths are audited during packaging.

A separate system Python or Homebrew is not required. If a bundled component is broken, reinstall the complete LumaNX app from its official release; do not modify its Python with pip. Repair engine problems by reinstalling the complete app and preparing the private tool cache again.

**Environment installation guide** opens this included guide in LumaNX's offline reader. Already prepared runtimes can launch without an available engine directory or build tools when their runtime files and launch checks pass. Rebuilding or importing requires restoring the bundled engine and preparation tools.
