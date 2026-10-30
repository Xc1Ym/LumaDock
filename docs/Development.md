# Developing LumaNX

[简体中文](开发说明.md) · [Project README](../README.md)

The launcher uses SwiftUI / AppKit and a Python Worker. nxnative is bundled under `Engine/nxnative`; CI combines synthetic interface fixtures with native engine tests and builds, without games or keys. See the [architecture](架构说明.md) and [engine interface](引擎修改.md) (Chinese).

## Tests and local builds

Use an Apple Silicon Mac with full Xcode, Homebrew and the [.NET 10 SDK for macOS Arm64](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) on `PATH`. Run from the repository root; adjust `DEVELOPER_DIR` for your Xcode location.

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
mkdir -p work
brew install python@3.14 spirv-cross zstd xcodegen actionlint
"$(brew --prefix python@3.14)/bin/python3.14" -m venv work/python-venv
work/python-venv/bin/python -m pip install -r requirements-runtime.txt -r requirements-build.txt
actionlint .github/workflows/*.yml
work/python-venv/bin/python -B -m unittest discover -s tests -v
swift test --disable-sandbox --cache-path "$PWD/work/spm-cache" -c release
```

For the real macOS / iOS Metal and synthetic UIKit IPA checks, install the iOS platform in Xcode and run:

```bash
xcodebuild -downloadComponent MetalToolchain
work/python-venv/bin/python -B scripts/check_shader_diagnostics.py
```

To build the app, DMG and source archive, then verify signatures, runtime relocation and checksums:

```bash
swift scripts/make_icons.swift
work/python-venv/bin/python -B scripts/bundle_converter.py
work/python-venv/bin/python -B scripts/bundle_runtime.py
work/python-venv/bin/python -B scripts/bundle_engine.py
work/python-venv/bin/python -B scripts/package.py
work/python-venv/bin/python -B scripts/source_archive.py
work/python-venv/bin/python -B scripts/verify_release.py
```

Packaging refuses to replace a running output app or its active runtime children. Use `scripts/package.py --output-dir release/local-preview --app-only` to build a separate copy while testing. A complete signed app is validated in a staging directory before publication; failed publication or relocated-runtime validation restores the previous app.


Outputs are placed in `release/`. Bundled dependency versions are recorded in the app's `Runtime/versions.json`; toolchains vary with the build environment, so byte-for-byte reproducibility is not guaranteed.

DMGs use LZMA (`ULMO`) compression. Runtime staging removes Python development examples, generated fontTools C files and Crypto self-tests, and keeps only the ARM64 slice of universal binaries before signing. Runtime modules, engine profiles, notices and corresponding dependency source archives remain bundled for offline use. Packaging applies the same optimization to previously collected runtimes without modifying `work/Runtime` or a running app.

Use the ignored `work/` directory for development. Launch with `--data-root <directory>` to isolate application data. Never commit `work/`, `release/`, `Runtime`, games, keys, saves or player caches.

Conversion collection pins SAK-Mac, NSC_BUILDER and nsz commits in `scripts/bundle_converter.py`, plus Python versions in `requirements-conversion.txt`. It downloads sources and dependencies on the release builder, applies the upstream macOS patch, retains notices and corresponding GPL/MPL sources, and excludes keys, title databases and player content. The app uses these bundled tools offline. `Runtime/converter/manifest.json` records exact upstream commits, package versions, source URLs and hashes.

## CI and releases

[GitHub CI](../.github/workflows/ci.yml) tests, builds and verifies packages on a macOS ARM64 runner. Main/master pushes, PRs and manual runs produce build artifacts, retained for 14 days. A version tag matching `product.json` publishes a Release only after the Mac build and checksum checks succeed. Releases contain only the CI-generated DMG; its SHA-256 is in the Release notes. Source ZIPs, checksums, audits and icons remain internal CI artifacts.

Current packages use ad-hoc signing and are not notarized. CI does not run commercial games or replace physical-device validation. See the [release process](发布准备.md) and [validation record](验收记录.md) (Chinese).

Daily upstream sync runs at 03:00 Asia/Shanghai (GitHub may delay schedules). `scripts/sync_engine.py` records the upstream SHA and file hashes, excludes screenshots/private files, and reapplies the shared Mac/iOS controller policy. Interface changes fail the sync. The candidate must pass the complete reusable CI, including packaging and relocation, before a normal push to main; a changed main rejects stale candidates. Failed checks preserve the previous engine. Daily runs do not create tags or Releases. Build the App/DMG above for the latest synchronized snapshot; Release packages are provided on demand. Branch protection may require repository administrators to allow the bot push; no force push or bypass is configured.

The sync also guards the iOS 27 `deviceMotionBody` declaration at compile time so Xcode 26 can build the engine using the existing orientation fallback. SDK 27 builds retain the runtime availability check and the view-based motion frame. The guard is reapplied on every import; a changed patch interface fails before replacing the previous snapshot.

## Product identity

The Swift package, source target, executable and repository are named **LumaNX**. The original icon is unchanged. `org.nsmac.launcher`, `Application Support/NSMac` and `.nsmac-library.json` remain stable for existing installations and libraries. Historical copyright and third-party notices retain their original names.
