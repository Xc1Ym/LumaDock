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
