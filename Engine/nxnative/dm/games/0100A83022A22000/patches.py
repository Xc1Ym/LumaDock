# Absolum (0100A83022A22000): the rewriter's patches of this game's own builds. dm/tools/patch_nso.py loads every profile's patches.py and applies those of a module's NSO build ID;
# CUTS, OBS and FRAME_STEP as described there ("Registered patches"). Patches of Nintendo SDK module builds are in dm/tools/sdk_patches.py
CUTS = {
  # Absolum 1.1.1 (v393216) main: nninitStartup (main+0x1b54d0) initializes malloc's StandardAllocator with virtual address memory over 40 GB of address space (main+0x28bff4, then
  # main+0x7562d0). Its largest block is FNA3D's GPU heap, 1.75 GB allocated at FNA3D_CreateDevice (main+0xc03660 → main+0x563370); measured into the first level, the allocator's blocks reach
  # 332 MB from the region's start and 1.82 GB from its end, 2.19 GB in all and no more after the title. 2.5 GB holds that with 300 MB to spare
  '916f5b8d61baa16d0939404ea047e129': [
    (0x28bff4, '4001c0d2', '0000b4d2', 'malloc region size: mov x0,#0xa00000000 → mov x0,#0xa0000000 (40 GB → 2.5 GB of address space)'),
  ],
}
