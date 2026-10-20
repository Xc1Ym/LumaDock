# 05 — Debugging recipes

## Reading a crash report

```
[dm] CRASH sig=11 addr=0 pc=main+0x373e04 lr=main+0x373dd8 sp=0x7066dd6370
x0=… x28=…
[dm] bt: main+0x373dd8 main+0x2ea2ac …          frame-pointer backtrace
[dm] fp=…  0x100 bytes below sp: …                 the 32 words below sp (the frame that was just popped)
[dm] stack scan sp=…: [-72]main+0x57a14 [+24]main+0x57618 …   every word near sp that resolves to a module or host symbol
[dm] thread 0x1001 'main thread' …                  all guest threads, what they wait on, their backtraces
```

- `pc` and `lr` are module-relative (`main+…`, `sdk+…`) or host symbols. Module offsets are the same as in the decompressed NSO and the ELF (Ghidra adds 0x100000).
- Look at the registers before the code: a pointer that is a valid pointer plus garbage high bits, an index of `0xfffffffe`, or `pc == lr == 0x100000000` each tell a different story. a fault at `0x74a740e114 = 0x70a740c570 + 0xfffffffe·4 + 0x1bac` was an index of −2 widened as unsigned; `pc == lr` on a nonsense value is a `ret` through an overwritten saved LR (look at the zeroed frame below `sp`).
- When the frame-pointer backtrace is empty, the stack scan's negative offsets (below `sp`) show the return addresses of the calls the crashing function made last.
- `[dm] *xN:` lines show the first six words each register points at (read safely, so a bad pointer is skipped). A word inside a module prints as `main+…`: the first word of an object is its vtable, which names its class, and comparing it with the class's own vtable shows whether the object was destroyed (a base-class vtable) or rebuilt.

## Ghidra / objdump

```bash
# decompile the functions containing these module offsets
JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless $W/ghidra/proj <proj> -process <module>.elf \
  -noanalysis -readOnly -scriptPath <repo>/dm/tools/ghidra -postScript Decompile.java 0x373e04,0x2ea2ac

# raw disassembly (works where Ghidra defined no function)
objdump -d --start-address=0x2ea1c0 --stop-address=0x2ea2b0 $W/elf/<module>.elf
```

Prefix an offset with `@` (`... Decompile.java @0x49740`) to (re)create the function at exactly that address. Code reached only through vtables has no function, and Ghidra's analysis marked some `nn::os` imports (`LockMutex`) as non-returning, which cut many functions short right after the first lock. The script clears that flag and the call-return overrides on such calls before decompiling.

Map GOT slots to NVN names with the survey table (`census/*_nvn_slots.tsv`): a call through `[x8, #0x3e8]` after `adrp x8, 0x35ad000` is GOT entry 0x35ad3e8.

## Probes without a debugger (`DM_PROBE`)

`DM_PROBE=main:4290c0,main:9712c` (module:offset, comma-separated; `host/probe.c`, Mac only) replaces the instruction with `brk`, and on every hit prints the guest thread (`T=`), x0–x7 (and strings they point to), x19–x23, lr, x8 and a backtrace, then runs the original instruction from a trampoline. Put probes at function entries or where x16 is dead; the probed instruction must not be PC-relative (no `adrp`, `adr`, `b`, `bl`, literal `ldr`: probe the next instruction instead). Output from several threads interleaves; parse it with a regex rather than by line. Probes slow the game, which can shift heap addresses between runs.

Per-probe suffixes, in this order:

| Suffix | Effect |
|---|---|
| `@off`, `@*off`, `@xN+off`, `@*xN+off` | Print 16 bytes at x0+off (or xN+off); `*` dereferences that address first |
| `?xN=val`, `?[xN+off]=val` | Only report hits where the register (or the 64-bit word at xN+off) equals `val` (hex); others pass silently. E.g. `main:4743c0?[x0+30]=781548` = only allocations into the heap whose size field is 0x781548 |
| `!xN` | Treat xN as a `sead::ExpHeap` and print its free and used blocks (offset+size) |

`DM_PROBE_ALL=1` adds x9–x18; `DM_PROBE_X2=<bytes>` dumps the memory x2 points to.

Use it when lldb is unavailable: after macOS revokes the debugger authorization (`DevToolsSecurity -status` says developer mode is disabled), `lldb` launches hang waiting for a GUI approval prompt. `sudo DevToolsSecurity -enable` (run by the user) restores it.

## lldb

The host uses SIGSEGV for dirty-page tracking, so lldb must pass it through without stopping. Address randomization is off under lldb, so guest addresses repeat across runs. Template (`$W/dbg/*.py`, run with `perl -e 'alarm 240; exec @ARGV' lldb -b -o "command script import x.py"`):

```python
import lldb
HOST = '/path/to/dm/host/dmhost'
def __lldb_init_module(dbg, _):
    dbg.SetAsync(False); ci = dbg.GetCommandInterpreter(); res = lldb.SBCommandReturnObject()
    ci.HandleCommand('settings set platform.plugin.darwin.ignored-exceptions EXC_BAD_ACCESS|EXC_BAD_INSTRUCTION', res)
    t = dbg.CreateTarget(HOST); t.BreakpointCreateByName('run_module_inits')
    li = lldb.SBLaunchInfo(['<patched dir>']); li.SetEnvironmentEntries(['DM_ROMFS=…', 'DM_SAVE=…', 'DM_TEMP=…'], True)
    p = t.Launch(li, lldb.SBError())
    for sig in ('SIGSEGV', 'SIGBUS', 'SIGUSR1', 'SIGUSR2', 'SIGPIPE'): ci.HandleCommand('process handle %s -n false -p true -s false' % sig, res)
    base = None
    while p.GetState() == lldb.eStateStopped:
        fr = p.GetSelectedThread().GetFrameAtIndex(0)
        if base is None and fr.GetFunctionName() == 'run_module_inits':
            base = t.EvaluateExpression('(unsigned long)g_mod[0].base').GetValueAsUnsigned()   # g_mod[0] = main
            t.BreakpointCreateByAddress(base + 0x2ea228)                                       # module offset
        elif base is not None and fr.GetPC() == base + 0x2ea228:
            print('x0=%#x' % fr.FindRegister('x0').GetValueAsUnsigned(), flush=True)          # flush: a timeout kill loses buffered output
        p.Continue()
    p.Kill()
```

Patterns that worked: print every call of one function with its arguments; stop when a return value is null and print the backtrace; trace the branch path through one function (one-shot breakpoints on every branch site). Hardware watchpoints on words touched by `ldxr`/`stxr` may stay silent.

## Scripted input and thread scheduling

- `DM_KEYS="<seconds>:<button>[+button][~hold],…"` presses buttons from host start (`hle_hid.c`). `<seconds>:<button>*<count>/<interval>` repeats a press, e.g. `42:A*170/2` presses A every 2 s from 42 s on, 170 times; at most 1,024 steps after expansion. Steps run in time order, so repeated groups interleave (`f17400:Left~0.3*120/500,f17480:A*120/500,f17560:Left~0.3*120/500,f17640:A*120/500` = Left, A, Left, A every 500 frames: Fire Emblem: Three Houses' confirm dialogs default to No, and this cycle confirms Yes whether a dialog is open or not when it starts; A, Left, A loops forever once it starts on an open dialog); a list that mixes seconds and frame numbers keeps its listed order. A long run through a game's story is then a single switch, such as Metroid Dread's title, new game and story recap. `LLeft` / `LUp` / `LRight` / `LDown` push the left stick fully (Super Mario 3D World moves on its map by stick only); combos such as `L+R~0.5` press buttons together. An `f` before the time counts presented frames instead of seconds (`f2500:A`, repeat intervals in frames too): with another heavy job running, seconds drift away from the game's progress and a route stops lining up; frame numbers do not. Breath of the Wild from its title menu into the autosave: `DM_KEYS=f2500:A,f2800:A,f3100:A,f3400:A` (control at frame ~3900).
- Frame numbers are a stable way to aim dumps (`DM_NVN_PASSDUMP=<frame>`, `DM_NVN_SHOT=…`) at the same scene in another run: the per-frame NVN call counts (`[nvn] frame N: … calls`) matched between runs of the same script. Times in seconds drift with load.
- `DM_PREEMPT=0` / `1` turns the same-core preemption approximation off / on whatever the profile's `core_preempt` says (`hle_thread.c`). The thread dump at exit reports `same-core preemption yields N, total T ms, hit the cap K times` (yields, total wait, 5 ms cap hits). A higher-priority thread that keeps a core busy shows up in the first eight `same-core preemption yield hit its cap` lines, with its last SVC and call site.

## Racy crashes: load, trace gates

A crash that needs an unlucky thread interleaving (one run in three, or once in a long session on the phone) gets much more frequent when the CPU is busy, because threads are descheduled at more places. 12 busy shell loops (`for i in $(seq 12); do (while :; do :; done) & done`) beside a scripted Mac run made Link's Awakening's physics crash happen in every run instead of 2 of 5, and the frame rate kept switching between 60 and 30 as on the phone. That is enough to test a fix: same load, same route, a few runs.

To see the order of events, put temporary observation gates (`OBS` in `patch_nso.py`, only at function entries or right after a `bl`, on position-independent instructions) on the functions involved. Their host callbacks append `(time, thread, event, pointers)` to an in-memory ring, and the crash handler prints the last ~150 entries. Printing each event as it happens is too slow and changes the timing. A function whose first instruction is PC-relative (an `adrp`, typical of short destructors) cannot take a gate: a temporary cut can put `svc #0x8f` at its entry and move its body into the `udf` padding after it (inside the same 4 KB page, an `adrp` keeps its encoding), with `svc_host_call` handling the number. Inside the host callback, the caller's return address is on the guest stack, in the frame the gate pushed (`regs + 800 + 8`), because the gate's own call has replaced `x30`. Remove all of it afterwards.

## Memory growth

1. The host's memory report line (`memory up to frame …`) every few hundred frames; `footprint -p <pid>` from outside. On a phone, a crash with no log usually means `headroom to the system memory limit` reached 0.
2. `vmmap -summary <pid>` twice a few seconds apart: which region grows. "owned unmapped (graphics)" = private Metal resources.
3. `DM_NVN_ALLOCPROF=1`: growth per replayed op type and per function (`tex_mtl` / pass begin / pipelines / argument buffers), command allocator sizes, and a log of new textures with serial, size, format and storage. A stream of new serials with the same sizes = objects re-created every frame.
4. GPU allocated climbing while the residency set, `shared textures` and the upload counts stay flat: retired objects kept alive by an autorelease pool that never drains. Any objc call on the guest submit thread outside `g_sub_pool` leaks what it autoreleases (Metroid Dread; Breath of the Wild, GitHub issue #9). Build the host with the suspect wrapped in `@autoreleasepool` and compare.
5. `serial objects` climbing by the same amount every frame with GPU memory flat: entries the serial table never deletes. A census of `g_by_serial` by class and size in `mtl_mem_stat` shows which (BotW: finalized textures replay resolved again; they now go to the small table counted as `finalized textures still referenced`).

Instruments' Metal Resource Events didn't record this process from the command line (`xctrace record --launch`, with `--env` for the variables); the in-host probes were faster.

## Save failures

`DM_TEST_FS_FAILAT=<point>[:<count>][,…]` makes steps of the save transaction fail with ENOSPC (`mountclone`, `reclone`, `guestname`, `renameback`; `dm/host/tests/t_fs.c` section 6). The game must keep running: a mount that cannot clone its work directory falls back to the committed saves read-only, and the iOS front end shows a notice.

## Render-pass investigation

See [04](04-graphics.md) section 7. Notes: pass dumps are large and may contain non-UTF-8 bytes; filter with `LC_ALL=C grep -a "\[pass\] F600 " | grep -av " o cmd"`. A Python one-liner with PIL (the dm venv has it) gives mean colour and non-black share of each dumped PNG, which is quicker than opening 20 images.

## On-device diagnostics (iOS)

The phone runs an unsigned IPA the user sideloads; nothing is attached to a debugger. The loop is: build an IPA with switches, the user plays and sends `Documents/log.txt` (the previous launch is `log.prev.txt`), read it, repeat.

- **Switches**: `DM_ENV_FILE=<file> dm/ios/tools/build_ipa.sh` bakes `KEY=VALUE` lines into the app (`dm/env.txt`); `Documents/env.txt` overrides them without a rebuild. Every applied switch is logged at boot (`boot: env KEY=VALUE (source file)`). The app's working directory is `Documents`, so relative output paths (`DM_NVN_SHOT=3600:shot_%d.png`, `DM_NVN_TEXDUMP`) land where the Files app can reach them.
- **Which build ran**: the first lines name the modules (`main: … patch_off …`), the shader map size (`shader map N entries`) and, for builds that have it, the build-ID gate line. Compare them with the build you sent before reading further; users sometimes send an old log. The save path (`fs mount save:`) shows the data folder, which changes when a sideloading tool gives a reinstall a new one.
- **Reading the periodic lines**: `[longframe]` gives each long frame's submit / GPU / pipeline-compile / upload split; a burst of `new pipelines` in long frames after an install is first-use compilation (see "Prewarm lists" in [docs/development.md](../development.md)). In `display link up to tick N: …`, `empty ticks` (refreshes with no new frame) and `old frames dropped by merging` are totals since launch, not per window. `on-screen up to frame N` windows give dropped frames (a frame on screen longer than 1.5 × its own hold, so a frame-step hold of 2 vsyncs at 33.3 ms is not dropped; discarded presents count too), p99 frame time and the physical footprint; `memory up to frame N` gives resident and Metal-allocated memory. Memory that steps up at level loads and stays flat in between is not a leak.
- **Power**: `power up to frame N` covers the window since the previous one, for the whole process: CPU energy in watts and per frame (`task_energy` from `TASK_POWER_INFO_V2`, CPU only; compare per frame when one build holds the frame rate better), CPU time (100% = one core) and the share on performance cores, wakeups per second, the thermal state (0 nominal … 3 critical; changes are also logged as `front end: thermal state → n`), and the two guest threads that yielded most with how many of those yields the back-off turned into sleeps (`DM_YIELD_BACKOFF`, see [docs/development.md](../development.md)). A thread yielding hundreds of thousands of times per window with few back-off sleeps is a busy spin. `residency set up to frame N` gives residency-set commits and their time, what was added by source line of `nvn_mtl.m` (count, MB), removals, how many draw passes began with a full barrier or without one (`DM_NVN_BARRIER=game`), and segment commits: a source line adding gigabytes per window is allocation churn. It ends with render-target traffic per frame: attachment bytes loaded and stored, passes that load and store everything, and the stores `DM_NVN_UNWRITTEN_DC` saved (the same counters as the TSV's `@rt_load_mb` / `@rt_store_mb`). `threads up to frame N` gives guest-thread CPU time in ms per second by Switch priority band (≤ 44, the main thread's level and above; 45–59; ≥ 60) and the three busiest threads with their priority; it shows what `DM_QOS_MAP` would move. On the Mac the same lines appear; energy readings vary by tens of percent between identical runs, so compare runs interleaved and over the same scene.
- **Screen recordings** from the user are useful for timing and visual symptoms; extract frames with `ffmpeg -ss <t> -i rec.mov -frames:v 1 out.png`.

## Offline pipeline link check

Pipeline link errors depend only on the two libraries, so all vertex / pixel pairs can be checked on the Mac after a shader build, without the game: for each line of `shader_pairs.tsv`, load `<vs>_b.metallib` and `<ps>_b.metallib` from `b-<V>/`, build a vertex descriptor from the vertex function's `vertexAttributes` (format from each attribute's type), set colour attachment formats from the `[[color(n)]]` outputs in the pixel shader's `_b.metal` (uint / int / float formats to match), add a depth format when it writes `[[depth(...)]]`, and call `newRenderPipelineStateWithDescriptor:`. Count failures by message. Mario: 8,712 linked / 331 failed before the vertex output padding, 9,043 / 0 after, and 14,603 / 0 for the v0 + 1.2.1 tables. Pipelines built this way have the default blend state and sample count, so this checks linking only.

## Intermittent rendering glitches

A glitch that comes and goes between frames or runs needs a detector before bisection, or "no glitch in these 16 frames" proves nothing. What worked for Mario's fountain panels:

1. Screenshot a dense frame range (`DM_NVN_SHOT=$(seq -s, 4430 10 4590):x_%d.png`) and score each frame automatically. The first metric (texture busyness) missed the flat translucent variant of the glitch; a metric tuned to its shape (long vertical straight edges in a sky region) separated glitch frames (≈1.0) from clean ones (≈0.3) reliably. Look at a few frames by eye before trusting a metric.
2. Run a control with nothing changed to measure how often the glitch appears per run.
3. Bisect with `DM_NVN_SKIP_FS` (up to 16 fragment shader keys per run) until one draw remains, then `DM_NVN_HILITE` it to see its geometry.
4. Dump that draw's inputs across frames (`DM_NVN_CBDUMP` + `DM_NVN_CBDUMP_KEY`). If every input is byte-identical between good and bad frames, the difference is on the GPU side: follow the textures it samples (`DM_NVN_TEXINFO`, `DM_NVN_TEXRAW`) to whatever writes them.
5. For a GPU-side simulation, trace its state on the GPU timeline (`DM_NVN_T2T_TRACE`), re-implement the shader step in numpy with the logged uniform updates (the `Y update_ub` lines print the first four floats), and compare frame by frame. Frames that disagree show which input the GPU really used; for the fountain, a coefficient of −1 instead of 1.81 explained every bad texel and led to the missing intra-encoder barrier.
