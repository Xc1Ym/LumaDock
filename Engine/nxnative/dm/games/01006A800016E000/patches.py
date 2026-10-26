# Super Smash Bros. Ultimate (01006A800016E000): the rewriter's patches of this game's own builds. dm/tools/patch_nso.py loads every profile's patches.py and applies those of a module's NSO build ID;
# CUTS, OBS and FRAME_STEP as described there ("Registered patches"). Patches of Nintendo SDK module builds are in dm/tools/sdk_patches.py
CUTS = {
  # Super Smash Bros. Ultimate 13.0.5 (v2031616) main: the engine's memory (the nu:: allocator, set up by a static constructor at main+0x37c9a20) reserves 62 GB of address space with
  # nn::os::AllocateAddressRegion(0xf80000000) and hands it out in 64 KB units: a number line of free ranges, first [0, 0xf7f20) units from the region's start (main+0x37c9b98, given to
  # main+0x37c9c00), and the top 14 MB (region + 0xf7f200000) as the pool of its range nodes, committed 64 KB at a time up to the region's end (the bound checks at main+0x37c9a9c, +0x37c9c50,
  # +0x37ca3cc and +0x37caf68). The Switch's 64 GB alias region holds it; an iPhone's single 6 GB reservation cannot, and the abort at main+0x37c9bd0 followed. Booted on the Mac with a
  # 64 GB alias region, the game commits from the region's start upward (1.73 GB contiguous from it at the title, 75 s in) and the node pool's first 64 KB at the top, so the region is
  # cut to 4 GB (the application pool, 3.2 GB, bounds what it can commit), every constant derived from its size with it: the node pool at 4 GB − 14 MB, the first free range 0xff20 units
  '21450c647b8c5940ed5b68218ea128fd': [
    (0x37c9a5c, 'e11361b2', '2100c0d2', 'AllocateAddressRegion size mov x1,#0xf80000000 → mov x1,#0x100000000 (62 GB → 4 GB)'),
    (0x37c9a6c, 'e97f7cb2', '09fe9fd2', 'node pool top check, low part mov x9,#0xffffffff0 → mov x9,#0xfff0'),
    (0x37c9a70, '0be4afd2', '0be4bfd2', 'node pool start mov x11,#0x7f200000 → mov x11,#0xff200000'),
    (0x37c9a74, '09e4aff2', '09e4bff2', 'node pool top check movk x9,#0x7f20,lsl #16 → movk x9,#0xff20,lsl #16 (0xff20fff0)'),
    (0x37c9a78, 'eb01c0f2', '0b00c0f2', 'node pool start movk x11,#0xf,lsl #32 → movk x11,#0,lsl #32 (0xff200000 = 4 GB − 14 MB)'),
    (0x37c9a9c, 'e91361b2', '2900c0d2', 'node pool bound: region end mov x9,#0xf80000000 → mov x9,#0x100000000'),
    (0x37c9b98, '01e48f52', '01e49f52', 'first free range in 64 KB units mov w1,#0x7f20 → mov w1,#0xff20'),
    (0x37c9b9c, 'e101a072', '0100a072', 'first free range movk w1,#0xf,lsl #16 → movk w1,#0,lsl #16 (0xff20 units = 4 GB − 14 MB)'),
    (0x37c9c50, 'e91361b2', '2900c0d2', 'node pool bound: region end mov x9,#0xf80000000 → mov x9,#0x100000000'),
    (0x37ca3cc, 'e81361b2', '2800c0d2', 'node pool bound: region end mov x8,#0xf80000000 → mov x8,#0x100000000'),
    (0x37caf68, 'e91361b2', '2900c0d2', 'node pool bound: region end mov x9,#0xf80000000 → mov x9,#0x100000000'),
  ],
}
