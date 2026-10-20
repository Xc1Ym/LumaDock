# Generic NSO rewriter: Switch aarch64 module → an image that can execute natively on Apple systems.
# Usage: patch_nso.py <NSO file> <output dir> <module name>
# Rewrites (the Apple kernel modifies x18 and tpidr_el0; Horizon's thread area, svc and timers have no counterpart on Apple):
#   x18 read/write      → thread slot K18 (TSD, via tpidrro_el0)
#   mrs tpidr_el0       → read thread slot KTLS; msr tpidr_el0 → write KTLS
#   mrs tpidrro_el0     → read thread slot KTLR (Horizon ThreadLocalRegion pointer)
#   svc #n, mrs cntpct_el0 → host gate (gate address taken from thread slot KGATE; once in C, gates.tsv is looked up by return point)
#   Registered cuts (CUTS, restricted by NSO build ID): before rewriting, the original bytes are asserted one by one and any mismatch aborts; results are listed in <name>.cuts.tsv
#   Registered observation gates (OBS, restricted by build ID): one instruction at the entry is replaced with "enter the host observation callback → execute the original instruction → jump back", so diagnostics modify zero code at runtime; listed in <name>.obs.tsv
# The key page only stores "actual key number × 8" at the end of the data segment, and patch code fetches thread slots indirectly through the key page: the loader may use any key number.
# Output: <name>.patched.bin (key page and patch area appended after the image at PATCH_OFF; when that would start beyond 112 MB the patch area sits before the base, see FAR), <name>.fixups.tsv (layout and key page index header), <name>.gates.tsv, <name>.sites.tsv, <name>.cuts.tsv, <name>.obs.tsv
import struct, re, sys, os
from itertools import combinations
import lz4.block
from capstone import *

src, outdir, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
d = open(src, 'rb').read()
assert d[:4] == b'NSO0'
flags = struct.unpack_from('<I', d, 0xc)[0]
segs = [struct.unpack_from('<III', d, 0x10 + i * 0x10) for i in range(3)]
bss = struct.unpack_from('<I', d, 0x3c)[0]
csz = struct.unpack_from('<III', d, 0x60)
# Every jump between the patch area and the code is a B (±128 MB). A patch area appended after the image (with bss) cannot reach the code when it would start beyond 112 MB (leaving 16 MB for the patch area): Metroid Dread's main has about 1.8 GB of bss (the engine's static heap); Engage's main starts its patch area at about 103 MB and keeps it after the image.
# The patch area then sits FRONT bytes before the module base (PATCH_OFF is negative), and the output file holds only text + ro + data (FILE_IMAGE_LEN) followed by the patch area; the loader supplies zero pages for bss and the key page (IMAGE_SIZE is the whole image).
# The key page stays after bss (the patch area reaches it through ADRP, ±4 GB). Modules below the limit produce output byte-identical to before
NEAR_PATCH_OFF = ((((segs[2][1] + segs[2][2] + bss + 0x3FFF) & ~0x3FFF) + 0x4000 + 0xFFFF) & ~0xFFFF)   # where an appended patch area would start (as in the else branch below)
FAR, FRONT = NEAR_PATCH_OFF > 0x7000000, 0x2000000
# A text segment that ends within 32 MB of the ±128 MB reach (Monster Hunter Rise: 125.3 MB of text) puts the patch area right before the base instead. Its stubs follow the sites in address
# order, so the last site's stub ends up about as far from it as the text is long. The first pass tries the gap that keeps every site in reach; when the patch area does not fit there
# (Monster Hunter Rise: 3.6 MB), the rewriter runs again with exactly the size it needs (DM_PATCH_FRONT, set only by that rerun) and B() checks every branch
BIG_TEXT = FAR and segs[0][2] + FRONT > 0x8000000 - 0x10000
if BIG_TEXT: FRONT = int(os.environ.get('DM_PATCH_FRONT', '0'), 0) or (0x8000000 - 0x10000 - segs[0][2]) & ~0xFFFF
IMG = bytearray(segs[2][1] + segs[2][2] + (0 if FAR else bss))
for i, (fo, mo, sz) in enumerate(segs):
    raw = d[fo:fo + csz[i]]
    if flags >> i & 1: raw = lz4.block.decompress(raw, uncompressed_size=sz)
    IMG[mo:mo + sz] = raw
TEXT_END = segs[0][2]
RO_OFF, DATA_OFF = segs[1][1], segs[2][1]
if FAR:
    FILE_IMAGE_LEN = (len(IMG) + 0x3FFF) & ~0x3FFF
    KEY_PAGE_OFF = (len(IMG) + bss + 0x3FFF) & ~0x3FFF
    IMAGE_SIZE, PATCH_OFF = KEY_PAGE_OFF + 0x4000, -FRONT
else:
    KEY_PAGE_OFF = (len(IMG) + 0x3FFF) & ~0x3FFF
    IMG.extend(bytes(0x4000))
    PATCH_OFF = (len(IMG) + 0xFFFF) & ~0xFFFF

# ---- Registered cuts: {NSO build ID: [(offset, original bytes, new bytes, reason)]} ----
# Networking cuts (excluded scope: Battle.net / online play): taken from a community offline fix (LFS Mod Offline Fix for v2228224, which differs from the official 94012 main in only these 7 words).
# Measured: the system service layer (nifm offline / DNS black hole / account service) cannot get around it: the game itself sends Battle.net requests directly and allows offline play according to the "last online" time.
CUTS = {
  # Super Mario Bros. Wonder v0 main
  'cd6e42aee7934f4d8393cd43893ae25e': [
    # Resource heap slack: each resource unit's ExpHeap is created with the resource size table value + 0x1008 (main+0x1e603c → ExpHeap::create main+0x4aac38); the table holds Nintendo's measured peaks with almost no margin
    # (PlayerYoshiAnm uses 99%). On the host, Model/NpcCommonerA.bfres in the opening course Course900 is about 0x70 bytes short: after the model resource's last GPU chunk (MatBlock,
    # 0x9000 bytes, 4 KB aligned, main+0x4290c0) is placed, its 0x598-byte descriptor does not fit, the GPU allocation fails → a buffer is built on a null memory pool → null read crash at main+0x106f5c8.
    # Where this differs from hardware is not known (every allocation size before this block is determined by game code and data); for now every resource heap gets +16 KB.
    (0x1e62fc, 'e00317aa', 'e0124091', 'resource heap size: mov x0,x23 → add x0,x23,#0x4000 (ExpHeap::create size argument +16 KB)'),
  ],
  # Super Mario Bros. Wonder 1.2.1 (v327680) main: same as above. Location carried over from v0 by dm/tools/nso_fnmap.py (containing function 0x1e603c → 0x1cf6f0 identical after address masking, ExpHeap::create 0x4aac38 → 0x4c4a18)
  'ff773e90972d544eb79406eaa65396d5': [
    (0x1cf9b0, 'e00317aa', 'e0124091', 'resource heap size: mov x0,x23 → add x0,x23,#0x4000 (ExpHeap::create size argument +16 KB)'),
  ],
  'db0507f36b84200ac05f75d76ed5026f': [
    # (Placed in the base rewrite shared by all build outputs): game video memory allocator budget 260 MB → 512 MB
    (0x8524c4, '0808a2d2', '0800a4d2', 'video memory allocator init config: mov x8,#0x10400000 (260 MB) → mov x8,#0x20000000 (512 MB); the following movk #0xa0,lsl48 and str [sp,#0x238] are unchanged; '
     'under the original budget an internal resolution above about 3.45 million pixels (2736x1260 passes, 2864x1240 crashes) leaves no room for the render targets: main+0x174b018 returns null and main+0x17417a4 crashes reading it; '
     'only a video memory budget, it does not enter game logic: the cvd5 tick-by-tick comparison matches at both 1600x900 and 2868x1320'),
    (0x1979bc, 'e8a79f1a', 'e8d79f1a', 'offline grace window: reads the last-online time of a save data settings key (the string at 0x1d53e80); '
     '"now − last online < 0x0009356907420000 ns (= 30 days)" sets [x20+0x2c]; lt→gt'),
    (0x5b14dc, 'e8a79f1a', 'e8d79f1a', 'calls 0xddab50 (buffer [x10+0x138]+x25, remaining length, callback 0x527d50, table 0x209cdb8, 9 entries) and sets the flag when it returns < 1; '
     'when set the 0x5b14f8 branch is taken; lt→gt (its meaning was not determined from strings)'),
    (0x5f3184, 'e8a79f1a', 'e8d79f1a', 'data table [0x2d64a18+idx*16] → +0xf90 record (0x1fc bytes) +0x4c index → +0xfd0 record (0x128 bytes) +0xf1 signed byte < 0 sets the flag, '
     'which is ANDed with (w26>0x24) and passed on as the 4th argument; lt→gt (its meaning was not determined from strings)'),
    (0x1d53e80, '55736572204c617374204f6e6c696e6500', '566f6963654c616e677561676500000000',
     'read-only string "User Last Online" → "VoiceLanguage": the first site reads a settings key that always exists instead, "last online" gets a small value, the difference always exceeds 30 days, and with gt it always passes'),
    # Product cut: the opening Logo and the "Press A to Start" page are cut, and startup goes straight to the main menu (the loading screen is kept)
    (0x8019ec, '280f0034', 'e8feff34', 'front-end boot first-entry branch: cbz w8,#0x801bd0 (LogoMenuPanel → logo video → title page) becomes cbz w8,#0x8019c8'
     ' (landing on the direct path 0x23e5e0(1) → 0xb156a0 into the main menu; it skips the two instructions from 0x8019bc that set online mode [0x2d7badc]=1, so online mode keeps its startup value 0 = offline, '
     'and the network check at 0x80ec44, the disconnected popup and the return to the title page are not triggered); the r4 target 0x8019bc set online mode 1, and in testing it still returned to the title page with the disconnected popup'),
    # Cuts for host-native implementations (host only: the ground-truth emulator does not apply them, Ryujinx does not know host call numbers from 0x80 up; equivalence is proven by per-block decoding matching 5511/5511)
    (0x1b0ee60, 'fc6fbaa9fa6701a9', '011000d4c0035fd6', 'TACT BLTE block zlib decode entry (DecodeZlib) → svc #0x80 ; ret: the host implements it with libdeflate'
     ' (hle_tact.c, call number registered in hle.h SVC_HOST_TACT_ZLIB); the rewriter applies cuts before scanning, so svc #0x80 becomes a host gate by itself, the gate block saves and restores x30, and ret returns to the original caller', 'host-only'),
    # Hook points for host test switches (host only): by default the host forwards as is, behavior unchanged
    (0x5d3a88, 'a27a0194', '211000d4', 'call site in the receive pump 0x5d3960 that delivers client command packets, bl 0x632510 → svc #0x81: by default the host calls 0x632510 with the original arguments (the caller ignores the return value); '
     'with DM_C2S_REPLAY the commands the client issues itself are dropped and the tick entry injects them from the file instead (diag.c, call number registered in hle.h SVC_HOST_C2S_DELIVER)', 'host-only'),
    (0x5d39c8, 'ba750194', '411000d4', 'call site in the receive pump 0x5d3960 that delivers system messages, bl 0x6310b0 → svc #0x82: by default the host calls 0x6310b0 with the original arguments (the caller ignores the return value); '
     'with DM_C2S_REPLAY, from the first tick of the replay file on, the system messages the host client issues itself are dropped (join messages before that pass) and the tick entry injects them from the file instead (diag.c, call number registered in hle.h SVC_HOST_C2S_SYS)', 'host-only'),
    # Screen aspect (host only, together with the resolution parameter slots in PARAMS below): output resolution cap {u32 width, u32 height}, read or written at only three places in resolution selection
    # (0xe12e28 / 0xe10d70 read: if the selected value's width or height exceeds the cap, no switch is made; 0xe12f54 writes it to the selected value after initialization finishes selecting); initial value 1920x1080 → 4096x2160, so that a width widened to the screen aspect can pass
    (0x211da30, '8007000038040000', '0010000070080000', 'output resolution cap initial value 1920x1080 → 4096x2160 (data segment): the width the host derives from the screen aspect ratio (e.g. 1956x900 on a 19.5:9 iPhone)'
     ' is chosen only if it does not exceed the cap; the Mac front end still gives the original 1600x900 / 1280x720, behavior unchanged', 'host-only'),
    # The width that the operation-mode notification handler (0xe10d30) gives to the "window size changed" event: original code mov w9,#0x740; and x9,x25,x9 -- the compiler knew the width could only be 1280 (0x500) / 1600 (0x640),
    # and optimized "take the low 32 bits" into & (0x500|0x640). The KRES0 / KRES1 parameter slots replaced those two constants, but this derived mask was not changed along with them: 2868 & 0x740 = 768, 2296 & 0x740 = 64
    # (after switching docked / handheld while running, the output width was 64 / 768; the iOS overheating downgrade takes exactly this path). Changed to take the low 32 bits directly: same result for the original game's two widths, correct for any width
    (0xe10e48, '09e880522903098a', 'e903192a1f2003d5', 'width in the window-size event sent by the operation-mode notification: mov w9,#0x740; and x9,x25,x9 → mov w9,w25; nop (takes the low 32 bits instead of the constant mask derived from the original two widths)', 'host-only'),
    (0xe12e88, '09e880528902098a', 'e903142a1f2003d5', 'the same mask in the startup resolution choice (0xe12d70): mov w9,#0x740; and x9,x20,x9 → mov w9,w20; nop (found by the structck check of masks downstream of the parameter slots; at startup the event receiver usually does not exist yet, so it rarely shows)', 'host-only'),
    # Product cut (reproducing the exclusion list item "classic picture toggle"): the two state writes of the classic picture toggle 0xb15d60 → nop.
    # The picture transition state starts at 0x2dc0758 (+4 start, +8 target, +0xc progress; 1.0 = new picture); in the whole program the only writers are 0x852280 (startup init writes 1), 0x85cb20 (force back to the new picture, writes 1),
    # 0x856be0 (writes only +0xc) and 0xb15d60 (when not in a run, or when the run version is 1 / 2, flips the target between 0 / 1 according to the current coefficient) -- the last is the only place that can push the target toward 0;
    # the callers 0x36a5a0 / 0x4035e8 / 0xc25f48 / 0xc2725c are all toggle actions (the video option LegacyGraphicsMode, the character creation page's ToggleLegacy, the console version's ClassicToggle and the key LegacyToggle all converge here).
    # What is cut is two plain stores, containing no calls: the list of synchronization primitives and external side effects of the cut part is empty (the cut rule). The hint branch for run version 3 in a run (from 0xb15e2c) is untouched
    (0xb15e20, '0281002d', '1f2003d5', 'classic picture toggle writes start / target (stp s2, s0, [x8, #4]) → nop: the target stays 1.0 (new picture)'),
    (0xb15e24, '1f0d00b9', '1f2003d5', 'classic picture toggle clears progress (str wzr, [x8, #0xc]) → nop'),
    # Widescreen (host only, together with the KASPECT aspect ratio cap in PARAMS): the cap in UI canvas width = min(screen width, 4560 = 2160 × 19/9) is opened up to 0xffff.
    # In the original game at 16:9 the screen width of 3840 units < 4560, so the result is unchanged; on iPhone 1952x900 the screen width is about 4685 units, which used to be clamped to 4560, leaving about 26 pixels on each side
    (0xb1a660, '083a8252', 'e8ff9f52', 'UI canvas width cap mov w8, #4560 → mov w8, #0xffff (canvas width = screen width)', 'host-only'),
    # (Reverted: the cuts 0x3172f8 / 0x3173e4 for "SetLanguage 0x317298 clear + reload string tables" in place since r13 / r15 (originally set up to exclude languages other than Simplified Chinese),
    # reverted because of the English version -- switching language in the original game relies on this reload.)
    # Product cut: the loading of string table A (legacy, 0x2d70ff0 / 0x2d71010) is skipped as a whole. The load function 0x7f64f0(w0 = whether to load legacy)
    # branches at the tbz w23 at 0x7f669c: when not loading, the success flag is set to 1 (0x7f6800), the same result as all 17 strings-legacy/*.json loading successfully.
    # No-reader proof: of the 128 functions in the whole program that reference table A, 124 also read the table-select flag [0x2d71098] and select the table by "flag = 0 → table B (0x2d71030 / 0x2d71050)"
    # (e.g. the csel at 0x13b7d8); the other 4 are the table's own static constructor 0x7f8f80, load 0x7f64f0, table insert 0x7f72e0 and clear 0x7f5b60. The flag's only write site 0xb1bcf4
    # writes !obj[0xb9], and obj[0xb9] is obtained by comparing the picture transition state 0x2dc0758 with 1.0 -- r14 already cut the classic picture toggle, the only thing that can push the target away from 1.0; the flag is in .bss
    # (initial value 0), and the probe at 0xb1bcfc over the whole r15 cvd5 run hit 0 times (the write site never executed) ⇒ only table B is read throughout. The cut tree = 17 single-file loads via 0x7f72e0; same as the supplementary proof of
    # the language reload cut above (the same 0xdf67f0 read transaction, paired, no external waiters)
    (0x7f669c, '370b0036', '59000014', 'string table load tbz w23, #0 (whether to load legacy table A) → b 0x7f6800: table A has no readers (the table-select flag is always 0 → table B), so none of the 17 legacy files is loaded'),
    # The per-block decode call sites of the two streaming segment read paths of Granny segment decoding (BitKnit2): by default the host forwards as is to 0x11f4af0 (the replacement hook point of pre-decode plan A, hle_granny.c)
    (0x11f02dc, '05120094', '611000d4', 'segment read 0x11f0110 per-block decode bl 0x11f4af0(ctx, block, length) → svc #0x83: by default the host calls it with the original arguments and writes back w0 (hle.h SVC_HOST_GRANNY_A)', 'host-only'),
    # Drop light (host only): the item's appearance definition path lookup bl 0xa14dc4(resource manager, unit, x8 output string) → svc #0x87: the host forwards the call as is,
    # and for items in mode 3 / 5 (on the ground / dropping) repoints the path by rule to the lit variant in the overlay (dm_dropfilter.c svc_ground_asset; hle.h SVC_HOST_GROUND_ASSET)
    # Tier-one drop sound (host only): fetching the drop sound on landing bl 0x470c20(item, &trigger frame) → svc #0x88: the host forwards the call as is, and tier-one items get a notification sound instead (dm_dropfilter.c svc_drop_sound)
    (0x468f2c, '3d1f0094', '011100d4', 'item landing drop-sound call site bl 0x470c20 → svc #0x88: the host makes the original call, then by rule replaces the drop sound of tier-one items with a notification sound (others unchanged)', 'host-only'),
    (0x8fa590, '0d6a0494', 'e11000d4', 'item appearance path call site bl 0xa14dc4 → svc #0x87: the host makes the original call, then by rule points items on the ground at their lit variant (stashed / worn / belt / socketed untouched)', 'host-only'),
    # Run-entry spawn point (entering a run lands next to the town waypoint, with the corpse in the same place as the player; host only): the player join function 0x5d7f70 fetches a spawn point once for the player and once for the corpse, both via bl 0x5596c0(data version, act, level, cell type 0, &x, &y, unit size)
    # → svc #0x8a (player) / #0x8b (corpse): the host forwards the call as is; when the run is entered in town it instead picks the point by "waypoint cell 13 + a fixed safe distance", and the player, corpse and mercenary are placed in one go by the original game (the player is no longer moved by a level change on tick 2, and the corpse no longer stays at the original spawn point) (dm_townwp.c svc_join_spawn)
    (0x5d8040, 'a005fe97', '411100d4', 'run-entry player spawn point call site bl 0x5596c0 → svc #0x8a: the host makes the original call, and when the run is entered in town the spawn point moves next to the waypoint (hle.h SVC_HOST_JOIN_SPAWN)', 'host-only'),
    (0x5d8400, 'b004fe97', '611100d4', 'run-entry corpse placement call site bl 0x5596c0 → svc #0x8b: as above, the corpse gets the same point as the player (hle.h SVC_HOST_JOIN_CORPSE)', 'host-only'),
    (0x11f0914, '77100094', '811000d4', 'segment read 0x11f07d0 per-block decode bl 0x11f4af0(ctx, block, length) → svc #0x84: as above (hle.h SVC_HOST_GRANNY_B)', 'host-only'),
  ],
  # Fire Emblem Engage 2.0.0 (v327680) sdk: AddressRegionManager node area 0x3fe00000 (about 1 GB) → 0x3e00000 (62 MB).
  # The constructor (sdk+0x346420) carves the node area out of the start of the alias region (a unit heap of 0x30-byte nodes, mapped only as used) before AllocateAddressRegion hands out regions.
  # The hardware alias region is 64 GB, so the 1 GB does not matter there; the host's alias region is only 5.375 GB (iOS caps a single reservation at 6 GB), and after StandardAllocator's 3.14 GB block (1 GB aligned)
  # Unity's low-level virtual allocator (main+0x9aa0f4 → AllocateAddressRegion) had only about 1.2 GB left; about 357 s into the prologue battle it got no region → returned 0 → null write crash at main+0x9a4664.
  # 62 MB holds about 1.35 million nodes (a few hundred regions are live in measurements). Both movs must change together: +0x346430 sets the node area limit, +0x3464cc registers it as an occupied region.
  # Fire Emblem Engage 2.0.0 (v327680) main: run the game's own 60 fps path (vertical sync count always 1).
  # The game's time class App.GameTime picks a vertical sync count per scene (Slow = 2, i.e. 30 fps: system, movies, demos, combat cutscenes, the hub; Normal is 1 only when GameConfig.IsPerformance)
  # and hands it to Unity through GameTime.SetVsyncCount(int) (QualitySettings.vSyncCount → NVN present interval). About 96 pieces of per-frame logic (cameras, map cursor, unit actors, menu scrolling and cursors, hub camera, minigames)
  # step by GameTime.VsyncFixedCount (= vSyncCount, how many 60 Hz ticks each frame advances): with a count of 2 and 60 frames on screen they all run twice as fast, with a count of 1 at 60 fps they are right.
  # The real-time VsyncDeltaCount / VsyncDeltaTime (hub character movement, fishing, dragon ride and so on, about 120 places) do not depend on the frame rate.
  # The cut is in Unity's managed wrapper QualitySettings.set_vSyncCount (main+0x32f92c0): both paths use w19 as the argument, mov w19,w0 → mov w19,#1,
  # so every caller (GameTime, QualitySettingsStack.PopImpl, XRSystem) can only set 1; the read side (get_vSyncCount) follows at 1 and the game stays consistent. No code calls SetQualityLevel.
  '8c08b9719e085f91847b5e0f935d9488': [
    (0x32f92d4, 'f303002a', '33008052', 'QualitySettings.set_vSyncCount wrapper: argument mov w19,w0 → mov w19,#1 (the 60 fps path of the game itself)', 'host-only'),
  ],
  # The Legend of Zelda: Breath of the Wild 1.9.0 (v1114112) main: 60 fps. The main loop of sead::GameFrameworkNx (main+0x112660c) runs a dynamic interval (framework +0x267 = 1):
  # every frame it computes how many vsyncs the last frame needed (rounded up), clamped to [2, max 3] (the max comes from the interval controller +0xc, constructed at main+0x1126c04); it steps up after 3 overrunning frames in a row,
  # steps down one level every 6 frames until 2, and hands the result through setWaitVsyncInterval (vtable +0x130, main+0x11269b8) to presentation (nvnWindowSetPresentInterval).
  # The game logic time step follows it: ksys::VFR is initialized with a base interval of 2 (constant 2 at main+0x127e740 → VFR::init main+0x151d2d0), and every frame VFR::updateInterval (main+0x151d3d0,
  # called at main+0xcf9ad4 / main+0x1281044) takes the framework's current interval (vtable +0x138); the frame ratio = current interval / 2 -- at interval 1 each frame advances half a 30 fps tick and the game speed stays the same;
  # when it struggles and steps back to 2 / 3 the ratio is 1 / 1.5, again at the same speed. So only the floor changes from 2 to 1: the lower bound of the candidate interval (two places), the step-down target recorded when stepping up, max(candidate, 3) - 1 → max(candidate, 2) - 1,
  # and stepping down stops at < 3 → < 2. On hardware the same logic starting from 1 would also be 60 fps; it falls back to 30 by itself only when its input shows a slow frame (the last two cuts make that input include the GPU time)
  'cd57b23fa4bbad65803d9788c01821ee': [
    (0x112670c, '6041201e', '4041201e', 'lower bound of the candidate interval: fmov s0,s11 (2.0) → fmov s0,s10 (1.0)', 'host-only'),
    (0x1126710, '7f0b0071', '7f070071', 'lower bound of the candidate interval: cmp w27,#2 → cmp w27,#1', 'host-only'),
    (0x112665c, '78008052', '58008052', 'step-down target recorded when stepping up, max(candidate, w24) − 1: mov w24,#3 → mov w24,#2', 'host-only'),
    (0x1126748, '1f0d0071', '1f090071', 'step-down target recorded when stepping up: cmp w8,#3 → cmp w8,#2', 'host-only'),
    (0x1126794, '3f0d0071', '3f090071', 'stepping down stops at < 3 → at < 2: cmp w9,#3 → cmp w9,#2', 'host-only'),
    # The controller's input (framework +0x250, controller main+0x1126cec..) is the main thread's CPU span up to the draw step (about 2.7 ms in the first shrine), so GPU-bound frames stayed at interval 1 and the game ran slow
    # (iPhone 16 Pro Max: 25 ms frames, two thirds of the speed). The game has a GPU-time path that uses max(CPU span, GPU time between the frame's two timestamp reports, framework +0x220, read after the fence wait)
    # but takes it only while [main+0x1e3a638]+0x1d2b8 is set (64 of 6,046 shrine frames); both of its checks become branches into it. The GPU time needs the profile's gpu_timestamps segment
    (0x112691c, 'c00000b4', '03000014', 'interval controller always takes the GPU time path (CPU span timing): cbz x0,#0x1126934 → b #0x1126928', 'host-only'),
    (0x1126974, 'c00000b4', '03000014', 'interval controller always takes the GPU time path (takes max(CPU span, GPU time)): cbz x0,#0x112698c → b #0x1126980', 'host-only'),
  ],
  '56ec24747ec9e7f19b3efb062483a19d': [
    (0x346430, '08fca752', '087ca052', 'AddressRegionManager constructor: node area limit mov w8,#0x3fe00000 → mov w8,#0x3e00000', 'host-only'),
    (0x3464cc, '09fca752', '097ca052', 'AddressRegionManager constructor: length of the node area registered as an occupied region mov w9,#0x3fe00000 → mov w9,#0x3e00000', 'host-only'),
  ],
  # Ace Attorney Investigations Collection 1.0.0.2 (v131072) sdk (SDK 17.5.3): the same node area cut as Engage's. Without it nninitStartup's StandardAllocator::Initialize(nullptr, pool − used)
  # (main+0x874b6c, virtual address memory) aborts at its first CentralHeap::Init: the 1 GB-aligned region of 3.14 GB did not fit in the 4.375 GB alias region after the node area.
  # The constructor is at sdk+0x139458 (limit = alias start + 0x3fe00000 at +0x28, a unit heap of 0x30-byte nodes, the area then registered as occupied)
  '311deab1f062b504f3d646a49ddcd4e8': [
    (0x139468, '08fca752', '087ca052', 'AddressRegionManager constructor: node area limit mov w8,#0x3fe00000 → mov w8,#0x3e00000', 'host-only'),
    (0x1394fc, '09fca752', '097ca052', 'AddressRegionManager constructor: length of the node area registered as an occupied region mov w9,#0x3fe00000 → mov w9,#0x3e00000', 'host-only'),
  ],
  # The Legend of Zelda: Link's Awakening 1.1.0 (v131072) main: the physics step (main+0x15730, main thread) rebuilds each world's PhysX completion task in place
  # (a PxLightCpuTask at world+0xc8) and passes it to simulate. A worker runs it (main+0x10ccf80: fetchResults, world+0x1d8 done = 1, notify, unlock) and then calls its
  # release (main+0x10cd070), which calls the task's own destructor: vtable back to the PxLightCpuTask base, mTm = 0 (main+0x10cced0). At 30 fps the game steps twice
  # per frame (step, wait, step, wait); the unlock hands the world's mutex to the woken main thread, and when the worker is descheduled there the main thread's
  # next step rebuilds the task before the late destructor runs, which then wipes the new task. The next simulation's NpSceneCompletion::release reads its mTm = 0:
  # crash at main+0x10ccf28 (lr main+0x13c236c; seen on the iPhone and in 2 of 5 Mac runs, in every Mac run under CPU load). On the Switch the release follows the
  # unlock within nanoseconds. The release becomes a plain ret: the destructor only resets the vtable and mTm (no resources), the step rebuilds every field, and this
  # release is used by this one vtable (main+0x1c51308 slot 7) only
  '909e904af78ac1b8deefe97ab2ccdb51': [
    (0x10cd070, '080040f9', 'c0035fd6', 'physics completion task release (calls its own destructor): ldr x8,[x0] → ret (no longer destroyed; the step function rebuilds it in place every step)', 'host-only'),
  ],
  # Fire Emblem: Three Houses 1.2.0 (v327680) main: 60 fps. KTGL runs the game on the main thread at 60 updates a second whatever it shows: each update steps by
  # 1/fps with fps = 60.0 (main+0x1a38f08, set at main+0x50e114; dt at main+0x510010), and the frame end (main+0x50f680) waits out 60/fps ticks of 1/59.94 s in a yield loop
  # (main+0x5be430). The render thread (main+0x50f8c0) draws the latest update and presents with the interval of the render mode (frame +0xbb84, set at main+0x50f3d0:
  # 0 = 1080p docked, 2 = 720p handheld; 3 / 5 their two-view variants; 1 and 4 are 720p / 1080p modes at interval 1 that nothing selects). Measured on the Mac: 59.2 updates
  # and 29.8 presents a second. The per-mode interval table (int at main+0xd13de0, read by main+0x4b0420 for the present and by the 6-tick fade counter in main+0x4b7530;
  # float at main+0xd13e40, the per-frame scroll step in main+0x4c2b30) becomes 1 for every mode, as in modes 1 and 4: every update is shown and the render thread's
  # own steps stay at the same speed. Resolutions stay per mode
  '89048449ba238c8cf565518b83bf02d3': [
    (0xd13de0, '020000000100000002000000020000000100000002000000', '010000000100000001000000010000000100000001000000', 'per-render-mode present interval table {2,1,2,2,1,2} → all 1 (60 fps; the game logic already runs at 60 updates a second)', 'host-only'),
    (0xd13e40, '000000400000803f00000040000000400000803f00000040', '0000803f0000803f0000803f0000803f0000803f0000803f', 'per-render-mode interval as float {2.0,1.0,2.0,2.0,1.0,2.0} → all 1.0 (render-thread per-frame steps)', 'host-only'),
    # The render thread still presents with interval 2 while either of two flags is set: main+0x21c9a03, a full-screen image drawn before the frame (main+0x4b4908: the opening movie),
    # and frame +0xc55f / +0xc560 (from the object at app +0x40: the character creation screen after the movie, and so on). In the engine's own 60 fps modes this traded 60 fps for
    # resolution in those scenes (main+0x50f7d0 drops 720p mode 1 to 1080p mode 0); here it would show them at 30 with the render thread's own steps at half speed. Both are ignored
    (0x50fb7c, '2801082a', 'e8031f2a', 'render thread forced interval 2: orr w8,w9,w8 (either flag) → mov w8,wzr (the mode\'s interval, 1)', 'host-only'),
    # The frame limiter's wait (main+0x5be430: yield, read the tick, until 60/fps ticks of 1/59.94 s have passed since the last frame end; x8 = time passed and x23 = target, in 100 ns)
    # is a busy loop on the host: the yield back-off spins its first 2 ms on a performance core and then oversleeps by up to 250 µs, so frames took 16.8 ms (59.5 fps, a repeated
    # display frame every 2 s) and CPU energy went from 0.16 W at 30 fps to 1.5 W on the Mac. The yield becomes nn::os::SleepThread of 96% of the time left, and the loop goes back to
    # the limiter's own tick read and comparison at main+0x5be44c (the instructions after the b are no longer reached); the host's sleep never oversleeps, so the frames take 16.68 ms
    (0x5be4c0, '20fa1494', 'e00208cb', 'frame limiter wait: bl YieldThread → sub x0,x23,x8 (time left, 100 ns units)', 'host-only'),
    (0x5be4c4, 'bbf71494', '01e87bd3', 'frame limiter wait: bl GetSystemTick → lsl x1,x0,#5', 'host-only'),
    (0x5be4c8, '680240f9', '2018008b', 'frame limiter wait: ldr x8,[x19] → add x0,x1,x0,lsl #6 (96 ns per 100 ns left)', 'host-only'),
    (0x5be4cc, '080008cb', '8df71494', 'frame limiter wait: sub x8,x0,x8 → bl nn::os::SleepThread (PLT main+0xafc300)', 'host-only'),
    (0x5be4d0, '087d149b', 'dfffff17', 'frame limiter wait: mul x8,x8,x20 → b main+0x5be44c (read the tick and compare again)', 'host-only'),
    # The render thread waits for the next update with KTGL's event wait (main+0xaa90e0, timeout in µs: × 1000 → nn::os::TimedWaitEvent) and passes 1/fps × 1000 = 16, one frame in ms,
    # so it polls every 16 µs: at 60 fps it draws in about 3 ms and then polled for the rest of the frame (42,000–53,000 wakeups a second on the Mac, against 1,200 at 30 fps, where
    # it waited in the present instead). The other four callers wait without a timeout. The timeout becomes 1000/fps × 1000 = 16,666 µs (s8 = 1000.0, loaded first)
    (0x50f8e8, '01102e1e', '483d0090', 'render thread wait timeout: fmov s1,#1.0 → adrp x8,#0xcb7000', 'host-only'),
    (0x50f8ec, '2018201e', '08514bbd', 'render thread wait timeout: fdiv s0,s1,s0 → ldr s8,[x8,#0xb50] (1000.0)', 'host-only'),
    (0x50f8f0, '483d0090', '0019201e', 'render thread wait timeout: adrp x8,#0xcb7000 → fdiv s0,s8,s0 (1000/fps; the fmul by s8 that follows makes it µs)', 'host-only'),
    (0x50f8f4, '08514bbd', '1f2003d5', 'render thread wait timeout: ldr s8,[x8,#0xb50] → nop (moved up)', 'host-only'),
  ],
  # Hyrule Warriors: Age of Calamity 1.3.0 (v327680) main: the init (main+0x8d9610) hands the KTSL sound engine three heaps carved from one block: 15 MB engine memory, 2 MB, and
  # 142 MB sound data (sizes built by mov x8,#0xf00000; movk x8,#0x20,lsl #48 and mov w9,#0x8e00000; constructor main+0x12647a0, heaps created at main+0x1a2ba58). The audio renderer
  # work buffer in the 15 MB heap is 0x760000 (the SDK's AudioRenderSystem::GetWorkBufferSize, 0x40a9c8 of it command buffer), and the engine's setup asks for about 16.9 MB in
  # all: the fourth 0x1b5860-byte player block (main+0x1a32f70; three of the four players mix 5.1) came back null, the setup released its memory pools and gave up (-51),
  # the first sound archive (ASRS) never loaded and nnMain's resource wait (main+0x8d9bc8) spun forever. Where hardware differs is not known. The engine heap gets 4 MB from the
  # sound data heap, so the block the three come from keeps its size
  'c3cf52bf2b05d7310884971b50bcccb8': [
    (0x8d9610, '081ea0d2', '0826a0d2', 'sound engine heap: mov x8,#0xf00000 → mov x8,#0x1300000 (+4 MB)'),
    (0x8d9618, '091ca152', '0914a152', 'sound data heap: mov w9,#0x8e00000 → mov w9,#0x8a00000 (-4 MB; the block the three heaps come from keeps its total size)'),
    # 60 fps. nnMain builds KTGL's device config on its stack and inits the device once (main+0x8d94c4 → main+0x17c34f0): {1920, 1080, 3, 9, 5, interval 2, 9, …}. The device
    # keeps the interval (main+0x17c4ba8 → device +0x2aa4, passed to every present at main+0x17ced78, which sets it on the window when it changes) and its frame rate,
    # 59.94 / interval (main+0x17c37c8 → device +0x32d0), which the game steps its time by (the event scripts at main+0x7802c4: timescale / frame rate). Forcing interval 1 at the
    # present alone would keep the 1/29.97 step at 60 frames a second. With interval 1 in the config the device runs the engine's own 60 fps mode: frame rate 59.94, interval 1
    (0x8d94b0, '4900c0f2', '2900c0f2', 'KTGL device config present interval: movk x9,#0x2,lsl #32 → #0x1 (60 fps; the device frame rate becomes 59.94 / 1)', 'host-only'),
    # The frame itself is paced by a KIDS task (main+0x166d9c0, on a KIDSTaskScheduler thread): it waits until 1 / fps has passed since the last frame (tick frequency / fps,
    # SleepThread and a poll), then steps the game by the time that really passed (+0x24, seconds). fps (+0x30) is 30, from engine data (main+0x166daa4)
    (0x166db80, '14159f1a', '94078052', 'KIDS frame task wait: csinc w20,w8,wzr,ne (fps, at least 1) → mov w20,#60 (wait 1/60 s; the step stays the measured time)', 'host-only'),
  ],
}
# ---- Registered observation gates: {NSO build ID: [(offset, number, original instruction word, reason)]}. Numbers match OBS_* in the host's hle.h;
# the original instruction must be position independent (no PC-relative / branch / anything involving x18 or tpidr), asserted offline; when the host has no callback attached the gate block goes in and out once and returns ----
OBS = {
  # Metroid Dread 2.1.0 main: the movie player posts "link / unlink holders" requests into the dispatcher thread's request ring (main+0x222cc8) and goes on without waiting for them (after an unlink it frees the wrapper object and builds a new one in place).
  # On hardware the dispatcher thread (priority 30, core 0 only) preempts the main thread (priority 44, core 0) at once and finishes first; the host waits for the ring to empty after each post (hle_movie.c movie_ring_wait). The gates sit on the add x22, x22, #8 after the bl
  '646761f643afebb379edd5e6a5151af2': [
    (0x2247a4, 19, '910022d6', 'link request posted (loop at main+0x224728, x19 = request ring): wait for the dispatcher; orig add x22, x22, #8'),
    (0x2248e4, 20, '910022d6', 'unlink request posted (loop at main+0x224868, x19 = request ring): wait for the dispatcher before the object is freed; orig add x22, x22, #8'),
  ],
  'db0507f36b84200ac05f75d76ed5026f': [
    (0xb1dc60, 1, 'd10603ff', 'UI message bus virtual implementation entry (x1 = message {u64 type hash, u64 action hash, char* panel name, …}): '
     'the only source of the DM_UIMSG message stream and the DM_BOOTPROF boot phases; orig sub sp, sp, #0x180'),
    (0x5d3bc0, 2, 'd10503ff', 'server tick entry (x0 = game object G): DM_TICKS per-tick 6-field state hash (dm/verify/tick_state_format.md, the same capture point as the ground truth swtick.py); '
     'orig sub sp, sp, #0x140'),
    (0x6e5b40, 3, 'd10103ff', 'client command dispatch entry (G, unit, packet, length): DM_C2S_LOG command packet sequence (dm/verify/command_packet_format.md, the same capture point as the ground truth); '
     'orig sub sp, sp, #0x40'),
    (0x6310b0, 4, 'a9bb67fc', 'system client message handler entry (buf = u32 client number + packet, packet length): packet IDs ≥ 0x67 (join / heartbeat 0x6d / 0x6f etc.), the receive pump drains this queue first; '
     'DM_C2S_LOG records it as "q":"sys"; orig stp x28, x25, [sp, #-0x50]!'),
    (0x317298, 5, 'd10183ff', 'SetLanguage entry (x1 → u32 new language number, language name table main+0x20ae478): together with the language reload cut above, the host asserts that the new language is zhCN; '
     'orig sub sp, sp, #0x60'),
]}
BUILD_ID = d[0x40:0x50].hex()
# Build-time product rules: the old original-resource / comparison domain is unchanged by default; the touchscreen version is issued separately as a new version, and guest code is not written at runtime.
RULESET = os.environ.get('DM_RULESET', 'native')
assert RULESET in ('native', 'touch-run-v4'), f'unknown rule set {RULESET}'
RULE_BUILD = 'db0507f36b84200ac05f75d76ed5026f'
RULE_RUN = RULESET == 'touch-run-v4' and NAME == 'main'
if RULE_RUN:
    import hashlib
    assert BUILD_ID == RULE_BUILD, f'Run rule build ID mismatch {BUILD_ID}'
    RULE_ORIG_SHA = hashlib.sha256(IMG).hexdigest()
cuts = list(CUTS.get(BUILD_ID, []))
# The touchscreen rule domain by default also carries the host-private gates; the rule gate check can turn them off explicitly, keeping the same packaging entry point and rule domain.
PRIVATE_GATES = os.environ.get("DM_PRIVATE_GATES", "1") != "0"
PRIVATE_AIM = RULE_RUN and PRIVATE_GATES
if PRIVATE_AIM:
    cuts.append((0x2faf04, 'fde7fe97', 'c11000d4',
      'skill-aim-v1-private: skill ground direction call only; svc86 delegates original2b4ef8 then sampled-right/original rotation+grid; zero/nonplayer/non-skill retain original; busy/town/skill/server untouched', 'host-only'))
if RULE_RUN:
    # Directional light shadow map edge length (quality level 1, 0x168a520 fills +0x48 → creates the 2-layer array 0x1697394): 2100 → 1024. Authorization: "visually indistinguishable is enough";
    # on the second Mac, 108 images + 16 consecutive frames: for camp / wilderness / combat, at every level down to 1024 the FLIP cannot be told apart from the noise of a rerun with the same settings, and the change between adjacent frames in shadow regions is 0.71 → 0.75; on a real device the two shadow maps total about 0.7–1.4 ms / frame.
    # The shadow size constants and the viewport that the game passes to the shader change with the same config value (verified by dump). The native rule domain (the Mac gate check against the original game's ground truth) stays at 2100
    SHADOW_SIDE = 1024
    movz_w14 = lambda n: struct.pack('<I', 0x52800000 | (n << 5) | 14).hex()   # movz w14,#n -- the bytes are computed by an expression, not written by hand (a hand calculation came out as #32768, and the shadow map allocation of 32768² failed, crashing at startup)
    cuts.append((0x168a580, movz_w14(2100), movz_w14(SHADOW_SIDE), f'shadow map side mov w14,#2100 → mov w14,#{SHADOW_SIDE} (quality level 1)', 'host-only'))
if RULE_RUN:
    # Purely informational system notifications do not swallow the function key: the controller version's notification panel handler 0x3d84a0, on "action 9 (PLUS) pressed", executes the confirm action carried by the notification and swallows the key (meant for "press PLUS on a level-up notification to go straight to the skill tree").
    # The confirm action carried by a system notification (event queue class 12, 0xab5c08; e.g. "game difficulty set to N..." after changing the difficulty) only closes itself, and the result is that during the 10 seconds the notification stays up the first press of the red cross does nothing (reproduced on a real device + Mac).
    # Fix: system notifications carry no confirm action (the category hash is stored as 0); notifications without a confirm action do not handle PLUS (they take the original function's "forward to child widgets" exit 0x3d880c) and close by themselves at notificationSeconds. Notifications with a confirm action are unchanged
    cbz_x8 = lambda at, to: struct.pack('<I', 0xB4000008 | (((to - at) >> 2) & 0x7ffff) << 5).hex()
    str_x19_178 = lambda rt: struct.pack('<I', 0xF9000000 | (0x178 // 8) << 10 | 19 << 5 | rt).hex()
    cuts.append((0xab5c28, str_x19_178(8), str_x19_178(31), 'system notification confirm-action category str x8,[x19,#0x178] → str xzr (no confirm action)', 'host-only'))
    cuts.append((0x3d853c, cbz_x8(0x3d853c, 0x3d8560), cbz_x8(0x3d853c, 0x3d880c), 'notification panel: confirm-action category empty → PLUS not handled', 'host-only'))
    cuts.append((0x3d8544, cbz_x8(0x3d8544, 0x3d8560), cbz_x8(0x3d8544, 0x3d880c), 'notification panel: confirm-action hash empty → PLUS not handled', 'host-only'))
if RULE_RUN:
    # The skill tooltip appears beside the skill tree and does not cover the tree: the skill tree panel's per-frame update (0xc356b0) calls the tooltip entry 0xb16660 at 0xc35fd4, with position argument x1 = the icon's absolute coordinates (low 32 bits x, high 32 bits y + 3);
    # the controller version's tooltip expands against the icon's lower right, which on a touchscreen covers exactly the few skills around the finger. The bfxil x1,x8,#0,#32 at 0xc35fb0 is a no-op that copies the low half of x1 back into x1 (x8 = x1),
    # and is replaced with movk x1,#3000: the x coordinate is put off screen, and the tooltip entry's own clamp-back (0xb0d560, by TooltipsPanel's screenEdgePadding) snaps it to the right safe-area edge; the y coordinate is untouched
    cuts.append((0xc35fb0, struct.pack('<I', 0xB3407D01).hex(), struct.pack('<I', 0xF2800000 | 3000 << 5 | 1).hex(), 'skill tooltip x coordinate put off screen, the original clamp-back snaps it to the right edge (does not cover the skill tree)', 'host-only'))
if RULE_RUN and PRIVATE_GATES:
    # Only stamina eligibility / movement selection / walk-run preference are registered; direction, real magnitude, legal mode and the zero-axis branch are not changed.
    # The type0 guard for the two generic cost / selector points is in the small native trampoline below; non-player keeps the original behavior.
    run_words = [
        (0x2c620c, 0xb90e511f, 0x52800029, 'preference init: mov w9,1 (x8 still 2d20000)'),
        (0x2c6210, 0xd00152c8, 0xb90e5109, 'preference init: str w9,[x8,e50]; replaces the duplicate adrp of the same page, keeps the original x8'),
        (0x369a90, 0xd100c3ff, None, 'client RunOff entry tail-jumps to the original RunOn; keeps its player0 / legal mode / environment gates'),
        (0x369980, 0x340006a0, 0xd503201f, 'client RunOn: only cancels the zero-stamina rejection after the existing player0 gate'),
        (0x2b2c74, 0x340000a0, 0xd503201f, 'controller d29 eligibility: only cancels the stat10 zero limit; magnitude comparison and stick release unchanged'),
        (0x2b2dc0, 0x3900031f, 0xd503201f, 'controller d29: only cancels the stat10 zero clear; magnitude normalization unchanged'),
        (0x2b30fc, 0x0a090101, 0x52800021, 'movement encoding select bit fixed to Run once past the legal-action / zero-axis gates; magnitude unchanged'),
        (0x2b3104, 0x2a1f03e1, 0x52800021, 'Run encoding bit fixed also without a user walk/run preference; direction / magnitude unchanged'),
        (0x6dc2c4, 0x1a880502, 0x52800062, 'server42 legal move request fixed to Run3; the original type0 / death / lock / magnitude / direction gates stay'),
        (0x6dce90, 0x340000e0, 0xd503201f, 'server49: only cancels the zero-stamina rejection after the existing player0 / mode2 gates'),
        (0x6dcec0, 0xa9bf7bfd, None, 'server4A entry tail-jumps to the original 49; length / type0 / mode gates stay'),
    ]
    for off, old, new, why in run_words:
        if new is None:
            target = 0x369900 if off == 0x369a90 else 0x6dce50
            new = 0x14000000 | (((target - off) >> 2) & 0x3ffffff)
        cuts.append((off, struct.pack('<I', old).hex(), struct.pack('<I', new).hex(), 'touch-run-v4: ' + why))
cuts = [c if len(c) == 5 else (*c, 'all') for c in cuts]          # 5th item is the scope: all | host-only (host-only = not applied by the ground-truth emulator)
for off, ob, nb, why, scope in cuts:
    ob, nb = bytes.fromhex(ob), bytes.fromhex(nb)
    assert len(ob) == len(nb) and IMG[off:off + len(ob)] == ob, f'cut original bytes mismatch {off:#x}: {bytes(IMG[off:off + len(ob)]).hex()}'
    IMG[off:off + len(nb)] = nb
# Key page indices are fixed; the key page content is written by the loader as "actual key number × 8".
KEYS = {'K18': 508, 'KTLS': 509, 'KTLR': 510, 'KGATE': 511, 'KRES0': 506, 'KRES1': 507, 'KASPECT': 505, 'KASPECTUI': 504}   # KRES*: resolution parameter slots; KASPECT: picture aspect ratio cap (see PARAMS)
KEY_INDEX = {k: i for i, k in enumerate(('K18', 'KTLS', 'KTLR', 'KGATE', 'KRES0', 'KRES1', 'KASPECT', 'KASPECTUI'))}

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM); md.detail = True
patch = bytearray(); fix = []; gates = []; stats = {}
def stat(k): stats[k] = stats.get(k, 0) + 1
def here(): return PATCH_OFF + len(patch)
def emit(w, kind=None):
    if kind: fix.append((len(patch), kind))
    patch.extend(struct.pack('<I', w & 0xFFFFFFFF))

def emit_key_addr(reg, kind):
    fix.append((len(patch), kind)); emit(ADRP(reg, here(), KEY_PAGE_OFF)); emit(LDRX(reg, reg, KEY_INDEX[kind]))

def emit_slot_addr(base, key_reg, kind):
    emit_key_addr(key_reg, kind); emit(ADDR(base, base, key_reg))

# ---- Encoders ----
def B(frm, to):
    off = to - frm; assert -(1 << 27) <= off < (1 << 27) and off % 4 == 0
    return 0x14000000 | ((off >> 2) & 0x3FFFFFF)
def STP(t, t2, n, off): return 0xA9000000 | (((off // 8) & 0x7F) << 15) | (t2 << 10) | (n << 5) | t
def LDP(t, t2, n, off): return 0xA9400000 | (((off // 8) & 0x7F) << 15) | (t2 << 10) | (n << 5) | t
def STP_PRE(t, t2, n, off): return 0xA9800000 | (((off // 8) & 0x7F) << 15) | (t2 << 10) | (n << 5) | t
def LDP_POST(t, t2, n, off): return 0xA8C00000 | (((off // 8) & 0x7F) << 15) | (t2 << 10) | (n << 5) | t
def STUR(t, n, off): return 0xF8000000 | ((off & 0x1FF) << 12) | (n << 5) | t   # stur xt,[xn,#off] (off may be negative)
def LDUR(t, n, off): return 0xF8400000 | ((off & 0x1FF) << 12) | (n << 5) | t   # ldur xt,[xn,#off]
def LDRX(t, n, imm12=0): return 0xF9400000 | (imm12 << 10) | (n << 5) | t
def STRX(t, n, imm12=0): return 0xF9000000 | (imm12 << 10) | (n << 5) | t
def MRS_TPIDRRO(t): return 0xD53BD060 | t
def ADRP(dd, pc, target):
    imm = ((target & ~0xFFF) - (pc & ~0xFFF)) >> 12; assert -(1 << 20) <= imm < (1 << 20)
    return 0x90000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7FFFF) << 5) | dd
def ADDI(dd, n, imm12, sh=0): return 0x91000000 | (sh << 22) | (imm12 << 10) | (n << 5) | dd
def ADDR(dd, n, m): return 0x8B000000 | (m << 16) | (n << 5) | dd
def SUBI(dd, n, imm12, sh=0): return 0xD1000000 | (sh << 22) | (imm12 << 10) | (n << 5) | dd
def BR(n): return 0xD61F0000 | (n << 5)
def CMPR(n, m): return 0xEB00001F | (m << 16) | (n << 5)   # cmp xn, xm (subs xzr)
def BEQ(frm, to):
    off = to - frm; assert -(1 << 20) <= off < (1 << 20) and off % 4 == 0
    return 0x54000000 | (((off >> 2) & 0x7FFFF) << 5)
def BRK(imm): return 0xD4200000 | ((imm & 0xFFFF) << 5)
def BLR(n): return 0xD63F0000 | (n << 5)
NOP = 0xD503201F

def dis(w, addr):
    l = list(md.disasm(struct.pack('<I', w), addr)); assert len(l) == 1, hex(w)
    return l[0]
def regset(ins):
    r, w = ins.regs_access()
    return {ins.reg_name(x) for x in r}, {ins.reg_name(x) for x in w}
def num(name):
    m = re.fullmatch(r'[xw](\d+)', name or ''); return int(m.group(1)) if m else None
def has18(ins): return re.search(r'\b[xw]18\b', ins.op_str) is not None
def regs_in(ins):
    s = {int(n) for n in re.findall(r'\b[xw](\d+)\b', ins.op_str)}
    try:
        rd, wr = regset(ins); s |= {num(n) for n in rd | wr} - {None}
    except Exception: pass
    return s
def pick(avoid, n=2):
    out = [r for r in range(0, 16) if r not in avoid and r != 18][:n]; assert len(out) == n; return out

def subst(ins, S):
    """x18/w18 → xS/wS: only the 4 register field positions are changed, verified against the disassembly text."""
    w = struct.unpack('<I', ins.bytes)[0]
    want = re.sub(r'\b([xw])18\b', lambda m: f'{m.group(1)}{S}', ins.op_str)
    pos = [p for p in (0, 5, 10, 16) if (w >> p) & 31 == 18]
    for k in range(len(pos), 0, -1):
        for c in combinations(pos, k):
            nw = w
            for p in c: nw = (nw & ~(31 << p)) | (S << p)
            try: dd = dis(nw, ins.address)
            except AssertionError: continue
            if dd.mnemonic == ins.mnemonic and dd.op_str == want: return nw
    raise RuntimeError(f'subst fail {ins.address:x} {ins.mnemonic} {ins.op_str}')

# ---- Rewrite blocks of each kind ----
def sp_delta(ins):
    """The amount an instruction writes back to sp (pre-index [sp, #i]! / post-index [sp], #i); returns 0 if sp is not written back."""
    m = re.search(r'\[sp, #(-?(?:0x)?[0-9a-f]+)\]!', ins.op_str)
    if m: return int(m.group(1), 0)
    m = re.search(r'\[sp\], #(-?(?:0x)?[0-9a-f]+)$', ins.op_str)
    if m: return int(m.group(1), 0)
    assert not re.match(r'(sp|wsp),', ins.op_str), f'writes sp: {ins.address:x} {ins.op_str}'
    return 0

def site_plain(ins):
    S, T = pick(regs_in(ins))
    dlt = sp_delta(ins)
    save = -16 if dlt == 0 else -112          # Instructions that modify sp write below sp, so the scratch save is placed deep in the reserved area
    assert dlt == 0 or dlt >= -96, f'sp delta {dlt} at {ins.address:x}'
    start = here()
    emit(STP(S, T, 31, save)); emit(MRS_TPIDRRO(T)); emit_slot_addr(T, S, 'K18'); emit(LDRX(S, T))
    emit(subst(ins, S))
    emit(STRX(S, T))                 # Always write back: capstone can miss reporting a write (the adds w18 instance)
    emit(LDP(S, T, 31, save - dlt)); emit(B(here(), ins.address + 4))
    return start

def site_sp(ins):
    """Destination is sp and a source is x18 (Engage's alloca: mov x18, sp; sub x18, x18, x0; mov sp, x18). site_plain saves its scratch relative to the old sp and would restore it relative to the new one:
    copy the old sp into T first, and after the instruction restore S / T relative to T (without writeback, ldp may use the base register as a destination). x18 is not written, so the slot is not written back"""
    S, T = pick(regs_in(ins))
    start = here()
    emit(STP(S, T, 31, -16)); emit(MRS_TPIDRRO(T)); emit_slot_addr(T, S, 'K18'); emit(LDRX(S, T))
    emit(ADDI(T, 31, 0))             # mov T, sp (in add immediate, 31 is sp)
    emit(subst(ins, S))
    emit(LDP(S, T, T, -16)); emit(B(here(), ins.address + 4))
    return start

def site_cond(ins):
    w = struct.unpack('<I', ins.bytes)[0]
    S, T = pick(regs_in(ins))
    tgt = ins.operands[-1].imm
    start = here()
    emit(STP(S, T, 31, -16)); emit(MRS_TPIDRRO(T)); emit_slot_addr(T, S, 'K18'); emit(LDRX(S, T))
    m = ins.mnemonic
    taken = here() + 4 * 3
    off = (taken - here()) >> 2
    nw = ((w & 0xFF000000) | ((off & 0x7FFFF) << 5) | S) if m in ('cbz', 'cbnz') else ((w & 0xFFF80000) | ((off & 0x3FFF) << 5) | S)
    pc = here(); emit(nw)
    dd = dis(nw, pc); assert dd.mnemonic == m and dd.operands[-1].imm == taken
    emit(LDP(S, T, 31, -16)); emit(B(here(), ins.address + 4))
    assert here() == taken
    emit(LDP(S, T, 31, -16)); emit(B(here(), tgt))
    return start

def site_pcrel(ins):
    tgt = ins.operands[1].imm
    S, T = pick(set())
    start = here()
    emit(STP(S, T, 31, -16)); emit(MRS_TPIDRRO(T)); emit_slot_addr(T, S, 'K18')   # S first serves as a temporary for the key page offset; the next instruction then loads the target value
    pc = here(); emit(ADRP(S, pc, tgt))
    if ins.mnemonic == 'adr': emit(ADDI(S, S, tgt & 0xFFF))
    emit(STRX(S, T))
    emit(LDP(S, T, 31, -16)); emit(B(here(), ins.address + 4))
    return start

def site_br(ins, base, count):
    """Jump table br x18: target = base + 4i. Stash x16 in the red zone → equally spaced landing pads → restore x16 → original target."""
    start = here()
    emit(STUR(16, 31, -16)); emit(STUR(17, 31, -24))   # x16 / x17 are temporary registers that can stay live within a function; save them to the red zone before borrowing
    emit(MRS_TPIDRRO(16)); emit_slot_addr(16, 17, 'K18'); emit(LDRX(16, 16)); emit(LDUR(17, 31, -24))
    padbase = start + 4 * 24
    delta = padbase - base
    op = ADDI if delta >= 0 else SUBI; dl = abs(delta)
    ops = []; hi, lo = dl >> 12, dl & 0xFFF
    while hi: h = min(hi, 0xFFF); ops.append(op(16, 16, h, 1)); hi -= h
    if lo: ops.append(op(16, 16, lo, 0))
    assert len(ops) <= 12
    for o in ops: emit(o)
    emit(BR(16))
    while here() < padbase: emit(NOP)
    tails = padbase + 4 * count
    for i in range(count): emit(B(here(), tails + 8 * i))
    for i in range(count):
        emit(0xF85F0000 | (31 << 5) | 16)      # ldur x16,[sp,#-16]
        emit(B(here(), base + 4 * i))
    return start

def site_br_tab(ins, targets):
    """Offset-table br x18 (ldrsw x18,[xB,x18,lsl #2]; add x18,x18,xB): target = table base + signed entry; the table is constant, so all targets are read at rewrite time.
    x16 = guest x18, compared with each target in turn (adrp + add put the target address in x17); on a match restore x16 / x17 and jump to the original target; no match → brk (the original bounds check already stops out-of-range indices)"""
    start = here()
    emit(STUR(16, 31, -16)); emit(STUR(17, 31, -24))   # as in site_br: save x16 / x17 to the red zone before borrowing
    emit(MRS_TPIDRRO(16)); emit_slot_addr(16, 17, 'K18'); emit(LDRX(16, 16))
    uniq = sorted(set(targets))
    pads = here() + 4 * (4 * len(uniq) + 1)
    for k, t in enumerate(uniq):
        emit(ADRP(17, here(), t)); emit(ADDI(17, 17, t & 0xFFF)); emit(CMPR(16, 17)); emit(BEQ(here(), pads + 12 * k))
    emit(BRK(0x18))
    for t in uniq:
        emit(LDUR(16, 31, -16)); emit(LDUR(17, 31, -24)); emit(B(here(), t))
    return start

def site_blr(ins):
    """blr x18 (Engage main+0x9ff324): x16 = guest x18, x30 = the instruction after the original blr, br x16. At a call site x16 / x17 are intra-procedure-call temporaries under the calling convention, so they need no saving;
    the return address is the original one, so the callee returns straight there (IL2CPP's C++ exceptions look up unwind tables by return address and must not stop in the patch area)"""
    start = here()
    emit(MRS_TPIDRRO(16)); emit_slot_addr(16, 17, 'K18'); emit(LDRX(16, 16))
    ret = ins.address + 4
    emit(ADRP(30, here(), ret)); emit(ADDI(30, 30, ret & 0xFFF)); emit(BR(16))
    return start

def site_br_call(ins):
    """br x18 as an indirect tail call (tail_call): x16 = guest x18, br x16. As at site_blr, x16 / x17 are intra-procedure-call temporaries at a call, and x30 keeps the caller's return address"""
    start = here()
    emit(MRS_TPIDRRO(16)); emit_slot_addr(16, 17, 'K18'); emit(LDRX(16, 16)); emit(BR(16))
    return start

def site_sysreg_read(ins, kind):
    """mrs xN, tpidr_el0 / tpidrro_el0 → xN = thread slot value."""
    N = ins.bytes[0] & 31
    tmp = 16 if N != 16 else 17
    start = here()
    emit(STUR(tmp, 31, -16)); emit(MRS_TPIDRRO(N)); emit_slot_addr(N, tmp, kind); emit(LDRX(N, N)); emit(LDUR(tmp, 31, -16))   # tmp is saved by borrowing the red zone
    emit(B(here(), ins.address + 4))
    return start

def site_tpidr_write(ins):
    N = struct.unpack('<I', ins.bytes)[0] & 31
    (T,) = pick({N}, 1)
    start = here()
    emit(0xF81F0000 | (31 << 5) | T)           # stur xT,[sp,#-16]
    tmp = next(x for x in (16, 17) if x not in (N, T))
    emit(STUR(tmp, 31, -24)); emit(MRS_TPIDRRO(T)); emit_slot_addr(T, tmp, 'KTLS'); emit(STRX(N, T)); emit(LDUR(tmp, 31, -24))
    emit(0xF85F0000 | (31 << 5) | T)           # ldur xT,[sp,#-16]
    emit(B(here(), ins.address + 4))
    return start

def emit_gate_call():
    """Common section of a gate block (right after stp x29,x30,[sp,#-16]! and before blr x30): x30 = the gate address in thread slot KGATE.
        Fetching the slot through the key page needs a second register to be borrowed; x29 is borrowed and then immediately restored from the stack: the x29 saved by _dm_gate must be the guest's original value --
        the host identifies the caller by [x29+8] (skill binding observation gate 6, private aiming gate svc86), and the crash backtrace also walks the x29 chain
        (since r24 plan C it was borrowed and not returned, the x29 the host got was the slot offset from the key page, and skill icons fell back to placeholder text)."""
    emit(MRS_TPIDRRO(30)); emit_slot_addr(30, 29, 'KGATE'); emit(LDRX(30, 30)); emit(LDRX(29, 31))

def site_gate(ins, kind, arg):
    """svc / mrs cntpct_el0 → host gate. The gate address is taken from thread slot KGATE; the gate looks up gates.tsv by return point (the address of this block's ldp)."""
    start = here()
    emit(STP_PRE(29, 30, 31, -16))
    emit_gate_call()
    emit(BLR(30))
    ret = here()
    emit(LDP_POST(29, 30, 31, 16))
    emit(B(here(), ins.address + 4))
    gates.append((ret, kind, arg, ins.address))
    return start

def site_obs(off, oid, word):
    """Observation gate: original entry instruction → enter the host gate (arg = observation number) → restore x29/x30 → execute the original instruction → jump back to off+4.
        The first half of the gate block is word-for-word isomorphic with site_gate; the host only reads registers and does not modify them (the x0–x8 written back by dm_gate are the original values)."""
    ins = dis(word, off)
    assert ins.mnemonic not in ('adr', 'adrp', 'b', 'bl', 'br', 'blr', 'ret', 'cbz', 'cbnz', 'tbz', 'tbnz') and not ins.mnemonic.startswith('b.') \
        and not (ins.mnemonic.startswith('ldr') and '[' not in ins.op_str) and not has18(ins), f'observation gate original instruction cannot be relocated {off:#x} {ins.mnemonic} {ins.op_str}'
    start = here()
    emit(STP_PRE(29, 30, 31, -16))
    emit_gate_call()
    emit(BLR(30))
    ret = here()
    emit(LDP_POST(29, 30, 31, 16))
    emit(word)
    emit(B(here(), off + 4))
    gates.append((ret, 'obs', oid, off))
    return start

# ---- Exclusive windows ----
EXCL_LD = ('ldxr', 'ldaxr', 'ldxp', 'ldaxp', 'ldxrb', 'ldaxrb', 'ldxrh', 'ldaxrh')
EXCL_ST = ('stxr', 'stlxr', 'stxp', 'stlxp', 'stxrb', 'stlxrb', 'stxrh', 'stlxrh')
def find_windows(insl):
    out = []
    for i, ins in enumerate(insl):
        if ins.mnemonic not in EXCL_LD: continue
        j = i
        while j < len(insl) and insl[j].mnemonic not in EXCL_ST: j += 1
        if j >= len(insl) or j - i >= 16: continue
        # Another exclusive load before the store: this one has no store of its own (a retry block, see retry_block); spanning both would merge two sequences
        # (Tears of the Kingdom main+0x5a4674: ldxr w18; cmp; b.eq <stxr of 0x5a427c>; ...; 0x5a469c: ldxr w13; and; stxr; cbnz, a loop other code branches to)
        if any(x.mnemonic in EXCL_LD for x in insl[i + 1:j]): continue
        if j + 1 < len(insl) and insl[j + 1].mnemonic in ('cbz', 'cbnz'): j += 1
        seg = insl[i:j + 1]
        if any(has18(x) for x in seg): out.append(seg)
    return out

def site_window(seg):
    used = set()
    for x in seg: used |= regs_in(x)
    S, T = pick(used)
    lo, hi = seg[0].address, seg[-1].address + 4
    start = here()
    emit(STP(S, T, 31, -16)); emit(MRS_TPIDRRO(T)); emit_slot_addr(T, S, 'K18'); emit(LDRX(S, T))
    copy0 = here(); n = len(seg)
    # Exit stubs: the first stub right after the window must be the fall-through one (after the last window instruction, hi); targets of branches leaving the window come after it.
    # Previously the fall-through stub came last: as soon as a window contains a conditional branch out (e.g. ldxr; cmp; b.ne out; stxr; cbnz), a successful stxr fell into the
    # first branch-out stub, i.e. took the "compare not equal" path (SMBW main 0x81c40: the enqueue retried forever, the tail index filled up without storing a single task, and the job system hung). D2R's windows had no branch out, so it never hit this.
    exits = copy0 + 4 * n + 16
    ex_targets = []; words = []
    for k, x in enumerate(seg):
        w = struct.unpack('<I', x.bytes)[0]
        if has18(x): w = subst(x, S)
        m = x.mnemonic
        if m in ('cbz', 'cbnz', 'tbz', 'tbnz') or m.startswith('b.'):
            tgt = x.operands[-1].imm
            if lo <= tgt < hi: newt = copy0 + (tgt - lo)
            else: ex_targets.append(tgt); newt = exits + 16 * (len(ex_targets) - 1)
            pc = copy0 + 4 * k; off = (newt - pc) >> 2
            if m in ('tbz', 'tbnz'): w = (w & 0xFFF8001F) | ((off & 0x3FFF) << 5)
            else: w = (w & 0xFF00001F) | ((off & 0x7FFFF) << 5)
            dd = dis(w, pc); assert dd.operands[-1].imm == newt and dd.mnemonic == m
        else:
            assert m not in ('adr', 'adrp', 'b', 'bl', 'br', 'blr', 'ret') and not (m == 'ldr' and '[' not in x.op_str), hex(x.address)
        words.append(w)
    for w in words: emit(w)
    for t in [hi] + ex_targets:   # fall-through first
        emit(STRX(S, T)); emit(LDP(S, T, 31, -16)); emit(B(here(), t)); emit(NOP)
    return start, lo, hi

def retry_block(insl, k, wseg):
    """The branch insl[k] lands in the middle of window wseg. Accepted only when it ends an out-of-line retry block that re-enters the window at its store-exclusive:
    an exclusive load, then instructions that do not branch, then this branch. Tears of the Kingdom main+0x18598: ldxr w17,[x10]; cmp w15,w17; b.eq 0x181fc,
    where 0x181fc is the stxr w17,w18,[x10] of the window 0x181ec..0x18200, whose failed stxr branches back to 0x18598 (same shape at 0x185e8 → 0x18244).
    Returns (the retry block, the window from that store on), or None"""
    t = insl[k].operands[-1].imm
    tail = [y for y in wseg if y.address >= t]
    if not tail or tail[0].mnemonic not in EXCL_ST: return None
    for p in range(k - 1, max(-1, k - 8), -1):
        q = insl[p]
        if q.mnemonic in EXCL_LD: return insl[p:k + 1], tail
        if q.mnemonic in ('b', 'bl', 'br', 'blr', 'ret', 'cbz', 'cbnz', 'tbz', 'tbnz') or q.mnemonic.startswith('b.') or q.mnemonic in EXCL_ST: return None
    return None

def site_retry_window(parts):
    """A retry block (see retry_block) gets a patch copy of its own: it cannot jump into the window's copy, because the x18 stand-in would have to be loaded
    between its exclusive load and the store. parts = [(retry block, its fall-through), (window from the store on, the window's fall-through)] are copied one
    after the other under one prologue, each followed by its fall-through stub; branches to any copied instruction (between the parts, and the failed store's
    branch back to the retry block's head) stay inside the copy, every other target leaves through an exit stub as in site_window"""
    used = set()
    for seg, _ in parts:
        for x in seg: used |= regs_in(x)
    S, T = pick(used)
    start = here()
    emit(STP(S, T, 31, -16)); emit(MRS_TPIDRRO(T)); emit_slot_addr(T, S, 'K18'); emit(LDRX(S, T))
    pos, at = {}, here()
    for seg, _ in parts:
        for x in seg: pos[x.address] = at; at += 4
        at += 16
    exits, ex_targets = at, []
    for seg, ft in parts:
        for x in seg:
            w = struct.unpack('<I', x.bytes)[0]
            if has18(x): w = subst(x, S)
            m, pc = x.mnemonic, here()
            if m in ('cbz', 'cbnz', 'tbz', 'tbnz') or m.startswith('b.'):
                tgt = x.operands[-1].imm
                if tgt not in pos and tgt not in ex_targets: ex_targets.append(tgt)
                newt = pos[tgt] if tgt in pos else exits + 16 * ex_targets.index(tgt)
                off = (newt - pc) >> 2
                if m in ('tbz', 'tbnz'): w = (w & 0xFFF8001F) | ((off & 0x3FFF) << 5)
                else: w = (w & 0xFF00001F) | ((off & 0x7FFFF) << 5)
                dd = dis(w, pc); assert dd.operands[-1].imm == newt and dd.mnemonic == m
            else:
                assert m not in ('adr', 'adrp', 'b', 'bl', 'br', 'blr', 'ret') and not (m == 'ldr' and '[' not in x.op_str), hex(x.address)
            emit(w)
        emit(STRX(S, T)); emit(LDP(S, T, 31, -16)); emit(B(here(), ft)); emit(NOP)
    for t in ex_targets:
        emit(STRX(S, T)); emit(LDP(S, T, 31, -16)); emit(B(here(), t)); emit(NOP)
    return start

# ---- Function boundaries (eh_frame_hdr) ----
m0 = struct.unpack_from('<I', IMG, 4)[0]
assert IMG[m0:m0 + 4] == b'MOD0'
ehs = m0 + struct.unpack_from('<i', IMG, m0 + 16)[0]
def rd(o, enc):
    fmt, app = enc & 0xF, enc & 0x70
    v, sz = {0x3: (struct.unpack_from('<I', IMG, o)[0], 4), 0xB: (struct.unpack_from('<i', IMG, o)[0], 4),
             0x4: (struct.unpack_from('<Q', IMG, o)[0], 8)}[fmt]
    if app == 0x10: v += o
    if app == 0x30: v += ehs
    return v, sz
_, penc, cenc, tenc = IMG[ehs:ehs + 4]
o = ehs + 4
_, s = rd(o, penc); o += s
nfde, s = rd(o, cenc); o += s
starts = set()
for _ in range(nfde):
    a, s = rd(o, tenc); o += s
    _, s = rd(o, tenc); o += s
    starts.add(a)
starts = sorted(x for x in starts if x < TEXT_END)

# ---- Linear scan to find all rewrite points (not relying on register read/write reports) ----
kinds = {}
for o in range(0, TEXT_END, 4):
    w = struct.unpack_from('<I', IMG, o)[0]
    if w & 0xFFE0001F == 0xD4000001: kinds[o] = ('svc', (w >> 5) & 0xFFFF); continue
    if w & 0xFFFFFFE0 == 0xD53BD040: kinds[o] = ('tpidr_r', None); continue
    if w & 0xFFFFFFE0 == 0xD51BD040: kinds[o] = ('tpidr_w', None); continue
    if w & 0xFFFFFFE0 == 0xD53BD060: kinds[o] = ('tpidrro_r', None); continue
    if w & 0xFFFFFFE0 == 0xD53BE020: kinds[o] = ('cntpct', w & 31); continue
    if w & 0xFFFFFFE0 == 0xD53BE040: kinds[o] = ('cntvct', w & 31); continue
    # mrs xN, ctr_el0 (cache type): the Apple kernel does not expose it to user mode (SIGILL); SDK 16's nn::os::FlushDataCache reads it for the cache line size
    if w & 0xFFFFFFE0 == 0xD53B0020: kinds[o] = ('ctr', w & 31); continue
    for ins in md.disasm(IMG[o:o + 4], o):
        if has18(ins): kinds[o] = ('x18', None)

# Take the instruction table per function, find the windows and jump tables
import bisect
def func_of(a):
    i = bisect.bisect_right(starts, a) - 1
    return (starts[i], starts[i + 1] if i + 1 < len(starts) else TEXT_END) if i >= 0 else (a, a + 4)
done = set(); windows = []; jumps = {}; tabjumps = {}; tailcalls = set(); retries = []
def jump_offsets(insl, j):
    """The br x18 is preceded by the offset-table form (Engage main+0x12eec94): cmp w18,#N; b.hi; ldrsw x18,[xB,x18,lsl #2]; add x18,x18,xB.
    The index may be another register, and the bounds check may be on a register copied into it: Link's Awakening's GLSLC (subsdk0+0x1be6e8) has
    sub w0,w18,#0xd1; cmp w0,#0x31; b.hi; ldrsw x18,[x17,x0,lsl #2], its movie module (subsdk1+0xae9a4) cmp w21,#7; b.hi; ...; mov w18,w21; ldrsw x18,[x4,x18,lsl #2].
    The entry may also be loaded into another register and only the add writes x18: Cuphead (Unity 2017.4, main+0x1bb872c) has cmp w17,#7; ldrsw x17,[x15,x17,lsl #2]; add x18,x17,x15
    (found by armyja, GitHub pull request #1).
    For the table base xB, search back for the nearest writer: it must be add xB,xB,#lo, and the writer before it must be adrp xB. Returns all targets, or None if not recognized"""
    ctx = insl[max(0, j - 16):j]
    add = next((p for p in reversed(ctx) if p.mnemonic == 'add' and re.fullmatch(r'x18, x\d+, x\d+', p.op_str)), None)
    if not add: return None
    _, t, rb = add.op_str.split(', ')   # t = the loaded entry, rb = the table base
    ld = next((p for p in reversed(ctx) if p.mnemonic == 'ldrsw' and re.fullmatch(rf'{t}, \[{rb}, x(\d+), lsl #2\]', p.op_str)), None)
    if not ld: return None
    # GLSLC subsdk0+0x2f403c checks a masked copy instead: and w16,w18,#0x3f; cmp w16,#0xe; b.hi; ...; and x18,x18,#0x3f; ldrsw x18,[x15,x18,lsl #2]
    idx = {'w' + re.fullmatch(rf'{t}, \[{rb}, x(\d+), lsl #2\]', ld.op_str).group(1)}
    masked = None   # (source, mask, position) when the index is "source & mask"
    k0 = ctx.index(ld); cmp = None
    def wname(r): return 'w' + r[1:]
    for i in range(k0 - 1, -1, -1):   # walk back from the load: follow register copies into the index, stop at the bounds check
        p = ctx[i]
        m = re.fullmatch(r'(w\d+), (w\d+)', p.op_str) if p.mnemonic == 'mov' else None
        if m and m.group(1) in idx: idx.add(m.group(2)); continue
        m = re.fullmatch(r'([wx]\d+), ([wx]\d+), #(0x[0-9a-f]+|\d+)', p.op_str) if p.mnemonic == 'and' else None
        if m and wname(m.group(1)) in idx and masked is None: masked = (wname(m.group(2)), int(m.group(3), 0), i); continue
        m = re.fullmatch(r'(w\d+), #(0x[0-9a-f]+|\d+)', p.op_str) if p.mnemonic == 'cmp' else None
        if not m: continue
        if m.group(1) in idx: cmp = p; break
        if masked:   # the checked register must be "the same source & the same mask", with the source unchanged up to the index's and
            for q in range(i - 1, -1, -1):
                w = [wname(ctx[q].reg_name(r)) for r in ctx[q].regs_access()[1]]
                if m.group(1) not in w: continue
                mm = re.fullmatch(r'([wx]\d+), ([wx]\d+), #(0x[0-9a-f]+|\d+)', ctx[q].op_str) if ctx[q].mnemonic == 'and' else None
                if mm and wname(mm.group(2)) == masked[0] and int(mm.group(3), 0) == masked[1] and \
                   not any(masked[0] in [wname(ctx[z].reg_name(r)) for r in ctx[z].regs_access()[1]] for z in range(q + 1, masked[2])):
                    cmp = p
                break
            if cmp: break
    if not cmp: return None
    n = int(cmp.op_str.split('#')[1], 0) + 1
    k = insl.index(ld); lo = page = None
    for p in reversed(insl[max(0, k - 256):k]):   # the writer chain of the table base
        _, w = p.regs_access()
        if not any(p.reg_name(r) == rb for r in w): continue
        if lo is None and p.mnemonic == 'add' and re.fullmatch(rf'{rb}, {rb}, #(0x[0-9a-f]+|\d+)', p.op_str): lo = int(p.op_str.split('#')[1], 0); continue
        if lo is not None and p.mnemonic == 'adrp' and p.op_str.startswith(rb + ','): page = p.operands[1].imm
        break
    if page is None: return None
    tb = page + lo
    return [tb + struct.unpack_from('<i', IMG, tb + 4 * i)[0] for i in range(n)]
def table_base(insl, k, rb):
    """Address the table-base register rb holds at insl[k]: its writer chain before k must be add rb,rb,#lo after adrp rb (as in jump_offsets); None otherwise"""
    lo = None
    for p in reversed(insl[max(0, k - 256):k]):
        _, w = p.regs_access()
        if not any(p.reg_name(r) == rb for r in w): continue
        if lo is None and p.mnemonic == 'add' and re.fullmatch(rf'{rb}, {rb}, #(0x[0-9a-f]+|\d+)', p.op_str): lo = int(p.op_str.split('#')[1], 0); continue
        if lo is not None and p.mnemonic == 'adrp' and p.op_str.startswith(rb + ','): return p.operands[1].imm + lo
        return None
    return None
def jump_adr_offsets(insl, j):
    """Entries relative to an adr rather than to the table (Tears of the Kingdom main+0x393bb0): cmp w0,#5; b.hi; ...; adr x18,#L; ldrsw x1,[x17,x0,lsl #2];
    add x18,x18,x1; br x18 → target = L + entry, with the table base x17 from adrp + add. Tried only where jump_offsets finds nothing. Returns all targets, or None if not recognized"""
    ctx = insl[max(0, j - 16):j]
    add = next((p for p in reversed(ctx) if p.mnemonic == 'add' and re.fullmatch(r'x18, x\d+, x\d+', p.op_str)), None)
    if not add: return None
    ka = ctx.index(add); ops = add.op_str.split(', ')[1:]
    for e, a in (ops, ops[::-1]):   # e = the loaded entry, a = the adr base
        ld = next((p for p in reversed(ctx[:ka]) if p.mnemonic == 'ldrsw' and re.fullmatch(rf'{e}, \[x\d+, x\d+, lsl #2\]', p.op_str)), None)
        wa = next((p for p in reversed(ctx[:ka]) if any(p.reg_name(r) == a for r in p.regs_access()[1])), None)   # the nearest writer of a
        if not ld or not wa or wa.mnemonic != 'adr': continue
        tb_reg, ix = re.fullmatch(rf'{e}, \[(x\d+), x(\d+), lsl #2\]', ld.op_str).groups()
        idx, cmp = {'w' + ix}, None   # the index and the registers copied into it (main+0x596d30: cmp w15,#8; b.hi; mov w16,w15; ...; ldrsw x0,[x17,x16,lsl #2])
        for p in reversed(ctx[:ctx.index(ld)]):   # walk back from the load to the bounds check
            m = re.fullmatch(r'(w\d+), (w\d+)', p.op_str) if p.mnemonic == 'mov' else None
            if m and m.group(1) in idx: idx.add(m.group(2)); continue
            m = re.fullmatch(r'(w\d+), #(0x[0-9a-f]+|\d+)', p.op_str) if p.mnemonic == 'cmp' else None
            if m and m.group(1) in idx: cmp = p; break
            if any('w' + p.reg_name(r)[1:] in idx for r in p.regs_access()[1]): return None   # the index changes after the check
        if cmp is None: return None
        n, at = int(cmp.op_str.split('#')[1], 0) + 1, wa.operands[1].imm
        def targets(tb): return [at + struct.unpack_from('<i', IMG, tb + 4 * i)[0] for i in range(n)] if 0 <= tb and tb + 4 * n <= len(IMG) else None
        tb = table_base(insl, insl.index(ld), tb_reg)
        if tb is not None: return targets(tb)
        # The base register was loaded further away (main+0x5f2a9c: hoisted out of the dispatch block): take every adrp + add pair in the function that builds it,
        # and accept the table only if exactly one candidate makes every target an instruction of this function
        fa, fb = insl[0].address, insl[-1].address + 4
        cands = set()
        for k, p in enumerate(insl):
            if p.mnemonic != 'adrp' or not p.op_str.startswith(tb_reg + ','): continue
            q = next((x for x in insl[k + 1:k + 9] if any(x.reg_name(r) == tb_reg for r in x.regs_access()[1])), None)
            m = re.fullmatch(rf'{tb_reg}, {tb_reg}, #(0x[0-9a-f]+|\d+)', q.op_str) if q is not None and q.mnemonic == 'add' else None
            if m: cands.add(p.operands[1].imm + int(m.group(1), 0))
        ok = [tb for tb in sorted(cands) if (t := targets(tb)) and all(fa <= x < fb and x % 4 == 0 for x in t)]
        return targets(ok[0]) if len(ok) == 1 else None
    return None
def tail_call(insl, j):
    """The br x18 is an indirect tail call, not a jump table: the last write of x18 before it is a plain pointer load and the br ends the function. Ace Attorney Investigations Collection
    (Unity 2022.3 IL2CPP) main+0x1d271bc: ldr x18,[x0,#0x18]; ...; ldr x16,[sp]; ...; br x18, a thunk that moves stack arguments and jumps to the method pointer at +0x18"""
    if j + 1 != len(insl): return False
    for p in reversed(insl[:j]):
        if 'x18' not in [p.reg_name(r) for r in p.regs_access()[1]]: continue
        return p.mnemonic == 'ldr' and bool(re.fullmatch(r'x18, \[(x\d+|sp)(, #(0x[0-9a-f]+|\d+))?\]', p.op_str))
    return False
def disasm_fn(fa, fb):
    """A function's instructions. Capstone stops at the first word it cannot decode, so go on after it: Monster Hunter Rise main+0x6b34540 is a trap word (0xe7ffdefe)
    in the middle of a function, and the br x18 jump table after it (main+0x6b346d0) was never seen"""
    out, a = [], fa
    while a < fb:
        l = list(md.disasm(bytes(IMG[a:fb]), a))
        out += l; a = (l[-1].address + 4 if l else a) + 4
    return out
funcs = sorted({func_of(a) for a, (k, _) in kinds.items() if k == 'x18'})
for fa, fb in funcs:
    insl = disasm_fn(fa, fb)
    ws = find_windows(insl)
    for wseg in ws:
        windows.append(wseg); done |= {x.address for x in wseg}
    for j, ins in enumerate(insl):
        if ins.mnemonic == 'br' and ins.op_str == 'x18':
            base = width = None
            # 16 instructions back, as for the offset-table form: Hades main+0x1135d0 has six vector moves between the add and the br, which put its adr x18 nine back
            ctx = insl[max(0, j - 16):j]
            for p in reversed(ctx):
                if p.mnemonic == 'adr' and p.op_str.startswith('x18,'): base = p.operands[1].imm; break
            for p in reversed(ctx):
                if p.mnemonic == 'add' and p.op_str.startswith('x18, x18,') and 'lsl #2' in p.op_str:
                    # capstone names x30 'lr' (and x29 'fp'): Age of Calamity main+0x1382160 indexes with add x18,x18,x30,lsl #2 after ldrb w30,[x14,x12]
                    rn = p.reg_name(p.operands[2].reg); idx = {'lr': 30, 'fp': 29}.get(rn, num(rn))
                    for q in reversed(ctx):
                        if q.mnemonic in ('ldrb', 'ldrsb') and num(q.reg_name(q.operands[0].reg)) == idx: width = 256
                        if q.mnemonic in ('ldrh', 'ldrsh') and num(q.reg_name(q.operands[0].reg)) == idx: width = 65536
                        if width: break
                    break
            if not (base and width):
                tgt = jump_offsets(insl, j) or jump_adr_offsets(insl, j)
                if not tgt and tail_call(insl, j): tailcalls.add(ins.address); continue
                assert tgt, f'jump table {ins.address:x}'
                tabjumps[ins.address] = tgt; continue
            jumps[ins.address] = (base, width)
    # No jump may land in the middle of a window, except a retry block's branch onto the window's store-exclusive (retry_block), which gets a copy of its own
    inwin = {x.address for wseg in ws for x in wseg}; heads = {wseg[0].address for wseg in ws}
    rmid = set()
    for k, x in enumerate(insl):
        if x.mnemonic in ('b', 'bl', 'cbz', 'cbnz', 'tbz', 'tbnz') or x.mnemonic.startswith('b.'):
            t = x.operands[-1].imm
            if t in inwin and t not in heads:
                wseg = next(w for w in ws if any(y.address == t for y in w))
                rb = retry_block(insl, k, wseg) if x.mnemonic not in ('b', 'bl') else None
                assert rb, f'branch into window {x.address:x}'
                assert not any(y.address in done for y in rb[0]), f'retry block overlaps a window {rb[0][0].address:x}'
                retries.append([(rb[0], x.address + 4), (rb[1], wseg[-1].address + 4)])
                done |= {y.address for y in rb[0]}; rmid |= {y.address for y in rb[0][1:]}
    for x in insl:
        if x.mnemonic in ('b', 'bl', 'cbz', 'cbnz', 'tbz', 'tbnz') or x.mnemonic.startswith('b.'):
            assert x.operands[-1].imm not in rmid, f'branch into retry block {x.address:x}'
    for a_, tgt in tabjumps.items():
        if fa <= a_ < fb: assert not any(t in inwin and t not in heads for t in tgt), f'jump table target into window {a_:x}'

def put_branch(at, to): struct.pack_into('<I', IMG, at, B(at, to))
for wseg in windows:
    st, lo, hi = site_window(wseg); stat('window'); put_branch(lo, st)
for parts in retries:
    st = site_retry_window(parts); stat('retry_window'); put_branch(parts[0][0][0].address, st)
for a in sorted(kinds):
    if a in done: continue
    k, arg = kinds[a]
    ins = dis(struct.unpack_from('<I', IMG, a)[0], a)
    if k == 'x18':
        m = ins.mnemonic
        if m == 'br' and a in tailcalls: st = site_br_call(ins); stat('br_call')
        elif m == 'br': st = site_br_tab(ins, tabjumps[a]) if a in tabjumps else site_br(ins, *jumps[a]); stat('br')
        elif m in ('cbz', 'cbnz', 'tbz', 'tbnz'): st = site_cond(ins); stat('cond')
        elif m in ('adr', 'adrp'): st = site_pcrel(ins); stat('pcrel')
        elif m == 'blr': st = site_blr(ins); stat('blr')
        elif re.match(r'(sp|wsp),', ins.op_str): st = site_sp(ins); stat('sp')
        elif m in ('ret', 'b', 'bl') or (m == 'ldr' and '[' not in ins.op_str): raise RuntimeError(f'{a:x} {m} {ins.op_str}')
        else: st = site_plain(ins); stat('plain')
    elif k == 'tpidr_r': st = site_sysreg_read(ins, 'KTLS'); stat(k)
    elif k == 'tpidrro_r': st = site_sysreg_read(ins, 'KTLR'); stat(k)
    elif k == 'tpidr_w': st = site_tpidr_write(ins); stat(k)
    elif k == 'svc': st = site_gate(ins, 'svc', arg); stat(k)
    elif k in ('cntpct', 'cntvct'): st = site_gate(ins, k, arg); stat(k)
    elif k == 'ctr':   # replaced in place by a constant: DminLine = 4 (64-byte lines); movz xN, #4, lsl #16
        assert arg != 18, f'{a:x} mrs x18, ctr_el0'
        struct.pack_into('<I', IMG, a, 0xD2A00080 | arg); stat(k); continue
    put_branch(a, st)

# Private visual branch; not OBS, 0x85 is a read-only query. Only this experimental build explicitly opts in; the original Qty/children and Update are unchanged.
if RULE_RUN and PRIVATE_GATES:
    off, word = 0x3e443c, 0x3969c268
    assert struct.unpack_from('<I', IMG, off)[0] == word
    assert off < TEXT_END and off not in kinds and not any(seg[0].address <= off < seg[-1].address + 4 for seg in windows)
    start = here()
    emit(STP_PRE(8, 31, 31, -16))  # The w8 query result is used only for cbz; both paths restore the original x8.
    emit(STP_PRE(29, 30, 31, -16))
    emit_gate_call(); emit(BLR(30))
    ret = here(); emit(LDP_POST(29, 30, 31, 16))
    # cbz w8, nonmatch; NZCV is not changed. On match, restore the registers and then preserve children.
    emit(0x34000068)
    emit(LDP_POST(8, 31, 31, 16)); emit(B(here(), 0x3e4460))
    emit(LDP_POST(8, 31, 31, 16)); emit(word); emit(B(here(), 0x3e4440))
    gates.append((ret, 'svc', 0x85, off))
    put_branch(off, start); stat('private_skill_render')
    cuts.append((off, struct.pack('<I', word).hex(), struct.pack('<I', B(off,start)).hex(),
                 'private confirmed six HUD only: own image/text skip ->4460; unknown original ->4440; svc85 full800', 'host-only'))
elif RULE_RUN:
    patch.extend(bytes(0x80))
    stat('private_gates_reserved')

obs = list(OBS.get(BUILD_ID, []))
if RULE_RUN and PRIVATE_GATES:
    obs.append((0x43ecc8, 6, "b8686953", "private touch-run-v4 PRE-ldr; full800 host ABI"))
    obs.append((0x1237c60, 8, "d10143ff", "ui world anchor: camera world->screen entry (camera, point, out); host swaps x0 to a copy whose projection is shifted by the UI rect y (iPad UI kept 16:9 inside a taller screen), game camera untouched"))
    # Freeze the world while a panel is open (host diag.c freeze_tick, off by default, DM_PANEL_FREEZE=1 turns it on). Four entry gates, all of which only swap entry arguments.
    obs.append((0x5eb2c0, 10, "a9bc5ff8", "server world-sim entry (game G): while frozen the host swaps x0 to a stand-in whose event queue is empty, so no unit / timer callback runs this tick; the real queue is left untouched"))
    obs.append((0x4b7230, 11, "d10183ff", "client per-unit tick update entry (unit): while frozen the host swaps x0 to a stand-in unit carrying only the skip flag ([+0x124] bit 23), so the function takes its own early-out to the epilogue; all six call sites are inside the client tick simulation 0x461b80 / 0x461e60"))
    obs.append((0x4b74d0, 12, "f81e0ff3", "client per-unit per-frame update entry (unit): drives model animation / interpolation from the tick fraction; while frozen the host swaps x0 to a stand-in unit (type 9, no render component) so both the callee 0x2a18d0 and this function take their own early-outs"))
    obs.append((0x2c3c90, 13, "f81c0ff7", "render per-frame entry, called right after the main loop writes the world frame step [0x20cebb8] and world time [0x3114208]: while frozen the host rewrites the step to 0 and the world time to its value at freeze, the same thing the game's own pause path does at 0x2c1574"))
    obs.append((0xadc434, 14, "d10143ff", "TextBoxWidget text-changed entry (widget): reads the raw text at +0x88 and rebuilds the display; host rewrites +0x88 for strings our item-notes generator annotated with colour codes (TextBoxWidget draws U+E07E as '*'), exact-match table only, everything else untouched"))
    obs.append((0x442bc0, 15, "a9ba6ffc", "client event-message entry (x0 = packet; byte 1 = event subtype, jump table 0x1da6752): subtype 0x17 = offline difficulty scale changed -> 0x20f91c chat line + system notification; host rewrites byte 1 past the table (default branch, nothing shown) only for 0x17 and only in a rift game (dm_rift.c); otherwise untouched. orig stp x28, x27, [sp, #-0x60]!"))
    obs.append((0x634000, 16, "d10143ff", "server level change by level number (game, player, level, kind), used by waypoints / portals / quest moves: in a rift game, when the player leaves a rift map for a level that is neither town nor a rift map, the host swaps w2 to the rift's next map so the destination is replaced inside the single native transition"))
    obs.append((0x711040, 17, "d101c3ff", "server quest event 'monster killed' entry (game, monster, attacker), the only entry (callers 0x7d8550 kill, 0x7ab8dc); in a rift game, for a monster that died on a rift map, the host swaps x1 to a stand-in whose +0xc0 is null so the function takes its own early return (0x711064): bosses in the rift are combat only, no quest state / quest notifications"))
    obs.append((0x3d84a0, 18, "d10143ff", "NotificationPanel message handler entry (panel, message): on InputMessage / ControllerActionBegin with action id 9 (the menu key) the native handler re-sends the notice callback and marks the message bus consumed, so the first menu press only dismisses the notice. In touch mode the host swaps x1 to a copy of the message whose action id is not 9: the notice stays until it times out and the menu key opens the menu; controller mode keeps the native behaviour"))
    obs.append((0x2f7664, 7, "6dbb23e9", "touch target rank: candidate compare entry (closure, unit, kind, s0=score); host raises Boss/elite score, native eligibility unchanged"))
for off, oid, ow, why in obs:
    w = struct.unpack_from('<I', IMG, off)[0]
    assert f'{w:08x}' == ow, f'observation gate original instruction mismatch {off:#x}: {w:08x}'
    # Function entries, or the instruction right after a bl, only: dm_gate writes back only x0–x8 / x30, and host C code may modify x9–x17; at entry these carry no values under AAPCS64 (arguments are only in x0–x7 / x8),
    # and right after a call returns the callee was free to clobber them anyway (x16 / x17 are the veneer registers)
    after_bl = off >= 4 and struct.unpack_from('<I', IMG, off - 4)[0] >> 26 == 0x25
    assert off in set(starts) or after_bl or (oid == 6 and off == 0x43ecc8), f'private obs point not approved {off:#x}'
    assert off < TEXT_END and off not in kinds and not any(lo <= off < hi for wseg in windows for lo, hi in [(wseg[0].address, wseg[-1].address + 4)]), f'observation gate conflicts with a rewrite site {off:#x}'
    put_branch(off, site_obs(off, oid, w)); stat('obs')

# Rift exit rerouting (since r36): branch gate 0x89, hooked at the entry of "change level by the exit tile's connection" main+0x7cc1e0(game, player, tile). Its four callers (clicking an exit tile 0x6dbea0,
# entrance objects 0x6aeaa0 / 0x6b0500, quest 0x7314c0) all call it only after their own checks have passed; the destination is not a level id but the tile's peer room (in the already generated map of the same act), so it cannot be switched to another act.
# In a rift run the host replaces w2 / w3 with (the rift's next map, 11) and makes x8≠0 → the gate block jumps straight to "change level by level id" 0x634000, same caller, exactly one level change; in all other cases the original instruction is executed and control returns to 0x7cc1e4.
# The gate block is word-for-word isomorphic with the 0x85 branch gate (structck ⑪ checks it against the hle.h registry); like observation gates 15 / 16 it exists only in build outputs with host-private gates (touch)
if RULE_RUN and PRIVATE_GATES:
    off, word, tgt = 0x7cc1e0, 0xd10183ff, 0x634000
    assert struct.unpack_from('<I', IMG, off)[0] == word and off in set(starts) and tgt in set(starts)
    assert off < TEXT_END and off not in kinds and not any(seg[0].address <= off < seg[-1].address + 4 for seg in windows)
    start = here()
    emit(STP_PRE(8, 31, 31, -16))
    emit(STP_PRE(29, 30, 31, -16))
    emit_gate_call(); emit(BLR(30))
    ret = here(); emit(LDP_POST(29, 30, 31, 16))
    emit(0x34000068)
    emit(LDP_POST(8, 31, 31, 16)); emit(B(here(), tgt))
    emit(LDP_POST(8, 31, 31, 16)); emit(word); emit(B(here(), off + 4))
    gates.append((ret, 'svc', 0x89, off))
    put_branch(off, start); stat('rift_exit')
    cuts.append((off, struct.pack('<I', word).hex(), struct.pack('<I', B(off, start)).hex(),
                 'rift exit redirect: tile-link level change entry -> host swaps (level, kind) and x8!=0 takes the branch to level-number change 0x634000; otherwise original ->0x7cc1e4; svc89', 'host-only'))

# Current act written to the save while in a Rift (since r38): branch gate 0x8c, hooked at the "read difficulty" instruction main+0x6fa9d0 (ldrb w10,
# [x21, #0x104]) inside the original save-header writer 0x6fa3e0.
# The preceding instruction 0x6fa9cc has just loaded "which act the player is currently in" into w9 (ldrb w9, [x24, #0x2e8]); below, 0x6fa9e4 / 0x6fa9e8
# write it as the difficulty byte 0x80 | act number (.d2s 0x98–0x9a),
# which decides which town the next session starts in. While the player is in a Rift map the host replaces w9 with 4 (Act 5 → re-enter in Harrogath);
# only this one value written to the save is changed, the running act number is untouched.
# A branch gate is used rather than "replace one instruction": structck only recognizes three registered forms, "bl call site", "entry" and "branch
# gate". The host always sets x8 = 0 (the jump path is never taken);
# the gate block restores x8, executes the original instruction and returns to 0x6fa9d4; the jump target is set to the return point itself only to
# satisfy the template (never reached). The gate block is word-for-word identical in structure to 0x85 / 0x89
if RULE_RUN and PRIVATE_GATES:
    off, word, tgt = 0x6fa9d0, 0x394412aa, 0x6fa9d4   # An instruction in the middle of a function (same as gate 0x85); it need not be a function entry; the original instruction does not depend on pc
    assert struct.unpack_from('<I', IMG, off)[0] == word
    assert off < TEXT_END and off not in kinds and not any(seg[0].address <= off < seg[-1].address + 4 for seg in windows)
    start = here()
    emit(STP_PRE(8, 31, 31, -16))
    emit(STP_PRE(29, 30, 31, -16))
    emit_gate_call(); emit(BLR(30))
    ret = here(); emit(LDP_POST(29, 30, 31, 16))
    emit(0x34000068)
    emit(LDP_POST(8, 31, 31, 16)); emit(B(here(), tgt))
    emit(LDP_POST(8, 31, 31, 16)); emit(word); emit(B(here(), off + 4))
    gates.append((ret, 'svc', 0x8c, off))
    put_branch(off, start); stat('rift_save_act')
    cuts.append((off, struct.pack('<I', word).hex(), struct.pack('<I', B(off, start)).hex(),
                 'rift save act: save-header writer, right after it loads the current act into w9 -> host swaps w9 to 4 (act V) while the player is in a rift map; x8 stays 0, original insn runs ->0x6fa9d4; svc8c', 'host-only'))
# Extra mercenary equipment slots (since r39): branch gate 0x8d, hooked in the monster-owner branch of the original game's generic placement check main+0x6493a8 at main+0x64a34c (mov w9, w25).
# This section (0x64a314–0x64a354) lets through only two kinds of items for monster-type owners: 0x574bc0(item, 3 armor) and 0x574bc0(item, 0x25 helm); if neither, it takes the weapon path (by the left / right hand types in monstats), and if that fails too it rejects.
# The gate is hooked after the "is it a helm" call returns and before cbnz w0: when "the owner is the player's mercenary + highest rift level cleared ≥ 10 + the item is a belt / boots / gloves / ring / amulet", the host changes w0 to 1,
# taking the same pass path as the helm (the generic checks that follow, such as the body location cell and whether the location is empty, run as usual). The host always sets x8 = 0; the gate block is word-for-word isomorphic with 0x85 / 0x89 / 0x8c
if RULE_RUN and PRIVATE_GATES:
    off, word, tgt = 0x64a34c, 0x2a1903e9, 0x64a350   # The original instruction does not depend on pc
    assert struct.unpack_from('<I', IMG, off)[0] == word
    assert off < TEXT_END and off not in kinds and not any(seg[0].address <= off < seg[-1].address + 4 for seg in windows)
    start = here()
    emit(STP_PRE(8, 31, 31, -16))
    emit(STP_PRE(29, 30, 31, -16))
    emit_gate_call(); emit(BLR(30))
    ret = here(); emit(LDP_POST(29, 30, 31, 16))
    emit(0x34000068)
    emit(LDP_POST(8, 31, 31, 16)); emit(B(here(), tgt))
    emit(LDP_POST(8, 31, 31, 16)); emit(word); emit(B(here(), off + 4))
    gates.append((ret, 'svc', 0x8d, off))
    put_branch(off, start); stat('merc_slot')
    cuts.append((off, struct.pack('<I', word).hex(), struct.pack('<I', B(off, start)).hex(),
                 'merc slots: placement check, monster-owner branch right after the helm type test -> host sets w0=1 for ring/amulet/boots/gloves/belt on a hireling (rift best >= 10 for new equips; always on load); x8 stays 0, original insn runs ->0x64a350; svc8d', 'host-only'))
# Client half of the extra mercenary equipment slots (same generation as r39): branch gate 0x8e, hooked inside the client's "can the mercenary wear this" function main+0x3bea44(mercenary, item) at main+0x3beb58 (mov x0, x19).
# This function follows the same rule as the server-side section: if either 0x574bc0(item, 3 armor) or 0x574bc0(item, 0x25 helm) matches it returns 1, and if neither does it takes the weapon path. The item cell widget uses its result to draw the "cannot place" red and
# to decide whether to place on release -- without changing it, an unlocked new cell still shows red when the right item is dragged over it, and the original game's drop fails (previously the touch layer's fallback called 0x3bed60 directly).
# The gate is hooked after "mov w1, #0x25" and before the bl of this type check: when "highest rift level cleared ≥ 10 + the item is a belt / boots / gloves / ring / amulet", the host replaces w1 with the item's own type number,
# so the type check passes naturally and takes the same return-1 path as the helm. The host always sets x8 = 0; the gate block is word-for-word isomorphic with 0x8d
if RULE_RUN and PRIVATE_GATES:
    off, word, tgt = 0x3beb58, 0xaa1303e0, 0x3beb5c   # The original instruction does not depend on pc
    assert struct.unpack_from('<I', IMG, off)[0] == word
    assert off < TEXT_END and off not in kinds and not any(seg[0].address <= off < seg[-1].address + 4 for seg in windows)
    start = here()
    emit(STP_PRE(8, 31, 31, -16))
    emit(STP_PRE(29, 30, 31, -16))
    emit_gate_call(); emit(BLR(30))
    ret = here(); emit(LDP_POST(29, 30, 31, 16))
    emit(0x34000068)
    emit(LDP_POST(8, 31, 31, 16)); emit(B(here(), tgt))
    emit(LDP_POST(8, 31, 31, 16)); emit(word); emit(B(here(), off + 4))
    gates.append((ret, 'svc', 0x8e, off))
    put_branch(off, start); stat('merc_slot_client')
    cuts.append((off, struct.pack('<I', word).hex(), struct.pack('<I', B(off, start)).hex(),
                 'merc slots (client): hireling can-equip check, between "mov w1,#0x25" and the type test -> host swaps w1 to the item\'s own type for ring/amulet/boots/gloves/belt (rift best >= 10); x8 stays 0, original insn runs ->0x3beb5c; svc8e', 'host-only'))

# ---- Parameter slots (host only): {NSO build ID: [(offset A, original word A, offset B, original word B, register, key, reason)]}.
# The two constant-building instructions at the original site are changed so that the first jumps to a parameter trampoline in the patch area and the second is a nop; the trampoline fetches the key page value indirectly and jumps back to just after the first (A+4): when A and B are not adjacent, the original instructions in between execute as usual
# (it used to jump back to B+4; in the operation-mode notification handler 0xe10d5c/0xe10d60 that skipped adrp x19.. and another trampoline, and switching to handheld crashed immediately; structck ⑩ checks the trampoline exit).
# xR must not be read or written between A and B (offline assertion: the instructions in between do not contain xR). The host supplies values according to the front end, Mac supplies the original constants → behavior unchanged ----
PARAMS = {'db0507f36b84200ac05f75d76ed5026f': [
    (0xe12d8c, 'd280c813', 0xe12d90, 'f2c07093', 19, 'KRES1', 'startup init: docked-mode output resolution 1600x900 (packed as {u32 width, u32 height})'),
    (0xe12e1c, 'd280a008', 0xe12e20, 'f2c05a08', 8, 'KRES0', 'startup init: handheld-mode output resolution 1280x720'),
    (0xe10d60, 'd280c818', 0xe10d80, 'f2c07098', 24, 'KRES1', 'operation-mode change notification (0x1f) handler: docked mode 1600x900'),
    (0xe10d5c, 'd280a016', 0xe10d74, 'f2c05a16', 22, 'KRES0', 'operation-mode change notification (0x1f) handler: handheld mode 1280x720'),
    # Aspect ratio cap 19:9 (float 0x40071c72): screens wider than 19:9 get black bars on both sides. The host supplies the float bit pattern (low 32 bits) of max(19/9, output width / height);
    # the original game outputs 16:9 (1600x900 / 1280x720) ⇒ still 19/9, behavior unchanged; iPhone 1952x900 (2.17:1) ⇒ 2.169, black bar width 0
    (0x1663ee8, '52838e49', 0x1663eec, '72a800e9', 9, 'KASPECTUI', 'UI constant buffer slot 0x15 [screen width, screen height, aspect ratio cap]: the UI sprite shader uses it to draw black bars on both sides beyond the cap (with a soft edge about 20–30 pixels inward; the host adds a margin that pushes the soft edge off screen)'),
    (0xb152bc, '52838e48', 0xb152c0, '72a800e8', 8, 'KASPECT', 'new-picture mode viewport: margin = (screen width − screen height × cap) / 2, a centered viewport set through 0x85bc90'),
    (0x23e888, '52838e48', 0x23e88c, '72a800e8', 8, 'KASPECT', 'new-picture mode coordinate clamp (0x23e760): x is clamped into [margin, margin + screen height × cap], so a pointer / touch at the sides of a wide screen is no longer clamped back to the middle'),
]}
params = PARAMS.get(BUILD_ID, [])
for oa, wa, ob_, wb, r, key, why in params:
    for o, w0 in ((oa, wa), (ob_, wb)):
        w = struct.unpack_from('<I', IMG, o)[0]
        assert f'{w:08x}' == w0, f'parameter slot original instruction mismatch {o:#x}: {w:08x}'
        assert o not in kinds and not any(lo <= o < hi for wseg in windows for lo, hi in [(wseg[0].address, wseg[-1].address + 4)]), f'parameter slot conflicts with a rewrite site {o:#x}'
    for o in range(oa + 4, ob_, 4):
        ins = dis(struct.unpack_from('<I', IMG, o)[0], o)
        assert r not in regs_in(ins), f'x{r} is used between the parameter slot instructions: {o:#x} {ins.mnemonic} {ins.op_str}'
    start = here()
    tmp = 16 if r != 16 else 17
    emit(STUR(tmp, 31, -16)); emit(MRS_TPIDRRO(r)); emit_slot_addr(r, tmp, key); emit(LDRX(r, r)); emit(LDUR(tmp, 31, -16)); emit(B(here(), oa + 4))
    struct.pack_into('<I', IMG, oa, B(oa, start)); struct.pack_into('<I', IMG, ob_, NOP); stat('param')

# ---- Frame step in whole vsyncs (The Legend of Zelda: Tears of the Kingdom 1.4.3 and Breath of the Wild 1.9.0 main, host only) ----
# Both games step their game time by a whole number of vsyncs (1/60 s) per frame that their own interval logic picks. With the stubs the host picks it (hle_nvn.c fstep_tick,
# nvn_fstep.h): the step is the number of vsyncs the host keeps the frame on screen (1 = 60 fps, 2 = 30 when 60 does not hold), plus one while the game is behind real time after
# a late frame, so motion is even and game time = real time. The steps stay values the games' own logic uses (1 to 3).
# State page = the page after the key page (zero in the file, read-write in both loaders): +0 float target fps written by the loader (fps_target, DM_FPS_TARGET; 0 = every stub
# runs the original instructions), +4 TOTK movie flag, +8 double lead (TOTK legacy), +0x10 float render scale (TOTK, below), +0x18 double game seconds (TOTK legacy),
# +0x20 u32 step in vsyncs (host; 0 = not decided yet), +0x24 u32 a step the game fixes itself (BotW's VFR override; 0 = none), +0x28 u32 mode (loader: 0 = whole vsyncs, 1 = legacy),
# +0x30 u64 vsyncs stepped (the stubs; logged by the host to check the game's speed). Legacy (DM_FRAME_STEP=legacy, profile frame_step) is each game's earlier method, kept for
# the iPhone A/B test: TOTK's elapsed-time step (below); for BotW the loader writes target 0 (its own interval controller with the 60 fps cuts above). The value per build is
# whether legacy keeps the state page on (fixups FPS_LEGACY_ELAPSED). Stub bodies assembled with clang
FRAME_STEP = {'277178b7dba1b6d4949a84778d4abc58': 1, 'cd57b23fa4bbad65803d9788c01821ee': 0}
FS_STATE_OFF = 0
if BUILD_ID in FRAME_STEP and NAME == 'main':
    FS_STATE_OFF = KEY_PAGE_OFF + 0x4000
    assert not FAR and FS_STATE_OFF % 0x1000 == 0 and FS_STATE_OFF + 0x40 <= PATCH_OFF and not any(IMG[FS_STATE_OFF:]), 'frame step state page'
    def fs_site(off, orig):
        ob = bytes.fromhex(orig)
        assert IMG[off:off + len(ob)] == ob, f'frame step original bytes mismatch {off:#x}: {bytes(IMG[off:off + len(ob)]).hex()}'
        for o in range(off, off + len(ob), 4):
            assert o not in kinds and not any(seg[0].address <= o < seg[-1].address + 4 for seg in windows), f'frame step site is a rewrite site {o:#x}'
    def fs_put(off, words, why):
        old = bytes(IMG[off:off + 4 * len(words)])
        for i, w in enumerate(words): struct.pack_into('<I', IMG, off + 4 * i, w)
        cuts.append((off, old.hex(), bytes(IMG[off:off + 4 * len(words)]).hex(), why, 'host-only')); stat('frame_step')
# Tears of the Kingdom picks a present interval each frame (main+0x2db174: 2 = 30 fps, 3 under load) and steps its game time by 60 / fps (int fps at timing +0x50, read at main+0x2daa54
# and main+0x3e562c). The stub replaces that logic: int fps = 60 / step, and the float fps (timing +0x24, unused, per masagrator's FPSLocker config for this build, which found the
# sites) the same, which the consumers read. Legacy: the step is the measured frame time (timing frame +0xd8, 19.2 MHz ticks), clamped to [1 / cap, 1 / 15 s]; game time that ran
# ahead after a short frame (the "lead", at most 0.25 s; totk-mobile) is paid back by later frames. Prerendered movies set a 30 cap (flag set and cleared around main+0x2b36100 /
# main+0x2b33918), the D-pad menu fade starts at full rate (FPSLocker's fix at main+0x1fbc80) and the swapchain argument at main+0xbe14a8 becomes 1 as in FPSLocker
if FS_STATE_OFF and BUILD_ID == '277178b7dba1b6d4949a84778d4abc58':
    # frame step (replaces ldrb w9,[x0,#0x58], the first instruction after the prologue)
    fs_site(0x2db18c, '09604139')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xbd400200,   # ldr s0,[x16]           target fps
              0x1e202008,   # fcmp s0,#0.0
              0x54000680,   # b.eq off (+52)        target 0: original path
              0xb9402a02,   # ldr w2,[x16,#0x28]     mode
              0x350001e2,   # cbnz w2,elapsed (+15)  legacy
              0xb9402202,   # ldr w2,[x16,#0x20]     step in vsyncs
              0x340001a2,   # cbz w2,elapsed (+13)   not decided yet
              0x1e230041,   # ucvtf s1,w2
              0x1e27d003,   # fmov s3,#30.0
              0x1e211872,   # fdiv s18,s3,s1
              0x1e322a52,   # fadd s18,s18,s18       fps = 60 / step
              0xbd002412,   # str s18,[x0,#0x24]     float fps
              0x52800785,   # mov w5,#60
              0x1ac208a5,   # udiv w5,w5,w2
              0xb9005005,   # str w5,[x0,#0x50]      integer fps
              0xf9401a04,   # ldr x4,[x16,#0x30]
              0x8b224084,   # add x4,x4,w2,uxtw
              0xf9001a04):  # str x4,[x16,#0x30]     vsyncs stepped
        emit(w)
    emit(B(here(), 0x2db284))                                       # the original epilogue
    for w in (0xf9406c22,   # elapsed: ldr x2,[x1,#0xd8]  last frame time in 19.2 MHz ticks
              0x9e630041,   # ucvtf d1,x2
              0x529f0003,   # mov w3,#0xf800
              0x72a02483,   # movk w3,#0x124,lsl #16 (19,200,000)
              0x1e630062,   # ucvtf d2,w3
              0x1e621821,   # fdiv d1,d1,d2          elapsed seconds
              0xb9400604,   # ldr w4,[x16,#4]        movie flag
              0x1e27d003,   # fmov s3,#30.0
              0x7100009f,   # cmp w4,#0
              0x1e201c60,   # fcsel s0,s3,s0,ne      cap = movie ? 30 : target
              0x1e22c000,   # fcvt d0,s0
              0x1e6e1003,   # fmov d3,#1.0
              0x1e601864,   # fdiv d4,d3,d0          shortest step 1 / cap
              0x1e65d005,   # fmov d5,#15.0
              0x1e651865,   # fdiv d5,d3,d5          longest step 1 / 15
              0xfd400606,   # ldr d6,[x16,#8]        lead
              0x1e663827,   # fsub d7,d1,d6
              0x1e6448e7,   # fmax d7,d7,d4
              0x1e6558e7,   # fmin d7,d7,d5          step = clamp(elapsed - lead)
              0x1e6728c6,   # fadd d6,d6,d7
              0x1e6138c6,   # fsub d6,d6,d1          lead += step - elapsed
              0x2f00e410,   # movi d16,#0
              0x1e7048c6,   # fmax d6,d6,d16
              0x1e6a1011,   # fmov d17,#0.25
              0x1e7158c6,   # fmin d6,d6,d17         lead in [0, 0.25]
              0xfd000606,   # str d6,[x16,#8]
              0x1e671872,   # fdiv d18,d3,d7         fps = 1 / step
              0x1e624252,   # fcvt s18,d18
              0xbd002412,   # str s18,[x0,#0x24]     float fps
              0x1e380245,   # fcvtzs w5,s18
              0xb9005005,   # str w5,[x0,#0x50]      integer fps
              0xfd400e13,   # ldr d19,[x16,#0x18]
              0x1e672a73,   # fadd d19,d19,d7
              0xfd000e13):  # str d19,[x16,#0x18]    game seconds stepped
        emit(w)
    emit(B(here(), 0x2db284))                                       # the original epilogue
    emit(0x39416009); emit(B(here(), 0x2db190))                     # off: ldrb w9,[x0,#0x58]; back
    fs_put(0x2db18c, [B(0x2db18c, start)], 'frame step from the host in whole vsyncs, legacy by elapsed time (state page target fps; 0 = original interval logic)')
    # the two readers of the integer fps: float fps when on; the scvtf a few instructions later moves into the stub (s0 is not touched in between)
    for site, cvt, r in ((0x2daa54, 0x2daa6c, 19), (0x3e562c, 0x3e5638, 22)):
        fs_site(site, struct.pack('<I', 0xbd425000 | r << 5).hex()); fs_site(cvt, '00d8215e')
        start = here(); emit(STP_PRE(16, 17, 31, -16)); emit(ADRP(16, here(), FS_STATE_OFF))
        for w in (0xb9400211,                # ldr w17,[x16]
                  0x34000071,                # cbz w17,off (+12)
                  0xbd422400 | r << 5,       # ldr s0,[xR,#0x224]  float fps
                  0x14000003,                # b done (+12)
                  0xbd425000 | r << 5,       # off: ldr s0,[xR,#0x250]  integer fps
                  0x5e21d800,                # scvtf s0,s0
                  0xa8c147f0):               # done: ldp x16,x17,[sp],#16
            emit(w)
        emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], 'game step reads the float fps (original integer fps and scvtf when off)')
        fs_put(cvt, [NOP], 'scvtf moved into the stub at the load')
    # D-pad menu fade (w8 is overwritten right after the site)
    fs_site(0x1fbc80, '0820201e0a04081f')
    start = here(); emit(ADRP(8, here(), FS_STATE_OFF))
    for w in (0xb9400108, 0x340001a8,       # ldr w8,[x8]; cbz w8,off (+52)
              0x1e202028, 0x54000101,       # fcmp s1,#0.0; b.ne go
              0x785fa308, 0x7100151f, 0x540000a1,   # ldurh w8,[x24,#-6]; cmp w8,#5; b.ne go
              0x785f8308, 0x7100151f, 0x54000041,   # ldurh w8,[x24,#-8]; cmp w8,#5; b.ne go
              0x1e2e1008,                   # fmov s8,#1.0
              0x1f08040a, 0x1e202008, 0x14000003,   # go: fmadd s10,s0,s8,s1; fcmp s0,#0.0; b end
              0x1e202008, 0x1f08040a):      # off: the original fcmp s0,#0.0; fmadd s10,s0,s8,s1
        emit(w)
    emit(B(here(), 0x1fbc88))
    fs_put(0x1fbc80, [B(0x1fbc80, start), NOP], 'D-pad menu fade starts at full rate under fractional steps (FPSLocker)')
    # swapchain argument (x16 is dead before the bl that follows)
    fs_site(0xbe14a8, '61a24039')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9400210, 0x34000070, 0x52800021, 0x14000002, 0x3940a261):   # ldr w16,[x16]; cbz w16,off; mov w1,#1; b end; off: ldrb w1,[x19,#0x28]
        emit(w)
    emit(B(here(), 0xbe14ac))
    fs_put(0xbe14a8, [B(0xbe14a8, start)], 'swapchain argument 1 when on (FPSLocker)')
    # prerendered movie start and end set and clear the flag (x16 / x17 are free at a call)
    fs_site(0x2b36100, 'b6f37097'); fs_site(0x2b33918, 'de170214')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF)); emit(0x52800031); emit(0xb9000611); emit(B(here(), 0x772fd8))   # mov w17,#1; str w17,[x16,#4]; tail call
    fs_put(0x2b36100, [B(0x2b36100, start) | 0x80000000], 'movie starts: 30 fps cap')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF)); emit(0xb900061f); emit(B(here(), 0x2bb9890))                     # str wzr,[x16,#4]; tail call
    fs_put(0x2b33918, [B(0x2b33918, start)], 'movie ends')
    # Render scale (state +0x10, float written by the loader: DM_RENDER_SCALE, 1.0 by default). main+0xd5c24 sizes each view: screen size x the view's scale (5/6 for the scene: 1600x896
    # docked) x the dynamic-resolution multiplier, clamped to 8..16384 and floored to the view's alignment. The stub multiplies both extents by the factor (s6, w8 and the flags are dead
    # at main+0xd5cc0: s6 is set to 8.0 right after); any factor but 1.0 also replaces the dynamic multiplier (main+0xd5d80) with 1, so the size is fixed. 1.0 = bit-exact original
    fs_site(0xd5cc0, '08d0a8524008251e6108241e0401271e'); fs_site(0xd5d80, '062940bd')
    start = here(); emit(ADRP(8, here(), FS_STATE_OFF))
    for w in (0xbd401106,   # ldr s6,[x8,#0x10]   render scale
              0x1e250840,   # fmul s0,s2,s5       (original)
              0x1e240861,   # fmul s1,s3,s4       (original)
              0x1e2020c8,   # fcmp s6,#0.0
              0x5400006d,   # b.le skip (+12)     not set
              0x1e260800,   # fmul s0,s0,s6
              0x1e260821,   # fmul s1,s1,s6
              0x52a8d008,   # skip: mov w8,#0x46800000 (original)
              0x1e270104):  # fmov s4,w8          (original)
        emit(w)
    emit(B(here(), 0xd5cd0))
    fs_put(0xd5cc0, [B(0xd5cc0, start)], 'view render size x the host render scale (1.0 = original)')
    start = here(); emit(0xbd402906); emit(ADRP(8, here(), FS_STATE_OFF))   # ldr s6,[x8,#0x28] (original: the dynamic multiplier); x8 is dead after it
    for w in (0xbd401107,   # ldr s7,[x8,#0x10]
              0x1e2e1010,   # fmov s16,#1.0
              0x1e3020e0,   # fcmp s7,s16
              0x54000080,   # b.eq done (+16)     scale 1: the game's dynamic resolution
              0x1e2020e8,   # fcmp s7,#0.0
              0x5400004d,   # b.le done (+8)      not set
              0x1e204206):  # fmov s6,s16         a fixed scale: no dynamic multiplier
        emit(w)
    emit(B(here(), 0xd5d84))
    fs_put(0xd5d80, [B(0xd5d80, start)], 'dynamic resolution only at render scale 1.0')
# Breath of the Wild: the framework's interval controller (the 60 fps cuts above) hands its interval to setWaitVsyncInterval (main+0x11269b8), which the main loop calls once a frame
# (main+0x11267c0); the framework keeps it at fw+0x244 (getter vtable +0x138, read by both callers of VFR::updateInterval and directly in 43 places) and passes it on to
# nvnWindowSetPresentInterval. The stub at the setter's entry replaces it with the host's step, read once a frame: ksys::VFR::updateInterval (main+0x151d3d0, x0 = the VFR at
# [main+0x1e93890]; called from GameScene::calc and the per-frame delegate main+0x1280f80) takes the framework's interval in the next frame (ratio = step / 2, base interval 2, and the
# int interval that 16 pieces of logic read), so the time step and everything else that reads the interval agree. The step is not written into the VFR call itself: the game presents
# on its own thread, so the host's step can change between the two VFR calls of a frame. The VFR's own override (+0x29 flag, +0x2c interval: 2 at main+0xc3b588 and main+0xc5ebf8,
# 1 at main+0xc609d8, set and cleared by game scenes) wins in the VFR:
# a stub there publishes it at state +0x24 so the host holds frames that long, and the setter stub leaves the framework's interval to the game while it is set. x16 / x17 are free
# at both entries
if FS_STATE_OFF and BUILD_ID == 'cd57b23fa4bbad65803d9788c01821ee':
    fs_site(0x11269b8, 'fd7bbea9'); fs_site(0x151d3d0, 'fd7bbea9')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9400211,   # ldr w17,[x16]          target fps (0 = off)
              0x340001d1,   # cbz w17,orig (+14)
              0xb9402a11,   # ldr w17,[x16,#0x28]    mode
              0x35000191):  # cbnz w17,orig (+12)    legacy
        emit(w)
    emit(ADRP(17, here(), 0x1e93890)); emit(LDRX(17, 17, 0x890 // 8))   # the VFR
    for w in (0xb4000131,   # cbz x17,orig (+9)
              0x3940a631,   # ldrb w17,[x17,#0x29]   the VFR's override
              0x350000f1,   # cbnz w17,orig (+7)     the framework keeps the game's interval
              0xb9402211,   # ldr w17,[x16,#0x20]    step in vsyncs
              0x340000b1,   # cbz w17,orig (+5)      not decided yet
              0x2a1103e1,   # mov w1,w17
              0xf9401a11,   # ldr x17,[x16,#0x30]
              0x8b214231,   # add x17,x17,w1,uxtw
              0xf9001a11,   # str x17,[x16,#0x30]    vsyncs stepped
              0xa9be7bfd):  # orig: stp x29,x30,[sp,#-0x20]!
        emit(w)
    emit(B(here(), 0x11269bc))
    fs_put(0x11269b8, [B(0x11269b8, start)], 'setWaitVsyncInterval: the host\'s step unless the VFR override is set (state page target fps; 0 = the game\'s interval)')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9400211,   # ldr w17,[x16]          target fps (0 = off)
              0x340000f1,   # cbz w17,orig (+7)
              0xb9402a11,   # ldr w17,[x16,#0x28]    mode
              0x350000b1,   # cbnz w17,orig (+5)     legacy
              0x3940a411,   # ldrb w17,[x0,#0x29]    the VFR's override
              0x34000051,   # cbz w17,pub (+2)       none: 0
              0xb9402c11,   # ldr w17,[x0,#0x2c]
              0xb9002611,   # pub: str w17,[x16,#0x24]  the game's own step: the host holds frames that long
              0xa9be7bfd):  # orig: stp x29,x30,[sp,#-0x20]!
        emit(w)
    emit(B(here(), 0x151d3d4))
    fs_put(0x151d3d0, [B(0x151d3d0, start)], 'VFR::updateInterval: its own override published for the host (state page target fps; 0 = original)')
    # Render scale (state +0x10, float written by the loader: DM_RENDER_SCALE, 1.0 by default; independent of the frame step). The dynamic-resolution method (main+0x12666e4) keeps a
    # scale in 0.8–1.0 rounded to 0.05 steps (+0x1218, main+0x1266818), or the game's forced 0.75 / 0.5 (+0x284 & 0x1800), in s8; from main+0x1266880 it applies s8: each view's
    # scale (+0x28a0 / +0x28a4 = s8 × base width (+0x1214: 1600 docked, 1280 handheld) / output width), from which the scene buffers are sized each frame (main+0x106340c), the
    # shader ratio uking_dynamic_resolution_ratio and the other readers (main+0xc3c3f4, an LOD check at main+0x14126b4). Setting s8 there keeps them all consistent (a multiply in the
    # size function, TOTK's way, would leave the ratio and those readers at the old scale). The apply block runs only when the dynamic path has just recomputed the scale (+0x280 bit 4,
    # set at main+0x1266830) or in a forced mode, else main+0x126686c skips it; with a factor it is taken every frame, as in the dynamic mode, so the factor holds with dynamic
    # resolution off too. Factors above 1.0 are refused by the loader: the per-frame texture pool's size is unknown. x8, s0, s1 and the flags are dead at both sites
    fs_site(0x1266880, '88ae40f9'); fs_site(0x126686c, struct.pack('<I', B(0x126686c, 0x1266950)).hex())
    apply = here(); emit(ADRP(8, here(), FS_STATE_OFF))
    for w in (0xbd401100,   # ldr s0,[x8,#0x10]      render scale
              0x1e202008,   # fcmp s0,#0.0
              0x540000ad,   # b.le orig (+5)         not set
              0x1e2e1001,   # fmov s1,#1.0
              0x1e212000,   # fcmp s0,s1
              0x54000040,   # b.eq orig (+2)         1.0: the game's own scale
              0x1e204008,   # fmov s8,s0             the host's scale
              0xf940ae88):  # orig: ldr x8,[x20,#0x158]
        emit(w)
    emit(B(here(), 0x1266884))
    fs_put(0x1266880, [B(0x1266880, apply)], '3D view scale = the host render scale (1.0 = the game\'s dynamic resolution)')
    start = here(); emit(ADRP(8, here(), FS_STATE_OFF))
    for w in (0xb9401108,   # ldr w8,[x8,#0x10]      render scale (float bits)
              0x34000088,   # cbz w8,skip (+4)       not set
              0x52091908,   # eor w8,w8,#0x3f800000
              0x34000048):  # cbz w8,skip (+2)       1.0
        emit(w)
    emit(B(here(), 0x1266880)); emit(B(here(), 0x1266950))   # apply the host's scale; skip: the original branch
    fs_put(0x126686c, [B(0x126686c, start)], 'scale apply block taken every frame when the host render scale is not 1.0')

# The three existing native rule trampolines all use only the dead temporary w8 that is overwritten afterwards, and do not change the w0/stat return, sp or NZCV.
# 6c6290 is after the original mode3 gate; the Blaze / reference count and data invalidation 6c62dc branches before it and the state update after it are untouched.
rule_blocks = []
if RULE_RUN:
    def run_branch(off, old, body, why):
        assert struct.unpack_from('<I', IMG, off)[0] == old, f'Run trampoline original word mismatch {off:#x}'
        start = here()
        for word in body(start): emit(word)
        new = B(off, start)
        struct.pack_into('<I', IMG, off, new)
        cuts.append((off, struct.pack('<I', old).hex(), struct.pack('<I', new).hex(), why, 'all'))
        rule_blocks.append((start, bytes(patch[start - PATCH_OFF:]).hex(), why))
    def cbz(at, target, r, nonzero=False):
        delta = target-at; assert delta%4==0 and -(1<<20)<=delta<(1<<20)
        return (0x35000000 if nonzero else 0x34000000) | (((delta>>2)&0x7ffff)<<5) | r
    run_branch(0x6c6648, 0x34000060, lambda a: [
        0xb9400268, cbz(a+4,a+12,8,True), B(a+8,0x6c664c),
        cbz(a+12,a+20,0), B(a+16,0x6c664c), B(a+20,0x6c6654)],
        'touch-run-v4: Run selection ignores the stamina gate for player0 only, non-player returns by the original stat; w8 is overwritten afterwards')
    run_branch(0x6c6290, 0x710006df, lambda a: [
        0xb9400268, cbz(a+4,a+12,8,True), B(a+8,0x6c62ec), 0x710006df, B(a+16,0x6c6294)],
        'touch-run-v4: in the original legal Run cost section only player0 skips the stat10 deduction / drop to walking when exhausted; non-player keeps the original cmp')


    # After the original mode3 / currently controlled unit gate at client4abc60; the actual GetStat has already returned, W0 is preserved, and only for type0 is the STA auto Stop cancelled.
    run_branch(0x4ac368, 0x35000460, lambda a: [
        0xb9400268, cbz(a+4,a+12,8), B(a+8,a+16), B(a+12,0x4ac3f4),
        cbz(a+16,a+24,0), B(a+20,0x4ac3f4), B(a+24,0x4ac36c)],
        'touch-run-v4: client currently controlled Run3: only player0 skips the STA-zero auto Stop; the original getter value and real stick release stay, non-player keeps the original gate')


    # After the original unit null/type5 gate, with w8 still the original unitType; only player request 2 is normalized, and the other original action dispatch / eligibility checks run in full.
    run_branch(0x6c6580, 0x51000849, lambda a: [
        cbz(a,a+16,8,True), 0x51000849, cbz(a+8,a+16,9,True),
        0x52800062, 0x51000849, B(a+20,0x6c6584)],
        'touch-run-v4: original generic legal move: only a player0 Walk2 request is normalized to Run3, non-player and other requests unchanged, w8 / original eligibility unchanged')

os.makedirs(outdir, exist_ok=True)
P = lambda ext: os.path.join(outdir, f'{NAME}.{ext}')
if FAR:   # patch area before the base: file = text + ro + data (padded to 16K) + patch area
    if BIG_TEXT and len(patch) > FRONT - 0x4000 and 'DM_PATCH_FRONT' not in os.environ:
        need = (len(patch) + 0x4000 + 0xFFFF) & ~0xFFFF
        print(f'{NAME}: patch area of {len(patch):#x} bytes does not fit in {FRONT:#x} before the base; rewriting again with {need:#x}', flush=True)
        os.execve(sys.executable, [sys.executable] + sys.argv, dict(os.environ, DM_PATCH_FRONT=hex(need)))
    assert len(patch) <= FRONT - 0x4000, f'patch area of {len(patch):#x} bytes does not fit in the {FRONT:#x} before the base'
    open(P('patched.bin'), 'wb').write(IMG + bytearray(FILE_IMAGE_LEN - len(IMG)) + patch)
else:
    open(P('patched.bin'), 'wb').write(IMG + bytearray(PATCH_OFF - len(IMG)) + patch)
import hashlib
with open(os.path.join(outdir, 'build_src.sha256'), 'w') as f:
    f.write(hashlib.sha256(open(os.path.abspath(__file__), 'rb').read()).hexdigest() + '  patch_nso.py\n')
if PRIVATE_AIM:
    with open(P('aim.tsv'), 'w') as f:
        f.write('# RULESET\tskill-aim-v1-private\n# ORIGINAL_CALL\t0x2faf04\t97fee7fd\n# ORIGINAL_CALLEE\t0x2b4ef8\n# SKILL_CALLER\t0x2b5b80\n# SVC\t0x86\n# INPUT\tactual GetNpad sampled right; move axis unchanged\n')
        f.write('# IMAGE_SHA256\t'+hashlib.sha256(open(P('patched.bin'),'rb').read()).hexdigest()+'\n')
if RULE_RUN:
    with open(P('rules.tsv'), 'w') as f:
        f.write(f'# RULESET\t{RULESET}\n# BUILD_ID\t{BUILD_ID}\n# ORIGINAL_SHA256\t{RULE_ORIG_SHA}\n# IMAGE_SHA256\t{hashlib.sha256(open(P("patched.bin"), "rb").read()).hexdigest()}\n')
        for off, raw, why in rule_blocks: f.write(f'{off:#x}\t{raw}\t{hashlib.sha256(bytes.fromhex(raw)).hexdigest()}\t{why}\n')
elif os.path.exists(P('rules.tsv')):
    os.unlink(P('rules.tsv'))  # When rebuilding native, clear this module's old rule registration so the old manifest does not leak into the original-resource domain
with open(P('fixups.tsv'), 'w') as f:
    f.write(f'# PATCH_OFF\t{PATCH_OFF:#x}\n# KEY_PAGE_OFF\t{KEY_PAGE_OFF:#x}\n# KEY_PAGE_SIZE\t0x4000\n# TEXT_END\t{TEXT_END:#x}\n# RO_OFF\t{RO_OFF:#x}\n# DATA_OFF\t{DATA_OFF:#x}\n')
    if FAR: f.write(f'# IMAGE_SIZE\t{IMAGE_SIZE:#x}\n# FILE_IMAGE_LEN\t{FILE_IMAGE_LEN:#x}\n')   # patch area before the base (negative PATCH_OFF): whole image size, length of the image part of the file
    for k in KEY_INDEX: f.write(f'# KEY_{k}_IDX\t{KEY_INDEX[k]}\n')
    if FS_STATE_OFF: f.write(f'# FPS_STATE_OFF\t{FS_STATE_OFF:#x}\n# FPS_LEGACY_ELAPSED\t{FRAME_STEP[BUILD_ID]:#x}\n')   # frame step state page (FRAME_STEP): the loader writes the target fps and the mode there
    f.write(f'# BUILD_ID\t{BUILD_ID}\n')   # the host identifies the build by it: features with hard-coded addresses only run on the build they belong to
with open(P('gates.tsv'), 'w') as f:
    for ret, k, arg, orig in gates: f.write(f'{ret:#x}\t{k}\t{arg}\t{orig:#x}\n')
with open(P('sites.tsv'), 'w') as f:
    for a in sorted(kinds):
        if a not in done: f.write(f'{a:#x}\t{kinds[a][0]}\n')
    for wseg in windows: f.write(f'{wseg[0].address:#x}\tW\t{wseg[-1].address + 4:#x}\n')
    for a, (b, c) in jumps.items(): f.write(f'{a:#x}\tJ\t{b:#x}\t{c}\n')
    for a, tgt in tabjumps.items(): f.write(f'{a:#x}\tT\t' + ' '.join(f'{t:#x}' for t in tgt) + '\n')   # offset-table jump and all its targets
with open(P('cuts.tsv'), 'w') as f:
    f.write(f'# BUILD_ID\t{BUILD_ID}\n')
    for off, ob, nb, why, scope in cuts: f.write(f'{off:#x}\t{ob}\t{nb}\t{scope}\t{why}\n')   # Columns: offset, original bytes, new bytes, scope, reason
with open(P('params.tsv'), 'w') as f:
    f.write(f'# BUILD_ID\t{BUILD_ID}\n')
    for oa, wa, ob_, wb, r, key, why in params: f.write(f'{oa:#x}\t{ob_:#x}\tx{r}\t{key}\t{why}\n')
with open(P('obs.tsv'), 'w') as f:
    f.write(f'# BUILD_ID\t{BUILD_ID}\n')
    for off, oid, ow, why in obs: f.write(f'{off:#x}\t{oid}\t{ow}\t{why}\n')
print(NAME, stats, 'cuts', len(cuts), 'obs', len(obs), 'patch', len(patch), 'PATCH_OFF', hex(PATCH_OFF), 'slot_refs', len(fix), 'gates', len(gates))
# The boot block list ships with main: take the repository's versioned data dm/data/bootlist_<main build ID>.tsv, copy it as is into the build output directory and write its sha256 (the list is checked in, not re-recorded for every version;
# the recording itself is racy -- three recordings of the same build output gave block sets of 5292 / 5114 / 5281, and the initiating threads also differed -- re-record only when the build ID changes or for a deliberate improvement, and attach an A/B from the second Mac to the commit)
if NAME == 'main':
    import hashlib, shutil
    BL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', f'bootlist_{BUILD_ID}.tsv')
    if not os.path.isfile(BL):   # the public repository does not ship this list (each line carries the first bytes of an original resource block): without it there is no prefetch, so launch skips one ahead-of-time decode step and nothing else is affected
        print('bootlist: no boot block list, skipped (no prefetch). To use one, record it yourself: dm/tools/tact_bootlist.py')
    else:
        hd = open(BL, encoding='utf-8').readline().split()
        if hd[-1:] != [BUILD_ID]: sys.exit(f'[RED] {BL} header build ID {hd[-1:]} does not match main {BUILD_ID}')
        shutil.copyfile(BL, os.path.join(outdir, 'bootlist.tsv'))
        sha = hashlib.sha256(open(BL, 'rb').read()).hexdigest()
        open(os.path.join(outdir, 'bootlist.sha256'), 'w').write(f'{sha}  bootlist.tsv\n')
        print('bootlist', os.path.relpath(BL), sha[:12])
