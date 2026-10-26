# Third-party components and copyright

LumaDock's launcher and original icon use the MIT License, Copyright © 2026 LumaDock contributors. Third-party components retain their own licenses. This license grants no rights to Nintendo games, firmware, keys, trademarks or other rights holders' material.

## Bundled engine acknowledgements

Special thanks to [nxnative](https://github.com/seedds/nxnative) (MIT, Copyright © 2026 jhaizhou). The pinned source snapshot and shader translator are bundled in `Engine/nxnative`, together with upstream LICENSE and dependency notices. A LibHac metadata reader is compiled on the app builder and included under `Engine/reader`. `Engine/nxnative/manifest.json` records the upstream revision, hashes and local controller adaptation. Engine screenshots are excluded. The snapshot retains the licenses for Ryujinx / Spv.Generator, libvpx, stb_vorbis and Vulkan headers under `dm/third_party`. We also thank [d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile) and [MacNativeGames](https://github.com/ly05010419/MacNativeGames). LumaDock’s metadata bridge is in `Worker/NspMetadata.cs`.

## S2Arm milestone progress

Game-preparation and IPA milestone plans, step-time projection and local-history medians adapt [S2Arm](https://github.com/jhaizhou-ops/S2Arm) at `601b545407d45063d005b4e7ca7f078620f0d630`, specifically `pack/jobs/milestones.py` and `platforms/macos/Sources/S2ArmLauncher/MilestoneProgressView.swift`. The upstream [LumaDock copyright/MIT notice](licenses/S2Arm-progress-NOTICE.txt) is retained. The integration follows nxnative's actual stages and completed shader outputs; S2Arm's engine, shader pipeline and game-specific timing evidence are not bundled or presented as LumaDock validation.

## SAK-Mac conversion integration

Conversion command orchestration and machine-readable / tqdm progress parsing are adapted from [SAK-Mac](https://github.com/ggaoph-lab/SAK-Mac), Copyright (c) 2026 ggaoph-lab, at commit `c8e0baa59a168d9efaa0b556af70e0a08bda51de`. The complete upstream [MIT notice](licenses/SAK-Mac-LICENSE.txt) is retained in source and bundled documentation.

[NSC_BUILDER](https://github.com/julesontheroad/NSC_BUILDER) (`e9083e83383281bdd9e167d3141163dcc56b6710`, MIT) and [nsz](https://github.com/nicoboss/nsz) (`4aea60e8ea7cb1099f286fc57cc7aade6338f32c`, MIT) are included under `Runtime/converter`. NSC_BUILDER includes SAK-Mac's Python 3.11+ / macOS patch; each upstream license and the patch are in `Runtime/converter/licenses`. Keys are never bundled, and NSC_BUILDER runs from a private temporary snapshot.

Pinned Python dependencies and their exact source URLs/hashes are listed in `Runtime/converter/manifest.json`. Their original license/notice files remain in each package's `.dist-info` metadata. Dependencies include Unidecode (GPL-2.0-or-later), pykakasi (GPL-3.0-or-later), and MPL-2.0 components enlighten, jinxed, prefixed, certifi and tqdm (also MIT). Corresponding unmodified source distributions for these components are included in `Runtime/converter/sources`; their licenses apply to those components. The conversion backends run as separate Python processes. `scripts/bundle_converter.py` and `requirements-conversion.txt` describe the collection process; no backends are fetched while using the app.

## Bundled generic dependencies

CPython (PSF License), .NET runtime (MIT and third-party notices), Capstone (BSD), lz4 (BSD), fontTools (MIT), SPIRV-Cross (Apache-2.0), Zstandard (BSD option), and their runtime dependencies retain their license texts in `Runtime/licenses` and package metadata. Exact versions are recorded in `Runtime/versions.json`. The .NET SDK is installed separately by the user when building the engine reader from source.

Apple Xcode, Metal compiler components and fonts are not redistributed. LumaDock includes no games, updates, DLC, firmware, keys, game artwork, saves or player caches. It is not affiliated with, sponsored by or endorsed by Nintendo or game publishers. Import only content you are authorized to use.
