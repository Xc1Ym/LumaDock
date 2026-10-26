# ANIMAL WELL (`010020D01AD24000`)

Update 1.0.10 (v655360), SDK 20.5.7, on NVN (46 BNSH shaders). Modules `main` and `sdk`. All its assets, the shaders among them, are embedded in `main`: the program has no RomFS. The standard host and rewriter run this build with no game-specific fix: no shader overrides, rewriter cuts or host changes. Only this update is registered in the profile. The unsigned IPA is confirmed playable on the iPhone.

On the Mac: the opening rooms at 60 fps with movement, jumping and audio; item pickup and pause menus work. One repeat run recovered from an AudioUnit startup timeout through the existing audio restart path.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `romfs_marker` empty | [`game.tsv`](game.tsv) | the Program NCAs have no data section: `nx_extract` creates an empty RomFS directory, which the empty marker checks; see [Files](#files) |
| 3.5 GB layout: `mem_reserve 0xe0000000`, `mem_alias 0x10000000`, `mem_stack 0x10000000`, `app_pool 0xCD500000` | `game.tsv` | the provisional layout, which holds: a 256 MB alias region, a 256 MB stack region and a 2816 MB heap region. `main` sets a heap of at most the pool − 64 MB − 536 MB of bss (counted as used memory) |
| `sys_resource 0x0` | `game.tsv` | the NPDM declares 0 MB of system resource: `IsVirtualAddressMemoryEnabled` is false, as on Horizon |
| `pad_layout simple` | `game.tsv` | the 2D virtual pad; B jumps |
| `shader_groups /=romfs` | `game.tsv` | the shaders are in `main` |

## Files

- Both the base and the update Program NCAs have no data section. The assets live in `main`, whose read-only segment is about 32 MB.
- **Current:** `nx_extract` creates an empty RomFS directory (and a header-only survey manifest) when neither program has a data section. Base and update extraction were checked in both full and manifest modes.

## Shaders

- **Current:** 46 BNSH shaders embedded in `main` (1 vertex, 45 pixel), all translated for Mac and iOS by the existing splitter and translator. The prewarm list covers the opening rooms.

## Memory

- `main` has about 537 MB of bss, counted by the existing big-module memory rule.
- During a four-minute Mac run, resident memory stayed near 855 MB and Metal allocations at 159 MB.

## Found on this game

- **An empty RomFS for a program without a data section** (`nx_extract`; an empty `romfs_marker` checks the directory itself): [dm/games/README.md](../README.md).

## Open

- Save and reload are unverified: the test did not reach a save checkpoint.
- The bss is 536 MB in `game.tsv`'s comment and about 537 MB in the bring-up notes ([Memory](#memory)).
- The player-facing [README](../../../README.md) lists the games that start in the 2D layout and says the others start in 3D; ANIMAL WELL is not in that list, but its profile has `pad_layout simple` (2D).
