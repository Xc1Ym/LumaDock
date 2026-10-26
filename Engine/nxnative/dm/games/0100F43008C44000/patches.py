# Pokémon Legends: Z-A (0100F43008C44000): the rewriter's patches of this game's own builds. dm/tools/patch_nso.py loads every profile's patches.py and applies those of a module's NSO build ID;
# CUTS, OBS and FRAME_STEP as described there ("Registered patches"). Patches of Nintendo SDK module builds are in dm/tools/sdk_patches.py
CUTS = {
  # Pokémon Legends: Z-A 2.0.2 (v393216) main: nninitStartup (main+0x1b2e650) initializes its StandardAllocator with virtual address memory over 12 GB of address space (main+0x1b3e3e4), which
  # the Switch's 64 GB alias region holds and an iPhone's single 6 GB reservation cannot. The allocator commits pages as it goes and the pool (3.2 GB) bounds what it maps (profile mem_map_limit);
  # its largest block is nninitStartup's own probe of pool − used (3.15 GB, allocated and freed at once), so 4 GB of address space holds it
  'b1f12fd919eae86ab8a978317677e64b': [
    (0x1b3e3e4, '6200c0d2', '2200c0d2', 'StandardAllocator::Initialize(nullptr, size): address space mov x2,#0x300000000 → mov x2,#0x100000000 (12 GB → 4 GB)'),
  ],
}
# The same cut for builds without registered CUTS (dm/tools/nso_match.py), found by the fingerprint of the function that makes the call (132 bytes, the mov at +52) and its direct
# callees' (the allocator option getter it calls first, StandardAllocator::Initialize). The base game 1.0.0 (v0, main 7222e13e…, GitHub issue #266) has it at main+0x19f84b4
# (function main+0x19f8480: an exact nso_fnmap.py match of 2.0.2's main+0x1b3e3b0, the same fingerprint) and ships 2.0.2's sdk (df7a3960…), so the node area cut and the
# 5 GB layout hold for it unchanged
allocator = 'StandardAllocator::Initialize(nullptr, size): address space 12 GB → 4 GB'
MATCH_CUTS = {'main': [
    {'name': allocator, 'size': 132, 'fingerprints': ['af8eeda3d34bbfbfee1896ee0469ada1804c957695f3c7f2b8a970a20f495879'],
     'cuts': [(52, '6200c0d2', '2200c0d2', allocator + ': mov x2,#0x300000000 → mov x2,#0x100000000 (as 2.0.2 main+0x1b3e3e4)')]},
]}
