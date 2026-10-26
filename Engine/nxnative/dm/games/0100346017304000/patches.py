# Taiko Risshiden V DX (0100346017304000): the rewriter's patches of this game's own builds. dm/tools/patch_nso.py loads every profile's patches.py and applies those of a module's NSO build ID;
# CUTS, OBS and FRAME_STEP as described there ("Registered patches"). Patches of Nintendo SDK module builds are in dm/tools/sdk_patches.py
CUTS = {
  # Taiko Risshiden V DX 1.1.1 (v131072) main: KTGL's frame end (main+0x443e8c, after the present) waits until N / 60 s have passed since the frame's start tick (taken at main+0x443d44
  # after the previous present; N = 1, the int at GOT 0xa1c088), polling nn::os::GetSystemTick and sleeping 2 ms per round (main+0x4c9f24, SleepThread). With about 2 ms of work
  # a frame the rounds end at 18.2 ms, never at 16.7: the Mac ran 55 fps in the menus and the town (frame time p50 18.17 / p95 18.69 ms), every 11th frame on screen for two
  # vsyncs. The game presents at interval 1, so the swap chain holds it to the display anyway; the check jumps straight to the end, and the host's present pacing (the acquire
  # waits) sets the 60. In the town then: 60.0 fps, frame time p50 16.66 / p95 16.85 ms, display interval p99 17.0 ms; the main thread waits in the acquire instead of nine
  # sleeps a frame (wakeups 2,050 → 320 a second, CPU energy 1.7 → 0.7 mJ a frame). The opening movie, paced by its own player, was at 60 before
  'f5ab74b9d45f955de2dc91da8e039c57': [
    (0x443fd4, '82000054', '04000014', 'frame limiter: b.hs end → b end (no 2 ms sleep rounds until 1/60 s since the frame start; the present pacing holds 60)'),
  ],
}
