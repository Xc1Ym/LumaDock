# Development

The README covers packing and playing. This page is for working on nxnative itself: how it is built, the script's options, running games on the Mac, adding a game, and per-game notes. Agent-oriented details (bring-up failure catalogue, graphics specifics, debugging recipes) are in [docs/agents](agents/README.md).

## How it works

| Part | State |
|---|---|
| Rewriter (`dm/tools/patch_nso.py`, `DM_RULESET=native`) | Runs unchanged on every module of every supported game. Per-build cuts are keyed by the module's build ID |
| Host (`dm/host`) | Stands in for the Horizon kernel and the system services the games call: threads and synchronization, memory, file system with transactional saves, HID, audio, movies (VP9 through libvpx, Vorbis sound through stb_vorbis), software keyboard, focus and lifecycle |
| Graphics (`dm/gfx`) | NVN on Metal. Shaders are extracted by `shader_split.py` from Nintendo's containers and from Unity's `Shader` objects, then translated offline. Mario: 16,266 of 16,268 shaders compile. Engage: 9,268 of 9,269 |
| Audio | Games that carry the SDK's audio renderer (Mario) run it in-process; games that use AudioOut directly (Engage: Wwise) feed it straight. Output goes through Core Audio (default on iOS, `DM_AUDIO=1` on the Mac) |
| Input | iOS: the touch gamepad and physical controllers. Mac: scripted input (`DM_KEYS=<seconds>:<button>,…`, with `DM_KBD=<text>` answering the system keyboard) or `DM_WINDOW=1` for a window with keyboard input |
| iOS app | One unsigned IPA for iPhone and iPad. The rewritten code is embedded in the executable; the shader libraries, the RomFS and the game icon are inside the app |
| Known gaps | Conditional render is always drawn; `MultiDraw*IndirectCount` waits on the CPU for the GPU-written count; geometry shaders do not translate. TBDR optimizations are off by default (they don't understand bindless textures yet). No amiibo. The bundled prewarm lists are empty. On the Mac, Mario's menu and dialogue text render blank (fine on the iPhone) |

## The packing script in detail

`scripts/build_ipa_from_nsp.py` (`-h` lists every option):

```
# written to the Desktop with your own home-screen name
python3 scripts/build_ipa_from_nsp.py ~/Games/MarioWonder -k ~/keys/prod.keys -o ~/Desktop/Mario.ipa --app-name "Mario Wonder"

# pack Mario 1.0.0 instead of 1.2.1 (the folder still needs both NSPs: the shader tables cover both versions)
python3 scripts/build_ipa_from_nsp.py ~/Games/MarioWonder -k ~/keys/prod.keys -p v0

# delete the extracted game files after the IPA is built (they are kept by default, to skip extraction next time and to run the game on the Mac)
python3 scripts/build_ipa_from_nsp.py ~/Games/MarioWonder -k ~/keys/prod.keys --no-keep-extracted

# a diagnostic build with environment switches baked in (one KEY=VALUE per line)
python3 scripts/build_ipa_from_nsp.py ~/Games/MarioWonder -k ~/keys/prod.keys --env-file diag_env.txt

# a damaged NSP (files failing the NCA's hash check) stops the build after listing them; this packs those files as read
python3 scripts/build_ipa_from_nsp.py ~/Games/MarioGalaxy -k ~/keys/prod.keys --allow-damaged

# a game without a profile: survey, provisional profile (a heap check on the Mac when the game needs one), best-effort IPA
python3 scripts/build_ipa_from_nsp.py ~/Games/NewGame -k ~/keys/prod.keys

# test the guesses on a game that has a profile: build from a provisional one (the IPA is named <ipa>-provisional.ipa)
python3 scripts/build_ipa_from_nsp.py ~/Games/MarioGalaxy -k ~/keys/prod.keys --provisional --allow-damaged
```

In Spyder, open the script, fill in the settings at the top (`NSP_DIR`, `PROD_KEYS`, and optionally `PACKAGE`, `OUT_IPA`, `APP_NAME`, `BUNDLE_ID`, `KEEP_EXTRACTED`; for a game without a profile `HEAP_CHECK`, `HEAP_CHECK_SECS`, `PROVISIONAL`), and press F5. Empty paths are asked for at run time.

What the script does:
1. It finds the game profile from the title ID (the `[title ID]` in the file names, or the NSP's ticket; the update by its `[vN]` tag).
2. It extracts the NSPs.
3. It rewrites the code modules, checking each build ID against the profile. A provisional profile (a game without one in `dm/games`) then gets `mem_used` from the rewritten modules, and, when the game has virtual address memory and sets a heap, a heap check: the Mac host is built into `<id>_build/tools/dmhost` and the game boots in it until its first heap request (a few seconds, log `<id>_build/logs/heap_check.log`), which sizes the heap region (see [dm/games/README.md](../dm/games/README.md), Adding a game).
4. For a profile with `shader_glslc_capture on` (Three Houses), it captures the shaders the game compiles at run time, which no game file holds. It builds the Mac host into `<id>_build/tools/dmhost` and boots the game in it, headless and silent, with `DM_GLSLC_CAPTURE` pointing at `<id>_build/extract/<version>/glslc_capture`. The save, temporary storage and log all stay in `<id>_build/`. It stops the game as soon as every capture file named in the profile's shader map is there (Three Houses: 9, about a second after launch), and gives up after 30 s. A folder that already holds them all is reused.
   A Vulkan profile with `shader_vk_capture on` (Super Mario Galaxy) gets the same kind of run: the game boots in the Mac host with `DM_VK_CAPTURE` pointing at `<id>_build/extract/<version>/vk_capture` until every SPIR-V key in the profile's `vk_capture.tsv` is there (Galaxy: 3,089, about 7 s after launch), and gives up after 120 s.
5. It splits out the shaders and checks them against the profile's tables (a Vulkan profile: it translates the RomFS's SPIR-V and the capture with `vk_shaders.py` instead).
6. It builds the iOS shader libraries.
7. It calls `build_ipa.sh`. Xcode builds the app, and `dm/ios/tools/pack_ipa.py` packs it with the shader libraries, the add-on content and the RomFS straight from where they are. It reads and deflates files on all cores and writes at about the T7's write speed (300 MB/s): Breath of the Wild's 16 GB IPA takes 57 s, Info-ZIP's copy and zip took 2 min 50 s.

A repeat build skips work whose inputs have not changed. The extraction is kept (`extract/`). The rewrite, the shader split and the iOS (or Vulkan) shaders each write a key beside their output: a sha256 of their inputs (the game files, the tools, the profile, Xcode's and spirv-cross's versions). When the key matches, the stage line says `reused (inputs unchanged)` and the step does not run. Any change to a tool or the profile runs the step again; deleting the `.key` file forces it.

While it runs, the console shows one line per stage: building nx_extract, extracting each version, the DLC, the rewrite, the run-time shader capture (only for such profiles), the shader split, the iOS shaders, the app build and packing the IPA. Each line shows `[k/n]`, the stage and its current step. Where the work can be counted, it adds a bar with done/total, percent, elapsed time and ETA. Counted work is bytes extracted, modules rewritten, shaders (cache check, translation, compile), files compiled by Xcode, and bytes packed into the IPA. Elsewhere a spinner shows the elapsed time. A total marked `~` is an estimate. A version's first extraction is estimated from the NSPs' size, and later extractions use the previous run's exact size. The IPA is estimated from the previous IPA, or from the files' size before compression. In a terminal or in Spyder the line is redrawn in place. When the stage ends, it becomes a `✓` line with the elapsed time and a summary:

```
[15:24:28] ✓ [2/7] extract v327680 (0:20): 9,779 files, 5.0 GB
⠸ [7/7] IPA pack · packing  ████████▍░░░░░░░░░░░  42%  1.9/~4.5 GB · 13,597 entries  0:05 · ETA 0:07
```

When the output goes to a file or a pipe, the script prints a plain line instead, every `BEAT` seconds (30). `--progress bar|lines|off` (`PROGRESS` in Spyder) overrides that choice; `off` prints only each stage's start and end. The tools' own output goes only to the logs in `<id>_build/logs/`, one per step. When a step fails, the script prints the last 40 lines of that step's log and the log's path.

Everything it writes stays in the NSP folder: intermediate files and logs in `<id>_build/`, the IPA next to the NSPs. The extracted game files stay in `<id>_build/extract/` for the next build; `--no-keep-extracted` (`KEEP_EXTRACTED = False` in Spyder) deletes them at the end. It exits with 0 when done and 1 on an error. The app's bundle ID is `org.nxnative.<base game title ID>` (for example `org.nxnative.0100a6301214e000`), and its version is the game's display version: the update's when an update is packed, else the base game's (Engage 2.0.0); `--app-name` / `--bundle-id` (or `APP_NAME` / `BUNDLE_ID` in Spyder) override the name and ID.

On the device, environment switches go in `Documents/env.txt` (one `KEY=VALUE` per line), and game files are also accepted at `Documents/romfs`.

## Port another game

Each game has a profile in `dm/games/<id>/`:
- `game.tsv` holds the title ID, known builds, code modules, RomFS marker, memory split, NVN driver tables, app name and bundle ID;
- the shader tables: `shader_map.tsv`, `shader_facts.tsv`, `shader_pairs.tsv`, `c1_full.tsv`, `pso_manifest.tsv`;
- `dmsh_chain.h` holds the chain version.

The shader tools pick a profile with `DM_GAME=<id>`; `make -C dm/host` and `build_ipa.sh` pick it with `GAME=<id>`. Profiles are named after the base game's title ID. There is no default game: without `GAME` / `DM_GAME` the tools stop and list the profiles. `python3 dm/games/game.py list` lists the profiles. Host code that relies on one build's fixed addresses checks that build's ID.

To add a game:
1. Run `scripts/build_ipa_from_nsp.py` on its NSP folder. With no matching profile, it writes a survey to `<title ID>_survey/survey.md`. The survey covers the modules, SDK, engine, containers, rewrite sites, and the imports compared with the host's hooks. It then writes a provisional profile into `<title ID>_build/profile/<title ID>/` (outside the repository; tools find it through `DM_GAMES_DIR`) with the keys `dm/games/profile_guess.py` reads off the game files: the graphics API, the modules to load, where the shaders come from, the memory partition, SDK and engine presets. After the rewrite it sets `mem_used` from the rewritten modules and, for a game with virtual address memory that sets a heap, boots it on the Mac until its heap request (the heap check, a few seconds) to size the heap region. Then it generates the shader tables and chain header and packs a best-effort IPA that may not boot. `--survey-only` stops after the survey, `--no-heap-check` skips the heap check, and `--profile-out` puts the profile elsewhere. `--provisional` does all this for a game that has a profile, to test the guesses; `python3 dm/games/profile_guess.py --check` compares the static guesses with every profile. Details in [dm/games/README.md](../dm/games/README.md).
2. Add a profile as described in [dm/games/README.md](../dm/games/README.md).
3. Bring the game up following [docs/agents](agents/README.md): extraction, binary survey, a catalogue of host bring-up failures, graphics, and debugging recipes.

## Build by hand (Mac)

You need the same tools as the script. The shader translator is the prebuilt `dm/gfx/tools/dmsh_xlate_bin`, the build that matches `dmsh_chain.lock`; a fresh `dotnet publish` gives different fingerprints. The commands use three variables:
- `G`, the profile;
- `W`, the game's work folder: `<title ID>-work` inside the game's NSP folder, outside this repository and off the home folder (it grows to the size of the game files);
- `VER`, a version folder named after the NSP version.

```
G=010015100B514000; W="<NSP folder>/$G-work"; VER=v327680
# 1. extract: the base game alone (update -), or an update layered over it (the last argument lets unchanged files become clones)
dotnet build dm/tools/nx_extract -c Release -o $W/build/nx_extract
$W/build/nx_extract/nx_extract <prod.keys> <base NSP> - $W/data/v0
$W/build/nx_extract/nx_extract <prod.keys> <base NSP> <update NSP> $W/data/$VER $W/data/v0/RomFS
# 2. rewrite the profile's code modules
for m in $(python3 dm/games/game.py $G modules); do DM_RULESET=native python3 dm/tools/patch_nso.py $W/data/$VER/ExeFS/$m $W/build/patched_$VER $m; done
# 3. shaders: extract from every version in the profile's shader_versions (comma-separated, base first), then translate into <cache>/b-<chain version>/
DM_GAME=$G python3 dm/gfx/tools/shader_split.py $W/data/v0/RomFS,$W/data/$VER/RomFS $W/data/v0/ExeFS/main,$W/data/$VER/ExeFS/main $W/shader/pkg dm/games/$G/shader_map.tsv dm/games/$G/shader_facts.tsv dm/games/$G/shader_pairs.tsv
DM_GAME=$G python3 dm/gfx/tools/dmsh_chain.py --header
DM_GAME=$G python3 dm/gfx/tools/dmsh_build.py $W/shader/pkg $W/build/cache/metal_shader_cache
python3 dm/gfx/tools/c1_guard.py $W/build/cache/metal_shader_cache/b-<chain version> dm/games/$G/c1_full.tsv
# 4. the host, and the button-icon font for the Nintendo-extension shared font
make -C dm/host GAME=$G dmhost
python3 dm/tools/make_ext_font.py $W/build/font/nintendo_ext.ttf
# 5. run on the Mac
DM_ROOT=$W DM_ROMFS=$W/data/$VER/RomFS DM_SAVE=$W/run/save DM_TEMP=$W/run/temp DM_MSL_DIR=$W/build/cache/metal_shader_cache DM_FONT_DIR=$W/build/font dm/host/dmhost $W/build/patched_$VER
# 6. iOS shader libraries (about 15 min for Mario), then the IPA (default <NSP folder>/<the profile's ipa>)
IOSOUT=$W/build/ios/dmsh_b DM_GAME=$G python3 dm/gfx/tools/dmsh_build.py $W/shader/pkg $W/build/cache/metal_shader_cache
GAME=$G W=$W dm/ios/tools/build_ipa.sh [out.ipa]
```

Notes on these steps:
- `dmsh_build.py` compiles each shader's Metal source through a cache keyed by that source, the compile flags and the compiler (`dm/gfx/tools/dmsh_mtlcache.py`, in `<cache>/cas/metallib/`). A chain change that leaves a shader's MSL unchanged, such as a translator fix, costs that shader no Metal compile. Before building, the cache takes the libraries of the earlier `b-*/` folders beside its output (and beside `IOSOUT`), and of `DMSH_PREFILL=<Mac root>[=<iOS root>]` (several separated by `:`). It takes a folder only when its recorded flags are the current ones and a fresh compile of a few of its shaders reproduces their libraries byte for byte. The summary line `Metal cache:` shows reused, compiled and filled counts per target.
- `build_ipa.sh` takes the rewritten modules from `$W/build/patched_<package>` and the RomFS from `$W/data/<package>/RomFS`; `PATCHED` and `ROMFS` override them. The shader libraries, the RomFS and the add-on content never go through Xcode: `pack_ipa.py` packs them into the IPA beside the app Xcode built, as `DmIOS.app/msl/b-<chain version>`, `romfs` and `aoc`.
- It also bundles a standard font (macOS's Arial Unicode, `STD_FONT=` overrides it) and the generated `nintendo_ext.ttf`.
- The icon is the `icon.jpg` that `nx_extract` saves next to `RomFS/`; `DM_ICON=` points at another image.
- `DM_ENV_FILE=` bakes environment switches into the app, and `DM_DISPLAY_NAME=` renames it.
- If Xcode's Locations setting puts products in a custom place, the script finds the app through the build log.
- hactool cannot read every update (Mario 1.2.1's patch NCA gives "Invalid BKTR layout!"), which is why `nx_extract` uses LibHac.

## Prewarm lists

Metal compiles each combination of shaders and pipeline settings for the GPU the first time it is used. Each takes tens of milliseconds, so a burst of them on entering a level is a visible freeze. The host records what it had to compile and rebuilds those pipelines on a background queue at the next launch:

- `pso_user.tsv` sits next to the save directory: `Documents/pso_user.tsv` on iOS, the parent of `DM_SAVE` on the Mac (`DM_PSO_USER=path` overrides it). It is appended while playing, one line per item built on the spot: a shader (`S`), a render pipeline (`R`, the hex of `pso_skey` in `dm/gfx/nvn/nvn_pso_skey.h`) or a compute pipeline (`C`).
- `dm/games/<id>/pso_manifest.tsv` is the seed list bundled with the app, prewarmed before `pso_user.tsv`.

The lines name shaders by content key and hold no compiled code and nothing personal, so a list recorded on one device works on any other. To seed the bundled list:
1. Record on the Mac with prewarm off, so everything is built on demand: `DM_PSO_MANIFEST=off DM_PSO_RECORD=<file>`, playing the scenes players reach first. Engage's list covers boot, the opening movie, the title, a save load and the prologue battle.
2. Append the recorded lines below the header comments, in the recorded order. Duplicates are dropped at load.
3. Rebuild the IPA.

Record on the game version you ship. At launch the log names each list it read and its line count (`pipeline prewarm list …: N lines`), or says that `pso_user.tsv` does not exist yet.

## Power

The game's own work and its frame rate stay as they are; the host avoids work of its own that the Switch never did. Every 300 frames the log has a `power` line (CPU energy in watts and per frame, CPU time, wakeups, thermal state, the threads that yield most) and a `residency set` line; [05](agents/05-debugging.md) explains them.

- **Yield loops.** On the Switch, a yield with nothing else to run is free; a guest loop that polls the clock or a flag and yields is a busy spin on the host. Three Houses waited out each frame this way (228,000 yields a frame on an iPhone) until a per-build cut made its frame limiter sleep (see its notes), and Breath of the Wild's `PlacementMgr` and `RadarMgr` wait for work this way. After 2 ms of consecutive yields with no other SVC, each yield sleeps an eighth of the wait so far, from 10 to 250 µs (`DM_YIELD_BACKOFF=0` turns it off, `=<cap µs>[:<start µs>]` sets the cap and the start). Three Houses on the Mac, before that cut: CPU time 78% → 19% of a core, same frame times. The back-off first started after 200 µs, which also caught Tears of the Kingdom's main thread waiting for its workers on the frame's critical path: frames ran past 33 ms and the game dropped itself to 20 fps (9 times in 300 s on the Mac; on the iPhone the threads also stayed on efficiency cores). From 2 ms on it never backs off there.
- **Waits block instead of polling:** the in-process audio renderer, upload batches, `nvnQueueFinish`. A signalled event wakes only the threads waiting on it; leaving an SVC takes the global lock only while a pause (IL2CPP's garbage collector) is pending.
- **Real-time policy.** The thread that acquires the window texture declares a Mach time-constraint policy, which tells the performance controller the frame deadline. `DM_RT=0` leaves it on its QoS, for measuring.
- **Thread classes.** Every guest thread runs at QoS user-interactive, whatever its Switch priority. `DM_QOS_MAP=1` (off by default, for a phone A/B) maps priority ≤ 44 to user-interactive, 45–59 to user-initiated and the rest to utility (`DM_QOS_EDGES=44,59` moves the edges). `SetThreadPriority` moves a thread's class too, and a thread waiting on a lock lends its class to the owner until the lock is handed over. Host helper threads then set their own class (audio notify, silent sink and vsync user-interactive, movie decode user-initiated) instead of inheriting it from the guest thread that made them.
- **Replay CPU.** Memory-pool addresses are cached per thread; per-encoder draw state is sent only when it changes; texture IDs of GPU-only textures stay cached when the game writes other memory; upload staging blocks are reused (Breath of the Wild used to allocate, make resident and free a 32 MB block for each re-upload of a small CPU-written texture, about 3 GB/s) and the residency set is committed only when it changed.
- **GPU.** An inline uniform update inside a render pass no longer ends the pass (Metroid Dread ended about 246 passes a frame this way, each one storing and reloading its attachments): the update lands when the pass ends, and the draws after it read a copy of the updated data (`DM_NVN_UB_DEFER=0` restores the old behaviour). A format-changing texture copy that covers the whole destination level does not load it first. `DM_NVN_BARRIER=game` lets a pass's vertex work overlap the previous pass ([04](agents/04-graphics.md) section 7); it is off by default, as the games issue their own barriers before most passes anyway.

## Game notes

**Super Mario Bros. Wonder (`010015100B514000`)**
- **Versions:** v0 (1.0.0) and 1.2.1 (v327680). With the update layered over v0, unchanged files become APFS clones, so the merged RomFS adds only about 114 MB to the 3.5 GB base.
- **Shaders:** 12,811 in v0 and 16,268 across both versions; the tables hold both.
- **1.2.1:** it is a new `main` build (SDK 16.2.12), whose resource-heap cut (+16 KB slack) was carried over with `dm/tools/nso_fnmap.py`. It also makes new SDK calls, which the host answers: `nn::nfp` finds no amiibo, `pl::IsRunningOnOunce` is false, the shop call is a no-op, and `account::PopOpenUsers` returns none.
- **Mac input:** `DM_KEYS="12:A,14:A,20:A,26:A,32:A"` reaches the opening course.

**Fire Emblem Engage (`0100A6301214E000`)**
- **Engine:** Unity 2020.3 IL2CPP, SDK 12.3.7. The shaders are read out of Unity bundles (`unityfs.py`).
- **Memory:** a 5 GB guest block, the total proven on a phone, with a 2.5 GB application pool. A per-build cut shrinks the SDK's address-region node area to 62 MB.
- **Audio:** Wwise drives AudioOut directly.
- **Movies:** VP9, decoded on the host.
- **60 fps:** the Switch version runs at 30; one patch to its code switches it to the 60 fps timing the game already has, so nothing runs too fast.

**The Legend of Zelda: Breath of the Wild (`01007EF00011E000`)**
- **60 fps at normal speed (30 on the Switch).** The game steps its time by the frame interval its framework picks (`ksys::VFR`: interval / 2 of a 30 fps tick). With the profile's `fps_target` (60) the host picks it instead, in whole vsyncs (`patch_nso.py` `FRAME_STEP`, `hle_nvn.c` `fstep_tick`, `nvn_fstep.h`, the same frame step as Tears of the Kingdom's): a stub at the framework's `setWaitVsyncInterval` hands the game the host's step once a frame, and the host keeps each frame on screen that many vsyncs.
  - It holds 1 (60 fps). Three late frames in a row (the frame or its GPU work more than 1.7 ms over) step up to the cost, 2 (30 fps) as a rule: no 40 fps on 120 Hz screens. 30 frames that would fit the shorter hold try it again, and each failed try doubles the wait before the next (1 → 8 s).
  - Real time lost to a late frame or a hitch is paid back one vsync per frame (at most 15; the rest of a long load is dropped), so game time = real time. The log line `frame step: game time 30.00 s in 30.00 s (1.000 of real time)` checks it every 1,800 presents, with the frames held 1 / 2 / 3 vsyncs, late frames, paid-back vsyncs and hold changes.
  - Scenes that fix the game's step themselves (the VFR's override: 2 at `main+0xc3b588` / `+0xc5ebf8`, 1 at `main+0xc609d8`) keep it, and the host holds frames that long (log line `the game fixes its own step`; not reached on the Mac yet).
  - Mac (M4 Pro), from the title into the save's scene: 1.000 of real time at 60; with 12 ms added to every frame (`DM_TEST_PRESENT_LAG=1,12`) it drops to 30 and stays at 1.000. `DM_FPS_TARGET=30` holds 30 (saves power).
- **Legacy method** (`DM_FRAME_STEP=legacy`, kept for the iPhone A/B test): patches to the game's frame-interval logic lift its floor from 2 to 1. The game's time step follows its frame interval, so the speed is right at a steady 60, 30 or 20. The game picks the interval from the frame's CPU time and its GPU time, which it reads from two GPU timestamps around the frame; the host gives each timestamp the GPU time of the work around it (profile key `gpu_timestamps`, which its dynamic resolution needs too). Before that it saw only the main thread's CPU time (about 3 ms a frame in the first shrine) and stayed at 60 in slow motion: at 40 fps, about two thirds of the normal speed (an iPhone 16 Pro Max in handheld mode, GitHub issue #9; [04](agents/04-graphics.md)). Under load it still ran at 0.93–0.98 of real time.
- **Render scale:** `DM_RENDER_SCALE=0.5`–`1.0` (also from `Documents/env.txt`) fixes the 3D views at that fraction of 1600×900 docked (1280×720 handheld) and turns the game's own dynamic resolution off; 1.0, the default, keeps it. A stub sets the scale where the game applies its own (`main+0x1266880`), so every scene pass, the shader's resolution ratio and the LOD check follow it: at 0.5 the 1600×900 passes become 800×450 and the 800×450, 400×225, 200×112 and 100×56 chains halve too, while the shadow maps and the 1920×1080 output keep their size and the HUD stays sharp. It holds in handheld mode too (960×540 at 0.75). On the Mac (M4 Pro) the GPU time does not change (about 13 ms in the first shrine at 1.0 and at 0.5): a frame has about 650 passes, most of them tiny, whose fixed cost outweighs their pixels there. Whether it helps an iPhone, whose GPU loads and stores each pass's attachments, is what the setting is for.
- **Open: an intermittent crash at the world load on the Mac.** About 3 s after Start, a task worker's `operator new[]` (`main+0x155a79c`) gets null from a game heap and writes through it (`main+0x155a7a4`). It happens in legacy too (1 of 8 runs), so the frame step does not cause it, though it may make it likelier: 12 of 33 runs across the variants tried (each stub alone, no pay-back, the game's interval as a floor), solo or beside other runs. None of the about 95 earlier logs (up to 2026-10-19) has it.
- **Memory:** about 2.8 GB in the first shrine in handheld mode, idle or walking (Mac measurement), against the 3.4 GB an 8 GB iPhone gives the app.
- The game waits for each frame's GPU work before submitting the next, so the host hands its translated commands to the GPU in segments ([04](agents/04-graphics.md)).
- **HUD prompt shadows and glows, stamina wheel, System menu background:** the game rebuilds each layout capture (a blurred mask of a prompt bar, the menu's background) on the same storage with its own channel mapping and keeps the new texture only if `nvnTextureCompare` calls the two different; the host's comparison ignored the mapping, so captures read alpha 1 (hard-edged dark boxes, cream cloud rectangles, a black menu background). It compares the mapping now ([04](agents/04-graphics.md)).

**The Legend of Zelda: Link's Awakening (`01006BB00C6F0000`)**
- **Engine:** Grezzo's engine on NintendoWare, SDK 8.2.0 (the oldest so far), NVN 53. Modules main + subsdk0 (GLSLC, NVN's runtime shader compiler) + subsdk1 (movie) + sdk; 9,698 shaders from the bfsha archives, effects and layouts.
- **Window origin:** the only game so far that keeps NVN's default lower-left (OpenGL) window origin; the host flips its viewports and winding and the window image at present ([04](agents/04-graphics.md)). Before that, text the game renders into textures came out upside down.
- **Movies:** VP9 with a 5.1 Vorbis sound track; the host decodes the sound with stb_vorbis.
- **Lighting:** tiled forward lighting whose tile lists a compute shader builds each frame; it needs the dispatch size in NVN's driver segment `c0` ([04](agents/04-graphics.md)). Before the host supplied it, lights piled into the bottom tile row and the doorway step flickered with white tiles.
- **Sound:** SDK 8 numbers the audio renderer's commands differently (the output command is 0x10, not 0x13); the host recognises the output command by its size. Before that, music and sound effects were silent and only the movies had sound ([03](agents/03-bringup.md)).
- **Mac input:** the title wants L+R: `DM_KEYS="f6000:L+R~0.4,f6300:A,f6500:A,f6700:Down,f6800:A"` reaches a new file's name entry (a fresh save directory via `SV=`).
- **Frame rate:** gameplay runs at 60 like on the Switch; the game itself drops to 30 (present interval 2) for event cutscenes.
- **Depth of field:** outdoors the game blurs the top and bottom of the screen by depth. It sets NVN's near = 0 depth mode, which the shader translation now follows for every game (an entry point per mode, picked at run time); before that the whole screen was blurred ([04](agents/04-graphics.md)).
- **Sunlight:** outdoors the sun's shadow test failed everywhere, so the scene was dim and nothing cast a shadow. The world position its shaders pass between stages has no w written, and the translation filled it with 0 instead of the hardware's 1; every game's shaders now get the hardware's default ([04](agents/04-graphics.md)).
- **Physics:** at 30 fps the game steps physics twice per frame. Its completion task destroys itself after it runs, and on Apple devices that destructor could land after the next step had already rebuilt the task, so the physics workers crashed when a conversation or cutscene began. A per-build cut drops the destructor call ([03](agents/03-bringup.md)).

**Super Mario Odyssey (`0100000000010000`)**
- **Engine:** Nintendo EPD's sead / agl with NintendoWare, SDK 7.3.2 (the oldest so far), update 1.4.1. Modules main + subsdk0 (movie) + sdk; 27,984 shaders (agl `sharcb` and `bfsha` in `ShaderData`, particles in `EffectData`); its three geometry shaders (a thunder effect) do not translate.
- **Start-up services:** it calls several system services no other game did, each answered by the host: the aborting `account::OpenPreselectedUser` and `GetLastOpenedUser`, news delivery (`bcat`: the delivery storage does not mount, which the game treats as "nothing delivered"), HOME-button blocking, the parental 3D-mode setting, `vi::SetLayerScalingMode`, `time::ToPosixTimeFromUtc`, the debug pad, and the SDK 7 names of two audio-device calls ([03](agents/03-bringup.md)).
- **Movies:** MP4 / H.264 (the videos in its tutorial hint boxes, the kingdom travel videos), 41 of 44 High or Main profile with B-frames. The host decodes them with VideoToolbox; the SDK's demuxer passes the parameter sets as the `avcc` record (the MP4 `avcC` box), and pictures leave in presentation order through a small queue.
- **Sticks:** the game reads all 16 entries of the controller history whatever count comes back; the host now fills every entry (before, only the first, and neither stick did anything in play while buttons and menus worked).
- **HUD:** the coin counters are layout panes that take their alpha from single-channel render targets, as in Breath of the Wild; the profile lists the 26 layout shaders under `alpha_from_red` (before, they were solid white cards). Since the `nvnTextureCompare` fix the game's own capture mapping does that and the list no longer fires on the Mac ([04](agents/04-graphics.md)).
- **Ground:** a depth pre-pass followed by a less-or-equal G-buffer pass needs bit-identical positions from different vertex shaders; every shader is now compiled with `-fpreserve-invariance` (before, the Cap Kingdom ground showed stale 32×32 blocks on every fourth frame) ([04](agents/04-graphics.md)).
- **Fog:** the Cap Kingdom ground fog parts around Mario through a small fluid simulation fed by point-sprite splats. Their vertex shader clamps the point size to the driver segment's `c0 + 0x610`, which the host left at 0, so no splat was ever drawn and the fog never moved; the host now writes the largest point size there ([04](agents/04-graphics.md)).

**Hades (`0100535012974000`)**
- **Engine:** Supergiant's engine on The Forge renderer, SDK 9.3.0, update 1.0.38233. It renders with **Vulkan**: `main` imports 100 `vk*` functions from subsdk0 (the Vulkan loader, over NVIDIA's driver in subsdk1). The host implements them on Metal itself (`dm/gfx/vk/hle_vk.m`), so only main and sdk are loaded; the profile says `graphics vulkan`.
- **Vulkan layer:** one Tegra X1-like device (Vulkan 1.1); device memory is a shared `MTLBuffer` made on first use, images are their own textures; command buffers are recorded and replayed into one Metal command buffer per submit on the layer's own queue; swapchain images are shown through the NVN layer's present path once their frame's GPU work is done. Names the game asks for through `vkGet*ProcAddr` are logged once each.
- **Shaders:** 74 SPIR-V files in `Content/EffectsForgeSwitch`. `dm/gfx/tools/vk_shaders.py <RomFS> <shader dir> [--ios <dir>]` translates them with SPIRV-Cross into `<dir>/vk/`: one library, and a table of the Metal slot each (set, binding) moved to. The game hands the same words to `vkCreateShaderModule`, so the host finds each shader by the hash of its SPIR-V.
- **Notification event:** the game polls `oe::GetNotificationMessageEvent` every frame; the SDK's own event was never created (the host's `oe::Initialize` is a no-op), so the host now hands out an event of its own, signalled while a notification is queued.
- **Online:** its `EOS_*` imports (Epic Online Services, an NRO it would load through `nn::ro`) stay offline.
- **Mac input:** `DM_KEYS="f800:A,f1000:A,f1200:A,f1500:A,f1900:A"` goes through the title and the intro into Tartarus.
- **Packing:** for a `graphics vulkan` profile the NSP script runs `vk_shaders.py` (Mac and iOS libraries in `<id>_build/shader/vk` and `shader/ios/vk`) in place of the NVN shader split and chain build.

**Hyrule Warriors: Age of Calamity (`01002B00111A2000`)**
- **Engine:** Koei Tecmo's KTGL on NVN, SDK 9.6.0, update 1.3.0 (v327680), four DLC packages (one is only a licence). Modules main + subsdk0 (movie) + sdk.
- **Files:** everything sits in RDB archives (`asset/*.rdb` index; `asset/*.rdb.bin*` and `asset/data/*.file` hold `IDRK` entries, zlib in 16 KB chunks) ([01](agents/01-extract.md)).
- **Shaders:** 40,726 GLSLC outputs: KTGL's G2S containers and one `_DOK` container in `system.rdb.bin*`, plus 117 in `main`. Many have 0x850-byte controls and the compute ones no code header ([04](agents/04-graphics.md)). The game builds 8,705 programs during its first frame (about 10 s on the Mac).
- **Heap:** its three modules take 66.6 MB, more than the 64 MB the host reported as used, so `SetHeapSize` failed and `nnMain` returned at once; the profile's `mem_used` reports 72 MB.
- **Sound:** the engine's 15 MB heap was too small on the host (renderer work buffer plus four players, three of them 5.1). The sound setup then gave up quietly, the first sound archive never loaded and the main thread waited forever; a per-build cut moves 4 MB from the 142 MB sound data heap to it ([03](agents/03-bringup.md)). The multi-stream hardware Opus decoder is the SDK's software one.
- **Graphics fixes it brought:** compute programs get their own binding in the replay (draws after a dispatch were dropped, so the intro movie stayed black), `nvnTexturePoolRegisterImage`, indirect draws (its GPU-driven effects are indirect quads, converted by a compute pass), and the movie planes (CPU-written, published with `nvnMemoryPoolFlushMappedRange`) through `tex_flush_upload`.
- **60 fps (30 on the Switch).** `nnMain` sets KTGL's device up with present interval 2, and the device's frame rate, 59.94 / interval, is what its event scripts step by. The frame itself is paced by a KIDS task on a `KIDSTaskScheduler` thread: it waits until 1 / fps has passed since the last frame (fps 30, from engine data) and then steps the game by the time that really passed. Two per-build cuts on 1.3.0 `main` (`patch_nso.py`) make the interval 1 and the wait 1/60 s; the game then asks for interval 1 itself. On the Mac the opening scenes at frame 2N match the original's frame N (same subtitle, same poses), and they hold 60.
- **Battles: vertex conversion over the draw's vertices (`vconv_range`).** The soldiers' Half2 and Short2 attributes feed integer shader inputs, which the replay converts on the CPU (`vconv_bind` in `nvn_mtl.m`). KTGL binds whole mesh pools of up to ~590,000 vertices, so converting the bound ranges came to 4.4 million vertices per submission in the first battle: 24 of the 32 ms the replay took per frame on the Mac, 26 fps at a 30 or a 60 fps target. The profile's `vconv_range` converts only what each draw reads (219,000 vertices per submission, about twelve submissions a frame), and the half and 8 / 16-bit integer formats have conversion loops of their own. Keeping the conversions across frames did not pay: the soldiers' attributes change every frame. `DM_NVN_VCONV_CHECK=1` found no stale index range in 983,000 reuses. The visibility buffer ring was 4 deep, so the submit thread waited for the previous frame's GPU work; it now has as many buffers as command allocators (8). The battle runs at 58.6 fps on the Mac (M4 Pro; frame p50 16.9 ms, replay CPU 10 ms, GPU 11 ms). On an iPhone the GPU decides: the game steps by the time that really passed, so a battle below 60 runs at normal speed.
- **Other games' saves:** it asks whether Breath of the Wild's (and `0100A2C01320E000`'s) save exists for bonus items; the host says no.
- **Mac input:** with a save whose first-boot settings were made, `DM_KEYS="f300:A,f420:A,f540:A,f660:A,f780:A,f900:A,f1300:Plus,f1350:Plus"` confirms the settings, skips the intro movie and plays the opening into the first battle, The Battle of Hyrule Field (about frame 4000).

**Fire Emblem: Three Houses (`010055D009F78000`)**
- **Engine:** Koei Tecmo's older KTGL (the game is co-developed with Intelligent Systems), SDK 6.5.0 (the oldest so far), update 1.2.0. Modules main + subsdk0 (GLSLC, NVN's runtime shader compiler) + subsdk1 (movie) + sdk. RomFS: the LINKDATA archive (`DATA0.bin` is the index, `DATA1.bin` holds 6.9 GB), loose overrides in `patch1`–`patch4`, WebM movies and KTSL sound banks; compressed entries and `*.gz` files are Koei Tecmo's chunked zlib ([01](agents/01-extract.md)).
- **Shaders:** 1,364. `shader_split.py` reads the SPKG packages (G2S containers, as in Age of Calamity) in `DATA1.bin` and `patch*/nx/shader`, a `_SPK4100` post-effect package, and the BNSH and GLSLC outputs in `main`. SDK 6's GLSLC writes 0x848 / 0x850-byte control sections and compute code with no header, which the reader used to drop ([04](agents/04-graphics.md)).
- **Shaders compiled at run time:** KTGL compiles 9 built-in GLSL shaders at boot with the game's own GLSLC (2D primitives, text, the loading quill). No game file holds their output, so they are captured on the Mac. The game runs with `DM_GLSLC_CAPTURE=<version dir>/glslc_capture` (`hle_glslc.c`), and the profile key `shader_glslc_capture on` makes `shader_split.py` read that folder. The outputs are identical on every run. The NSP script does this by itself in its `GLSLC capture` stage, so the NSPs and prod.keys are enough. The stage builds the Mac host into `<id>_build/tools/` and boots the game until the 9 files are in `<id>_build/extract/v327680/glslc_capture`, which takes about 10 s in all. Without the folder the split tables would differ from the profile, and the script would stop at its table check. By hand, run the game for a few seconds with that variable (step 5 of the build by hand).
- **Host changes it needed** ([03](agents/03-bringup.md), [04](agents/04-graphics.md)):
  - it submits on two NVN queues from two threads (submissions are serialized now);
  - its command buffer records into one 16 MB ring chunk and frees the ring by `GetCommandMemoryUsed`, which now counts from the last `AddCommandMemory` as NVN does (frames stopped after about 15 s);
  - its two texture pools and two sampler pools use the same IDs, now kept apart (menus showed plain bars or only the cursor);
  - SDK 6's `account::OpenPreselectedUser` returns a Result (the save never mounted and the first loading screen never ended);
  - SDK 6's audio command header has its own layout (no sound);
  - its character shaders read Half2 UVs through integer-declared inputs, now converted to float32 bits at replay (black silhouettes, then flat tan characters);
  - depth clamp is replayed.
- **Fixed:** the ground under close-up battle cameras showed as flat blue. The terrain's signed 16-bit heights were read zero-extended, so the vertices with negative heights went out of view ([04](agents/04-graphics.md), Three Houses).
- **Fixed:** the first loading screen took 78 s on the iPhone. The loader calls `nvnQueueFinish` after each resource it uploads, and that call waited for the display to take every queued frame; it now waits only for the GPU ([04](agents/04-graphics.md), Three Houses).
- **Open:** 64-pixel rectangles in the ground where decals land. One red line per run says a texture buffer is bound where a shader samples 2D: the decal and light lists.
- **Memory:** about 3.5 GB resident and 2.8 GB of Metal allocations on the Mac; the game itself makes a 1.5 GB GPU-only memory pool.
- **60 fps:** the Switch version shows 30, but KTGL already updates the game 60 times a second on its main thread, each update a fixed 1/60 s step; the render thread draws the latest update and presents it with the interval of the render mode (2 for the docked 1080p and handheld 720p modes; the engine also has a 720p and a 1080p mode at interval 1 that nothing selects). Per-build cuts on 1.2.0 `main` set every mode's interval to 1, so every update is shown and the game runs at the same speed; the render thread's own per-frame steps (a fade counter, a scroll) read the same table. Two more cuts make the waits cheap. The frame limiter (`main+0x5be430`) yielded and polled the clock, which on the host spun 2 ms a frame on a performance core and ran at 59.5 updates a second; it now sleeps the time left. The render thread waits for the next update with a timeout of one frame given in milliseconds to a wait that takes microseconds, so it polled every 16 µs (about 50,000 wakeups a second at 60 fps); it now waits a frame. Prologue battle on the Mac: 59.9 fps, 55% of a core and 1.8 W of CPU energy (the original at 30 fps: 44% and 1.7 W). The render thread also forced interval 2 while either of two flags was set: one for the opening movie, one for scenes such as the character creation screen after it (the engine's own 60 fps modes dropped to 30 there to keep 1080p). A fourth cut ignores both (`main+0x50fb7c`), so those scenes run at 60 too; the movie still lasts 210.6 s (6,318 frames at 30 fps), as in the original.
- **Mac input:** a fresh save needs `DM_KBD=<name>` for the name entry, and its confirm dialogs default to No. From a new game into the prologue battle (frame-based at 60 fps, about 7 minutes): `DM_KEYS="f720:A*185/90,f2400:Plus*35/438,f17400:Left~0.3*120/500,f17480:A*120/500,f17560:Left~0.3*120/500,f17640:A*120/500,f18020:Plus*100/562"`; the game offers a save right before the battle. The repeating Left, A, Left, A reaches Yes whether a confirm dialog is open or not (A, Left, A loops once it starts on an open dialog: A answers No, Left changes the selection, A reopens it). A presses during the opening movie pause it, so the scenes after it start a few seconds later from run to run.

**Super Mario Galaxy (`010099C022B96000`)**
- **Engine:** the Wii game (codename Comet) on NERD's Hagi layer, SDK 18.3.5, update 1.3.1 (v327680). The PowerPC code is statically recompiled into `main` (`hagi.config`: `Cpu` `Jit false`, `Statifier true`), so there is no JIT; Hagi stands in for the Wii hardware: GX on Vulkan, the DSP with its ROMs in `data/dsp`, the disc from the RomFS, HD texture packs in `data/texture_replace` and `data/ondemand_texture_replace`. Modules main + subsdk0 (movie) + sdk; subsdk1 (GLSLC), subsdk2 (`nn::pcm`) and subsdk3 / subsdk4 (NVIDIA's OpenGL and Vulkan drivers) are not loaded.
- **Memory:** `main`'s bss is 2.9 GB (the emulated memory); the game never calls `SetHeapSize`, so the guest block is 1 GB. Footprint on the Mac 1.9 GB, 1.1 GB of it Metal.
- **Vulkan:** 99 `vk*` imports through Hades' layer (`hle_vk.m`), which Galaxy extended: push constants, descriptor arrays, dual-source blending from an output at location 1, copies inside a render pass, linear images over their memory, timestamp and occlusion queries, pipeline caches, `vkCmdDraw`, image copies and read-backs, the GX vertex formats (USCALED / SSCALED, three components), viewport and scissor kept across render passes, the swapchain's INHERIT transform and the vi layer crop ([04](agents/04-graphics.md)).
- **Shaders:** Hagi generates its GX shaders as SPIR-V at run time. While it shows "Initializing system..." it creates 3,089 modules (the 56 built into `main` among them) and 4,535 pipelines from `data/database/pip/pipelineDB.pip`, the same on every boot (about 15 s on the Mac). Profile key `shader_vk_capture on` and the key list `vk_capture.tsv`: the NSP script's `Vulkan shader capture` stage boots the game in the Mac host with `DM_VK_CAPTURE=<version dir>/vk_capture` until every listed key is there (under a minute), then `vk_shaders.py` translates the RomFS and the capture. Its two geometry shaders (GX points and lines, expanded to quads) are skipped: those draws come out as one-pixel points and lines.
- **Pointer:** docked, Galaxy's pointer is the Joy-Con gyro, which the host does not have; handheld, it is the touch screen. The profile's `op_mode handheld` starts it in handheld mode (720p). On the iPhone, touches no gamepad control takes go to the game's touch screen (all of them while a controller is connected); on the Mac the mouse is a finger, and `DM_KEYS` taps with `T<x>x<y>` (normalized picture coordinates).
- **CPU:** Hagi polls with `SleepThread(100 ns)`, which the host used to return from at once: one thread kept a core at 100%. Sleeps under 20 µs now count as yields and get the yield back-off ([03](agents/03-bringup.md)).
- **Not yet:** GX points and lines (the geometry shaders), sampler LOD bias (GX uses it; Metal samplers have none, red line). The base NSP in hand was damaged (147 MB zeroed near its end: the two WebM prologue movies, which the storybook prologue does not use); it was packed with `--allow-damaged`.
- **Mac input:** from a fresh save, `DM_KEYS="f1500:A,f1950:T0.373x0.70,f2300:A,f2700:A,f3200:A,f3600:LRight,f3800:A,f4200:T0.247x0.426,f4500:A,f4800:LRight,f5000:A,f5400:T0.659x0.366,f5800:A,f6200:LRight,f6400:A,f7000:A,f8000:A,f9000:A,f10000:A,f11000:A"` creates file 1 (Mario icon, Regular Mode) and plays the storybook prologue into the Star Festival (about frame 12,000). Screenshots of the handheld picture need `DM_NVN_SHOT_OUT=1280x720` (the raw swapchain image is 1920x1080 with the picture in its top-left 1280x720).

**The Legend of Zelda: Tears of the Kingdom (`0100F2C0115B6000`)**
- **60 fps at normal speed:** the game picks a present interval each frame (2 = 30 fps, 3 under load) and steps its game time by 60 / fps. Stubs in `patch_nso.py` (`FRAME_STEP`; the sites come from masagrator's FPSLocker config for this build) replace that logic with the host's frame step in whole vsyncs, as in Breath of the Wild: int fps = 60 / step. Prerendered movies hold 30. On the Mac (M4 Pro) the opening cave holds 60 at 1.000 of real time; with 12 ms added to every frame it drops to 30 after three late frames and stays at 1.000. `DM_FPS_TARGET=30` saves power, `0` gives the game's own step back (every stub then runs the original instructions).
- **Legacy method** (`DM_FRAME_STEP=legacy`, iPhone-tested at 60, kept for the A/B test): the stub steps by the measured frame time, capped at the target, and presents follow the cap. Game time that ran ahead after a short frame is paid back by the next frames (the idea from OJZen/totk-mobile); frames longer than 1/15 s are not caught up.
- **Render scale:** `DM_RENDER_SCALE=0.5`–`1.0` multiplies the size of the 3D views (1600x896 docked) and fixes it there; the game's own dynamic resolution runs only at 1.0. The HUD keeps its resolution.

**Monster Hunter Rise (`0100B04011742000`)**
- **Engine:** Capcom's RE Engine, SDK 11.4.3, update 16.0.2 (v2228224, Sunbreak). The base game is an XCI (cartridge dump; nx_extract reads its secure partition), the update an NSP, and its 252 DLC NSPs are licences only. `main` has 125 MB of text: the rewriter puts its patch area right before the base (`BIG_TEXT`, a second pass with `DM_PATCH_FRONT`).
- **Files and shaders:** everything sits in KPKA PAK archives, later patch PAKs overriding earlier ones by path hash. The 63,111 shaders are in SDF files (`shader_split.py` `kpka_jobs`), with combined and separate texture tables at once (profile key `nvn_septex_base`).
- **GPU heap:** one 64 GB sparse virtual pool built from 4 MB physical pools. The host aliases mapped pages (`vm_remap`) and keeps a 4 KB page table the replay reads textures through (streamed textures 32 GB in, mip tails at 4 KB offsets). The scene is GPU-driven (`MultiDrawElementsIndirectCount`).
- **Keyboard:** the hunter, Palamute and Palico are named through the inline keyboard (`DM_KBD` on the Mac, the input box on the iPhone); the name is masked through `ngc::ProfanityFilter`'s vtable, which the host fills.
- **Frame rate:** 60 fps (30 on the Switch). The frame loop (main+0x6b106c8) sleeps until `[obj+0x430] / [obj+0x434]` sixtieths of a second have passed and steps the game by the time that really passed; the game sets the limit at `[main+0x1295b3f0]+0x434` to 30 after boot and asks for present interval 2. The host writes the profile's `fps_target` there (`hle_fpslock.c`, FPSLocker's address for this build) and the profile's `present_interval display` ignores the interval; both are needed. `DM_FPS_TARGET=30` gives back 30, and the Mac `DM_KEYS` routes below count frames at 30, so run them with it.
- **Mac input:** a fresh save (with the first-boot notices accepted) reaches character creation with `DM_KEYS="f4100:A~0.3,f6300:A~0.3,f7000:A~0.3,f7600:A~0.3"`. With `DM_KBD=Hunter`, `DM_KEYS="f4100:A~0.3,f6300:A~0.3,f7000:A~0.3,f7600:A~0.3,f8000:A~0.3,f8150:Down~0.25*6/40,f8450:A~0.3,f8650:A~0.3,f8900:A~0.3,f9100:A~0.3,f9500:A~0.3,f9800:Down~0.25*9/40,f10250:A~0.3,f10450:A~0.3,f10700:A~0.3,f10950:A~0.3,f11300:A~0.3,f11800:Down~0.25*10/40,f12250:A~0.3,f12450:A~0.3,f12700:A~0.3,f12950:A~0.3,f13300:A~0.3,f16000:A~0.3,f16300:A~0.3"` goes on through creation (hunter, Palamute, Palico, each named) and saves to slot 1. Holds under 0.25 s are not seen, and 0.5 s repeats in lists. From a save made that way, `f4100:A~0.3,f6300:A~0.3,f6800:A~0.3,f7100:A~0.3,f7500:A~0.3` continues into the opening.

**Ace Attorney Investigations Collection (`010005501E68C000`)**
- **Status:** brought up on the Mac (first-boot settings, title, Investigations 1's menus, Episode 1's opening and first investigation up to the first Logic prompt; 25 minutes with no red line) and playable on an iPhone. Much of the bring-up was worked out first by armyja in a fork (GitHub issues #17, #18, #19 and pull requests #15, #16).
- **Engine:** Unity 2022.3.17f1 IL2CPP, SDK 17.5.3, update 1.0.0.2 (v131072). The base game is an XCI; its DLC NSP is a licence only. Two IL2CPP thunks end in an indirect tail call through `x18` (`main+0x1d271bc`, `+0x204ebec`), which the rewriter now recognises ([03](agents/03-bringup.md)).
- **Shaders:** 4,951 (2,475 vertex / pixel pairs and one geometry shader, which Metal cannot express) in the player's serialized files and the Addressables bundles. Unity 2022 keeps each program's parameters as blob entries of their own and dropped the subprograms' local keywords; the player's files borrow the `Shader` type tree of the `unitybuiltinshaders` bundle ([04](agents/04-graphics.md)). Binding layout as Engage's.
- **Files:** the C# file API goes through the SDK's C library (`File.Exists` → `stat` → `open`), which checks every path with `nn::fs::IsPathMounted` and the length-limit queries before calling `nn::fs`. The host answers them now; before that Addressables found no `settings.json` and the game crashed on a null asset (`main+0x31100ec`).
- **Clock:** the C library's real-time clock reads `nn::time::GetStandardUserSystemClockCurrentTimespec`, now the host's clock; `std::chrono::system_clock::now()` called `std::terminate` right after the first dialog.
- **Memory:** the guest block is Engage's 5 GB with the same node-area cut on this `sdk` build, and a 1 GB application pool: StandardAllocator commits only 0.19 GB, and with Engage's 2.5 GB pool its reservation left Unity's own pools so little address space that the live regions reached the end of the alias region after 140 s (ten minutes: +3.91 GB of 4.375 with a 1.5 GB pool, +2.85 GB with 1 GB). On the Mac about 1.55 GB resident and 1.25 GB of Metal allocations, flat from the first investigation on (25 minutes; address space at +2.81 GB).
- **Frame rate:** 60 fps, as on the Switch (present interval 1).
- **Mac input:** a fresh save goes through the first-boot notices (the privacy prompt's second button is "Next"), the title and Investigations 1's Episode 1 with `DM_KEYS="f600:A~0.3,f1200:A~0.3,f1800:A~0.3,f2400:A~0.3,f3000:Down~0.3,f3200:A~0.3,f3800:A~0.3,f4400:A~0.3,f5000:A~0.3,f5600:A~0.3,f6200:A~0.3,f6800:A~0.3*270/120"` (the first investigation in Edgeworth's office at about frame 18,000; at about frame 30,000 the first Logic prompt waits for L).

## Tools (`dm/tools`)

| Tool | What it does |
|---|---|
| `nx_extract/` | NSP → ExeFS / RomFS / icon with LibHac, merging an update over the base game (C#, `dotnet build`). `--manifest` writes ExeFS and a RomFS file list only, for surveys |
| `nso_fnmap.py` | Carries offsets from one build to another (function matching with addresses masked; globals via their references) |
| `nso2elf.py` | Converts NSO to ELF for Ghidra / REA |
| `insn_census.py` | Counts the instruction sites the rewriter must handle |
| `nso_syms.py` | Compares the SDK import surface of two games, or of one game (`-` for the reference) with the host hooks |
| `nvn_slots_got.py` | Builds the NVN fetch table and call sites (GOT-indirect loaders) |
