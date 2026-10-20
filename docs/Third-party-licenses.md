# Third-party components and copyright

LumaDock's launcher additions and original icon are licensed under the MIT License, Copyright © 2026 LumaDock contributors. This license does not cover Nintendo games, firmware, keys, trademarks, or other rights holders' materials. Third-party components retain their respective licenses.

The project includes pinned nxnative sources and modifications from [seedds/nxnative](https://github.com/seedds/nxnative), commit `4e2dcdc749668ddd4d61361117ad4a6980fabcf7`. Its full MIT license is in `Vendor/nxnative/LICENSE`. Component licenses and notices remain in the source tree. See `docs/引擎修改.md` for engine modifications.

The bundled runtime includes CPython (PSF License), .NET (MIT, with third-party notices), LibHac (MIT), Capstone (BSD), lz4 (BSD), fontTools (MIT), [SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross) (Apache-2.0), and [Zstandard](https://github.com/facebook/zstd) (the BSD option of its dual license). Their dependencies and license texts are preserved in the application. Exact collected versions are recorded in `Runtime/versions.json`; license files are in `Runtime/licenses` and package metadata.

The upstream shader translator uses Ryujinx.Graphics.Shader and other .NET libraries. Original binaries, project files, and upstream licenses are retained; see `Vendor/nxnative/dm/gfx/tools/dmsh_xlate/`. Licenses for libvpx, libdeflate, stb_vorbis, and Vulkan headers remain alongside their source directories.

The upstream engine includes graphics and shader improvements from [MacNativeGames](https://github.com/ly05010419/MacNativeGames) (MIT, Copyright © 2026 MacNativeGames contributors). See `Vendor/nxnative/dm/third_party/README.md` and `dm/third_party/macnativegames/LICENSE`. Ryujinx's MIT license is in `dm/third_party/ryujinx/LICENSE.txt`; Spv.Generator's license remains in its source directory. We thank nxnative, MacNativeGames, d2r-mobile, and their contributors.

Apple Xcode, the Metal toolchain, and system fonts are not distributed with LumaDock. Fonts are read from the player's Mac only when preparing runtime files. The application includes no Nintendo games, firmware, or keys.

LumaDock is not affiliated with, sponsored by, or endorsed by Nintendo or any game rights holder. Trademarks, game names, artwork, and content belong to their respective owners. The launcher provides neither that content nor authorization to use it. Import only files you are authorized to use. Do not redistribute player files, keys, or caches.
