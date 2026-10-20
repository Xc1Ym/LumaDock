#!/usr/bin/env python3
# All of Mario's shaders → the "package directory" dmsh_build.py understands + the shader map + the translation query answer table (thread group / shared memory of compute shaders).
# Sources (a full scan, not relying on file names): every file under RomFS (.zs is zstd-decompressed first, Yaz0 is decompressed, SARC is expanded member by member) and ExeFS main (NSO, lz4-decompressed), looking for
#   · BNSH ('BNSH\0\0\0\0', carried by bfsha / particle effect esetb / UI layout blarc / embedded in main):
#       +0x60 grsc block; +0x7c variation count u32; +0x80 variation table pointer (pointers are relative to the BNSH start). A variation is 0x40 bytes; the binary program is at +0x10;
#       the binary program has 6 stage pointers from +0x08: vertex, hull, domain, geometry, pixel, compute; the stage code descriptor has +0x08 control pointer, +0x10 code area pointer, +0x18 code area length, +0x1c control length.
#   · BAHS (agl's sharcb: the agl / gsys resource packs, GameAglShader in the Secred pack): file header +0x1c code region start, +0x18 code region length;
#       each binary entry in the table area is 16 bytes {code offset (relative to the code region, 0x100-aligned), 0, control length 0x880 / 0x88c (3D World 0x848), signed offset of the control relative to this entry's address}.
#       Control sections are shared between programs, so pairing goes by entry, never by finding code from a control; entries are recognized by a triple check of "control magic + code magic + consistent lengths".
#   · Unity (UnityFS bundles and the serialized files under Data, read by unityfs.py): the Switch subprograms of each Shader object; the program code = a 0x60 header + one block per stage.
#       The header is 4 i32 ×6 arrays indexed by NVN stage (0 vertex 1 pixel 2 geometry 3 hull 4 domain 5 compute): [0] unused (0 or a scratch size), [1] block offset (from +0x60, -1 = no such stage), [2] control length, [3] code length;
#       block = control section + code area. A program's vertex / pixel stages form a pair. The game's own serialized files (data.unity3d, unity default resources) carry no type trees and borrow the bundles' Shader type tree of the same hash (second pass)
#       Before 2019.3 (Cuphead, Unity 2017.4; found by armyja, GitHub pull request #2) a subprogram holds one stage: program code = a 0x10 header {?, ?, control length, code length} + control section
#       + code area, and the stage is not in the code but in the Shader's m_ParsedForm (unity_stages)
#       Unity 2022 (Ace Attorney Investigations Collection, 2022.3) keeps the 0x60 header in the program code, but the blob also holds parameter entries, which unity_code_blobs leaves out
#   · MSHD (MercurySteam, Metroid Dread system/shd/*.bshdat): each stage = a control section (+0x20 = control length; sometimes a small compiler option table follows) + the code area starting at the next code header;
#       NV assembly text follows the first 0x880 bytes of the control section, and SASS disassembly text follows the code area. All 478 files hold "vertex, pixel" in pairs (1, 2 or 4 pairs), paired two by two in order
#   · G2S (Koei Tecmo's KTGL, Hyrule Warriors: Age of Calamity): GLSLC compiler outputs inside the IDRK entries of the RDB data files (zlib in chunks), see idrk_shaders
#   · SPKG (the older KTGL of Fire Emblem: Three Houses): shader packages of G2S containers, loose and inside the LINKDATA archive DATA0.bin / DATA1.bin, see kt_shaders and linkdata_jobs
#   · SDF (Capcom's RE Engine, Monster Hunter Rise): shader definitions inside the PAK archives (KPKA, entries zstd / deflate compressed), only the newest copy of each path, see kpka_jobs and sdf_shaders
# Code area: 0x30 header + (graphics) 0x50 SPH + instructions; header magic 0x12345678 for graphics, 0x12345679 for compute. The control section starts with 0x98761234, +0x704 = code area length,
#   +0x700 = start of the c1 constant segment within the code area; for compute +0x748 thread group xyz (u32 ×3), +0x754 shared memory bytes (checked one by one against PC reflection on D2R's 22 compute shaders).
# Stage: BNSH uses the stage slot; BAHS uses bits 10..13 of SPH word 0 (1 vertex 2 hull 3 domain 4 geometry 5 pixel), and a compute header means compute.
# Key = sha256(first 0x880 bytes of the control section (its own length when control +0x20 says it is shorter, see ctl_len) + code area)[:16], the same as the host's prog_get: in this game many shaders share a control section but differ in code
#   (SecredUber's 16600 stage shaders have only 3079 distinct control sections, with 6367 cases of same control, different code), so hashing the control alone picks the wrong library.
# Output: <package dir>/<stage>_<source group>.bin, each record = 'BTCDBTCD' + header (+0x28 control length, +0x2c code length) padded to 0x38 + code area + control section, one copy per key;
#   map rows have the same columns as D2R's shader_map.tsv (column 5 records where the key first appeared); the answer table has one row per compute shader {"local", "shared"} (shared memory rounded up to 16 bytes, as D2R did).
# Usage: shader_split.py <RomFS dir> <ExeFS main> <output package dir> <output map> <output answer table> [<output pair table>]   (decompressing main needs lz4: run with dm's venv python)   Environment J=concurrency (default 8)
#   With an update: give RomFS and main as comma-separated lists (base game first, e.g. data/v0/RomFS,data/v327680/RomFS); the output is the union of both versions (see main())
#   Unity type trees need Unity's common string table, which is taken from the first main
# Pair table: (vertex key, pixel key) of every BNSH variation (every Unity program); dmsh_build uses it to give vertex shaders the outputs their pixel shaders read but they do not write (see dmsh_build.py vs_pad)
import collections, concurrent.futures as cf, hashlib, json, os, re, struct, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../games')); import game as _game
GAME = _game.load()   # the current game profile (DM_GAME, required): source group rules and the table header note
GROUPS, NOTE = GAME.pairs('shader_groups'), GAME.get('shader_note')
GLSLC = GAME.get('shader_main_glslc', 'off') == 'on'   # GLSLC compiler outputs in main (glslc_shaders)
SEPARABLE = GAME.get('shader_separable', 'off') == 'on'   # single-stage programs combined per stage at draw time (separable_pairs)
CAPTURE = GAME.get('shader_glslc_capture', 'off') == 'on'   # GLSLC outputs the game compiles at run time, captured on the Mac (DM_GLSLC_CAPTURE, hle_glslc.c)

CTL_MAGIC, GFX_MAGIC, CS_MAGIC = bytes.fromhex('34127698'), bytes.fromhex('78563412'), bytes.fromhex('79563412')
STAGES = ['vs', 'hs', 'ds', 'gs', 'ps', 'cs']
SPH_STAGE = {1: 'vs', 2: 'hs', 3: 'ds', 4: 'gs', 5: 'ps'}
STAGE_NAME = {'vs': 'vertex', 'hs': 'hull', 'ds': 'domain', 'gs': 'geometry', 'ps': 'pixel', 'cs': 'compute'}   # shader_map.tsv column 3

def red(msg): sys.exit('[RED] ' + msg)

def ctl_len(ctl):
    """Number of control bytes in the key: control +0x20 holds the section's own length. Every control section of Mario, Fire Emblem Engage, Metroid Dread and 13 Sentinels is at least 0x880 bytes, so the first 0x880 are used;
    SDK 10's Super Mario 3D World + Bowser's Fury has 2,888 that are only 0x850 bytes (the bfsha in ShaderData, 6 layouts), with other data right after them, so only their own length is used (the same as the host's keys_hash)"""
    n = struct.unpack_from('<I', ctl, 0x20)[0]
    return n if 0x760 <= n < 0x880 else 0x880

def skey(ctl, code):
    return hashlib.sha256(ctl[:ctl_len(ctl)] + code).hexdigest()[:16]

def check(where, st, ctl, code):
    """control section and code area consistent; returns the reason if not"""
    if ctl[:4] != CTL_MAGIC or len(ctl) < ctl_len(ctl): return 'bad control section'
    # a compute code area may have no header (SDK 10's Super Mario 3D World + Bowser's Fury and D2R: instructions start at +0; dmsh_build strips only a 0x12345679 header)
    if st == 'cs' and code[:4] in (CS_MAGIC, GFX_MAGIC) and code[:4] != CS_MAGIC or st != 'cs' and code[:4] != GFX_MAGIC: return 'code area header magic does not match the stage'
    if struct.unpack_from('<I', ctl, 0x704)[0] != len(code): return 'control +0x704 does not match the code area length'
    return None

def bnsh_shaders(d, base, label):
    if d[base + 0x60:base + 0x64] != b'grsc': red(f'{label} BNSH @{base:#x} has no grsc block')
    nvar, pvar = struct.unpack_from('<IQ', d, base + 0x7c)
    out = []
    for v in range(nvar):
        prog = struct.unpack_from('<Q', d, base + pvar + 0x40 * v + 0x10)[0]
        if not prog: continue
        for si, st in enumerate(STAGES):
            sc = struct.unpack_from('<Q', d, base + prog + 8 + 8 * si)[0]
            if not sc: continue
            pctl, pcode, ncode, nctl = struct.unpack_from('<QQII', d, base + sc + 8)
            ctl, code = d[base + pctl:base + pctl + nctl], d[base + pcode:base + pcode + ncode]
            why = check(label, st, ctl, code)
            if why: red(f'{label} BNSH @{base:#x} variation {v} {st}: {why}')
            out.append((f'{label}#BNSH@{base:#x}#var{v}', st, ctl, code))
    return out

def bahs_shaders(d, label):
    region, rsz = struct.unpack_from('<I', d, 0x1c)[0], struct.unpack_from('<I', d, 0x18)[0]
    if region + rsz > len(d): red(f'{label} BAHS code region out of bounds')
    out = []
    for a in range(0, region - 16, 4):
        off, z, csz, rel = struct.unpack_from('<IIIi', d, a)
        if z or not (csz in (0x880, 0x88c) or 0x760 <= csz < 0x880) or off % 0x100: continue   # control length: Mario 0x880 / 0x88c, 3D World's BAHS version 9 0x848
        c = a + rel
        if c < 0 or c + csz > region or d[c:c + 4] != CTL_MAGIC: continue
        n = struct.unpack_from('<I', d, c + 0x704)[0]
        if off + n > rsz: continue
        code, ctl = d[region + off:region + off + n], d[c:c + csz]
        st = 'cs' if code[:4] == CS_MAGIC else SPH_STAGE.get((struct.unpack_from('<I', code, 0x30)[0] >> 10) & 0xf) if code[:4] == GFX_MAGIC else None
        if not st or check(label, st, ctl, code): continue
        out.append((f'{label}#BAHS@{a:#x}', st, ctl, code))
    return out

def mshd_shaders(d, label):
    out, c = [], d.find(CTL_MAGIC)
    while c >= 0:
        nctl = struct.unpack_from('<I', d, c + 0x20)[0]
        g = d.find(GFX_MAGIC, c + nctl)
        if nctl < 0x880 or g < 0 or g - c - nctl > 0x400: red(f'{label} MSHD control section @{c:#x}: length {nctl:#x}, no code area header after it')
        ncode = struct.unpack_from('<I', d, c + 0x704)[0]
        ctl, code = d[c:c + nctl], d[g:g + ncode]
        st = SPH_STAGE.get((struct.unpack_from('<I', code, 0x30)[0] >> 10) & 0xf)
        if st != ('vs', 'ps')[len(out) % 2]: red(f'{label} MSHD @{c:#x}: stage {len(out)} is {st}, not alternating vertex / pixel')
        why = check(label, st, ctl, code)
        if why: red(f'{label} MSHD @{c:#x} {st}: {why}')
        out.append((f'{label}#MSHD#var{len(out) // 2}', st, ctl, code))
        c = d.find(CTL_MAGIC, g + ncode)
    if len(out) % 2: red(f'{label} MSHD: {len(out)} stages, not in pairs')
    return out

def glslc_shaders(d, label, need=True):
    """GLSLC compiler outputs (838 in 13 Sentinels' main read-only segment, one stage each): from the magic 0x19866891, +0x44 = the whole output's length; each output holds exactly one control section with the code area right after it (control +0x20 = control length).
    The magic is only 4 bytes and other games' mains have it too (Fire Emblem Engage has 11), so this runs only when the profile's shader_main_glslc is on, and keeps only outputs that pass the triple check.
    need: stop when there is none (main with shader_main_glslc on); a Koei Tecmo G2S container (idrk_shaders) may hold none.
    SDK 6's GLSLC (output version 0x1d.2, Fire Emblem: Three Houses) writes 0x848- and 0x850-byte control sections (ctl_len's lower range) and compute code with no 0x12345679 header: the instructions
    start at code +0 (the first word is a scheduling word), and the stage then comes from the control's thread group (+0x748), which only compute sections fill. Its few version-0x1d.0 outputs keep
    something else at control +0x20 (odd values such as 0x136b), so a length that is not a multiple of 4 is not a control length"""
    out = []
    for m in re.finditer(b'\x91\x68\x86\x19', d):
        h = m.start(); size = struct.unpack_from('<I', d, h + 0x44)[0]
        c = d.find(CTL_MAGIC, h, h + size) if 0x760 < size <= len(d) - h else -1
        if c < 0 or d.find(CTL_MAGIC, c + 4, h + size) >= 0: continue
        nctl, ncode = struct.unpack_from('<I', d, c + 0x20)[0], struct.unpack_from('<I', d, c + 0x704)[0]
        if nctl < 0x760 or nctl & 3 or c + nctl + ncode > h + size: continue
        ctl, code = d[c:c + nctl], d[c + nctl:c + nctl + ncode]
        headerless_cs = code[:4] not in (CS_MAGIC, GFX_MAGIC) and all(struct.unpack_from('<3I', ctl, 0x748))
        st = 'cs' if code[:4] == CS_MAGIC or headerless_cs else SPH_STAGE.get((struct.unpack_from('<I', code, 0x30)[0] >> 10) & 0xf) if code[:4] == GFX_MAGIC else None
        if not st or check(label, st, ctl, code): continue
        out.append((f'{label}#GLSLC@{h:#x}', st, ctl, code))
    if not out and need: red(f'{label}: the profile has shader_main_glslc on, but there is no GLSLC output')
    return out

IDRK, ZCHUNKED = b'IDRK0000', 0x100000
def idrk_entries(d):
    """Koei Tecmo RDB data files (Hyrule Warriors: Age of Calamity: asset/*.rdb.bin*, asset/data/*.file) are a run of IDRK entries: 'IDRK0000', u64 entry length, u64 stored length, u64 length,
    u32 0, u32 file KTID, u32 type KTID, u32 flags, a few parameter words, and the stored data at the end of the entry. Entries follow each other directly, some after padding (to 64 KB).
    → (start of the stored data, its end, flags) for each entry"""
    o = 0
    while o + 0x30 <= len(d):
        if d[o:o + 8] != IDRK:
            o = d.find(IDRK, o)
            if o < 0: return
        esz, csz = struct.unpack_from('<QQ', d, o + 8)
        yield o + esz - csz, o + esz, struct.unpack_from('<I', d, o + 0x2c)[0]
        o += esz

def idrk_data(d, a, b, flags, head=None):
    """An entry's data: flag 0x100000 = zlib in chunks (u32 stored length + a zlib stream each, a zero length ends; Age of Calamity's chunks inflate to at most 16 KB). head: only the first bytes"""
    import zlib
    if not flags & ZCHUNKED: return d[a:min(b, a + head) if head else b]
    out = []
    while a + 4 <= b:
        cs = struct.unpack_from('<I', d, a)[0]; a += 4
        if not cs: break
        if head: return zlib.decompressobj().decompress(d[a:a + min(cs, 1024)], head)
        out.append(zlib.decompress(d[a:a + cs])); a += cs
    return b''.join(out)

def idrk_shaders(path, label, out):
    """Koei Tecmo's KTGL keeps its shaders in G2S containers ('_S2G3000', type KTID 0x7bcd279f in Age of Calamity: 23,108 entries in three RDB files, 2.3 GB inflated), each a material's variations
    as GLSLC compiler outputs (glslc_shaders). One '_DOK0000' container (type KTID 0x20a6a0bb, the engine's system resources; once in system.rdb.bin and once in the update's .bin1) holds 151 bare
    GLSLC outputs without a G2S wrapper, among them 21 shaders the first battle draws. No other entry type holds any. The RDB files are up to 3.8 GB, so they are mapped rather than read,
    and only entries whose data starts with one of those two magics are inflated"""
    import mmap
    with open(path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as d:
        for a, b, flags in idrk_entries(d):
            if idrk_data(d, a, b, flags, 4) in (b'_S2G', b'_DOK'): out.extend(glslc_shaders(idrk_data(d, a, b, flags), f'{label}#IDRK@{a:#x}', need=False))

G2S, SPKG = b'_S2G3000', b'SPKG'
def kt_gz(d):
    """Koei Tecmo's older chunked zlib (Fire Emblem: Three Houses: the compressed entries of DATA1.bin and the patch*/…/*.gz files): u32 chunk size (0x10000), u32 chunk count, u32 inflated length,
    u32 stored length of each chunk, then the chunks at 0x80 alignment, each a u32 length + one zlib stream, or the plain bytes when the stored length equals the chunk's inflated length (a short last
    chunk, or one that does not compress). → the inflated data, or None when d is not in that form"""
    import zlib
    if len(d) < 16: return None
    cs, n, tot = struct.unpack_from('<III', d)
    if cs != 0x10000 or not n or n != (tot + cs - 1) // cs or 12 + 4 * n > len(d): return None
    sizes = struct.unpack_from(f'<{n}I', d, 12); o = (12 + 4 * n + 0x7f) & ~0x7f; out = []
    for i, s in enumerate(sizes):
        if o + s > len(d): return None
        if s == min(cs, tot - i * cs): out.append(bytes(d[o:o + s]))
        else:
            ln = struct.unpack_from('<I', d, o)[0]
            try: out.append(zlib.decompress(d[o + 4:o + 4 + ln]))
            except zlib.error: return None
        o = (o + s + 0x7f) & ~0x7f
    return b''.join(out)

def kt_shaders(d, label, out):
    """Three Houses' KTGL keeps its shaders in SPKG packages (patch*/nx/shader/*.spkg, and 132 entries of DATA1.bin), each holding G2S containers ('_S2G3000', as in Age of Calamity) of GLSLC outputs,
    and in '_SPK4100' packages without G2S (DATA1.bin entry 549, the post effects: 27 outputs); map and model archives in DATA1.bin carry packages of their own. So every inflated file or entry is
    searched for GLSLC outputs, and its SARC archives (the Nintendo layouts, 2D UI) for BNSH, as everywhere else"""
    z = kt_gz(d)
    if z is not None: d = z
    if b'\x91\x68\x86\x19' in d: out.extend(glslc_shaders(d, label, need=False))
    if d[:4] == b'SARC' or b'BNSH\0\0\0\0' in d: scan_blob(d, label, out)

def linkdata_jobs(path, rel, parts=64):
    """Three Houses' LINKDATA: DATA0.bin, beside DATA1.bin (6.9 GB), indexes it with 32-byte entries {u64 offset, u64 inflated length, u64 stored length, u64 compressed}. The entries are split into
    ranges of about equal stored size, one scan job each. → [(path, rel, (first entry, end entry)), …], or None when there is no index beside the file"""
    idx = os.path.join(os.path.dirname(path), 'DATA0.bin')
    if os.path.basename(path) != 'DATA1.bin' or not os.path.exists(idx): return None
    n = os.path.getsize(idx) // 32; step = os.path.getsize(path) / parts; jobs, lo = [], 0
    with open(idx, 'rb') as f: ents = [struct.unpack('<QQQQ', f.read(32)) for _ in range(n)]
    for i in range(1, n + 1):
        if i == n or ents[i][0] >= (len(jobs) + 1) * step: jobs.append((path, rel, (lo, i))); lo = i
    return jobs

def linkdata_shaders(path, rel, rng, out):
    import mmap
    with open(os.path.join(os.path.dirname(path), 'DATA0.bin'), 'rb') as f: idx = f.read()
    with open(path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as d:
        for i in range(*rng):
            off, n, stored, comp = struct.unpack_from('<QQQQ', idx, i * 32)
            if n: kt_shaders(d[off:off + (stored if comp else n)], f'/{rel}#{i}', out)

KPKA = b'KPKA'
SDF_STAGES = ['vs', 'hs', 'ds', 'gs', 'ps', 'cs']   # an SDF entry's stage offsets, in BNSH order
def kpka_entries(path):
    """Capcom's RE Engine PAK (Monster Hunter Rise: re_chunk_000.pak plus 16 .patch_NNN.pak, 19.6 GB): 'KPKA', u8 version 4, u8 0, u16 features (0: the table is not encrypted), u32 count, u32 fingerprint,
    then count 0x30-byte entries {u32 hash of the lower-case path, u32 hash of the upper-case path, u64 offset, u64 stored length, u64 length, u64 attributes, u64 checksum}.
    Attribute bits 0-3: 0 stored, 1 raw deflate, 2 zstd. → [(path hash, offset, stored length, length, attributes)]"""
    with open(path, 'rb') as f:
        h = f.read(16)
        if h[:4] != KPKA: return None
        ver, feat, n = h[4], struct.unpack_from('<H', h, 6)[0], struct.unpack_from('<I', h, 8)[0]
        if ver != 4 or feat: red(f'{path}: PAK version {ver}, features {feat:#x}: only version 4 with a plain entry table is known')
        t = f.read(0x30 * n)
    return [(lo | hi << 32, off, csz, usz, attr) for lo, hi, off, csz, usz, attr, _ in struct.iter_unpack('<IIqqqqQ', t)]

def kpka_data(d, e, head=None):
    """An entry's data (head: only its first bytes)"""
    import zlib
    _, off, csz, usz, attr = e; raw = d[off:off + csz]
    if attr & 0xf == 0: return raw[:head] if head else raw
    if attr & 0xf == 1: return zlib.decompressobj(-15).decompress(raw, head or 0)
    if attr & 0xf == 2:
        from compression import zstd
        if not head: return zstd.decompress(raw)
        return zstd.ZstdDecompressor().decompress(raw, max_length=head)
    red(f'PAK entry {e[0]:016x}: compression {attr & 0xf} is not known')

def kpka_jobs(files, parts=64):
    """The game reads its PAKs as one view: a path in a later patch PAK (re_chunk_000.pak.patch_NNN.pak, in name order after re_chunk_000.pak) replaces the same path hash in earlier ones.
    Only the newest copy of each path is scanned, so shaders of replaced files do not enter the tables. → ([(path, rel, entries), …] in about equal stored sizes, the PAK paths taken)"""
    paks = [(p, r) for p, r in files if p.endswith('.pak') and kpka_entries(p) is not None]
    if not paks: return [], set()
    view = {}
    for p, r in sorted(paks, key=lambda x: x[1]):
        for e in kpka_entries(p): view[e[0]] = (p, r, e)
    jobs, cur, size, step = [], collections.defaultdict(list), 0, sum(e[2] for _, _, e in view.values()) / parts
    for p, r, e in sorted(view.values(), key=lambda x: (x[1], x[2][1])):
        cur[(p, r)].append(e); size += e[2]
        if size >= step: jobs += [(p_, r_, tuple(es)) for (p_, r_), es in cur.items()]; cur, size = collections.defaultdict(list), 0
    jobs += [(p_, r_, tuple(es)) for (p_, r_), es in cur.items()]
    return jobs, {p for p, _ in paks}

def sdf_shaders(d, label):
    """RE Engine shader definition ('SDF\\0', 2,685 entries in Monster Hunter Rise's PAKs): u16 version 1, u16 entry count, u64, then 0x108-byte entries from +0x10. Entry +0x10: six u64 offsets
    (vertex, hull, domain, geometry, pixel, compute; 0 = no stage), each to {u32 control length, u32 code length} followed by the control section and the code area. Compute code has no header.
    The stages of one entry form a program, so its vertex / pixel stages are a pair"""
    ver, n = struct.unpack_from('<HH', d, 4); out = []
    if not ver and not n: return out   # an empty definition: 16 bytes, version 0, no entries
    if ver != 1: red(f'{label}: SDF version {ver}')
    for i in range(n):
        offs = struct.unpack_from('<6Q', d, 0x10 + 0x108 * i + 0x10)
        for st, o in zip(SDF_STAGES, offs):
            if not o: continue
            nctl, ncode = struct.unpack_from('<II', d, o); ctl, code = d[o + 8:o + 8 + nctl], d[o + 8 + nctl:o + 8 + nctl + ncode]
            why = check(label, st, ctl, code)
            if not why and st != 'cs' and SPH_STAGE.get((struct.unpack_from('<I', code, 0x30)[0] >> 10) & 0xf) != st: why = 'the SPH stage does not match the entry slot'
            if why: red(f'{label} SDF entry {i} {st}: {why}')
            out.append((f'{label}#SDF#var{i}', st, ctl, code))
    return out

def kpka_shaders(path, rel, ents, out):
    import mmap
    with open(path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as d:
        for e in ents:
            if e[3] >= 0x10 and kpka_data(d, e, 4) == b'SDF\0': out.extend(sdf_shaders(kpka_data(d, e), f'/{rel}#{e[0]:016x}'))

def yaz0(s):
    """Yaz0 decompression (Super Mario 3D World + Bowser's Fury: almost all of RomFS is .szs = SARC wrapped in Yaz0). Pure Python runs at about 20–45 MB/s per core, under a minute for the whole 4.7 GB RomFS in parallel, and needs no extra dependency.
    Group header bits: 1 = one literal byte; 0 = back-reference, 2 bytes {length high nibble, 12-bit distance} (distance + 1); length 0 reads one more byte + 0x12, else + 2. Overlapping copies are expanded by their period"""
    n = int.from_bytes(s[4:8], 'big'); out = bytearray(); si = 16
    while len(out) < n:
        h = s[si]; si += 1
        for _ in range(8):
            if h & 0x80:
                out.append(s[si]); si += 1
            else:
                b1, b2 = s[si], s[si + 1]; si += 2
                dist, ln = ((b1 & 15) << 8 | b2) + 1, b1 >> 4
                if ln: ln += 2
                else: ln = s[si] + 0x12; si += 1
                st = len(out) - dist
                out += out[st:st + ln] if dist >= ln else (out[st:] * (ln // dist + 1))[:ln]
            if len(out) >= n: break
            h <<= 1
    return bytes(out[:n])

def sarc_members(d):
    hl, bom, size, doff = struct.unpack_from('<HHII', d, 4)
    n = struct.unpack_from('<H', d, hl + 6)[0]
    names = hl + 12 + 16 * n + 8
    for i in range(n):
        h, attr, s, e = struct.unpack_from('<IIII', d, hl + 12 + 16 * i)
        nm = d[names + (attr & 0xffffff) * 4:].split(b'\0')[0].decode('utf-8', 'replace') if attr >> 24 else f'#{i}'
        yield nm, d[doff + s:doff + e]

NV_STAGES = ['vs', 'ps', 'gs', 'hs', 'ds', 'cs']   # NVN stage order
COMMON, TREES = None, {}   # Unity common strings and borrowed type trees (given when the pool starts)
ZDICTS, _ZD = {}, {}       # zstd dictionaries by ID (given when the pool starts) and their digested form in this process

def _pool_init(common, trees, zdicts={}):
    global COMMON, TREES, ZDICTS
    COMMON, TREES, ZDICTS = common, trees, zdicts

def zs_dicts(romfs):
    """Tears of the Kingdom compresses its RomFS files with zstd dictionaries (the frame header names one, ID 1 for the shader packages). They ship as Pack/ZsDic.pack.zs:
    a SARC (itself plain zstd) of *.zsdic files, each a zstd dictionary (magic 0xEC30A437, then its ID). → {ID: dictionary}; {} without that file (Mario's .zs are plain zstd)"""
    p = os.path.join(romfs, 'Pack/ZsDic.pack.zs')
    if not os.path.exists(p): return {}
    try:
        from compression import zstd          # Python 3.14+
    except:
        from backports import zstd            # pip install backports.zstd
    d = zstd.decompress(open(p, 'rb').read())
    return {struct.unpack_from('<I', m, 4)[0]: m for _, m in sarc_members(d) if m[:4] == bytes.fromhex('37a430ec')}

def unzs(path):
    """A .zs file decompressed: frames without a dictionary through the zstd command as before, frames that name one with that dictionary from ZDICTS"""
    d = open(path, 'rb').read()
    fhd = d[4] if len(d) > 5 and d[:4] == bytes.fromhex('28b52ffd') else 0
    n, o = (0, 1, 2, 4)[fhd & 3], 6 - (fhd >> 5 & 1)   # dictionary ID size; it follows the window descriptor, which single-segment frames omit
    did = int.from_bytes(d[o:o + n], 'little')
    if not did: return subprocess.run(['zstd', '-d', '-c', '-q', path], capture_output=True, check=True).stdout
    try:
        from compression import zstd          # Python 3.14+
    except:
        from backports import zstd            # pip install backports.zstd
    if did not in ZDICTS: red(f'{path}: a frame needs zstd dictionary {did}, which Pack/ZsDic.pack.zs does not have')
    if did not in _ZD: _ZD[did] = zstd.ZstdDict(ZDICTS[did])
    return zstd.decompress(d, zstd_dict=_ZD[did])

def unity_program(code, where, stage=None):
    """Unity's Switch program code → [(stage, control, code)]; stage = the subprogram's stage from m_ParsedForm, which only the pre-2019.3 layout needs"""
    if len(code) >= 0x14 and code[0x10:0x14] == CTL_MAGIC:   # before 2019.3: 0x10 header + control section + code area, one stage
        if stage is None: red(f'{where}: pre-2019.3 subprogram whose stage is not in m_ParsedForm')
        nctl, ncode = struct.unpack_from('<2i', code, 8); a = 0x10; end = a + nctl + ncode
        ctl, cd = code[a:a + nctl], code[a + nctl:end]
        why = check(where, stage, ctl, cd) if end <= len(code) else 'block out of bounds'
        if why: red(f'{where} {stage}: {why}')
        if end != len(code): red(f'{where}: program code is {len(code):#x} bytes, but control section + code area end at {end:#x}')
        return [(stage, ctl, cd)]
    h = struct.unpack_from('<24i', code, 0); out = []; end = 0x60
    for i, st in enumerate(NV_STAGES):
        off, nctl, ncode = h[6 + i], h[12 + i], h[18 + i]
        if off == -1: continue
        a = 0x60 + off; ctl, cd = code[a:a + nctl], code[a + nctl:a + nctl + ncode]
        why = check(where, st, ctl, cd) if a + nctl + ncode <= len(code) else 'block out of bounds'
        if why: red(f'{where} {st}: {why}')
        out.append((st, ctl, cd)); end = max(end, a + nctl + ncode)
    if end != len(code): red(f'{where}: program code is {len(code):#x} bytes, but the stage blocks end at {end:#x}')
    return out

def unity_stages(o):
    """Shader object → {subprogram index: stage}, from the passes of m_ParsedForm (progVertex / progFragment / ... m_SubPrograms[].m_BlobIndex)"""
    m = {}
    for sub in (o.get('m_ParsedForm') or {}).get('m_SubShaders', []):
        for p in sub.get('m_Passes', []):
            for field, st in (('progVertex', 'vs'), ('progFragment', 'ps'), ('progGeometry', 'gs'), ('progHull', 'hs'), ('progDomain', 'ds')):
                for sp in (p.get(field) or {}).get('m_SubPrograms', []): m.setdefault(sp.get('m_BlobIndex'), st)
    return m

def unity_code_blobs(o):
    """Shader object → the subprogram indices that hold program code, or None when every entry does (before Unity 2022). Unity 2022 also keeps the parameters of each program in the blob
    as entries of their own (m_ParameterBlobIndices of each program), and the player's programs are m_PlayerSubPrograms[tier][].m_BlobIndex (Ace Attorney Investigations Collection, Unity 2022.3).
    Both fields came together: UnityPy's type trees for 2020.3.18 (Engage) and 2021.3 have neither, so older games read every entry as before"""
    progs = [p.get(f) or {} for sub in (o.get('m_ParsedForm') or {}).get('m_SubShaders', []) for p in sub.get('m_Passes', [])
             for f in ('progVertex', 'progFragment', 'progGeometry', 'progHull', 'progDomain')]
    if not any('m_ParameterBlobIndices' in p for p in progs): return None
    return {sp['m_BlobIndex'] for p in progs for tier in p.get('m_PlayerSubPrograms', []) for sp in tier}

def unity_shaders(d, label, out, trees):
    """Shaders in a UnityFS bundle or serialized file → out; raises NoTree when no type tree is available"""
    import unityfs
    if COMMON is None: red(f'{label}: a Unity asset, but main has no Unity common string table')
    sers = unityfs.bundle_files(d) if d[:8] == b'UnityFS\0' else [('', d)]
    for node, x in sers:
        if not unityfs.is_serialized(x): continue
        for cid, pid, o in unityfs.serialized_objects(x, COMMON, {unityfs.CLASS_SHADER}, trees):
            name = o['m_ParsedForm']['m_Name'] if 'm_ParsedForm' in o else o.get('m_Name', '?')
            stages = unity_stages(o)
            for plat, k, sp in unityfs.shader_programs(o, unity_code_blobs(o)):
                where = f'{label}{":" + node if node else ""}#{name}#var{plat}.{k}'
                code = unityfs.subprogram(sp)[4]
                out.extend((where, st, ctl, cd) for st, ctl, cd in unity_program(code, where, stages.get(k)))

def scan_blob(d, label, out):
    if d[:4] == b'Yaz0': d = yaz0(d)
    if d[:4] == b'SARC':
        for nm, m in sarc_members(d): scan_blob(m, f'{label}/{nm}', out)
        return
    if d[:4] == b'BAHS': out.extend(bahs_shaders(d, label)); return
    if d[:4] == b'MSHD': out.extend(mshd_shaders(d, label)); return
    for m in re.finditer(b'BNSH\0\0\0\0', d):
        size = struct.unpack_from('<I', d, m.start() + 0x1c)[0]
        if m.start() + size <= len(d) and d[m.start() + 0x60:m.start() + 0x64] == b'grsc': out.extend(bnsh_shaders(d, m.start(), label))

def group(label):
    """source group (second half of the package file name)"""
    if label.startswith('main'): return 'main'
    for k, g in GROUPS:   # the profile's shader_groups, first match wins
        if k in label: return g
    return 'other'

def ps_inputs(code):
    """Generic attributes a pixel shader reads: SPH words 6–13 are the input map, 8 bits for each of the 32 attributes (Ryujinx ShaderHeader.ImapTypes), non-zero = read; the translated MSL inputs are exactly user(locn<attribute>)"""
    return {i for i in range(32) if struct.unpack_from('<I', code, 0x30 + 4 * (6 + (i >> 2)))[0] >> ((i & 3) * 8) & 0xff}

def separable_pairs(keys):
    """Single-stage programs (13 Sentinels: each GLSLC output becomes a program with one stage, and BindProgram's stage bits combine vertex and pixel programs per draw) have their real pairs only at draw time.
    vs_pad uses only the union of the locations the paired pixel shaders read, so every vertex shader is paired with a "cover": the fewest pixel shaders whose read locations together equal those of all pixel shaders (greedy, ties go to the smaller key);
    padded that way, a vertex shader links with any pixel shader. All pairs would be 376 × 375 rows; the cover needs a few rows × 376"""
    ins = {k: ps_inputs(v[3]) for k, v in keys.items() if v[1] == 'ps'}
    left, cover = set().union(*ins.values()) if ins else set(), []
    while left:
        k = min(ins, key=lambda k: (-len(ins[k] & left), k)); cover.append(k); left -= ins[k]
    return {(v, p) for v in keys if keys[v][1] == 'vs' for p in cover}, cover

def var_pairs(found):
    """(vertex key, pixel key) within the same BNSH variation"""
    var = collections.defaultdict(dict)
    for where, st, ctl, code in found:
        if '#var' in where: var[where][st] = skey(ctl, code)
    return {(v['vs'], v['ps']) for v in var.values() if 'vs' in v and 'ps' in v}

def scan_file(args):
    """→ (relative path, {key: …}, pairs, extra); extra = this file's Unity type trees, or 'defer' (no type tree, scanned again in the second pass)"""
    path, rel = args[:2]
    with open(path, 'rb') as f: head = f.read(16)
    found = []; trees = {}
    if head[:8] == IDRK:
        idrk_shaders(path, '/' + rel, found)
        return rel, uniq_keys(found), var_pairs(found), trees
    if len(args) > 2 and head[:4] == KPKA:   # entries of an RE Engine PAK (kpka_jobs)
        kpka_shaders(path, rel, args[2], found)
        return rel, uniq_keys(found), var_pairs(found), trees
    if len(args) > 2:   # a range of LINKDATA entries (linkdata_jobs)
        linkdata_shaders(path, rel, args[2], found)
        return rel, uniq_keys(found), var_pairs(found), trees
    if head[:4] == SPKG or head[:4] == b'\0\0\1\0' and path.endswith('.gz'):   # Three Houses' loose shader packages and chunked zlib files (kt_shaders)
        kt_shaders(open(path, 'rb').read(), '/' + rel, found)
        return rel, uniq_keys(found), var_pairs(found), trees
    d = unzs(path) if path.endswith('.zs') else open(path, 'rb').read()
    if d[:4] == b'Yaz0': d = yaz0(d)
    if d[:8] == b'UnityFS\0' or (d[8:11] == b'\0\0\0' and __import__('unityfs').is_serialized(d)):
        import unityfs
        try: unity_shaders(d, '/' + rel, found, trees if not TREES else dict(TREES))
        except unityfs.NoTree: return rel, {}, set(), 'defer'
    elif b'BNSH\0\0\0\0' not in d and b'BAHS' not in d and d[:4] != b'MSHD' and not (d[:4] == b'SARC' and b'Yaz0' in d): return rel, {}, set(), {}   # a SARC may hold Yaz0 members
    else: scan_blob(d, '/' + rel, found)
    return rel, uniq_keys(found), var_pairs(found), trees

def uniq_keys(found):
    uniq = {}
    for where, st, ctl, code in found:
        key = skey(ctl, code)
        if key in uniq and (uniq[key][2] != ctl or uniq[key][3] != code): red(f'key {key} is the same but the control section or code area differs ({where})')
        uniq.setdefault(key, (where, st, ctl, code))
    return uniq

def nso_image(path):
    import lz4.block
    d = open(path, 'rb').read()
    flags = struct.unpack_from('<I', d, 0xc)[0]; segs = [struct.unpack_from('<III', d, 0x10 + i * 0x10) for i in range(3)]; csz = struct.unpack_from('<III', d, 0x60)
    img = bytearray(segs[2][1] + segs[2][2])
    for i, (fo, mo, sz) in enumerate(segs):
        raw = d[fo:fo + csz[i]]
        img[mo:mo + sz] = lz4.block.decompress(raw, uncompressed_size=sz) if flags >> i & 1 else raw
    return bytes(img)

def main():
    romfs_l, main_l, pkg, mapout, factsout = sys.argv[1:6]
    pairsout = sys.argv[6] if len(sys.argv) > 6 else None
    # Several versions (base game + update): the RomFS and main arguments are comma-separated and paired one to one; the output is their union (keys are content hashes, shaders shared by versions appear once).
    # The first version's source column is unchanged; later versions are prefixed with their workspace directory name (e.g. v327680): /v327680/Shader/…, main@v327680. They sort after the first version, so existing rows keep their package indices.
    romfs_v, main_v = romfs_l.split(','), main_l.split(',')
    if len(romfs_v) != len(main_v): red(f'{len(romfs_v)} RomFS and {len(main_v)} main: they must pair one to one')
    files, results, common = [], [], None
    for i, (romfs, mainnso) in enumerate(zip(romfs_v, main_v)):
        tag = os.path.basename(os.path.dirname(os.path.abspath(romfs))) if i else ''
        files += sorted((os.path.join(dp, f), (tag + '/' if tag else '') + os.path.relpath(os.path.join(dp, f), romfs)) for dp, _, fs in os.walk(romfs) for f in fs)
        img = nso_image(mainnso)
        if not i:
            import unityfs
            try: common = unityfs.common_strings(img)
            except ValueError: common = None   # not a Unity game
        found = []; scan_blob(img, 'main' + ('@' + tag if tag else ''), found)
        if GLSLC: found += glslc_shaders(img, 'main' + ('@' + tag if tag else ''))
        if CAPTURE:   # GLSLC outputs the game compiles at run time, captured on the Mac (hle_glslc.c): <version dir>/glslc_capture, or DM_GLSLC_CAPTURE
            cap = os.environ.get('DM_GLSLC_CAPTURE') or os.path.join(os.path.dirname(os.path.abspath(romfs)), 'glslc_capture')
            names = sorted(f for f in os.listdir(cap) if f.endswith('.glslc')) if os.path.isdir(cap) else []
            if not names: print(f'[RED] the profile has shader_glslc_capture on, but there are no captured GLSLC outputs in {cap}: the shaders the game compiles at run time will have no translation', flush=True)
            for nm in names: found += glslc_shaders(open(os.path.join(cap, nm), 'rb').read(), f'/glslc_capture/{nm}')
        results.append(('main', {skey(c, k): (w, s, c, k) for w, s, c, k in found}, var_pairs(found), {}))
    zdicts = {k: v for r in romfs_v for k, v in zs_dicts(r).items()}   # Tears of the Kingdom's zstd dictionaries (zs_dicts)
    keys = {}
    # First pass: every file; Unity bundles carry type trees, and the Shader trees are collected on the way. Second pass: Unity serialized files without type trees are scanned again with the borrowed trees
    J = int(os.environ.get('J', '8'))
    big = [j for p, r in files for j in (linkdata_jobs(p, r) or [])]   # Three Houses' 6.9 GB DATA1.bin: one job per range of entries, not one read of the whole file
    pak_jobs, paks = kpka_jobs(files)   # Monster Hunter Rise's PAKs: the newest copy of each path, in ranges of entries
    big += pak_jobs
    files = [(p, r) for p, r in files if not linkdata_jobs(p, r) and p not in paks]
    with cf.ProcessPoolExecutor(J, initializer=_pool_init, initargs=(common, {}, zdicts)) as ex:
        results += list(ex.map(scan_file, big)) + list(ex.map(scan_file, files, chunksize=16))
    trees, defer = {}, []
    for rel, uniq, pr, extra in results:
        if extra == 'defer': defer.append(rel)
        elif extra: trees.update(extra)
    if defer:
        byrel = {r: p for p, r in files}
        with cf.ProcessPoolExecutor(J, initializer=_pool_init, initargs=(common, trees, zdicts)) as ex: again = list(ex.map(scan_file, [(byrel[r], r) for r in defer]))
        for rel, uniq, pr, extra in again:
            if extra == 'defer': red(f'{rel}: Unity serialized file without type trees, and no bundle has a Shader type tree of the same hash to borrow')
        results = [r for r in results if r[3] != 'defer'] + again
    per_src = collections.Counter(); pairs = set()
    for rel, uniq, pr, _ in results:
        pairs |= pr
        for key, v in uniq.items():
            if key in keys:
                if keys[key][2] != v[2] or keys[key][3] != v[3]: red(f'key {key} is the same but the control section or code area differs ({v[0]} / {keys[key][0]})')
                continue
            keys[key] = v; per_src[group(v[0])] += 1
    if SEPARABLE:
        sp, cover = separable_pairs(keys); pairs |= sp
        print(f'single-stage programs: every vertex shader is paired with a cover of {len(cover)} pixel shader(s) ({" ".join(cover)})')
    os.makedirs(pkg, exist_ok=True)
    for f in os.listdir(pkg):
        if f.endswith('.bin'): os.unlink(os.path.join(pkg, f))
    recs = collections.defaultdict(list); rows = []; facts = {}; stat = collections.Counter()
    for key in sorted(keys, key=lambda k: (group(keys[k][0]), keys[k][0], k)):   # the same input gives byte-identical output
        where, st, ctl, code = keys[key]
        name = f'{st}_{group(where)}.bin'
        rec = bytearray(b'BTCDBTCD' + bytes(0x30)); struct.pack_into('<2I', rec, 0x28, len(ctl), len(code)); rec += code + ctl
        if rec.find(CTL_MAGIC) != 0x38 + len(code): red(f'key {key}: the control magic appears in the code area, dmsh_build would split the record wrongly')
        if rec.count(b'BTCDBTCD') != 1: red(f'key {key}: the record separator appears inside the record')
        rows.append((name, len(recs[name]), STAGE_NAME[st], key, where)); recs[name].append(bytes(rec)); stat[st] += 1
        if st == 'cs':
            x, y, z = struct.unpack_from('<3I', ctl, 0x748); sh = struct.unpack_from('<I', ctl, 0x754)[0]
            if not x * y * z: red(f'compute shader {key}: control +0x748 thread group is 0 ({where})')
            facts[key] = {'local': [x, y, z], 'shared': (sh + 15) // 16 * 16}
    for name, rr in recs.items():
        with open(os.path.join(pkg, name), 'wb') as f: f.write(b''.join(rr))
    with open(mapout, 'w') as f:
        kinds = ' / '.join(k for k, hit in (('BNSH / BAHS', any('#BNSH@' in r[4] or '#BAHS@' in r[4] for r in rows)), ('Unity Shader', any('#var' in r[4] and '#BNSH@' not in r[4] and '#MSHD#' not in r[4] and '#SDF#' not in r[4] for r in rows)),
                                            ('MSHD', any('#MSHD#' in r[4] for r in rows)), ('GLSLC', any('#GLSLC@' in r[4] for r in rows)), ('RE Engine SDF', any('#SDF#' in r[4] for r in rows))) if hit)
        f.write(f'# kind: evidence  {NOTE} ({kinds} in RomFS + main) → control section + code area keys (dm/gfx/tools/shader_split.py)\n')
        f.write('# column 5 records where each key first appears; this game has no PC version to pair with\n')
        f.write('package\tindex\tstage\tdm_ctl_sha16\tsource\n')
        for r in rows: f.write('\t'.join(map(str, r)) + '\n')
    # Hand-written facts the machine code cannot give (the profile's shader_facts_manual.tsv, same row format) are merged over the generated ones, so the table stays reproducible
    manual = GAME.table('shader_facts_manual.tsv')
    if os.path.exists(manual):
        for ln in open(manual):
            if ln.strip() and not ln.startswith('#'): k, v = ln.rstrip('\n').split('\t', 1); facts[k] = {**facts.get(k, {}), **json.loads(v)}
    with open(factsout, 'w') as f:
        f.write('# Answer table for translation queries (generated by dm/gfx/tools/shader_split.py, do not edit): key <TAB> fact JSON. This game has no PC version to pair with: only the thread group / shared memory of compute shaders (taken from the control section); other queries get the translator defaults\n')
        for k in sorted(facts): f.write(k + '\t' + json.dumps(facts[k], sort_keys=True, separators=(',', ':')) + '\n')
    if pairsout:
        with open(pairsout, 'w') as f:
            f.write('# kind: evidence  vertex / pixel shader pairs within BNSH variations (generated by dm/gfx/tools/shader_split.py, do not edit): vertex key <TAB> pixel key\n')
            for a, b in sorted(pairs): f.write(f'{a}\t{b}\n')
    print(f'shaders: {len(rows)} (' + ', '.join(f'{STAGE_NAME[s]} {n}' for s, n in sorted(stat.items())) + '); sources ' + ', '.join(f'{g} {n}' for g, n in per_src.most_common()) + f'; compute shader answers {len(facts)} rows' + (f'; variation pairs {len(pairs)}' if pairsout else ''))

if __name__ == '__main__': main()
