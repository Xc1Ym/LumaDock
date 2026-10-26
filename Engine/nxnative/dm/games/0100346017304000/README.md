# Taiko Risshiden V DX (`0100346017304000`)

Update 1.1.1 (v131072) over the base game, SDK 12.3.3 (no other game's `sdk` build). Koei Tecmo's KTGL engine on NVN, mostly 2D. Modules `main` (15 MB), `subsdk0` (the movie library, NintendoSDK_movie: the WebM opening and ending movies) and `sdk`. In Japanese, Simplified and Traditional Chinese only (no English), so the NSP script packs Japanese (`DM_LANG` in `Documents/env.txt` switches). Plays on the iPhone (IPA 3.3 GB) by touch in handheld mode; 60 fps.

## What it needs

| Setting | Where | Why |
|---|---|---|
| Frame limiter wait skipped (`main+0x443fd4`, `b.hs end` → `b end`) | [`patches.py`](patches.py) `CUTS`, `main` build `f5ab74b9…` | its 2 ms sleep rounds ended frames at 18.2 ms (55 fps); see [Frame rate](#frame-rate) |
| `op_mode handheld` | [`game.tsv`](game.tsv) | handheld, the Switch build plays by touch; docked it reads only the pads |
| `pad_layout touch` | `game.tsv` | the Tap layout sends every touch to the game (the pads' corners would cover the cards, the menu icons at the top right and the on-screen B button) |
| 4 GB layout: `mem_reserve 0x100000000`, `mem_alias 0x10000000`, `mem_stack 0x10000000`, `app_pool 0xCD500000`, `sys_resource 0x0` | `game.tsv` | the NPDM declares no system resource (META +0x14 = 0): no virtual address memory; `nninitStartup` sets a heap of the pool − used memory (3.14 GB), which the game maps only as it touches it. The default 64 MB of used memory fits its small modules |

## Frame rate

- **Resolved: 55 fps with every frame 18.2 ms, the main thread asleep most of the time** (the menus and the town; the opening movie, paced by its own player, ran at 60). KTGL's frame end (`main+0x443e8c`, after the present) waits until N / 60 s have passed since the frame's start tick (taken at `main+0x443d44` after the previous present; N = 1, the int at GOT 0xa1c088), polling `nn::os::GetSystemTick` and sleeping 2 ms per round (`main+0x4c9f24`, `SleepThread`). With about 2 ms of work a frame the rounds end at 18.2 ms, never at 16.7: the Mac ran 55 fps (frame time p50 18.17 / p95 18.69 ms), every 11th frame on screen for two vsyncs.
- How it was found: sampling the host (`sample <pid>`: 90% of the main thread in `dm_guest_sleep_ns` under a guest return address of `main+0x443d74`) and a probe on the target's multiply (x20 = 1 frame, x0 = 19.2 MHz).
- **Current:** the game presents at interval 1, so the swap chain holds it to the display anyway; the cut makes the check jump straight to the end, and the host's present pacing (the acquire waits) sets the 60. In the town: 60.0 fps, frame time p50 16.66 / p95 16.85 ms, display interval p99 17.0 ms; the main thread waits in the acquire instead of nine sleeps a frame (wakeups 2,050 → 320 a second, CPU energy 1.7 → 0.7 mJ a frame).

## Input

- **Current:** handheld (`op_mode handheld`, `pad_layout touch`), the game plays by touch: tap the cards and buttons, drag or flick the map. On the iPhone those are all the touches in the Tap layout, on the Mac the mouse. The layout button brings back the gamepad (the map scrolls with the right stick in the 3D layout; L / R and ZL / ZR switch tabs and lists). It draws 1920x1080 in both modes.
- **Resolved: taps in handheld mode did nothing, though the game reads the touch screen** (the title's PRESS ANY BUTTON, the menus' cards). Its touch handler (`main+0x42f1ac`) uses `GetTouchScreenState` only to track the finger and takes its taps, pans and swipes from `hid::GetGestureStates` (it acts on types 5–9), which the host answered with no entries. The host now recognizes gestures from the same touch points (`hle_touch.c` `gesture_sample`, unit test `t_gesture`). Every menu, the cards, the map's drag and flick worked by touch with it. `DM_TOUCH_LOG=1` logs each gesture entry, and a `DM_CTL` line `drag <x0> <y0> <x1> <y1> [seconds]` moves a finger for testing pans and swipes on the Mac.

## Services

- **Resolved: null read at `sdk+0x362b8` (`apm::SetCpuOverclockEnabled`) in the first calls of `nnMain`** (`main+0x2e1e4c`). `oe::SetCpuOverclockEnabled(bool)` goes through the apm session the host never opened. The host keeps the flag and the query reports it (`hle_oe.c`); it does not scale clocks.

## Files and shaders

- Loose files, 3.3 GB: KTGL G1T textures (some in MRLK packs), the game's own TR5 / TE5 / TS5 data, KTSS Opus streams (`.kno`, through `nn::codec`) and KTSL wave banks (`.wbd` / `.whd`). `romfs_marker` is `TDATA/BUSTUP.G1T`.
- Shaders: 212 GLSLC outputs: 45 in `main` and 167 in the G2S container `eff/KTGLEffect.g1s` (`_S2G3000`, as Age of Calamity's), read by the existing splitter; nothing is compiled at run time. The game is almost all 2D sprites (two draws a frame in the menus).

## Status on the Mac

- The notice, the logos and the opening movie, the title, a new game (1560, Kinoshita Tokichiro) through the opening story, the town, the council with a battle proposal, the territory map, a rest at home, a save and a load, and the field battle tutorial, docked with buttons and in handheld mode by touch.
- 60 fps (frame time p50 16.66 ms, p95 16.85 ms in the town), sound; about 0.7 GB resident and 1.6 GB of Metal allocations, flat over 15 minutes. No red line on that route. The prewarm list covers it (18 lines).
- **Not a host bug:** the town's top-right panel runs off the screen on a council day (its "council today" text is longer than the usual "n days left"): the panel starts where the manual's screenshot has it and widens for the longer text; on other days it fits.

## Mac routes

- The work folder's `run/ctl.sh` drives a run started with `DM_CTL`. From an empty save: A skips the notice and the movie, A at the title and on New Game, then A five times (the scenario, its story, Tokichiro, his abilities, the settings) and about 150 presses of A through the story to the town (on the council day: A, Right ×3, A enters the castle).
- `run/save_ref` holds a save in the town on 1560 May 1.
- Handheld (`DM_OPMODE=0`), the same by touch: five taps at the centre (`T0.5x0.5`) reach the load screen of Continue, then `T0.5x0.29` and `T0.5x0.47` load slot 1.

## Found on this game

General host changes first needed here; each applies to every game:

- **`oe::SetCpuOverclockEnabled`** (`hle_oe.c`) and **gestures for `hid::GetGestureStates`** recognized from the touch points (`gesture_sample`: yuzu's rules plus an 8 px slop, `t_gesture`, `DM_TOUCH_LOG`, `DM_CTL` `drag`): [CPU overclock calls without an apm session](../../../docs/reference/services.md#cpu-overclock-calls-without-an-apm-session), [Touch gestures recognized from the touch points](../../../docs/reference/services.md#touch-gestures-recognized-from-the-touch-points).
