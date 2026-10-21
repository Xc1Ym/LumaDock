# Environment and repair guide

Setup and Settings use the same checks. They run once per app launch; opening Settings reuses the result. **Check again**, selecting a different engine/Xcode/library, and finishing component management refresh the checks. You can leave setup with **Set up later** / Esc or quit with **Quit LumaDock** / ⌘Q, including after a failure.

## External nxnative engine

LumaDock does **not** include nxnative source, an engine executable, its NSP reader, or its shader translator in the app, DMG or source archive. There is no engine download button or automatic engine download.

1. Obtain and extract a complete nxnative source tree yourself. Keep its licenses and dependencies intact.
2. Click **Choose nxnative directory…** in setup or Settings. Select the root that contains `dm` and `scripts`, rather than a parent folder or `dm` itself. ZIP files and partial source copies are not accepted.
3. Install the official **[Microsoft .NET 10 SDK for macOS Arm64](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)** if it is absent. Select the Arm64 **SDK** installer; a runtime alone cannot compile tools. Complete the installer yourself, then click **Check again**. Standard Microsoft and Homebrew installation locations are detected.
4. Click **Prepare engine tools**. LumaDock snapshots the selected source into its private cache, adds its metadata protocol bridge when needed, and compiles the NSP reader. The first build may restore the project's LibHac package from NuGet, so network access can be needed. This operation never downloads nxnative.
5. Check again. A complete cached reader no longer requires the SDK to remain installed. A damaged cache or a source change requires preparing the tools again.

The selected directory stays unchanged. Source snapshots, tool outputs, NuGet packages and SDK working files are under `~/Library/Application Support/NSMac/`; game builds use separate workspaces in the library. Moving identical sources allows tool reuse. A content change creates a new identity and cannot silently reuse a different engine's build. Old successful game runtimes are retained.

Validation checks required files, build functions, profiles, translator source fingerprints and actual reader execution. Arbitrary nxnative revisions are not guaranteed to be compatible. Directories with incompatible interfaces or external symlinks receive an actionable failure. The launcher neither updates a checkout nor follows a branch.

Input configuration requires an engine with `DM_INPUT_CONFIG` support. An engine without that interface uses its own controls; the mapping editor explains that saved LumaDock mappings will not apply. Switching to a capable engine requires preparing the game again.

## Required tools

| Tool | Installation / source | Verification | Needed for |
| --- | --- | --- | --- |
| Apple Silicon, macOS 26+ and Metal device | Mac hardware and macOS | Native arm64 process, OS version and actual Metal device creation | Preparation and launch |
| Full Xcode | Mac App Store / full Xcode | Install from the Mac App Store, open it and finish its license and components. Select the actual Xcode.app; Command Line Tools alone are insufficient | Preparation |
| macOS SDK, clang, make, ar, codesign | Selected Xcode installation | Supplied by Xcode; compile/link an original arm64 program, create a static library and verify local signing | Preparation |
| Metal compiler and metallib | Apple’s component manager | Install using the app's Apple component action after Xcode setup. Check by compiling an original test shader | Preparation |
| External nxnative | Player-provided local sources | Player-selected source directory, API/profile validation and source fingerprint | Import and preparation |
| .NET 10 SDK | Microsoft macOS Arm64 SDK installer | Player installs Microsoft's macOS Arm64 SDK; verify `--list-sdks` | Initial engine reader preparation |
| Engine reader / LibHac | Private build from external sources | Compiled from the external directory into private cache, never shipped | Import and preparation |
| Shader translator | External engine directory | Supplied by the external engine; executable/source fingerprint and required DLLs checked | Preparation |
| Python, capstone, lz4, fontTools | Bundled generic runtime | Bundled generic interpreter/extensions; isolated startup, versions, arm64 disassembly, compression round trip and font library loading | Python: preparation/launch; extensions: preparation |
| .NET 10 runtime | Bundled generic runtime | Bundled generic runtime, with version and load-path verification | Reader and translator execution |
| SPIRV-Cross and Zstandard | Bundled generic tools | Bundled generic tools, checked by actual execution | Preparation |
| Library storage | Player-selected volume | Connected, writable, executable volume with matching identity and enough space | Preparation and launch |

The generic free-space threshold is 5 GB; individual game builds check their actual source sizes again and can need 40–80 GB or more. No generic number guarantees enough space for every build.

## Xcode and Metal installation

Use **Get Xcode on the App Store**, open Xcode and finish Apple's license/initial components yourself. If Xcode is elsewhere, select it and check again. LumaDock sets its processes' `DEVELOPER_DIR` without changing global `xcode-select`.

Use **Install Metal compiler** after Xcode setup. This invokes Apple's `xcodebuild -downloadComponent MetalToolchain`; removal, when supported, uses the Apple component manager and requires confirmation. See [Apple's component instructions](https://developer.apple.com/documentation/xcode/downloading-and-installing-additional-xcode-components). No engine download occurs.

If initial setup still fails, expand **Installation and repair** to see the selected path, actual command and diagnostic. If Xcode setup is already complete, check again or quit and reopen LumaDock first. The optional manual repair command installs initial components and accepts the Xcode license; read and agree to the license before running it yourself. LumaDock never executes that administrator command automatically.

## Bundled dependencies and offline help

Generic runtimes are resolved relative to the current app at `Contents/Resources/Runtime`. Full paths printed by .NET describe the current installation, rather than a fixed developer path. Moving or renaming the complete app does not require reinstalling Python/.NET. Native dependency paths are audited during packaging.

A separate system Python or Homebrew is not required. If a bundled component is broken, reinstall the complete LumaDock app from its official release; do not modify its Python with pip. Engine problems are repaired through the external directory and private tool cache, rather than by looking for a bundled engine.

**Environment installation guide** opens this included guide in LumaDock's offline reader. Already prepared runtimes can launch without an available engine directory or build tools when their runtime files and launch checks pass. Rebuilding or importing requires restoring the external engine and preparation tools.
