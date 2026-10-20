# nxnative

Play your own Nintendo Switch games natively on iPhone and iPad. Bring your game (its NSP files) and your `prod.keys`; one script turns them into an IPA that you sideload.

It is not an emulator: the game's own code runs directly on the Apple chip, with Switch graphics rebuilt on Metal. Nothing from any game is in this repository, and the project is not affiliated with Nintendo or any game publisher.

## Acknowledgements

This project is built on other people's work:

- **[d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile)** (MIT) developed this native-execution approach, for Diablo II: Resurrected. nxnative (first called smbw-mobile) started as a copy of its generic parts: the NSO rewriter, the host that stands in for Horizon, the NVN-on-Metal layer and the iOS app shell. Fixes go both ways.
- **Ryujinx** (MIT): its shader translator (`Ryujinx.Graphics.Shader`, `Ryujinx.Common` and `Spv.Generator` 1.3.2, in `dm/third_party/ryujinx` with a few fixes listed in [its README](dm/third_party/ryujinx/README.md)) turns the games' Maxwell shaders into SPIR-V. Its emulation of the kernel and system services is also a reference when the host's behaviour is in doubt.
- **[Atmosphère](https://github.com/Atmosphere-NX/Atmosphere)**: its kernel, mesosphère, is the reference for Horizon's synchronization semantics (address arbiter, condition variables).
- **yuzu**: Maxwell instruction encodings for the shader reference tool, and a cross-check for kernel behaviour.
- **[LibHac](https://github.com/Thealexbarney/LibHac)**: reads NSPs and layers updates over the base game in `dm/tools/nx_extract`. **hactool** did the first extractions.
- **[SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross)**: SPIR-V to Metal Shading Language.
- **deko3d** (zlib): its texture layout size algorithm is ported in `dm/gfx/nvn/nvn_tex.c`.
- **libvpx** (VP9 movies), **stb_vorbis** (movie sound), **libdeflate**, the **Vulkan headers** and **NVIDIA FLIP** ship in `dm/third_party` with their licenses ([list](dm/third_party/README.md)).
- **Capstone**, **lz4**, **fontTools** and **XcodeGen** are used by the build.

## Games

All of these are tested on an iPhone and playable:

| Game | IPA | Notes |
|---|---|---|
| Super&nbsp;Mario&nbsp;Bros.&nbsp;Wonder | ~4&nbsp;GB | |
| Fire&nbsp;Emblem&nbsp;Engage | ~15&nbsp;GB | Upgraded to 60 fps (30 fps on Switch) |
| Metroid&nbsp;Dread | ~5&nbsp;GB | |
| 13&nbsp;Sentinels:&nbsp;Aegis&nbsp;Rim | ~5&nbsp;GB | |
| Super&nbsp;Mario&nbsp;3D&nbsp;World&nbsp;+&nbsp;Bowser's&nbsp;Fury | ~3&nbsp;GB | |
| The&nbsp;Legend&nbsp;of&nbsp;Zelda:&nbsp;Breath&nbsp;of&nbsp;the&nbsp;Wild | ~16&nbsp;GB | Upgraded to 60 fps (30 fps on Switch) |
| The&nbsp;Legend&nbsp;of&nbsp;Zelda:&nbsp;Link's&nbsp;Awakening | ~6&nbsp;GB | |
| Super&nbsp;Mario&nbsp;Odyssey | ~6&nbsp;GB | |
| Hades | ~4&nbsp;GB | |
| Hyrule&nbsp;Warriors:&nbsp;Age&nbsp;of&nbsp;Calamity | ~15&nbsp;GB | Upgraded to 60 fps (30 fps on Switch) |
| Fire&nbsp;Emblem:&nbsp;Three&nbsp;Houses | ~13&nbsp;GB | Upgraded to 60 fps (30 fps on Switch) |
| Super&nbsp;Mario&nbsp;Galaxy | ~3&nbsp;GB | |
| The&nbsp;Legend&nbsp;of&nbsp;Zelda:&nbsp;Tears&nbsp;of&nbsp;the&nbsp;Kingdom | ~17&nbsp;GB | Upgraded to 60 fps (30 fps on Switch) |
| Monster&nbsp;Hunter&nbsp;Rise | ~22&nbsp;GB | Upgraded to 60 fps (30 fps on Switch) |
| Ace&nbsp;Attorney&nbsp;Investigations&nbsp;Collection | ~7&nbsp;GB | |

| | |
|:---:|:---:|
| ![Super Mario Bros. Wonder](docs/images/super-mario-bros-wonder.jpg)<br>Super Mario Bros. Wonder | ![Fire Emblem Engage](docs/images/fire-emblem-engage.jpg)<br>Fire Emblem Engage |
| ![Metroid Dread](docs/images/metroid-dread.jpg)<br>Metroid Dread | ![13 Sentinels: Aegis Rim](docs/images/13-sentinels.jpg)<br>13 Sentinels: Aegis Rim |
| ![Super Mario 3D World + Bowser's Fury](docs/images/super-mario-3d-world.jpg)<br>Super Mario 3D World + Bowser's Fury | ![The Legend of Zelda: Breath of the Wild](docs/images/zelda-breath-of-the-wild.jpg)<br>The Legend of Zelda: Breath of the Wild |
| ![The Legend of Zelda: Link's Awakening](docs/images/zelda-links-awakening.jpg)<br>The Legend of Zelda: Link's Awakening | ![Super Mario Odyssey](docs/images/super-mario-odyssey.jpg)<br>Super Mario Odyssey |
| ![Hades](docs/images/hades.jpg)<br>Hades | ![Hyrule Warriors: Age of Calamity](docs/images/hyrule-warriors-age-of-calamity.jpg)<br>Hyrule Warriors: Age of Calamity |
| ![Fire Emblem: Three Houses](docs/images/fire-emblem-three-houses.jpg)<br>Fire Emblem: Three Houses | ![Super Mario Galaxy](docs/images/super-mario-galaxy.jpg)<br>Super Mario Galaxy |
| ![The Legend of Zelda: Tears of the Kingdom](docs/images/zelda-tears-of-the-kingdom.jpg)<br>The Legend of Zelda: Tears of the Kingdom | ![Monster Hunter Rise](docs/images/monster-hunter-rise.jpg)<br>Monster Hunter Rise |
| ![Ace Attorney Investigations Collection](docs/images/ace-attorney-investigations.jpg)<br>Ace Attorney Investigations Collection | |

Needs iOS / iPadOS 26 or later on an iPhone 15 Pro or newer (A17 Pro chip or later) or an iPad with an M1 chip or later: the games' textures are BC-compressed, and older iPhones can't read that format. Other games aren't supported yet. For them the script writes a survey and still tries its best to pack an IPA, guessing the game's settings; such an IPA may not start.

## Pack an IPA

**1. Get nxnative and its tools** (once, on a Mac with [Xcode](https://apps.apple.com/app/xcode/id497799835) and [Homebrew](https://brew.sh)):

```
git clone https://github.com/seedds/nxnative.git && cd nxnative
brew install xcodegen zstd spirv-cross
brew install --cask dotnet-sdk
python3 -m pip install lz4 capstone fonttools
```

**2. Put one game's NSPs in a folder**, base game (an NSP, or an XCI cartridge dump) and update (and any DLC):

```
~/Games/MarioWonder/
  Super Mario Bros. Wonder [010015100B514000][v0].nsp
  Super Mario Bros. Wonder [010015100B514800][v327680].nsp
```

**3. Run the script:**

```
python3 scripts/build_ipa_from_nsp.py ~/Games/MarioWonder -k ~/keys/prod.keys
```

The IPA appears in the same folder (here `~/Games/MarioWonder/SMBWMobile.ipa`). The first build takes 30–60 minutes, later ones about 10. You need free disk space of about twice the NSPs' size plus 10 GB. Options such as `-o` (output path) and `--app-name` are listed by `-h`.

**4. Install** the IPA with your sideloading tool (AltStore, Sideloadly, LiveContainer, …). The app gets the game's name, icon and version (the update's version, for example 1.2.1 for Mario Wonder; the base game's when there is no update).

## Play

**Touch controls.** Tap **2D** / **3D** at the top to switch layouts; the app remembers your choice. Wonder, Engage, Dread, 13 Sentinels and Link's Awakening start in 2D, the other games in 3D. In Super Mario Galaxy, touches outside the controls move the pointer.
A connected game controller hides the touch controls and keeps every button.

- **Game language** is English by default. For Chinese, add the line `DM_LANG=zh-Hans` to `Documents/env.txt`.
- **Saves and logs** are in the Files app, under the app's name: `save/` and `log.txt`. When something goes wrong, send `log.txt` (the previous run is `log.prev.txt`).
- **Short stutters** the first time a new scene appears are normal: the app compiles graphics for it once and remembers them for the next launch.
- **Reinstalling:** some sideloading tools give a reinstalled app a new data folder. Copy `save/` and `pso_user.tsv` over from the old one to keep your progress.
- **Settings without rebuilding:** put lines like `DM_OPMODE=0` (handheld mode: lower resolution, higher frame rate) in `Documents/env.txt`. `DM_FPS_TARGET=30` keeps Breath of the Wild and Tears of the Kingdom at their original 30 fps, which saves battery.

## Known issues

- No amiibo and no online features.
- Fire Emblem Engage: after switching away from the app and back, some sounds may stay silent until you restart it.
- Fire Emblem: Three Houses: small square patches on the ground where decals land.
- Super Mario Galaxy: effects drawn as points or lines come out one pixel wide.

## For developers

How it works, the script's options, running games on the Mac, adding a game, and per-game notes: [docs/development.md](docs/development.md). In-depth bring-up and debugging notes: [docs/agents](docs/agents/README.md).

## License

MIT (see [LICENSE](LICENSE)). Third-party code keeps its own license; see [dm/third_party](dm/third_party/README.md).
