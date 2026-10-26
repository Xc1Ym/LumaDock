# Hades (`0100535012974000`)

Update 1.0.38233 (v589824), SDK 9.3.0. Supergiant Games' engine on The Forge renderer, on **Vulkan**, not NVN: `main` imports 100 `vk*` functions from `subsdk0` (the Vulkan loader), which sits on NVIDIA's driver in `subsdk1` (NVN, OpenGL, Vulkan). The host implements those functions on Metal itself (`dm/gfx/vk/hle_vk.m`), so only `main` and `sdk` are loaded. Plays on the iPhone.

## What it needs

| Setting | Where | Why |
|---|---|---|
| `modules main sdk` | [`game.tsv`](game.tsv) | `subsdk0` / `subsdk1` (Vulkan loader, NVIDIA driver) are replaced by the host's Vulkan layer and not loaded |
| 4 GB layout: `mem_reserve 0x100000000`, `mem_alias 0x10000000`, `mem_stack 0x10000000`, `app_pool 0xCD500000` | `game.tsv` | the NPDM declares no system resource (META +0x14 = 0), so the game uses `SetHeapSize`. Link's Awakening's partition, not measured for this game |
| `pad_layout full` | `game.tsv` | the 3D gamepad layout: the right stick aims the cast |
| Vulkan shaders through `vk_shaders.py` | NSP script | the game has no NVN shaders (`shader_note`); see [Files and shaders](#files-and-shaders) |

## Vulkan layer

The layer was written for this game (Super Mario Galaxy extended it later: [010099C022B96000](../010099C022B96000/README.md)).

- **Current:** one Tegra X1-like device (Vulkan 1.1). Device memory is a shared `MTLBuffer` made on first use; images are their own textures.
- **Current:** command buffers are recorded and replayed into one Metal command buffer per submit on the layer's own queue. Swapchain images are shown through the NVN layer's present path once their frame's GPU work is done.
- **Current:** names the game asks for through `vkGet*ProcAddr` are logged once each.
- How the host tells the API apart: a `main` that imports Vulkan functions and not `nvnBootstrapLoader` renders with Vulkan. `profile_guess.py` leaves `vkGetInstanceProcAddr` (SDL's Vulkan loader in other games) out of its Vulkan count; Hades and both Galaxies import 99 or 100 Vulkan functions, `vkCreateInstance` among them.

## Files and shaders

- 74 SPIR-V files in `Content/EffectsForgeSwitch` (`.vert` / `.frag`; the `.shader` files list each program's pair). `romfs_marker` is `Content/EffectsForgeSwitch/Default.vert`.
- `dm/gfx/tools/vk_shaders.py <RomFS> <shader dir> [--ios <dir>]` translates them with SPIRV-Cross into `<dir>/vk/`: one library, and a table of the Metal slot each (set, binding) moved to. The game hands the same words to `vkCreateShaderModule`, so the host finds each shader by the hash of its SPIR-V.
- **Packing:** for a Vulkan game the NSP script runs `vk_shaders.py` (Mac and iOS libraries in `<id>_build/shader/vk` and `shader/ios/vk`) in place of the NVN shader split and chain build, and `build_ipa.sh` ships `$MSL_IOS/vk` instead of the NVN chain libraries (`GFXAPI`). The NVN shader tables stay empty.

## Services

- **Resolved: the notification event.** The game polls `oe::GetNotificationMessageEvent` every frame. The SDK's own event was never created (the host's `oe::Initialize` is a no-op), so the host now hands out an event of its own, signalled while a notification is queued.
- **Current: offline.** `main` imports `EOS_*` functions (Epic Online Services, from `/nro/EOSSDK-Switch-Shipping.nro`, loaded through `nn::ro`); they stay offline. `main` imports only EOS Auth, Connect and PlayerDataStorage (Epic-account cross-save, which the host cannot serve). Since the host loads NROs, it refuses online SDKs: an NRR that registers only such modules fails `RegisterModuleInfo`, and Hades never asks for the module (checked on 1.0.38233: `refused an NRR that registers only online SDKs (1 hashes)`, no `LoadModule`, its frames as before).

## Rewriter

- Under the spin-wait search with the lock, test and store rules, Hades' modules rewrite byte for byte as before ([development.md, Power](../../../docs/development.md#power)).

## Mac routes

- `DM_KEYS="f800:A,f1000:A,f1200:A,f1500:A,f1900:A"` goes through the title and the intro into Tartarus.

## Found on this game

General host changes first needed here; each applies to every game:

- **The Vulkan layer on Metal** (`dm/gfx/vk/hle_vk.m`) and the SPIR-V translation (`vk_shaders.py`), described above; [dm/games/README.md, What the game files decide at every build](../README.md#what-the-game-files-decide-at-every-build).
- **A host notification event** for `oe::GetNotificationMessageEvent` (`hle_oe.c`), described above.

## Open

- The memory partition is Link's Awakening's, not measured for this game (`game.tsv`).
- Online SDKs in NROs: always load them, refuse them (as now) or decide per profile is an open question for the maintainer ([Online SDKs in NROs are never loaded](../../../docs/reference/services.md#online-sdks-in-nros-are-never-loaded)).
