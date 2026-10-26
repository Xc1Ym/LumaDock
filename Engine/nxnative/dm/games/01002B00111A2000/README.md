# Hyrule Warriors: Age of Calamity (`01002B00111A2000`)

Update 1.3.0 (v327680) over the base game, with four DLC packages (one is only a licence). SDK 9.6.0. Koei Tecmo's KTGL engine on NVN. Modules `main`, `subsdk0` (Nintendo's movie library, NintendoSDK_movie, as in Metroid Dread) and `sdk`. Plays on the iPhone; 60 fps (30 on the Switch) through the host's frame step. Started from the NSP script's provisional profile.

## What it needs

| Setting | Where | Why |
|---|---|---|
| Frame step, `fps_target 60` | [`patches.py`](patches.py) `FRAME_STEP`, [`game.tsv`](game.tsv) | three stubs run the game's fixed-step updates at the cap; see [Frame rate](#frame-rate) |
| `fps_hold off` | `game.tsv` | the updates step by the cap whatever the hold, so holding late frames only paces the screen: each frame is shown as soon as it is ready (the 60fps IPA ran battles at 45–57) |
| Sound heap cut: engine heap +4 MB, sound data heap −4 MB | `patches.py` `CUTS`, `main` build `c3cf52bf…` | the KTSL sound setup gave up quietly and the main thread waited forever; see [Audio](#audio) |
| `mem_used 0x4800000` (72 MB) | `game.tsv` | the three modules take 66.6 MB, more than the default 64 MB, so `SetHeapSize` failed; see [Memory](#memory) |
| 4 GB layout: `mem_reserve 0x100000000`, `mem_alias 0x10000000`, `mem_stack 0x10000000`, `app_pool 0xCD500000` | `game.tsv` | the NPDM declares no system resource (META +0x14 = 0), so the game uses `SetHeapSize`. Link's Awakening's partition, not measured for this game |
| `tex_flush_upload on` | `game.tsv` | movie frames are CPU-written and published with `nvnMemoryPoolFlushMappedRange`; without the upload the intro movie stayed black under its "+ Skip" prompt |
| `vconv_range on` | `game.tsv` | KTGL binds whole mesh pools; the CPU vertex conversion runs only over the vertices each draw reads; see [Battles](#battles) |
| `pad_layout full` | `game.tsv` | the 3D gamepad layout: the camera is on the right stick |

## Frame rate

- The game steps a fixed amount per update, from three 30 fps values:
  - a KIDS task on `KIDSTaskScheduler` threads (`main+0x166d980`, once per update) waits until 1 / fps has passed since the last update (fps at time +0x30: 30 from a frame-rate object, `main+0x166daa4`; `csinc` at `main+0x166db80`) and then steps the game clock (system +0x3348, the step at +0x3350) by that object's step (x23 +0x34: 1/30 s times the game's timescale, a second time at +0x44, fps 30 at +0x48), not by the time that passed (the measured path, `main+0x166dca8`, runs only without the object);
  - the battle steps 1 / the game's frame rate per update: a block at `main+0x269e150` {fps, interval, fps, float fps} = {30, 2, 30, 30.0}, read by the scene update's caller (`main+0x8c3610`: step = 1.0 / fps) and its jobs (32 reads; the game's own writers at `main+0x8a35e0` / `main+0xfc1618`, a run-time interval request at +0x1d58, never ran in a probe);
  - the event scripts step by the KTGL device's frame rate (device +0x32d0), 59.94 / the present interval in its config (2). nnMain builds the device config on its stack and inits the device once (`main+0x8d94c4` → `main+0x17c34f0`): {1920, 1080, 3, 9, 5, interval 2, 9, …}. The device keeps the interval (`main+0x17c4ba8` → device +0x2aa4, passed to every present at `main+0x17ced78`, which sets it on the window when it changes) and its frame rate, 59.94 / interval (`main+0x17c37c8` → device +0x32d0).
- **Resolved:** the first 60 fps cuts (interval 1, a 1/60 s wait) were checked only on cutscenes, which follow the device: `DM_PROBE` showed the game clock at 2.00 × real time, and battles ran twice as fast on an iPhone. Fixing the clock alone was not enough: in a 3 s stick hold Link still covered twice the ground of the 30 fps original, and the enemy waves came early, until a `sample` profile of a battle led to the frame-rate block.
- **Current:** the game's updates are not held by the presents (the task kept 60 updates a second while the host held frames 3 vsyncs), so three frame-step stubs (`FRAME_STEP`) run the updates at the cap and the host's frame step paces only the presents:
  - at `main+0x166dab4` (where both fps paths join, before the update's tasks and the wait) the task's fps and the frame-rate block become the cap (60, or 30 at a 30 cap), the update's vsyncs (60 / cap) are marked (state +0x28) and the device frame rate becomes 59.94 / those vsyncs;
  - at `main+0x166dc60` the object's steps are scaled by its fps × vsyncs per update / 60, and the vsyncs are counted;
  - at `main+0x8d94b0` nnMain's device config gets interval 1 above a 30 fps cap (the engine's own 60 fps mode), else the game's 2.
- Every step stays per update, as on the Switch, so an update rate below the cap slows them all together. The host shows each frame as soon as it is ready (`fps_hold off`); the updates keep their speed whatever is shown.
- `DM_FPS_TARGET=30` runs updates and presents at 30; `DM_FPS_TARGET=0` is the Switch original (interval 2, the stubs' original paths; the device frame rate follows the game's fps, 29.97 at 30, and the steps and the block stay the game's).
- Checked on the Mac: the forced 30 and the original put Link on the same spot after the same stick hold, and the opening scenes at frame 2N at 60 match the original's frame N (same subtitle, same poses).
- x16, x17, s16–s18 and the flags are dead at the stub sites; the function uses no x16 / x17.

## Memory

- **Resolved: `nnMain` returned right after `nv::InitializeGraphics`, with no error.** The game's `nninitStartup` (`main+0x8ad318`) sizes its heap as total − used memory (`QueryMemoryInfo`), calls `SetMemoryHeapSize` and hands the block to its own malloc. The host reported 64 MB used beside the heap, but `SetHeapSize` checks a request against the real size of the loaded modules (66.6 MB, 68 MB rounded), so `SetHeapSize(pool − 64 MB)` failed with ResultLimitReached, `AllocateMemoryBlock` returned 0x1003, malloc was never set up, the 866 MB graphics heap allocation came back null (`main+0x8aeb4c`) and `nnMain` returned. Found by probing `DM_SVC=1`'s `svc 0x1` request and the `AllocateMemoryBlock` result. `mem_used` 72 MB (the image plus stacks) gives a heap of 0xc8c00000 (3212 MB), in which the game's fifteen sub-heaps (3098 MB) fit.

## Audio

- **Resolved: the main thread spun at start-up in a resource wait** (a `YieldThread` loop, no crash, right after `OpenAudioRenderer`; nnMain's resource wait at `main+0x8d9bc8`). Koei Tecmo's sound engine (KTSL) failed its setup quietly. The init (`main+0x8d9610`) hands it three heaps cut from one block: 15 MB engine memory, 2 MB and 142 MB sound data (sizes built by `mov x8,#0xf00000; movk x8,#0x20,lsl #48` and `mov w9,#0x8e00000`; constructor `main+0x12647a0`, heaps created at `main+0x1a2ba58`). In the 15 MB heap the setup allocates the renderer config and work buffer (0x760000: `AudioRenderSystem::GetWorkBufferSize`, 0x40a9c8 of it command buffer) and one block per player (up to 0x1b5860; three of the four mix 5.1), about 16.9 MB in all. The fourth player block (`main+0x1a32f70`) came back null, the setup released its memory pools (`RequestAttachMemoryPool` then `Detach` with no update between) and returned −51, the first sound archive (ASRS) never loaded, and the resource the main thread waited for depended on it.
- How it was found: probe the pump the wait calls (`main+0x8e1c0`: first missing stage bit → the type's stage handler), the handler's dependency list (an incomplete entry of type `0xbbd39f2d`, ASRS), then the memory pool states (`MemoryPoolInfo` +0x10: 1 new, 3 detached, 4 request attach, 5 attached, 6 unused) and the engine allocator's arguments and results.
- **Current:** a per-build cut moves 4 MB from the sound data heap to the engine heap (`mov x8,#0xf00000` → `#0x1300000` at `main+0x8d9610`, `mov w9,#0x8e00000` → `#0x8a00000` at `main+0x8d9618`), so the block the three come from keeps its size. Why hardware fits in 15 MB is not known.
- The multi-stream hardware Opus decoder is the SDK's software one (`HardwareOpusMultiStreamDecoder`, see [Services](#services)).

## Rendering

- **Resolved: draws after a dispatch were dropped, so the intro movie stayed black.** The game interleaves dispatches and draws; `BindProgram` with the compute bit replaced the one bound program, and the intro movie's NV12 → RGB draw was dropped (black under its "+ Skip" prompt). Compute programs now have a binding of their own in the replay.
- Images are registered on their own (`nvnTexturePoolRegisterImage`).
- Its GPU-driven effects are indirect quads, converted to indexed indirect arguments by a compute pass.
- **Movie frames:** the decoder's NV12 output (VP9) is copied by the game into a 1280×720 R8 and a 640×360 RG8 texture in a CPU-visible pool and published with `nvnMemoryPoolFlushMappedRange`, so the profile turns on `tex_flush_upload`. Buffer textures (a 1,048,576-texel R32F one) stay out of that path: they are views onto the pool buffer, and an upload would have sent them past Metal's 2D size limit.
- **Light and decal lists:** 16,438 shaders (98,970 bindings) read KTGL's light and decal lists (slots 16–21) from buffer textures with the instruction Maxwell also uses for 1D textures. The translation read them as 2D and the host bound a dummy, so every list read 0. They are now read as rows of 16,384 texels from a linear 2D texture over the buffer (row wrap). No shader both size-queries and fetches such a slot. A 15-minute Mac battle bound 15.7 million of them through 320 row textures, none failed; the first battle is darker and more saturated than with the zeros (mean luma 163 against 178 at the start of the battle), GPU time unchanged.
- **Open red line:** a 2D texture bound where three vertex shaders sample 3D (slots 8 and 9, `texture type mismatch … declares slot 8 as Metal type 7`) is still bound as is; it was hidden behind the earlier red line.

## Battles

- **Vertex conversion over the draw's vertices (`vconv_range`).** The soldiers' Half2 and Short2 attributes feed integer shader inputs, which the replay converted on the CPU (`vconv_bind` in `nvn_mtl.m`); without that conversion, reading the raw bytes as integers gave denormals and the soldiers' UVs collapsed onto one texel. KTGL binds whole mesh pools of up to ~590,000 vertices, so converting the bound ranges came to 4.4 million vertices per submission in the first battle: 24 of the 32 ms the replay took per frame on the Mac, 26 fps at a 30 or a 60 fps target. `vconv_range` converts only what each draw reads (219,000 vertices per submission, about twelve submissions a frame), and the half and 8 / 16-bit integer formats have conversion loops of their own. Keeping the conversions across frames did not pay: the soldiers' attributes change every frame. `DM_NVN_VCONV_CHECK=1` found no stale index range in 983,000 reuses.
- The visibility buffer ring was 4 deep, so the submit thread waited for the previous frame's GPU work; it now has as many buffers as command allocators (8).
- Then: the battle ran at 58.6 fps on the Mac (M4 Pro; frame p50 16.9 ms, replay CPU 10 ms, GPU 11 ms). On an iPhone the GPU decides (14–16 ms per frame at p50 in the first battle, 40–60 ms once the phone reaches thermal state 2): the frame step holds 30 there.
- **Shadow vertex inputs** have since replaced that CPU conversion, a quarter of the replay thread: 2,259 side libraries, 77 MB each for Mac and iOS; with more than 7 integer inputs the last ones get only the float shadow (169 of 8,201 inputs). Mac battle at 60 fps against the CPU conversion: 0 vertices converted instead of 545,000 per submission, submit + present 10.0 → 5.7 ms a frame, CPU 3.97 → 2.44 W, GPU unchanged, the same picture. `vconv_range` still serves the draws that keep the CPU conversion (transform feedback, `DM_NVN_VCONV_CPU=1`).
- **Resolved: battles after the first cutscene ran at 17 fps on the iPhone.** An iPhone log (2026-10-21, `fps_hold off`, thermal state 0) went from about 57 to 17 fps after the first battle's first cutscene: the same 1,000–1,400 draws a frame, but NVN calls from 82,000 to 287,000 a frame, GPU 15 → 51 ms and the replay 12 → 24 ms. The battle then runs more small compute dispatches (on the Mac about 280 → 900–1,500 a frame, each with a game barrier and about 17 texture binds), and two host costs grew with them:
  - every dispatch had a compute encoder of its own with full queue barriers on both sides (about 10 µs of GPU each on the Mac, GPU 9 → 18 ms a frame). Dispatches now share the copy encoder (about 1.3 µs each; GPU 7.3 → 8.1 ms across the cutscene);
  - KTGL registers a texture into the next ID of a ring before every bind (`RegisterTexture`, `GetTextureHandle` and `BindTexture` counts are equal: 8,000 a frame in battle, up to 28,000 after the cutscene). Only 1 in 6 registrations repeated what the ID held, so the per-ID view was rebuilt for half of all binds (`newTextureViewWithPixelFormat` took 45% of the replay thread). Views are now cached by texture serial.
  - Mac runs side by side, after the cutscene: GPU 18.0 → 8.1 ms and frame 35 → 22 ms with the dispatch change; the view cache took the replay before the cutscene from 14.3 to 10.8 ms (2,036 views made in 15 minutes, 211 million reused).
- The game builds 8,705 programs during its first frame (about 10 s on the Mac).

## Services

- **Resolved: null read in `oe::InitializeCopyrightFrameBuffer`** (right after the window setup): `InitializeCopyrightFrameBuffer`, `SetCopyrightImage` and `SetCopyrightVisibility` are host no-ops (`hle_oe.c`).
- **`HardwareOpusMultiStreamDecoder`:** the game builds it with the imported constructor and then calls it through its vtable; the constructor hook builds the SDK's software `OpusMultiStreamDecoder` in place (`hle_codec.c`). This game needed only the class and the four-argument work buffer size.
- **Other games' saves:** it asks whether Breath of the Wild's (and `0100A2C01320E000`'s) save exists for bonus items; the host says no.

## Files and shaders

- Everything sits in RDB archives: `asset/*.rdb` is the index (`_DRK0000` header, one `IDRK0000` record per file); `asset/*.rdb.bin*` and `asset/data/*.file` hold `IDRK` entries, zlib in 16 KB chunks (flag 0x100000). The DLC folders add `.rdb.bin3_0` files of the same layout ([01](../../../docs/agents/01-extract.md#compressed-romfs-content)). `romfs_marker` is `asset/MaterialEditor.rdb.bin`.
- Shaders: 40,726 GLSLC outputs (37,043 pixel, 3,440 vertex, 241 compute, 2 geometry): KTGL's G2S containers (`_S2G3000`, type KTID `0x7bcd279f`; 23,108 entries in `asset/system.rdb.bin*`, 2.3 GB inflated) and one `_DOK0000` container (type `0x20a6a0bb`, the engine's system resources: 151 bare GLSLC outputs, 21 of them drawn in the first battle), plus 117 in `main` (`shader_split.py` `idrk_shaders`). Many have 0x850-byte controls and the compute ones no code header. Mario's texture handle layout (`0x20 + 8 × slot`); pairs come from the single-stage cover (`separable_pairs`).
- `glslc_section` took 3 more outputs (GLSLC version 0x1d.0, whose control +0x20 holds odd values) that used to be dropped ([GLSLC outputs read through their section headers](../../../docs/reference/shaders.md#glslc-outputs-read-through-their-section-headers)).

## Mac routes

- With a save whose first-boot settings were made, `DM_KEYS="f300:A,f420:A,f540:A,f660:A,f780:A,f900:A,f1300:Plus,f1350:Plus"` confirms the settings, skips the intro movie and plays the opening into the first battle, The Battle of Hyrule Field (about frame 4000).

## Found on this game

General host changes first needed here; each applies to every game:

- **Rewriter:** byte jump tables indexed by x30 (`main+0x138216c`; capstone names x30 `lr` and x29 `fp`, mapped back): [Byte tables indexed by x30 (capstone register names)](../../../docs/reference/rewriter.md#byte-tables-indexed-by-x30-capstone-register-names).
- **`mem_used`** for games whose modules exceed 64 MB: [Heap sized from the application pool less used memory](../../../docs/reference/memory.md#heap-sized-from-the-application-pool-less-used-memory).
- **Copyright frame buffer no-ops** and the **hardware Opus multi-stream decoder** as the SDK's software one (`hle_oe.c`, `hle_codec.c`): [Copyright frame buffer overlay](../../../docs/reference/services.md#copyright-frame-buffer-overlay), [Hardware Opus decoders built on the SDK's software decoders](../../../docs/reference/audio.md#hardware-opus-decoders-built-on-the-sdks-software-decoders).
- **Compute's own binding** (`S.cprog`, `g_pp_cprog`), **`nvnTexturePoolRegisterImage`**, **indirect draws and dispatches** (`ixc_run`, `DM_NVN_IXCLOG`), **dispatches in the copy encoder** (`dispatch_enc`, `DM_NVN_DISPATCH_OWN=1`) and **texture views cached by texture** (`vc_get`): [Compute programs bound apart from graphics programs](../../../docs/reference/rendering.md#compute-programs-bound-apart-from-graphics-programs), [Images registered on their own](../../../docs/reference/nvn-objects.md#images-registered-on-their-own), [Indirect draws and dispatches read by the GPU](../../../docs/reference/rendering.md#indirect-draws-and-dispatches-read-by-the-gpu), [Compute dispatches share the copy encoder](../../../docs/reference/rendering.md#compute-dispatches-share-the-copy-encoder), [Texture views cached by texture and view parameters](../../../docs/reference/rendering.md#texture-views-cached-by-texture-and-view-parameters).
- **CPU vertex conversion over the draw's vertices** (`vconv_range`, `vconv_bind`): [dm/games/README.md](../README.md).
- **Shadow vertex inputs** (`dmsh_vin.py`, `vin_ct` / `vin_on`) and **row wrap** for buffer textures read by 1D fetches (`fetch1d`, `tbuf_as_2d`, `nvn_tbuf_rows`): [Shadow vertex inputs](../../../docs/reference/rendering.md#shadow-vertex-inputs), [Buffer textures read by 1D integer fetches (row wrap)](../../../docs/reference/rendering.md#buffer-textures-read-by-1d-integer-fetches-row-wrap).
- **`fps_hold off`** for games whose updates do not wait for the presents: [dm/games/README.md](../README.md).

## Open

- The 3D texture mismatch on slots 8 and 9 above.
- Sources disagree on small counts: `game.tsv` says 118 shaders in `main`, the shader notes 117; `game.tsv` puts the dispatches after the first cutscene at 1,000 to 2,800 a frame and the iPhone battle's GPU at 10 → 41 ms, the development notes at 900–1,500 a frame (Mac) and 15 → 51 ms (iPhone log); `patches.py` speaks of "two 30 fps values" before describing the third.
- The memory layout is Link's Awakening's, not measured for this game (`game.tsv`).
