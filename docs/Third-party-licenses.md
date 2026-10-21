# Third-party components and copyright

LumaDock's launcher and original icon use the MIT License, Copyright © 2026 LumaDock contributors. Third-party components retain their own licenses. This license grants no rights to Nintendo games, firmware, keys, trademarks or other rights holders' material.

## External engine acknowledgements

Special thanks to [nxnative](https://github.com/seedds/nxnative) (MIT, Copyright © 2026 jhaizhou), which provides native execution, rewriting and graphics translation. Players obtain and select the engine themselves. Its source, executable tools, LibHac reader and shader translator are **not distributed in the LumaDock app, DMG or source archive**. Its own licenses remain in the external directory.

We also thank [d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile) and [MacNativeGames](https://github.com/ly05010419/MacNativeGames). The selected engine may use their contributions and libraries such as Ryujinx / Spv.Generator, LibHac, libvpx, libdeflate, stb_vorbis and Vulkan headers. Consult the licenses and notices in that engine's source tree for the actual selected version. These acknowledgements do not imply that those engine components are bundled here.

LumaDock's own metadata-protocol extension is in `Worker/NspMetadata.cs`; it is compiled only in the user's private engine snapshot. No upstream engine implementation is embedded in that extension.

## Bundled generic dependencies

CPython (PSF License), .NET runtime (MIT and third-party notices), Capstone (BSD), lz4 (BSD), fontTools (MIT), SPIRV-Cross (Apache-2.0), Zstandard (BSD option), and their runtime dependencies retain their license texts in `Runtime/licenses` and package metadata. Exact versions are recorded in `Runtime/versions.json`. The .NET SDK is installed separately by the user when compiling external engine tools.

Apple Xcode, Metal compiler components and fonts are not redistributed. LumaDock includes no games, updates, DLC, firmware, keys, game artwork, saves or player caches. It is not affiliated with, sponsored by or endorsed by Nintendo or game publishers. Import only content you are authorized to use.
