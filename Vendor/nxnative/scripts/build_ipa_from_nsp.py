#!/usr/bin/env python3
# Unsigned IPA straight from the NSPs: identify the game (title ID → game profile dm/games/<id>/) → extract (nx_extract) → rewrite the code modules (patch_nso.py)
#   → (profiles with shader_glslc_capture: capture the shaders the game compiles at run time, by booting it in the Mac host for a few seconds) → split out the shaders and check them against the profile's tables (shader_split.py)
#   (a Vulkan game with shader_vk_capture, Super Mario Galaxy, boots the same way to capture the SPIR-V shaders it generates)
#   → iOS shader libraries (dmsh_build.py) → build_ipa.sh. A Vulkan game (profile key graphics vulkan: Hades) skips the NVN shader steps: vk_shaders.py translates its SPIR-V shaders instead. A game with no matching profile is surveyed (<NSP folder>/<title ID>_survey/survey.md), then gets a provisional profile guessed from
#   the survey (<NSP folder>/<title ID>_build/profile/<title ID>/, outside the repository, found through DM_GAMES_DIR) and a best-effort IPA that may not boot; SURVEY_ONLY / --survey-only stops after the survey.
# Two ways to run it: open this file in Spyder and press F5 (it uses the values under "Settings" below; an empty NSP folder or prod.keys is asked for at run time);
#   or in a terminal: python3 scripts/build_ipa_from_nsp.py <NSP folder> -k <prod.keys> [options] (values given on the command line override "Settings", -h lists every option;
#   without keyboard input a missing value is not asked for but reported as an error; exit code 0 on success, 1 on error, 130 when interrupted). Command-line options entered in Spyder's run configuration work the same way.
# Uses only three things: this repository, a folder holding one game's NSPs (the base game plus the updates listed in the profile's shader_versions are required; DLC NSPs, when present, are packed too and unlock the add-on content already in the game), and prod.keys.
# Every intermediate file is under <id>_build/ in the NSP folder: extract/ (the extracted game files, kept for the next build unless KEEP_EXTRACTED / --no-keep-extracted), aoc/ (each DLC's RomFS by index), tools/ (nx_extract, and the Mac host for a run-time shader capture), patched_*/, shader/ (shader package and caches, kept so the next build is fast), logs/ (each step's full output), tmp/, ipa/. The finished IPA also goes to the NSP folder by default.
# The rewrite, the shader split and the iOS (or Vulkan) shaders are reused when all their inputs are as at their last successful run (the game files, the tools, the profile, Xcode and spirv-cross: fingerprint() keys beside their output).
# The shader translator is the in-repo dm/gfx/tools/dmsh_xlate_bin (the build whose fingerprints match dmsh_chain.lock; a rebuilt dll has different fingerprints and dmsh_build refuses it).
# The Python running this file needs lz4, capstone and fonttools; also needed: Xcode, xcodegen, .NET SDK 10, zstd, spirv-cross. A first run takes 2 (Metroid Dread) to 10 minutes (Breath of the Wild: 5 of them the shader split), longer when shader libraries must be compiled; a repeat run with unchanged inputs takes about 20 s (Metroid Dread), mostly packing the IPA. Key values are never printed.
# The console shows one line per stage ([k/n] stage, with a bar, done/total, percent, elapsed time and ETA where the work can be counted); the tools' own output goes only to logs/ (PROGRESS / --progress).
import collections, ctypes, getpass, hashlib, os, re, shlex, shutil, struct, subprocess, sys, tempfile, threading, time, types, zlib
from pathlib import Path

# ---- Settings ----
NSP_DIR = '/Volumes/T7/nsp/The Legend of Zelda Tears of the Kingdom/'                            # folder holding the NSPs (empty = ask at run time)
PROD_KEYS = '/Users/f2pgod/My Drive/Python_Scripts/nsp_check/prod.keys'                          # path of prod.keys (empty = ask at run time)
PACKAGE = ''                            # version packed into the IPA (empty = the profile's package; Mario 'v327680' i.e. 1.2.1, or 'v0')
OUT_IPA = ''                            # output IPA (empty = <the profile's ipa> in the NSP folder)
APP_NAME = ''                           # app name on the home screen (empty = the game name in the base NSP)
BUNDLE_ID = ''                          # the app's bundle ID (empty = org.nxnative.<base game title ID in lowercase>)
KEEP_EXTRACTED = True                   # keep the extracted game files after the IPA is built (saves extraction next time; as big as the game files); False deletes them
DM_ENV_FILE = ''                        # optional: environment switches for a diagnostic build (one KEY=VALUE per line)
SURVEY_ONLY = False                     # a game with no profile in dm/games: only write the survey, no provisional profile and no IPA
PROFILE_OUT = ''                        # where a provisional profile goes (empty = <NSP folder>/<title ID>_build/profile; the profile is <this>/<title ID>/)
ALLOW_DAMAGED = False                   # a damaged NSP (files failing the NCA's hash check: an incomplete copy or a broken download) stops the build; True writes those files as read and goes on
PROVISIONAL = False                     # build from a provisional profile even when dm/games has one for the game (to test the guesses; the profile goes to PROFILE_OUT / <id>_build/profile)
HEAP_CHECK = True                       # a provisional profile whose game has virtual address memory and sets a heap: boot it on the Mac until its heap request (a few seconds) to size the heap region
HEAP_CHECK_SECS = 30                    # the longest heap check (it stops at the first heap request, or HEAP_CHECK_NNMAIN_SECS into nnMain without one)
HEAP_CHECK_NNMAIN_SECS = 5

PROGRESS = 'auto'                       # stage lines on the console: 'bar' (one line per stage, redrawn in place), 'lines' (a plain line every BEAT seconds), 'off' (only each stage's start and end); 'auto' = bar in a terminal or Spyder, lines when the output goes to a file
BEAT = 30                               # seconds between progress lines in 'lines' mode
TOOL_PATHS = ['/opt/homebrew/bin', '/usr/local/bin', '/usr/local/share/dotnet', os.path.expanduser('~/.dotnet')]   # GUI apps such as Spyder do not get the shell's PATH


class BuildError(Exception):
    pass


def clock():
    return time.strftime('%H:%M:%S')


def say(msg):
    PROG.say(f'[{clock()}] {msg}')


def hms(s):   # seconds → m:ss, or h:mm:ss from an hour on
    s = int(s); h, m = divmod(s // 60, 60)
    return f'{h}:{m:02d}:{s % 60:02d}' if h else f'{m}:{s % 60:02d}'


def size_unit(v):   # (unit, divisor) for a byte count
    return next(((u, d) for u, d in (('GB', 2**30), ('MB', 2**20)) if v >= d), ('KB', 2**10))


def amount(v, unit=''):   # a count, or a byte size when unit is 'B'
    if unit == 'B':
        u, d = size_unit(v); return f'{v / d:.1f} {u}'
    return f'{v:,}' + (f' {unit}' if unit else '')


# ---- Progress on the console ----
class Progress:
    """The console view of the build: one line per stage, "[k/n] stage · step", with a bar, done/total, percent, elapsed time and ETA when the work can be counted, else a spinner and the elapsed time.
    Modes: bar = the line is redrawn in place (a terminal, Spyder's console) and replaced by a ✓ line when the stage ends; lines = a plain line when a stage or step starts, every BEAT seconds and at the end
    (for output piped to a file); off = only each stage's start and end lines. Counters come from set(), or from a poll function that runs in a thread of its own (it may walk a big folder) and returns set()'s arguments.
    Messages go through say(), which prints them above the live line"""
    SPIN, BLOCKS, POLL = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏', ' ▏▎▍▌▋▊▉', 1.0

    def __init__(self, mode='off'):
        self.mode, self.lock, self.k, self.n, self.cur, self.shown, self.ticker = mode, threading.RLock(), 0, 0, None, 0, None

    def plan(self, n):   # the next n stages are numbered 1..n
        with self.lock: self.k, self.n = 0, n

    def add(self, n):   # n more stages than planned (one that turns out to be needed: a provisional profile's heap check)
        with self.lock: self.n += n

    def stage(self, name, poll=None, step='', **kw):
        """Start the next stage, ending the current one. kw: set()'s arguments"""
        with self.lock:
            self.end()
            self.k += 1; now = time.time()
            self.cur = types.SimpleNamespace(name=name, step=step, unit='', total=None, done=None, est=False, note='', t0=now, hist=collections.deque(), beat=now, pstop=None)
            if self.mode != 'bar': self._out(f'[{clock()}] [{self.k}/{self.n}] {name}' + (f' · {step}' if step else '') + ' …')
            self.set(**kw)
        if poll: self.watch(poll)
        if self.mode != 'off' and not self.ticker:
            self.ticker = threading.Thread(target=self._tick, daemon=True); self.ticker.start()

    def watch(self, poll):
        """Call poll() over and over until the stage ends or watch() is called again (None: stop); poll returns set()'s arguments, or None to leave the line as it is"""
        with self.lock:
            st = self.cur
            if not st: return
            if st.pstop: st.pstop.set()
            st.pstop = stop = threading.Event()
        if poll: threading.Thread(target=self._poll, args=(st, poll, stop), daemon=True).start()

    def set(self, done=None, total=None, step=None, unit=None, est=None, note=None):
        """done / total: the count of the current step (unit 'B' = bytes); est: total is an estimate (shown with ~); note: shown after the count;
        step: the step within the stage (a new step starts with no count and restarts the ETA)"""
        with self.lock:
            st = self.cur
            if not st: return
            if step is not None and step != st.step:
                st.step, st.done, st.total, st.unit, st.est, st.note, st.beat = step, None, None, '', False, '', time.time(); st.hist.clear()
                if self.mode == 'lines': self._out(f'[{clock()}] [{self.k}/{self.n}] {st.name} · {step} …')
            if unit is not None: st.unit = unit
            if total is not None: st.total = total
            if est is not None: st.est = est
            if note is not None: st.note = note
            if done is not None:
                st.done = done; now = time.time(); st.hist.append((now, done))
                while len(st.hist) > 2 and st.hist[1][0] < now - 60: st.hist.popleft()   # the ETA follows the rate of the last minute

    def end(self, summary='', ok=True):
        """End the current stage with a ✓ (or ✗) line: its elapsed time and a summary"""
        with self.lock:
            st, self.cur = self.cur, None
            if not st: return
            if st.pstop: st.pstop.set()
            self._out(f'[{clock()}] {"✓" if ok else "✗"} [{self.k}/{self.n}] {st.name} ({hms(time.time() - st.t0)})' + (f': {summary}' if summary else ''))

    def say(self, msg):
        with self.lock: self._out(msg)

    def close(self, ok=True):   # end the current stage and stop drawing
        with self.lock: self.end(ok=ok); self.mode = 'off'

    def _count(self, st):   # "1.9/~5.0 GB", "1,203/19,592 shaders", "2,301 files" (no total); '' without a count
        if st.done is None: return ''
        if not st.total: return amount(st.done, st.unit)
        t = '~' if st.est else ''
        if st.unit == 'B':
            u, d = size_unit(st.total); return f'{st.done / d:.1f}/{t}{st.total / d:.1f} {u}'
        return f'{st.done:,}/{t}{st.total:,}' + (f' {st.unit}' if st.unit else '')

    def _eta(self, st):   # seconds left at the rate of the last minute; None while unknown
        if not st.total or len(st.hist) < 2: return None
        (t1, d1), (t2, d2) = st.hist[0], st.hist[-1]
        if t2 - t1 < 3 or d2 <= d1: return None
        return max(st.total - st.done, 0) * (t2 - t1) / (d2 - d1)

    def _fields(self, st):   # (head, fraction done or None, count, note, times)
        head = f'[{self.k}/{self.n}] {st.name}' + (f' · {st.step}' if st.step else '')
        frac = min(st.done / st.total, 0.99) if st.total and st.done is not None else None   # 100 % only when the stage ends
        eta = self._eta(st)
        return head, frac, self._count(st), st.note, hms(time.time() - st.t0) + (f' · ETA {hms(eta)}' if eta is not None else '')

    def _line(self, st, width):
        head, frac, count, note, times = self._fields(st)
        head = f'{self.SPIN[int(time.time() * 8) % len(self.SPIN)]} {head}'
        pct = f'{frac * 100:.0f}%' if frac is not None else ''
        for note in (note, ''):   # a narrow console loses the note first, then the bar
            rest = '  '.join(x for x in (' · '.join(x for x in (count, note) if x), times) if x)
            barw = min(20, width - len(f'{head}  {pct:>4}  {rest}') - 3)   # the bar takes what the console's width leaves, up to 20 cells; none below 8
            if frac is None or barw >= 8: break
        if frac is not None and barw >= 8:
            cells = frac * barw; full = int(cells); part = int((cells - full) * 8)
            pct = ('█' * full + (self.BLOCKS[part] if part else '')).ljust(barw, '░') + f' {pct:>4}'
        return '  '.join(x for x in (head, pct, rest) if x)[:width - 1]

    def _out(self, text):   # a whole line above the live one (the caller holds the lock)
        if self.shown: sys.stdout.write('\r' + ' ' * self.shown + '\r'); self.shown = 0
        print(text, flush=True)
        if self.mode == 'bar' and self.cur: self._draw()

    def _draw(self):
        line = self._line(self.cur, shutil.get_terminal_size((80, 24)).columns)   # Spyder has no size to ask, and a line that wraps there cannot be redrawn: 80 columns
        sys.stdout.write('\r' + line + ' ' * max(self.shown - len(line), 0)); sys.stdout.flush()
        self.shown = len(line)

    def _tick(self):
        while self.mode != 'off':
            time.sleep(0.25 if self.mode == 'bar' and not in_ipython() else 1)   # Spyder's console gets fewer redraws
            with self.lock:
                st = self.cur
                if not st: continue
                try:
                    if self.mode == 'bar': self._draw()
                    elif self.mode == 'lines' and time.time() - st.beat >= BEAT:
                        st.beat = time.time(); head, frac, count, note, times = self._fields(st)
                        self._out(f'[{clock()}] {head}: ' + ', '.join(x for x in (f'{frac * 100:.0f}%' if frac is not None else '', count, note, times) if x))
                except Exception: pass   # progress never stops the build, and one bad line does not stop the next

    def _poll(self, st, poll, stop):
        while not stop.is_set():
            t, step = time.time(), st.step
            try: r = poll()
            except Exception: r = None   # progress never stops the build
            with self.lock:   # a count read for a step that ended meanwhile is dropped
                if r and self.cur is st and not stop.is_set() and ('step' in r or st.step == step): self.set(**r)
            stop.wait(max(self.POLL, (time.time() - t) * 5))   # a slow poll (a walk over tens of thousands of files) runs less often


PROG = Progress()


def progress_mode(want):   # auto: redraw in a terminal or in Spyder (IPython handles \r), plain lines when the output goes to a file or a pipe
    if want in ('bar', 'lines', 'off'): return want
    if want != 'auto': raise BuildError(f'PROGRESS / --progress must be auto, bar, lines or off: {want}')
    return 'bar' if in_ipython() or (sys.stdout and sys.stdout.isatty()) else 'lines'


def tree_size(d):   # (files, bytes) under d; (0, 0) when it does not exist yet
    n = b = 0; todo = [str(d)]
    while todo:
        try: it = os.scandir(todo.pop())
        except OSError: continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False): todo.append(e.path)
                    else: n += 1; b += e.stat(follow_symlinks=False).st_size
                except OSError: pass
    return n, b


def in_ipython():   # Spyder (and Jupyter) run this file inside IPython: input works there, and sys.exit must not be called (it piles an error onto the console)
    import builtins
    return hasattr(builtins, '__IPYTHON__')


def ask(prompt, what):   # what: what is missing, for the error message
    if not in_ipython() and not (sys.stdin and sys.stdin.isatty()):
        raise BuildError(f'{what} not given and there is no keyboard input to ask for it: give it on the command line (-h for usage)')
    s = input(prompt).strip().strip('"').strip("'").replace('\\ ', ' ')   # dragged-in paths come quoted or with escaped spaces
    return os.path.expanduser(s)


def run(cmd, log, env=None, cwd=None, on_line=None):
    """Run a subprocess with all its output written to log (the console shows the stage line instead: the shader build alone emits tens of thousands of compiler warnings);
    stop on a non-zero exit, printing the log's last lines. on_line: called with every output line (build_ipa.sh's own step lines move its stages on)"""
    cmd = [str(c) for c in cmd]
    log.parent.mkdir(parents=True, exist_ok=True)
    tail = collections.deque(maxlen=40)
    p = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', bufsize=1)
    try:
        with open(log, 'w') as f:
            for line in p.stdout:
                f.write(line); tail.append(line)
                if on_line:
                    try: on_line(line.rstrip('\n'))
                    except Exception: pass   # progress never stops the build
        p.wait()
    except KeyboardInterrupt:
        p.terminate(); p.wait(); raise
    if p.returncode:
        PROG.end(ok=False)
        PROG.say(f'---- last lines of {log} ----\n' + ''.join(tail).rstrip('\n'))
        tool = Path(cmd[1] if cmd[0] in (sys.executable, 'bash') else cmd[0]).name
        raise BuildError(f'{tool} exit code {p.returncode} (full output: {log})')


def build_id(nso):
    with open(nso, 'rb') as f:
        f.seek(0x40); return f.read(16).hex()


def rmtree(p):
    if p.is_symlink() or p.is_file(): p.unlink()
    elif p.exists(): shutil.rmtree(p)


def build_nx_extract(repo, work, logs, env):
    """Build nx_extract into <work>/tools/nx_extract/. It is built in a temporary folder and copied over: with an apostrophe in the output path (e.g. "Bowser's Fury") MSBuild's conditions break,
    LibHac.dll and the executable are not copied, and the build still reports success"""
    nx = work / 'tools/nx_extract/nx_extract'
    with tempfile.TemporaryDirectory(prefix='nx_extract_') as t:
        run(['dotnet', 'build', repo / 'dm/tools/nx_extract', '-c', 'Release', '-o', t, '-v', 'quiet', '-nologo'], logs / 'nx_extract_build.log', env=env)
        if not (Path(t) / 'nx_extract').exists(): raise BuildError(f'nx_extract built without an executable (see {logs / "nx_extract_build.log"})')
        rmtree(nx.parent); shutil.copytree(t, nx.parent)
    return nx


def swap_in(tmp, dst):   # swap the new output in as a whole (the old one is untouched on failure)
    rmtree(dst); tmp.rename(dst)


def free_gb(p):
    while not p.exists(): p = p.parent
    return shutil.disk_usage(p).free / 2**30


# ---- NSP identification ----
def pfs0_names(path):   # NSP = PFS0: list the file names inside
    with open(path, 'rb') as f:
        h = f.read(16)
        if h[:4] != b'PFS0': return []
        n, st = struct.unpack_from('<II', h, 4)
        ent, strs = f.read(n * 0x18), f.read(st)
    return [strs[o:strs.index(b'\0', o)].decode(errors='replace') for o in (struct.unpack_from('<I', ent, i * 0x18 + 0x10)[0] for i in range(n))]


def title_of(path):   # [title ID] in the file name, else the ticket name (the first 16 digits of the rights ID = title ID)
    m = re.search(r'\[([0-9A-Fa-f]{16})\]', path.name)
    if m: return int(m.group(1), 16)
    for n in pfs0_names(path):
        if re.match(r'[0-9A-Fa-f]{32}\.tik$', n): return int(n[:16], 16)
    return None


def version_of(path):
    m = re.search(r'\[v(\d+)\]', path.name)
    return int(m.group(1)) if m else None


def scan_nsps(nsp_dir):
    """Group by game: {application title ID: {'base': path, 'updates': [(version, path)], 'dlc': [(title ID, version, path)]}}"""
    fams, unknown = {}, []
    for p in sorted([*nsp_dir.glob('*.nsp'), *nsp_dir.glob('*.xci')]):   # a base game may be a cartridge dump (.xci: Monster Hunter Rise); nx_extract reads its secure partition
        if p.stat().st_size == 0:   # an empty file left by an incomplete download (the Zelda BotW folder holds a 0-byte DLC NSP next to the complete (1).nsp)
            say(f'skipping an empty file: {p.name}'); continue
        tid = title_of(p)
        if tid is None: unknown.append(p); continue
        low = tid & 0xFFF   # base …000, update …800, DLC = base + 0x1000 + index
        app = tid if low == 0 else tid & ~0xFFF if low == 0x800 else (tid & ~0xFFF) - 0x1000
        f = fams.setdefault(app, {'base': None, 'updates': [], 'dlc': []})
        if low == 0: f['base'] = p
        elif low == 0x800: f['updates'].append((version_of(p), p))
        else: f['dlc'].append((tid, version_of(p), p))
    if len(fams) == 1 and len(unknown) == 1 and next(iter(fams.values()))['base'] is None:   # a base game converted from a cartridge may have neither tags nor a ticket; build IDs are checked afterwards
        next(iter(fams.values()))['base'] = unknown[0]
    if not fams: raise BuildError(f'no NSP with a readable title ID in {nsp_dir}')
    if len(fams) > 1: raise BuildError('more than one game in the folder, keep one game per folder: ' + ', '.join(f'{t:016X}' for t in fams))
    app, fam = next(iter(fams.items()))
    if fam['base'] is None: raise BuildError(f'no base game NSP found in {nsp_dir} (title ID {app:016X})')
    return app, fam


def pick_nsps(fam, versions):
    """For each wanted version, (base game, update or None): v0 = the base game alone, v<N> = the base game + the update with version number N"""
    say(f'base: {fam["base"].name}')
    out = {}
    for ver in versions:
        if ver == 'v0': out[ver] = (fam['base'], None); continue
        n = int(ver[1:])
        upd = [u for v, u in fam['updates'] if v == n] or [u for v, u in fam['updates'] if v is None and len(fam['updates']) == 1]   # without a version in the file name only a single update is accepted; build IDs are checked afterwards
        if not upd: raise BuildError(f'no NSP for update {ver} (the game profile needs these versions: {", ".join(versions)})')
        say(f'update {ver}: {upd[0].name}'); out[ver] = (fam['base'], upd[0])
    return out


def can_clone(d):   # whether this volume supports APFS clones (nx_extract uses them to save space; without them it writes full copies)
    a, b = d / '.clone_test', d / '.clone_test2'
    try:
        a.write_bytes(b'x'); rmtree(b)
        return ctypes.CDLL(None, use_errno=True).clonefile(str(a).encode(), str(b).encode(), 0) == 0
    finally:
        rmtree(a); rmtree(b)


# ---- Survey of a new game (when no game profile matches) ----
def survey(nsp_dir, app, fam, keys, repo, py, env):
    work = nsp_dir / f'{app:016X}_survey'; logs, ex = work / 'logs', work / 'extract'
    say(f'no game profile for {app:016X}: surveying first')
    PROG.plan(4)   # nx_extract, the manifest, the code modules (reading them, then the rewrite-site census), the imports
    PROG.stage('survey: build nx_extract')
    nx = build_nx_extract(repo, work, logs, env)
    ups = sorted(fam['updates'], key=lambda u: u[0] or 0)
    upd = ups[-1][1] if ups else None
    tmp = work / 'extract.partial'; rmtree(tmp)
    def listed():   # files in the manifest so far
        try: return {'done': (tmp / 'romfs_manifest.tsv').read_bytes().count(b'\n'), 'unit': 'files'}
        except OSError: return None
    PROG.stage('survey: RomFS manifest', poll=listed)
    say(f'extracting the code modules and a RomFS manifest (no game files written) → {ex}')
    run([nx, keys, fam['base'], upd or '-', tmp, '--manifest'] + (['--allow-damaged'] if ALLOW_DAMAGED else []), logs / 'extract.log')
    swap_in(tmp, ex)
    PROG.stage('survey: code modules', step='reading')
    xlog = (logs / 'extract.log').read_text(errors='replace')
    dv = re.search(r'display version (\S+)', xlog)
    F = pg.facts_of(ex / 'ExeFS', ex / 'romfs_manifest.tsv'); mods, rom = F['mods'], F['romfs']   # dm/games/profile_guess.py: what the code modules and the RomFS show
    R = [f'# Survey: {nacp.name(ex / "control.nacp") or "?"} ({app:016X})', '', f'- display version: {dv.group(1) if dv else "?"}', f'- base: `{fam["base"].name}` ({fam["base"].stat().st_size / 2**30:.2f} GB)']
    R += [f'- update: `{p.name}` (v{v}, {p.stat().st_size / 2**30:.2f} GB){" (used for this survey)" if p == upd else ""}' for v, p in ups]
    R += [f'- DLC: `{p.name}` ({p.stat().st_size / 1024:.0f} KB{", licence only, no content" if p.stat().st_size < 1 << 20 else ""})' for _, _, p in fam['dlc']]

    # Code modules
    R += ['', '## Code modules', '', '| module | what | build ID | text / ro / data (MB) | bss (MB) |', '|---|---|---|---|---|']
    R += [f'| {n} | {m["kind"]} | `{m["bid"]}` | ' + ' / '.join(f'{z / 2**20:.1f}' for z in m['sizes']) + f' | {m["bss"] / 2**20:.1f} |' for n, m in mods.items()]
    if F['program'] is not None: R.append(f'\n- main.npdm program ID: `{F["program"]:016X}`')
    if (ex / 'ExeFS/main.npdm').exists(): R.append(f'- system resource: {F["sysres"] / 2**20:.0f} MB')
    R.append(f'- SDK: {", ".join(sorted(F["sdkver"])) or "?"} (Mario: 16_2_0 / 16_2_12; D2R ≈ 12)')
    R.append('- SDK components: ' + (', '.join(sorted(F['comps'])) or '—'))
    if F['unity']: R.append('- Unity: ' + ', '.join(sorted(F['unity'])))
    R.append('- engine and API markers: ' + ('; '.join(f'{k} ({", ".join(v)})' for k, v in F['markers'].items()) or '—'))
    extra = [n for n in mods if n not in ('main', 'sdk', 'rtld')]

    # RomFS manifest
    R += ['', f'## RomFS: {rom["n"]} files, {rom["bytes"] / 2**30:.2f} GB', '', '| top level | files | GB |', '|---|---|---|']
    R += [f'| {t} | {n} | {rom["topb"][t] / 2**30:.2f} |' for t, n in rom['tops'].most_common(20)]
    R += ['', '| header magic | files | GB |', '|---|---|---|'] + [f'| {m} | {n} | {rom["magb"][m] / 2**30:.2f} |' for m, n in rom['mags'].most_common()]
    R += ['', 'extensions: ' + ', '.join(f'`{e}` {n}' for e, n in rom['exts'].most_common(20))]

    # Rewrite-site census and SDK surface
    R += ['', '## Rewrite-site census (insn_census.py)', '', '```']
    census = [ex / 'ExeFS' / n for n in mods if n != 'rtld']   # rtld is replaced by the host
    for i, m in enumerate(census):
        PROG.set(step=f'rewrite sites in {m.name}', done=i, total=len(census), unit='modules')
        run([py, repo / 'dm/tools/insn_census.py', m], logs / f'census_{m.name}.log', env=env)
        R += (logs / f'census_{m.name}.log').read_text(errors='replace').rstrip().splitlines()
    R += ['```', '', '## Imports vs host hooks (nso_syms.py)', '', '```']
    PROG.stage('survey: imports vs host hooks')
    run([py, repo / 'dm/tools/nso_syms.py', repo / 'dm/host', '-', ex / 'ExeFS'], logs / 'nso_syms.log', env=env)
    PROG.end()
    R += (logs / 'nso_syms.log').read_text(errors='replace').rstrip().splitlines() + ['```']

    # What it means for a port
    G = pg.guess(F)   # the provisional profile's keys (write_profile writes the same)
    vulkan = G.get('graphics', ('nvn',))[0] == 'vulkan'
    notes = []
    if not vulkan and 'nvnBootstrapLoader' not in mods['main']['imports']: notes.append('main imports neither nvnBootstrapLoader nor Vulkan functions: the host implements only NVN and Vulkan')
    if vulkan: notes.append(f'{G["graphics"][1]}; the NVN shader steps are skipped' + (', and its shaders are captured by booting it on the Mac (no SPIR-V file in the RomFS)' if 'shader_vk_capture' in G else ''))
    if extra: notes.append(f'modules besides main / sdk: {", ".join(f"{n} ({mods[n]["kind"]})" for n in extra)}; the provisional profile loads {G["modules"][0]} (load order main, subsdk*, sdk)')
    if rom['mags']['UnityFS'] or 'Unity IL2CPP' in F['markers']: notes.append('Unity: the shaders are Shader objects in UnityFS bundles and data.unity3d, which shader_split.py reads through unityfs.py (written for Unity 2020.3\'s Switch format, also read for 2017.4 and 2022.3; check other Unity versions first)')
    if F['glslc']: notes.append(f'main has {F["glslc"]} GLSLC compiler output magics (0x19866891): ' + ('the shaders are compiled into main (13 Sentinels, the KTGL games): shader_main_glslc on' if 'shader_main_glslc' in G else 'not its shaders, the RomFS has shader containers (Engage)'))
    if not (rom['mags']['BNSH'] or rom['mags']['BAHS']) and not rom['mags']['UnityFS'] and not vulkan and 'shader_main_glslc' not in G:
        notes.append('no BNSH / BAHS at the top level: the shaders are inside compressed or other containers or in main, and must be located first')
    major = {v.split('_')[0] for v in F['sdkver']}
    if not major: notes.append('no SDK version string found')
    elif major != {'16'}: notes.append(f'SDK {"/".join(sorted(major))}, not Mario\'s 16: NVN object sizes, API version and service layouts differ by SDK (the host was converted from D2R\'s SDK 12 to SDK 16 sizes); check them one by one per docs/agents/03')
    if any(l.split()[:1] == ['nn::ro'] for l in R): notes.append('imports nn::ro (loads NRO modules at run time): not in the host')
    if fam['dlc']: notes.append('DLC present: it is extracted into the IPA and the host reports the indices as owned and mounts them; check that the host hooks every aoc / fs add-on content call main imports')
    R += ['', '## What it means for a port', ''] + [f'- {n}' for n in notes or ['—']]
    R += ['', '## Provisional profile keys (dm/games/profile_guess.py)', '', 'What the game files decide; mem_used follows the rewrite, and a game with virtual address memory that sets a heap gets a heap check on the Mac (scripts/build_ipa_from_nsp.py heap_check).', '', '```']
    R += [f'{k}\t{v}' + (f'\t# {why}' if why else '') for k, (v, why) in G.items()] + ['```']
    R += ['', 'Next steps: docs/agents (02 survey, 03 bring-up).']
    (work / 'survey.md').write_text('\n'.join(R) + '\n')
    for n in notes: say(n)
    say(f'survey report: {work / "survey.md"}')
    upv = ups[-1][0] if ups else None
    return {'F': F, 'name': nacp.name(ex / 'control.nacp') or '', 'display': dv.group(1) if dv else '?', 'version': 'v0' if upd is None else f'v{upv or 1}'}


# ---- Provisional profile (a game with no profile in dm/games) ----
def ipa_name(name, app):   # "The Legend of Zelda: Link's Awakening" → TheLegendOfZeldaLinksAwakening.ipa: ASCII words joined, apostrophes dropped; the title ID when nothing ASCII is left
    words = re.findall(r'[A-Za-z0-9]+', name.replace("'", '').replace('’', ''))
    words = [w.capitalize() if w.isupper() and len(w) > 1 else w[:1].upper() + w[1:] for w in words]
    return (''.join(words)[:48] or f'{app:016X}') + '.ipa'


EMPTY_TABLES = {   # the shader tables before (or, for a Vulkan game, instead of) a shader split: the chain version (dmsh_chain.py) and build_ipa.sh read them
    'shader_map.tsv': '# kind: evidence  provisional profile: filled by the shader split (a Vulkan game\'s SPIR-V shaders go through the Vulkan layer and leave it empty)\npackage\tindex\tstage\tdm_ctl_sha16\tsource\n',
    'shader_facts.tsv': '# Answer table for translation queries (generated by dm/gfx/tools/shader_split.py, do not edit): key <TAB> fact JSON. Provisional profile: filled by the shader split\n',
    'shader_pairs.tsv': '# kind: evidence  vertex / pixel shader pairs within BNSH variations (generated by dm/gfx/tools/shader_split.py, do not edit): vertex key <TAB> pixel key\n',
    'shader_map.tsv.conflicts.tsv': '# kind: evidence  control-section key conflict rulings: empty\ndm_ctl_sha16\tchosen_pc\tclass\tcandidates\trecords\n',
    'bf_want.tsv': '# generated\n',
    'pso_manifest.tsv': '# Prewarm seed list (shipped in the app, next to shader_map.tsv). Rows: S<TAB>shader key<TAB>stage / R<TAB>render pipeline key (pso_skey hex) / C<TAB>compute shader key.\n'
                        '# Provisional profile: empty until recorded on the Mac (DM_PSO_MANIFEST=off DM_PSO_RECORD).\n'}


def write_profile(pdir, app, f):
    """A provisional game.tsv (+ the empty tables) from the survey, in pdir (outside the repository). An existing game.tsv is kept, so it can be edited by hand; delete it to regenerate.
    The keys the game files decide come from dm/games/profile_guess.py (each written under its reason): the graphics API, the modules to load, the shader sources, the memory partition,
    the SDK 8 / 10 font and NVN API, engine presets; the rest keeps game.py's defaults until the heap check (below) or a developer sets it"""
    pdir.mkdir(parents=True, exist_ok=True)
    if (pdir / 'game.tsv').exists():
        say(f'reusing the provisional profile: {pdir / "game.tsv"} (delete it to regenerate from the survey)')
        return
    F = f['F']; G, R = pg.guess(F), F['romfs']
    groups, seen = [], {'main', 'other'}
    for d, _ in R['dirs'].most_common(24):   # shader package groups by RomFS top-level folder (this only names the package files; anything else goes to "other")
        g = re.sub(r'[^a-z0-9]', '', d.lower())[:16] or 'g'
        while g in seen: g += 'x'
        seen.add(g); groups.append(f'/{d}/={g}')
    # stored in the IPA uncompressed: file types that are mostly compressed already (Yaz0 / zstd / zip / media headers; Super Mario Odyssey's 3.8 GB of .szs took the zip 1 h 40 min to deflate again)
    # and big files (mostly compressed formats without a known header)
    store = sorted(e for e, b in R['extb'].items() if e and R['exts'][e] and (b / R['exts'][e] >= 1 << 20 or 2 * R['extc'][e] >= R['exts'][e]))
    name = f['name'] or f'{app:016X}'
    mods = G['modules'][0].split()
    T = '\t'
    def key(k, default=None):   # a key with the reason profile_guess.py gives for it above it; None when neither the guess nor a default has one
        v, why = G[k] if k in G else (default, '')
        return [] if v is None else ([f'# {why}'] if why else []) + [f'{k}{T}{v}']
    L = ['# Provisional game profile (generated by scripts/build_ipa_from_nsp.py from the survey with dm/games/profile_guess.py, not checked by hand)',
         f'# {name}, SDK {F["sdk"] or "?"}, survey {f["survey"]}', '',
         '# ---- Identity ----', f'title_id{T}{app:016X}', f'program_id{T}{(F["program"] or app):016X}', '',
         '# ---- App ----', f'name{T}{name}', f'ipa{T}{ipa_name(name, app)}', f'app_category{T}public.app-category.games', *key('pad_layout', 'simple'), *key('op_mode'), '',
         '# ---- Versions ----', T.join(['build', f['version'], f['display']] + [f'{m}={F["mods"][m]["bid"]}' for m in mods]), f'package{T}{f["version"]}', f'shader_versions{T}{f["version"]}', '',
         '# ---- Files ----', *key('modules'), f'romfs_marker{T}{R["biggest"][1]}', f'zip_store{T}{":".join(store + [".metallib"])}', '',
         '# ---- Graphics ----', *key('graphics', 'nvn'), *key('shader_vk_capture'), *key('shared_font'), *key('device_api'), '',
         '# ---- Memory ----', *key('mem_reserve'), *key('mem_alias'), *key('mem_stack'), *key('app_pool'), '',
         '# ---- NVN driver constant segments (Mario\'s values, the translator\'s built-in layout, unless the engine says otherwise) ----',
         *key('nvn_tex_base', '0x20'), *key('nvn_tex_slots', '32'), f'nvn_samp_base{T}0x568', f'nvn_img_base{T}0x120', f'nvn_img_slots{T}8', f'nvn_ssbo_bases{T}vs=0x110 ps=0x510 cs=0x310', '',
         '# ---- Shader split ----', f'shader_groups{T}{" ".join(groups) or "/=romfs"}', f'shader_note{T}{name} shaders (provisional profile)',
         *key('shader_main_glslc'), *key('shader_separable'), *key('shader_glslc_capture')]
    (pdir / 'game.tsv').write_text('\n'.join(L) + '\n', encoding='utf-8')
    for n, text in EMPTY_TABLES.items(): (pdir / n).write_text(text)
    say(f'wrote a provisional game profile: {pdir / "game.tsv"}')
    for k in ('graphics', 'modules', 'shader_vk_capture', 'shader_main_glslc', 'shader_glslc_capture', 'mem_reserve', 'op_mode'):
        if k in G and G[k][1]: say(f'  {k} {G[k][0]}: {G[k][1]}')


# ---- Stage reuse: a stage whose inputs are all as at its last successful run keeps its output ----
def files_under(d):   # (relative path, stat) of every file under d, sorted; [] when it does not exist
    out, todo = [], [str(d)]
    while todo:
        try: it = os.scandir(todo.pop())
        except OSError: continue
        with it:
            for e in it:
                if e.is_dir(follow_symlinks=False): todo.append(e.path)
                else: out.append((os.path.relpath(e.path, d), e.stat(follow_symlinks=False)))
    return sorted(out, key=lambda x: x[0])


def fingerprint(*items, env=None):
    """sha256 over a stage's inputs. Items: ('files', paths) = names and content (a missing file counts too); ('tree', folder) = relative path and size of every file under it
    (a RomFS: check_build pins its version, so names and sizes stand for its content); ('stat', folder) = relative path, size and mtime of every file under it (the translator's binaries);
    ('cmd', argv) = a tool's version output (run with env); anything else = its repr"""
    h = hashlib.sha256()
    for it in items:
        kind, v = it if isinstance(it, tuple) and len(it) == 2 and it[0] in ('files', 'tree', 'stat', 'cmd') else ('repr', it)
        h.update(f'\0{kind}\0'.encode())
        if kind == 'files':
            for p in map(Path, v):
                h.update(p.name.encode() + b'\0')
                try: h.update(hashlib.sha256(p.read_bytes()).digest())
                except OSError: h.update(b'missing')
        elif kind in ('tree', 'stat'):
            for rel, st in files_under(v): h.update(f'{rel}\0{st.st_size}\0{st.st_mtime_ns if kind == "stat" else ""}\n'.encode())
        elif kind == 'cmd':
            try: r = subprocess.run(v, env=env, capture_output=True, text=True, timeout=120); h.update((r.stdout + r.stderr).encode())
            except (OSError, subprocess.TimeoutExpired): h.update(b'missing')
        else: h.update(repr(v).encode())
    return h.hexdigest()


def reused(keyfile, key):   # the note the stage's last successful run wrote beside its key ('' when none), or None when the key differs or is missing
    try: k, _, note = keyfile.read_text().partition('\n')
    except OSError: return None
    return note.strip() if k == key else None


def tool_files(repo):   # what the shader stages run: dm/gfx/tools' scripts and the lock of the translator's fingerprints, the profile reader, the iOS compile convention, the NSO reader
    return sorted((repo / 'dm/gfx/tools').glob('*.py')) + [repo / p for p in ('dm/gfx/tools/dmsh_chain.lock', 'dm/games/game.py', 'dm/ios/tools/ios_metal.py', 'dm/verify/nsoimg.py')]


def profile_files(g):   # every file of the game profile (game.tsv and its tables)
    return sorted(p for p in g.dir.iterdir() if p.is_file())


# ---- Steps ----
def check_prereqs(env, xlate):
    missing = [m for m in ('lz4.block', 'capstone', 'fontTools') if not _importable(m)]
    if missing: raise BuildError(f'the current Python ({sys.executable}) is missing modules: {", ".join(missing)} (pip install lz4 capstone fonttools)')
    tools = {'xcodebuild': 'Xcode', 'xcodegen': 'brew install xcodegen', 'dotnet': '.NET SDK 10', 'zstd': 'brew install zstd', 'spirv-cross': 'brew install spirv-cross', 'make': 'Xcode'}
    gone = [f'{t} ({how})' for t, how in tools.items() if not shutil.which(t, path=env['PATH'])]
    if gone: raise BuildError('tools not found: ' + ', '.join(gone))
    if not xlate.exists(): raise BuildError(f'the shader translator is missing from the repository: {xlate}')


def _importable(m):
    try: __import__(m); return True
    except ImportError: return False


def extracted(log):   # (files, bytes) from the summary lines nx_extract wrote to log ("<dir>: N files X MB, ..." for ExeFS + RomFS; older logs have "| N files X MB"); None without them
    try: rows = re.findall(r'[:|] (\d+) files ([\d.]+) MB', log.read_text(errors='replace'))
    except OSError: return None
    return (sum(int(n) for n, _ in rows), int(sum(float(mb) for _, mb in rows) * 2**20)) if rows else None


def extract(nx, keys, ex, name, base, upd, cmp_dir, logs, g):
    dst, marker, log = ex / name, g.get('romfs_marker'), logs / f'extract_{name}.log'
    if (dst / 'ExeFS' / 'main').exists() and (dst / 'RomFS' / marker).exists():
        PROG.stage(f'extract {name}')
        say(f'reusing the extracted {name}: {dst}')
        check_build(dst, name, g)
        PROG.end('reused')
        return dst
    tmp = ex / (name + '.partial'); rmtree(tmp)
    last = extracted(log)   # the last extraction of this version (its log is about to be overwritten) has the exact size; without one, the NSPs' size is the estimate
    def poll():
        n, b = tree_size(tmp); return {'done': b, 'note': f'{n:,} files'}
    PROG.stage(f'extract {name}', poll=poll, unit='B', total=last[1] if last else base.stat().st_size + (upd.stat().st_size if upd else 0), est=not last)
    run([nx, keys, base, upd or '-', tmp] + ([cmp_dir] if cmp_dir else []) + (['--allow-damaged'] if ALLOW_DAMAGED else []), log)
    check_build(tmp, name, g); swap_in(tmp, dst)
    n, b = extracted(log) or (0, 0)
    PROG.end(f'{n:,} files, {amount(b, "B")}')
    return dst


def extract_aoc(nx, keys, work, app, fam, logs):
    """DLC NSPs in the folder → <id>_build/aoc/<index>/ (the RomFS of each one's data NCA; index = title ID − base − 0x1000). The host reports these indices as owned and mounts them (DM_AOC_DIR).
    Returns None without DLC. DLC packages are small (121 KB each for Engage, the content itself is in the update), so they are extracted again every time"""
    if not fam['dlc']: return None
    tmp = work / 'aoc.partial'; rmtree(tmp)
    best = {}   # when one DLC comes in several copies, take the highest version, and the largest of equal versions
    for tid, ver, p in fam['dlc']:
        k = (ver or 0, p.stat().st_size)
        if tid not in best or k > best[tid][0]: best[tid] = (k, p)
    PROG.stage('extract DLC')
    for i, (tid, (_, p)) in enumerate(sorted(best.items())):
        idx = tid - app - 0x1000
        PROG.set(step='extracting', done=i, total=len(best), unit='DLC')
        say(f'DLC index {idx}: {p.name}')
        run([nx, keys, '--aoc', p, tmp / str(idx)], logs / f'aoc_{idx}.log')
    swap_in(tmp, work / 'aoc')
    PROG.end(f'{len(best)} DLC')
    return work / 'aoc'


def check_build(d, name, g):   # every module's build ID must be the one registered in the profile's build row
    want = g.builds()[name]
    for m, bid in want.items():
        if m == 'display': continue
        got = build_id(d / 'ExeFS' / m)
        if got != bid: raise BuildError(f'{m} build ID {got} is not the {name} registered in game profile {g.id} ({bid})')


def rewrite(py, repo, exe_dir, out, env, logs, g):
    """patch_nso.py on every code module at once (each writes its own <module>.* files, main also the boot list, all the same build_src.sha256 line), each with its log.
    Reused when the modules, patch_nso.py, the boot lists, its switches and capstone are as at the last successful rewrite (Monster Hunter Rise's main alone takes 5.5 min)"""
    import capstone
    mods = g.words('modules')
    PROG.stage('rewrite', step='checking the inputs')
    kf = out.with_name(out.name + '.key')
    key = fingerprint(('files', [repo / 'dm/tools/patch_nso.py'] + [exe_dir / m for m in mods] + sorted((repo / 'dm/data').glob('bootlist_*.tsv'))), mods, capstone.__version__,
                      {k: env.get(k) for k in ('DM_PATCH_FRONT', 'DM_PRIVATE_GATES')})
    if all((out / f'{m}.patched.bin').is_file() for m in mods) and reused(kf, key) is not None:
        PROG.end(f'{", ".join(mods)}, reused (inputs unchanged)'); return
    tmp = out.with_name(out.name + '.partial'); rmtree(tmp); tmp.mkdir(parents=True); logs.mkdir(parents=True, exist_ok=True)
    PROG.set(step=', '.join(mods), done=0, total=len(mods), unit='modules')
    procs, logf = {}, {}
    try:
        for m in mods:
            logf[m] = open(logs / f'rewrite_{m}.log', 'w')
            procs[m] = subprocess.Popen([str(py), str(repo / 'dm/tools/patch_nso.py'), str(exe_dir / m), str(tmp), m], env=dict(env, DM_RULESET='native'), stdout=logf[m], stderr=subprocess.STDOUT)
        left = list(mods)
        while left:
            for m in [m for m in left if procs[m].poll() is not None]:
                left.remove(m); PROG.set(done=len(mods) - len(left))
                if procs[m].returncode:
                    log = logs / f'rewrite_{m}.log'; logf[m].close()
                    PROG.end(ok=False)
                    PROG.say(f'---- last lines of {log} ----\n' + ''.join(collections.deque(open(log, errors='replace'), maxlen=40)).rstrip('\n'))
                    raise BuildError(f'patch_nso.py exit code {procs[m].returncode} on {m} (full output: {log})')
            time.sleep(0.2)
    finally:   # an error or an interrupt stops the other rewrites
        for p in procs.values():
            if p.poll() is None: p.terminate(); p.wait()
        for f in logf.values(): f.close()
    rmtree(kf); swap_in(tmp, out); kf.write_text(f'{key}\n')
    PROG.end(', '.join(mods))


GLSLC_SECS = 30   # the longest capture run: Three Houses compiles its 9 shaders within 1.2 s of boot, and the run stops as soon as every file the profile names is there


def glslc_wanted(g):   # the capture files the profile's shader map was built from (column 5: /glslc_capture/<name>#GLSLC@…); None without any (a provisional profile)
    try: t = g.table('shader_map.tsv').read_text(errors='replace')
    except OSError: return None
    return set(re.findall(r'/glslc_capture/([0-9a-f]{16}\.glslc)#', t)) or None


def glslc_done(d):   # capture files written whole: a GLSLC output (magic 0x19866891) holds its own length at +0x44
    out = set()
    try: names = [n for n in os.listdir(d) if n.endswith('.glslc')]
    except OSError: return out
    for n in names:
        try: b = (d / n).read_bytes()
        except OSError: continue
        if len(b) >= 0x48 and b[:4] == b'\x91\x68\x86\x19' and struct.unpack_from('<I', b, 0x44)[0] == len(b): out.add(n)
    return out


def build_mac_host(repo, out, env, logs, g):
    """The Mac host for the profile, built into out: dm/host's own compile line (make -n) with the output moved, since make takes no target path with spaces and dm/host/dmhost may be another build's"""
    host = repo / 'dm/host'
    run(['make', '-s', f'GAME={g.id}', f'gen/{g.id}/game_profile.h', 'gen/vpx/libvpx.a'], logs / 'mac_host_make.log', env=env, cwd=host)
    dry = subprocess.run(['make', '-n', '-B', f'GAME={g.id}', 'dmhost'], env=env, cwd=host, capture_output=True, text=True)
    line = next((l for l in dry.stdout.splitlines() if ' -o dmhost ' in l), None)
    if not line: raise BuildError(f'make -n gave no compile line for the Mac host: {dry.stderr.strip()[-500:]}')
    cmd = shlex.split(line); cmd[cmd.index('-o') + 1] = out
    out.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, logs / 'mac_host_build.log', env=env, cwd=host)
    return out


def boot_mac(host, patched, henv, rd, log, secs, done=lambda: False):
    """Boot the game in the Mac host (headless and silent: no DM_WINDOW, no DM_AUDIO) with its output in log, until done() says so, the host exits, or secs pass;
    then SIGTERM (the host's graceful exit), a kill 5 s later. Returns the host's exit code, None when it was still running"""
    t0 = time.time()
    with open(log, 'w') as f:
        p = subprocess.Popen([str(host), str(patched)], env=henv, cwd=rd, stdout=f, stderr=subprocess.STDOUT)
        try:
            while not done() and p.poll() is None and time.time() - t0 < secs: time.sleep(0.25)
        finally:
            rc = p.poll()
            if rc is None:
                p.terminate()
                try: p.wait(5)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
    return rc


def host_stopped(log, rc, secs):   # a capture run whose host stopped by itself before the capture was complete: the game crashed or gave up, and the IPA will too (a provisional profile's IPA is still built)
    PROG.say(f'[RED] the game stopped after {secs:.0f} s in the Mac host (exit {rc}): its shaders are incomplete and the IPA will not get further; ---- last lines of {log} ----\n'
             + ''.join(collections.deque(open(log, errors='replace'), maxlen=12)).rstrip('\n'))


def capture_glslc(repo, dirs, pkg_ver, patched, work, env, logs, g):
    """Profiles with shader_glslc_capture on (Fire Emblem: Three Houses): the game compiles some shaders at run time with its own GLSLC, so no game file holds them. The game boots in the Mac host
    (headless and silent) with DM_GLSLC_CAPTURE (dm/host/hle_glslc.c), which writes each output to <version dir>/glslc_capture, where shader_split.py reads them; the outputs are the same on every run.
    dirs: {shader version: its extraction}; a folder that already holds every file the profile's shader map names is reused"""
    want = glslc_wanted(g)
    todo = [v for v, d in dirs.items() if not (glslc_done(d / 'glslc_capture') >= want if want else glslc_done(d / 'glslc_capture'))]
    PROG.stage('GLSLC capture')
    if not todo:
        say(f'reusing the captured run-time shaders: {", ".join(str(d / "glslc_capture") for d in dirs.values())}')
        PROG.end('reused'); return
    if todo != [pkg_ver]: raise BuildError(f'the run-time shader capture runs the packed version {pkg_ver}\'s code; {", ".join(v for v in todo if v != pkg_ver)} needs a capture of its own')
    PROG.set(step='building the Mac host')
    host = build_mac_host(repo, work / 'tools/dmhost', env, logs, g)
    d = dirs[pkg_ver]; cap, rd, log = d / 'glslc_capture.partial', work / 'tmp/glslc_run', logs / 'glslc_capture.log'
    rmtree(cap); rmtree(rd)
    for s in ('save', 'temp'): (rd / s).mkdir(parents=True)
    # everything the run writes stays in <id>_build (DM_ROOT is already there): a fresh save and temporary storage, no shader libraries yet, the profile's shader map (the host looks beside itself by default)
    henv = dict(env, DM_ROMFS=str(d / 'RomFS'), DM_SAVE=str(rd / 'save'), DM_TEMP=str(rd / 'temp'), DM_MSL_DIR=str(rd / 'msl'), DM_NVN_SHMAP=str(g.table('shader_map.tsv')), DM_GLSLC_CAPTURE=str(cap))
    PROG.set(step='booting the game', done=0, total=len(want) if want else None, unit='shaders')
    say(f'booting the game in the Mac host to capture the shaders it compiles at run time → {d / "glslc_capture"}')
    t0 = time.time()
    def done():   # every file the profile names is there (Three Houses: within its first frames)
        got = glslc_done(cap); PROG.set(done=len(got & want if want else got))
        return bool(want and got >= want)
    rc = boot_mac(host, patched, henv, rd, log, GLSLC_SECS, done)
    got = glslc_done(cap)
    if rc is not None and not (want and got >= want): host_stopped(log, rc, time.time() - t0)
    if not got or (want and not got >= want):
        PROG.end(ok=False)
        PROG.say(f'---- last lines of {log} ----\n' + ''.join(collections.deque(open(log, errors='replace'), maxlen=40)).rstrip('\n'))
        raise BuildError(f'captured only {len(got)} run-time shaders'
                         + (f', the profile needs {len(want)}' if want else '') + f' (host output: {log})')
    if want and got - want: say(f'[RED] captured files the profile\'s shader map does not name: {", ".join(sorted(got - want))}')
    swap_in(cap, d / 'glslc_capture'); rmtree(rd)
    PROG.end(f'{len(got)} shaders in {hms(time.time() - t0)}')


VK_CAPTURE_SECS = 120   # the longest Vulkan capture run: Super Mario Galaxy creates its 3,089 modules within 6 s of its first one (about 15 s after boot on an M4 Pro)


def vk_wanted(g):   # the SPIR-V keys the profile's vk_capture.tsv lists; None without the table (a provisional profile)
    try: keys = {l.strip() for l in g.table('vk_capture.tsv').read_text().splitlines() if l.strip() and not l.startswith('#')}
    except OSError: return None
    return keys or None


def vk_done(d):   # keys of the whole SPIR-V files in a capture folder (the host writes each under a temporary name and renames it)
    try: names = os.listdir(d)
    except OSError: return set()
    return {n[:-4] for n in names if n.endswith('.spv') and len(n) == 20}


def capture_vk(repo, d, patched, work, env, logs, g):
    """Profiles with shader_vk_capture on (Super Mario Galaxy): the game generates its SPIR-V shaders at run time (Hagi's GX shaders, from its pipeline database), so no game file holds them.
    The game boots in the Mac host (headless and silent, no shader library) with DM_VK_CAPTURE (dm/gfx/vk/hle_vk.m), which writes each module to <version dir>/vk_capture, where vk_shaders.py
    reads them with the RomFS; the modules are the same on every run. The run stops once every key the profile's vk_capture.tsv lists is there; without the table, once none has been added for 20 s.
    A folder that already holds every listed key is reused"""
    want, out = vk_wanted(g), d / 'vk_capture'
    PROG.stage('Vulkan shader capture')
    if want and vk_done(out) >= want:
        say(f'reusing the captured run-time shaders: {out}'); PROG.end('reused'); return out
    PROG.set(step='building the Mac host')
    host = build_mac_host(repo, work / 'tools/dmhost', env, logs, g)
    cap, rd, log = d / 'vk_capture.partial', work / 'tmp/vk_run', logs / 'vk_capture.log'
    rmtree(cap); rmtree(rd); cap.mkdir(parents=True)
    for x in ('save', 'temp', 'msl'): (rd / x).mkdir(parents=True)
    # everything the run writes stays in <id>_build (DM_ROOT is already there): a fresh save and temporary storage, an empty shader library folder (pipelines fail, the game still creates every module)
    henv = dict(env, DM_ROMFS=str(d / 'RomFS'), DM_SAVE=str(rd / 'save'), DM_TEMP=str(rd / 'temp'), DM_MSL_DIR=str(rd / 'msl'), DM_VK_CAPTURE=str(cap))
    PROG.set(step='booting the game', done=0, total=len(want) if want else None, unit='shaders')
    say(f'booting the game in the Mac host to capture the SPIR-V shaders it generates at run time → {out}')
    t0 = time.time(); last = {'n': 0, 't': t0}
    def done():   # every listed key is there; without the table, none has been added for 20 s
        got = vk_done(cap); n = len(got & want if want else got); PROG.set(done=n)
        if n != last['n']: last['n'], last['t'] = n, time.time()
        return bool((want and got >= want) or (not want and n and time.time() - last['t'] > 20))
    rc = boot_mac(host, patched, henv, rd, log, VK_CAPTURE_SECS, done)
    got = vk_done(cap)
    if rc is not None and not (want and got >= want): host_stopped(log, rc, time.time() - t0)
    if not got or (want and not got >= want):
        PROG.end(ok=False)
        PROG.say(f'---- last lines of {log} ----\n' + ''.join(collections.deque(open(log, errors='replace'), maxlen=40)).rstrip('\n'))
        raise BuildError(f'captured only {len(got)} run-time shaders'
                         + (f', the profile needs {len(want)}' if want else '') + f' (host output: {log})')
    if want and got - want: say(f'[RED] captured shaders the profile\'s vk_capture.tsv does not list: {len(got - want)}')
    swap_in(cap, out); rmtree(rd)
    PROG.end(f'{len(got)} shaders in {hms(time.time() - t0)}')
    return out


# ---- A provisional profile after the rewrite: mem_used and the heap check ----
def set_keys(g, changes, section):
    """Write keys into a provisional game.tsv, each under its reason, in a section of their own at the end; earlier rows of the same keys (and the reason line right above one) go.
    Returns the profile reloaded"""
    p = g.dir / 'game.tsv'; old = p.read_text(encoding='utf-8').splitlines(); out = []
    for line in old:
        if line.split('\t', 1)[0] in changes:
            if out and out[-1].startswith('# ') and not out[-1].startswith('# ----'): out.pop()
            continue
        out.append(line)
    out += ['', f'# ---- {section} ----'] + [x for k, (v, why) in changes.items() for x in ([f'# {why}'] if why else []) + [f'{k}\t{v}']]
    p.write_text('\n'.join(out) + '\n', encoding='utf-8')
    return type(g)(g.dir)


def provisional_prep(py, repo, env, logs, g):
    """What a provisional profile needs before a Mac host can be built for it: the shader tables (empty until a shader split fills them; an older provisional profile may lack some)
    and the chain version header (the host and build_ipa.sh read it; a Vulkan game never runs the NVN chain that writes it)"""
    for n, text in EMPTY_TABLES.items():
        if not g.table(n).exists(): g.table(n).write_text(text)
    run([py, repo / 'dm/gfx/tools/dmsh_chain.py', '--header'], logs / 'dmsh_chain.log', env=env)


def refine_after_rewrite(g, ex_dir, patched):
    """Keys of a provisional profile that need the rewritten modules: mem_used (dm/games/profile_guess.py), for a game without virtual address memory that sizes its heap as pool − used memory"""
    if any(k == 'mem_used' for k, _ in g.rows) or pg.npdm(ex_dir / 'ExeFS/main.npdm')[0]: return g
    used = pg.mem_used(patched, g.words('modules'))
    if not used: return g
    say(f'mem_used {used:#x}: the rewritten modules are larger than the 64 MB of used memory the game takes off the pool for its heap')
    return set_keys(g, {'mem_used': (f'{used:#x}', 'the rewritten modules are larger than the default 64 MB of used memory (Age of Calamity: 66.6 MB → 72 MB)')}, 'After the rewrite')


def heap_checked(g):   # the heap check's stamp in the profile ("# heap check: ..."): its result is kept, later runs skip it
    return any(l.startswith('# heap check: ') for l in (g.dir / 'game.tsv').read_text(encoding='utf-8').splitlines())


def heap_check(repo, d, patched, work, env, logs, g):
    """The heap check of a provisional profile whose game has virtual address memory (an NPDM system resource) and sets a heap (dm/games/profile_guess.py heap_check_needed):
    its heap request decides the alias / heap split of the guest block, and only a run shows it (Wonder asks for 1.44 GB, Tears of the Kingdom for 2.09 GB, which Engage's split
    has no room for). The game boots in the Mac host (headless and silent, no shader libraries) until its first heap request is answered or fails, or until it has run
    HEAP_CHECK_NNMAIN_SECS in nnMain without one (Engage sets none): a few seconds. The keys go into the profile (profile_guess.py heap_signals), which is stamped"""
    PROG.stage('heap check')
    host, rd, log = work / 'tools/dmhost', work / 'tmp/heap_run', logs / 'heap_check.log'
    PROG.set(step='building the Mac host'); build_mac_host(repo, host, env, logs, g)
    rmtree(rd)
    for x in ('save', 'temp', 'msl'): (rd / x).mkdir(parents=True)
    # a fresh save and temporary storage, no shader libraries (only the heap request matters), the profile's shader map
    henv = dict(env, DM_ROMFS=str(d / 'RomFS'), DM_SAVE=str(rd / 'save'), DM_TEMP=str(rd / 'temp'), DM_MSL_DIR=str(rd / 'msl'), DM_NVN_SHMAP=str(g.table('shader_map.tsv')))
    PROG.set(step='booting the game')
    t0, seen = time.time(), {}
    def done():   # the first heap request answered (or refused for good), or nnMain running for a while without one
        try: text = log.read_text(errors='replace')
        except OSError: return False
        if 'SetHeapSize OOM' in text or '[mem] heap ' in text: return True
        if '>>> nnMain' in text: seen.setdefault('nnmain', time.time())
        return time.time() - seen.get('nnmain', time.time()) > HEAP_CHECK_NNMAIN_SECS
    rc = boot_mac(host, patched, henv, rd, log, HEAP_CHECK_SECS, done)
    text = log.read_text(errors='replace'); rmtree(rd)
    sig = {k: v for k, v in pg.heap_signals(text, g).items() if g.get(k, '') != v[0]}
    for k, (v, why) in sig.items(): say(f'heap check: {k} {v}: {why}')
    m = re.search(r'\[mem\] heap ([0-9.]+ GB)', text)
    how = ('the heap request did not fit' if 'SetHeapSize OOM' in text else f'heap {m.group(1)}' if m else 'no heap set' if '>>> nnMain' in text
           else f'the host stopped before nnMain (exit {rc})' if rc is not None else 'no nnMain within the time limit')
    if sig: g = set_keys(g, sig, 'Heap check on the Mac')
    p = g.dir / 'game.tsv'; p.write_text(p.read_text(encoding='utf-8') + f'\n# heap check: {time.strftime("%Y-%m-%d")}, {how}' + (f'; set {", ".join(sig)}' if sig else '') + '\n', encoding='utf-8')
    if not m and '>>> nnMain' not in text and 'SetHeapSize OOM' not in text:   # stopped before any heap request: worth a look before the IPA is tried
        PROG.say(f'[RED] heap check: {how}; ---- last lines of {log} ----\n' + ''.join(collections.deque(open(log, errors='replace'), maxlen=20)).rstrip('\n'))
    PROG.end(f'{how} in {hms(time.time() - t0)}' + (f'; set {", ".join(sig)}' if sig else ''))
    return type(g)(g.dir)


def data_rows(b):   # a table's data rows (without # comment lines: the header changes with the shader_split.py version, not with the game files)
    return [l for l in b.splitlines() if not l.startswith(b'#')]


def split_shaders(py, repo, roms, mains, pkg, env, logs, g, provisional=False):
    """The shader split into pkg, checked against the profile's tables. Returns its key (None for a provisional profile or damaged files, which never reuse it): the package is reused
    when the tools, the profile and each version's main, RomFS (paths and sizes) and run-time capture are as at the last successful split"""
    names = ('shader_map.tsv', 'shader_facts.tsv', 'shader_pairs.tsv')
    PROG.stage('shader split', step='checking the inputs')   # then a spinner: shader_split.py writes the package and the tables only at the end
    kf = pkg.with_name(pkg.name + '.key')
    key = None if provisional or ALLOW_DAMAGED else fingerprint(('files', tool_files(repo)), ('files', profile_files(g)),
        *[x for r, m in zip(roms, mains) for x in (('files', [m]), ('tree', r), ('files', sorted((r.parent / 'glslc_capture').glob('*.glslc'))))])
    if key and pkg.is_dir() and (note := reused(kf, key)) is not None:
        PROG.end(f'{note}, reused (inputs unchanged)'); return key
    PROG.set(step='splitting')
    tmp = pkg.with_name(pkg.name + '.partial'); rmtree(tmp); (tmp / 'tables').mkdir(parents=True)
    run([py, repo / 'dm/gfx/tools/shader_split.py', ','.join(map(str, roms)), ','.join(map(str, mains)), tmp / 'pkg'] + [tmp / 'tables' / n for n in names], logs / 'shader_split.log', env=env)
    m = re.search(r'shaders: (\d+) \(', (logs / 'shader_split.log').read_text(errors='replace'))
    if provisional:   # a provisional profile takes the tables as they come
        for n in names: shutil.copyfile(tmp / 'tables' / n, g.table(n))
    else:
        # Data rows byte-identical to the profile's = the same game files the tables were built from; if not, stop (the profile's tables are left alone). Only data rows are compared: the header of Engage's profile tables was written by an older shader_split
        diff = [n for n in names if data_rows((tmp / 'tables' / n).read_bytes()) != data_rows(g.table(n).read_bytes())]
        if diff: raise BuildError(f'the split shader tables differ from game profile {g.id}\'s: {", ".join(diff)} (game files not the versions the profile registers?)')
    rmtree(kf); swap_in(tmp / 'pkg', pkg); rmtree(tmp)
    note = f'{int(m.group(1)):,} shaders' if m else ''
    if key: kf.write_text(f'{key}\n{note}\n')
    PROG.end(note)
    return key


class ShaderWatch:
    """Progress of dmsh_build.py, read from the files it writes (it prints nothing until it ends). It works in three phases:
    the cache check (a hit restores <key>_b.json into the iOS output b-<chain>/, a miss writes <key>.bin into its temporary folder dmsh_* under WORK),
    the translation of the misses (<key>.spv in the temporary folder), and the compile, which takes the keys in a fixed order (sorted, the vertex shaders with pixel pairs last)
    and writes <key>_b.json again for every miss and every pixel shader: the furthest key written so far tells how far it got"""
    def __init__(self, g, ios, tmp):
        keys = set()
        for ln in open(g.table('shader_map.tsv'), errors='replace'):   # the keys dmsh_build.py builds: column 4 of the rows from a shader package or from main
            c = ln.rstrip('\n').split('\t')
            if len(c) > 4 and (c[0].endswith('.bin') or c[0].startswith('main.rodata@')): keys.add(c[3])
        pairs = {ln.split()[0] for ln in open(g.table('shader_pairs.tsv'), errors='replace') if ln.strip() and not ln.startswith('#')}
        order = sorted(keys - pairs) + sorted(keys & pairs)
        self.pos, self.n = {k: i for i, k in enumerate(order)}, len(order)
        chain = re.search(r'#define DMSH_CHAIN "(.*)"', g.table('dmsh_chain.h').read_text()).group(1)
        self.out, self.tmp, self.t0, self.t1, self.w = ios / f'b-{chain}', tmp, time.time(), None, None
        self.hits, self.fin, self.top = set(), set(), -1

    def written(self, keys, since):   # those of keys whose <key>_b.json in the iOS output was written after since
        found = set()
        try:
            with os.scandir(self.out) as it:
                for e in it:
                    if e.name.endswith('_b.json') and e.name[:-7] in keys and e.stat().st_mtime > since: found.add(e.name[:-7])
        except OSError: pass
        return found

    def __call__(self):
        if not self.w:   # dmsh_build.py's temporary folder: the dmsh_* under WORK made since it started
            self.w = max((d for d in self.tmp.glob('dmsh_*') if d.stat().st_birthtime >= self.t0 - 2), key=lambda d: d.stat().st_birthtime, default=None)
        try: ext = collections.Counter(os.path.splitext(x)[1] for x in os.listdir(self.w)) if self.w else collections.Counter()
        except OSError: ext = collections.Counter()
        if self.t1 is None:
            self.hits |= self.written(self.pos.keys() - self.hits, self.t0 - 2)
            if len(self.hits) + ext['.bin'] < self.n and not ext['.spv'] and not ext['.metal']:
                return {'step': 'cache check', 'done': len(self.hits) + ext['.bin'], 'total': self.n, 'unit': 'shaders', 'note': f'{len(self.hits):,} cached'}
            self.t1 = time.time()   # the cache check is over: from now on a <key>_b.json is written by the compile
        if ext['.bin'] and not ext['.metal'] and ext['.spv'] < ext['.bin']:
            return {'step': 'translating', 'done': ext['.spv'], 'total': ext['.bin'], 'unit': 'shaders'}
        new = self.written(self.pos.keys() - self.fin, self.t1)
        self.fin |= new; self.top = max([self.top] + [self.pos[k] for k in new])
        return {'step': 'compiling' if ext['.bin'] else 'finishing', 'done': max(len(self.fin), self.top + 1), 'total': self.n, 'unit': 'shaders',
                'note': f'{ext[".bin"]:,} not cached' if ext['.bin'] else ''}


def toolchain():   # the compilers' versions, part of the shader stages' keys
    return ('cmd', ['xcodebuild', '-version']), ('cmd', ['spirv-cross', '--revision'])


def build_shaders(py, repo, sh, xlate, env, logs, g, provisional=False, split_key=None):
    """The iOS shader libraries (dmsh_build.py). Reused when the split's key (split_key; None never reuses) and the chain's tools, translator binaries, profile and compilers
    are as at the last successful build: dmsh_build.py would only restore every shader from its cache (63,000 for Breath of the Wild: about 100 s)"""
    ios, log = sh / 'ios', logs / 'dmsh_build.log'
    PROG.stage('iOS shaders')
    if provisional:
        PROG.set(step='chain header')
        run([py, repo / 'dm/gfx/tools/dmsh_chain.py', '--header'], logs / 'dmsh_chain.log', env=env)   # the profile's chain version header (dmsh_build checks it)
    chain = re.search(r'#define DMSH_CHAIN "(.*)"', g.table('dmsh_chain.h').read_text()).group(1)
    libs = ios / f'b-{chain}'; kf = libs.with_name(libs.name + '.key')
    if split_key:
        PROG.set(step='checking the inputs')
        key = fingerprint(split_key, ('files', tool_files(repo)), ('stat', xlate.parent), ('files', profile_files(g)), *toolchain(), str(xlate),
                          {k: env.get(k) for k in ('MAIN', 'XLATE_DEBUG', 'XLATE_REDUCED')}, env=env)
        if next(libs.glob('*_b.metallib'), None) and (note := reused(kf, key)) is not None:
            PROG.end(f'{note}, reused (inputs unchanged)'); return ios
    else: key = None
    rmtree(kf)
    try: PROG.watch(ShaderWatch(g, ios, Path(env['WORK'])))
    except Exception: pass   # progress never stops the build (a missing table is dmsh_build.py's to report)
    run([py, repo / 'dm/gfx/tools/dmsh_build.py', sh / 'pkg', sh / 'cache'], log, env=dict(env, XLATE=str(xlate), IOSOUT=str(ios)))
    PROG.watch(None)
    if provisional:
        PROG.set(step='c1 guard')
        run([py, repo / 'dm/gfx/tools/c1_guard.py', sh / 'cache' / f'b-{chain}', g.table('c1_full.tsv')], logs / 'c1_guard.log', env=env)   # shaders whose c1 reads are not proven bounded
    n = sum(1 for _ in libs.glob('*_b.metallib')) if libs.is_dir() else 0
    if n == 0: raise BuildError(f'no iOS shader libraries in {libs}')
    say(f'{n} iOS shader libraries ({libs})')
    t = log.read_text(errors='replace')
    m, c = re.search(r'shaders (\d+): ok (\d+)', t), re.search(r'shader cache: hit (\d+)', t)
    note = ''
    if m:
        total, ok = int(m.group(1)), int(m.group(2))
        failed = f'; {total - ok:,} failed, reasons at the end of {log}' if ok < total else ''
        note = f'{ok:,} of {total:,} shaders ready{failed}'
        PROG.end(f'{ok:,} of {total:,} shaders ready' + (f' ({int(c.group(1)):,} from the cache)' if c else '') + failed)
    else: PROG.end()
    if key: kf.write_text(f'{key}\n{note}\n')
    return ios


def build_vk_shaders(py, repo, roots, sh, env, logs, g, reuse=True):
    """A Vulkan game's SPIR-V shaders (roots: the RomFS, and a run-time capture folder) → one Metal library each for the Mac (sh/vk/) and the iPhone (sh/ios/vk/, what build_ipa.sh takes from MSL_IOS),
    replacing the NVN split and chain build. Reused when the roots (paths and sizes), the tools, the profile and the compilers are as at the last successful run (reuse False: never).
    Otherwise the old output is deleted first, so a failed run leaves nothing for build_ipa.sh to pick up; vk_shaders.py's temporary files go to WORK (on the NSP folder's volume)"""
    ios = sh / 'ios'; kf = ios / 'vk.key'
    PROG.stage('Vulkan shaders', step='checking the inputs')
    key = fingerprint(*[('tree', r) for r in roots], ('files', tool_files(repo)), ('files', profile_files(g)), *toolchain(), env=env) if reuse else None
    if key and (ios / 'vk/vk_shaders.metallib').is_file() and (note := reused(kf, key)) is not None:
        PROG.end(f'{note}, reused (inputs unchanged)'); return ios
    PROG.set(step='translating')
    rmtree(kf); rmtree(sh / 'vk'); rmtree(ios / 'vk')
    run([py, repo / 'dm/gfx/tools/vk_shaders.py', *roots, sh, '--ios', ios], logs / 'vk_shaders.log', env=dict(env, TMPDIR=env['WORK']))
    if not (ios / 'vk/vk_shaders.metallib').is_file(): raise BuildError(f'no iOS Vulkan shader library in {ios / "vk"}')
    m = re.search(r'iphoneos: (\d+)', (logs / 'vk_shaders.log').read_text(errors='replace'))
    note = f'{int(m.group(1)):,} shaders for the Mac and iOS' if m else ''
    if key: kf.write_text(f'{key}\n{note}\n')
    PROG.end(note)
    return ios


class IpaWatch:
    """Progress of build_ipa.sh, from its step lines ("[time] generate Gen/ …", "xcodebuild …", "pack IPA …", then pack_ipa.py's "pack: N entries, X bytes") and the files it writes:
    the CompileC lines in xcodebuild's build.log (one per source file: Gen/src, Gen/main/main.c, Gen/embed.S and the app's Sources), then the bytes of the archive pack_ipa.py is
    writing (<IPA>.partial, renamed at the end). Its two halves are the stages "app build" and "IPA pack" """
    XCODE = {'CompileC': 'compiling', 'Ld': 'linking', 'CpResource': 'copying resources', 'CompileAssetCatalogVariant': 'asset catalog', 'ProcessInfoPlistFile': 'Info.plist'}

    def __init__(self, repo, w, out_ipa):
        self.ios, self.o, self.part = repo / 'dm/ios', w / 'build/ios/pkg', out_ipa.with_name(out_ipa.name + '.partial')
        self.last = out_ipa.stat().st_size if out_ipa.is_file() else None   # the last IPA's size: the expected size of the new archive
        self.state, self.t, self.off, self.compiled, self.what, self.total, self.most, self.lock = None, 0, 0, 0, '', None, 0, threading.Lock()

    def line(self, line):   # a line of build_ipa.sh's output
        s = re.sub(r'^\[[\d:]+\] ', '', line)
        with self.lock:   # a poll sees a step change whole
            if s.startswith('generate Gen/'): self.state = 'gen'; PROG.set(step='generating sources')
            elif s.startswith('xcodebuild'):
                units = len(os.listdir(self.ios / 'Gen/src')) + 2 + sum(1 for p in (self.ios / 'Sources').iterdir() if p.suffix in ('.c', '.m'))   # + Gen/main/main.c and Gen/embed.S
                self.state, self.t = 'xcode', time.time(); PROG.set(step='xcodebuild', done=0, total=units, unit='files', est=True)   # an incremental build compiles fewer
            elif s.startswith('pack IPA'):
                try: self._poll()   # the rest of build.log (xcodebuild writes it in big blocks)
                except OSError: pass
                PROG.end(f'{self.compiled:,} file{"" if self.compiled == 1 else "s"} compiled')
                self.state, self.total, self.most = 'list', None, 0; PROG.stage('IPA pack', poll=self.poll, step='listing the files')
            elif self.state == 'list' and (m := re.match(r'pack: (\d+) entries, (\d+) bytes', s)):   # the files' bytes: the archive's size when nothing deflates, else the last IPA's size is closer
                self.state, self.total = 'pack', self.last or int(m.group(2)); PROG.set(step='packing', unit='B', note=f'{int(m.group(1)):,} entries')

    def poll(self):   # from the poll thread
        with self.lock: return self._poll()

    def _poll(self):
        state = self.state
        if state == 'xcode':
            log = self.o / 'build.log'
            if log.stat().st_mtime < self.t - 1: return None   # still the last build's log
            if log.stat().st_size < self.off: self.off = self.compiled = 0
            with open(log, 'rb') as f: f.seek(self.off); chunk = f.read()
            chunk = chunk[:chunk.rfind(b'\n') + 1]; self.off += len(chunk)
            for ln in chunk.split(b'\n'):
                w = ln.split(b' ', 1)[0].decode(errors='replace')
                if w == 'CompileC': self.compiled += 1
                self.what = self.XCODE.get(w, self.what)
            r = {'done': self.compiled, 'note': self.what}
        elif state == 'pack':
            try: self.most = max(self.most, self.part.stat().st_size)   # never backwards: the archive is renamed at the end
            except OSError: pass
            r = {'done': self.most, 'total': self.total, 'est': True}
        else: return None
        return r


def find_repo(here):   # this file lives in the repository's scripts/; walk up to the level that has dm/tools/nx_extract/Program.cs
    for d in here.parents:
        if (d / 'dm/tools/nx_extract/Program.cs').exists(): return d
    raise BuildError(f'cannot find the repository root above {here} (no dm/tools/nx_extract)')


def parse_args(argv):
    """Command-line options: when given they override "Settings"; F5 in Spyder passes none, so "Settings" is used as is. -h shows the help"""
    import argparse
    ap = argparse.ArgumentParser(prog='build_ipa_from_nsp.py',
        description='Build an unsigned IPA from a game\'s NSPs; a game with no profile is surveyed and gets a best-effort IPA from a provisional profile.',
        epilog='example: python3 scripts/build_ipa_from_nsp.py ~/nsp/"Super Mario Bros Wonder" -k ~/keys/prod.keys')
    ap.add_argument('nsp_dir', nargs='?', help='folder holding one game\'s NSPs (default: the NSP_DIR setting, else asked)')
    ap.add_argument('-k', '--keys', help='path of prod.keys (default: the PROD_KEYS setting, else asked)')
    ap.add_argument('-p', '--package', help='version packed into the IPA, e.g. v327680 / v0 (default: the profile\'s package)')
    ap.add_argument('-o', '--out', help='output IPA (default: <the profile\'s ipa> in the NSP folder)')
    ap.add_argument('--app-name', help='app name on the home screen (default: the game name in the base NSP)')
    ap.add_argument('--bundle-id', help='the app\'s bundle ID (default: org.nxnative.<base game title ID in lowercase>)')
    ap.add_argument('--keep-extracted', action=argparse.BooleanOptionalAction, help='keep the extracted game files after the IPA is built, for the next build (default: the KEEP_EXTRACTED setting, on)')
    ap.add_argument('--env-file', help='environment switches for a diagnostic build (one KEY=VALUE per line)')
    ap.add_argument('--survey-only', action='store_true', help='a game with no profile: only the survey, no provisional profile and no IPA')
    ap.add_argument('--allow-damaged', action='store_true', help='a damaged NSP (files failing the NCA hash check): write them as read and go on instead of stopping')
    ap.add_argument('--profile-out', help='where the provisional profile goes (default: <NSP folder>/<title ID>_build/profile)')
    ap.add_argument('--provisional', action='store_true', help='build from a provisional profile even when dm/games has one for the game (tests the guesses)')
    ap.add_argument('--no-heap-check', action='store_true', help='a provisional profile: skip the heap check on the Mac (the alias / heap split stays a guess)')
    ap.add_argument('--progress', choices=('auto', 'bar', 'lines', 'off'), help='stage lines on the console: bar = one line per stage, redrawn in place; lines = a plain line every BEAT seconds; off = only each stage\'s start and end '
                    '(default: the PROGRESS setting; auto = bar in a terminal or Spyder, lines when the output goes to a file or a pipe)')
    return ap.parse_args(argv)


def main(args=None):
    args = args or parse_args([])
    PROG.mode = progress_mode(args.progress or PROGRESS)
    global ALLOW_DAMAGED; ALLOW_DAMAGED = args.allow_damaged or ALLOW_DAMAGED
    here = Path(globals().get('__file__') or sys.argv[0]).resolve()
    repo = find_repo(here)
    sys.path.insert(0, str(repo / 'dm/games')); import game as gamemod   # game profiles
    global pg; import profile_guess as pg   # dm/games: a provisional profile's keys from the game files and from the heap check
    sys.path.insert(0, str(repo / 'dm/tools')); global nacp; import nacp   # the game name in the NSP's control data
    nsp_dir = Path(os.path.expanduser(args.nsp_dir or NSP_DIR or ask('NSP folder: ', 'the NSP folder'))).resolve()
    keys = Path(os.path.expanduser(args.keys or PROD_KEYS or ask('path of prod.keys: ', 'prod.keys (-k)'))).resolve()
    if not nsp_dir.is_dir(): raise BuildError(f'not a folder: {nsp_dir}')
    if not keys.is_file(): raise BuildError(f'no such file: {keys}')
    env = dict(os.environ, PATH=os.pathsep.join(TOOL_PATHS + [os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin')]))
    env.setdefault('USER', getpass.getuser())   # xcodegen fails without USER (Couldn't find current username)
    env.setdefault('J', str(os.cpu_count() or 8))   # shader_split.py's and dmsh_build.py's workers (their default is 8)
    py = sys.executable
    app, fam = scan_nsps(nsp_dir)
    force = args.provisional or PROVISIONAL   # a provisional profile even when dm/games has one (testing the guesses)
    g, provisional, shadowed = None if force else gamemod.by_title(app), False, False
    if g is None:   # no game profile: survey, then (unless --survey-only) a provisional profile outside the repository and a best-effort IPA
        missing = [m for m in ('lz4.block', 'capstone') if not _importable(m)]
        if missing: raise BuildError(f'the current Python ({sys.executable}) is missing modules: {", ".join(missing)}')
        if not shutil.which('dotnet', path=env['PATH']): raise BuildError('dotnet not found (.NET SDK 10)')
        pdir = Path(os.path.expanduser(args.profile_out or PROFILE_OUT)).resolve() if (args.profile_out or PROFILE_OUT) else nsp_dir / f'{app:016X}_build' / 'profile'
        if (pdir / f'{app:016X}' / 'game.tsv').exists() and not (args.survey_only or SURVEY_ONLY):
            say(f'no game profile for {app:016X}: reusing the provisional profile from the last run (delete it to survey again)')
        else:
            facts = survey(nsp_dir, app, fam, keys, repo, py, env)
            if args.survey_only or SURVEY_ONLY: return
            facts['survey'] = str(nsp_dir / f'{app:016X}_survey' / 'survey.md')
            write_profile(pdir / f'{app:016X}', app, facts)
        # the profile folder joins the search path of game.py, which the shader tools, make and build_ipa.sh all use (DM_GAMES_DIR)
        os.environ['DM_GAMES_DIR'] = env['DM_GAMES_DIR'] = os.pathsep.join([str(pdir)] + [d for d in os.environ.get('DM_GAMES_DIR', '').split(os.pathsep) if d and d != str(pdir)])
        if force and gamemod.by_title(app):   # dm/games has the game too: every tool (game.py, make, build_ipa.sh) takes the provisional profile first (DM_GAMES_FIRST)
            os.environ['DM_GAMES_FIRST'] = env['DM_GAMES_FIRST'] = '1'; shadowed = True
        g, provisional = gamemod.load(f'{app:016X}'), True
        say('[RED] provisional game profile: values guessed from the survey, the game may not boot; bring it up per docs/agents after packing')
    say(f'game profile: {g.id}{" (provisional: " + str(g.dir) + ")" if provisional else ""}')
    gfx = g.get('graphics', 'nvn')   # nvn, or vulkan (Hades: the host's Vulkan layer, SPIR-V shaders)
    if gfx not in ('nvn', 'vulkan'): raise BuildError(f'game profile {g.id}: graphics must be nvn or vulkan: {gfx}')
    if gfx == 'vulkan': say('Vulkan game: vk_shaders.py translates the shaders instead of the NVN shader chain')
    builds, need = g.builds(), g.words('shader_versions')
    pkg_ver = args.package or PACKAGE or g.get('package')
    if pkg_ver not in builds: raise BuildError(f"the version to pack (-p / PACKAGE) must be one the game profile registers: {', '.join(builds)}")
    versions = need + ([pkg_ver] if pkg_ver not in need else [])
    out_ipa = Path(os.path.expanduser(args.out or OUT_IPA)).resolve() if (args.out or OUT_IPA) else nsp_dir / g.get('ipa')   # by default in the NSP folder, next to the NSPs and <id>_build/
    if shadowed and not (args.out or OUT_IPA): out_ipa = out_ipa.with_name(out_ipa.stem + '-provisional.ipa')   # never over the IPA of the game's real profile
    say(f'output IPA: {out_ipa}')
    work = nsp_dir / f'{g.id}_build'
    keep = KEEP_EXTRACTED if args.keep_extracted is None else args.keep_extracted
    say(f'work folder (extracted game files in extract/, {"kept for the next build" if keep else "deleted after the IPA is built"}): {work}')
    xlate = repo / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate'
    # DM_GAME picks the profile; DM_ROOT / WORK point at <id>_build: the tools' default paths and temporary directories all stay inside it
    env.update(DM_GAME=g.id, DM_ROOT=str(work), WORK=str(work / 'tmp'))
    logs = work / 'logs'
    check_prereqs(env, xlate)
    picks = pick_nsps(fam, versions)

    ex = work / 'extract'; ex.mkdir(parents=True, exist_ok=True); (work / 'tmp').mkdir(exist_ok=True)
    gb = sum({p.stat().st_size for b, u in picks.values() for p in (b, u) if p}) / 2**30 + 6   # extraction + shader cache + slack
    if free_gb(work) < gb and not all((ex / v).exists() for v in versions): raise BuildError(f'less than {gb:.0f} GB free on the volume of {work}')
    glslc = gfx == 'nvn' and g.get('shader_glslc_capture', 'off') == 'on'   # shaders the game compiles at run time, captured in the Mac host (capture_glslc)
    vkcap = gfx == 'vulkan' and g.get('shader_vk_capture', 'off') == 'on'   # SPIR-V shaders the game generates at run time, captured in the Mac host (capture_vk)
    heapck = provisional and HEAP_CHECK and not args.no_heap_check and not heap_checked(g)   # the heap check, when the game needs one (once per provisional profile: it stamps the profile)
    PROG.plan(1 + len(versions) + bool(fam['dlc']) + glslc + vkcap + (5 if gfx == 'nvn' else 4))   # nx_extract, each version's extraction, the DLC, rewrite, the GLSLC / Vulkan capture, shader split + iOS shaders (or the Vulkan shaders), app build, IPA pack
    PROG.stage('build nx_extract')
    nx = build_nx_extract(repo, work, logs, env)
    PROG.end()
    dirs, clone = {}, None
    for ver in versions:   # the base game is extracted alone first; later updates clone against its RomFS
        b, u = picks[ver]
        dirs[ver] = extract(nx, keys, ex, ver, b, u, clone, logs, g)
        if u is None and clone is None and can_clone(ex): clone = dirs[ver] / 'RomFS'
    game = dirs[pkg_ver]
    aoc = extract_aoc(nx, keys, work, app, fam, logs)
    base = next((dirs[v] for v in versions if picks[v][1] is None), dirs[versions[0]])   # the folder the base game was extracted to alone
    # the app name and bundle ID both come from the base NSP: the game name in its control data, and a bundle ID from its title ID; a setting / the command line overrides them
    app_name = args.app_name or APP_NAME or nacp.name(base / 'control.nacp')
    if not app_name: raise BuildError(f'no game name in the base extraction ({base / "control.nacp"}; an older extraction did not save it: delete extract/ and run again, or give --app-name)')
    bundle_id = args.bundle_id or BUNDLE_ID or f'org.nxnative.{app:016x}'
    # the app version is the packed game's display version: the update's control data when an update is packed (nx_extract saves it next to the RomFS), else the base game's
    app_version = nacp.version(game / 'control.nacp') or nacp.version(base / 'control.nacp')
    say(f'app name: {app_name}; version: {app_version or "1.0"}; bundle ID: {bundle_id}')

    patched = work / f'patched_{pkg_ver}'
    rewrite(py, repo, game / 'ExeFS', patched, env, logs, g)
    if provisional:   # the keys that need the rewritten modules, then the heap check (both only change keys the host is built with, not the rewrite or the shader steps)
        provisional_prep(py, repo, env, logs, g)
        g = refine_after_rewrite(g, game, patched)
        if heapck and pg.heap_check_needed(game / 'ExeFS'):
            PROG.add(1); g = heap_check(repo, game, patched, work, env, logs, g)
    if glslc: capture_glslc(repo, {v: dirs[v] for v in need}, pkg_ver, patched, work, env, logs, g)
    sh = work / 'shader'
    if gfx == 'vulkan':   # the packed version's merged RomFS holds the SPIR-V files the game loads; a capture holds those it generates
        cap = capture_vk(repo, game, patched, work, env, logs, g) if vkcap else None
        ios = build_vk_shaders(py, repo, [game / 'RomFS'] + ([cap] if cap else []), sh, env, logs, g, reuse=not (provisional or ALLOW_DAMAGED))
    else:
        skey = split_shaders(py, repo, [dirs[v] / 'RomFS' for v in need], [dirs[v] / 'ExeFS/main' for v in need], sh / 'pkg', env, logs, g, provisional)
        ios = build_shaders(py, repo, sh, xlate, env, logs, g, provisional, skey)

    if free_gb(out_ipa.parent) < 5: raise BuildError(f'less than 5 GB free on the volume of {out_ipa.parent}')
    say(f'building the IPA → {out_ipa}')
    ipa_env = dict(env, GAME=g.id, W=str(work / 'ipa'), PATCHED=str(patched), ROMFS=str(game / 'RomFS'), MSL_IOS=str(ios), FONT_PY=py, DM_DISPLAY_NAME=app_name, DM_BUNDLE_ID=bundle_id, AOC=str(aoc or ''))
    if app_version: ipa_env['DM_APP_VERSION'] = app_version
    # app icon: the game icon nx_extract saved from the control data (English, icon.jpg); the packed version's first, then the base game's
    icon = next((d / 'icon.jpg' for d in (game, base) if (d / 'icon.jpg').exists()), None)
    if icon: ipa_env['DM_ICON'] = str(icon); say(f'app icon: {icon}')
    else: say('[RED] no game icon in the extraction (an older extraction did not save it: delete extract/ and run again); the home-screen icon will be blank')
    env_file = args.env_file or DM_ENV_FILE
    if env_file: ipa_env['DM_ENV_FILE'] = str(Path(os.path.expanduser(env_file)).resolve())
    watch = IpaWatch(repo, work / 'ipa', out_ipa)
    PROG.stage('app build', poll=watch.poll, step='starting')   # build_ipa.sh's "pack IPA" line starts the stage "IPA pack"
    run(['bash', repo / 'dm/ios/tools/build_ipa.sh', out_ipa], logs / 'build_ipa.log', env=ipa_env, on_line=watch.line)
    if not out_ipa.is_file(): raise BuildError(f'no IPA at {out_ipa}')
    PROG.end(f'{out_ipa.name}, {amount(out_ipa.stat().st_size, "B")}')
    rmtree(work / 'tmp')
    if not keep:
        say(f'deleting the extracted game files: {ex}'); rmtree(ex)
    say(f'done: {out_ipa} ({out_ipa.stat().st_size / 2**30:.1f} GB)')
    if provisional:
        say(f'[RED] this IPA was built from a provisional game profile and the game may not boot: {g.dir}')
        say(f'  bring-up on the Mac: DM_GAMES_DIR="{g.dir.parent}" make -C dm/host GAME={g.id} dmhost, see docs/agents')


def cli(argv):   # returns the exit code: 0 done, 1 error, 130 interrupted
    try:
        main(parse_args(argv))
    except BuildError as e:
        PROG.close(ok=False); print(f'[RED] {e}', flush=True); return 1
    except KeyboardInterrupt:
        PROG.close(ok=False); print('[RED] interrupted', flush=True); return 130
    finally:
        PROG.close(ok=False)   # an unexpected error: end the stage line before the traceback
    return 0


if __name__ == '__main__':
    code = cli(sys.argv[1:])
    if not in_ipython(): sys.exit(code)   # give an exit code in a terminal; do not exit in Spyder (keeps the console clean)
