# 01 — Extracting an NSP

## Keys

- Needs the user's own `prod.keys` and the title key from the NSP's ticket. Keep both under the work folder, e.g. `$W/build/keys/.switch/{prod,title}.keys`, and run hactool with `HOME` pointed there so it never reads anything else:

  ```bash
  # $W/build/keys/ht — hactool with a private key home
  HOME="$(cd "$(dirname "$0")" && pwd)" exec "$(dirname "$0")/../../tools/hactool/hactool" --disablekeywarns "$@"
  ```

- Dumped `prod.keys` files may contain malformed lines (seen: 33 `*master_kek_source_*` lines with the wrong length) that make hactool refuse the whole file. Drop lines whose value length is wrong for the key type; keep a backup of the original.
- Title key: the NSP carries `<rights id>.tik`. For a common ticket the encrypted title key is the first 16 bytes of the title-key block at 0x180; append `<rights id> = <key hex>` to `title.keys`. Never print the value.

## NSP → NCA → ExeFS / RomFS

```bash
ht -t pfs0 --outdir=$W/build/nsp game.nsp > $W/build/nsp.log         # NSP is a PFS0: NCAs + cnmt + tik/cert
ht -t nca $W/build/nsp/<id>.nca | head -40                             # identify the Program NCA (content type Program, has ExeFS + RomFS)
ht -t nca --listromfs $W/build/nsp/<program>.nca > romfs_list.txt     # quick look before extracting 3+ GB
ht -t nca --exefsdir=$W/data/v0/ExeFS --romfsdir=$W/data/v0/RomFS $W/build/nsp/<program>.nca
```

- ExeFS holds `main.npdm`, `rtld` (usually), `main`, `sdk` and sometimes `subsdk*` modules (NSO). D2R and Mario both had only `main` + `sdk` worth loading.
- Update NSPs: the update's Program NCA is a patch NCA; extract it with `--basenca=<base program nca>` so RomFS is the merged view. Keep base and update in separate directories (`data/v0`, `data/v<ver>`); the rewriter and the host take one ExeFS at a time.
- Newer patch NCAs (seen: Mario 1.2.1, key generation 17) make hactool stop with `Invalid BKTR layout!`. `dm/tools/nx_extract` (C#, LibHac 0.19) handles them: `nx_extract <prod.keys> <base.nsp> <update.nsp> <out dir> [<base RomFS dir>]`. It reads the NCAs straight out of both NSPs (no 3+ GB intermediate NCA), imports the common tickets itself, prints the display version and module build IDs, and with a base RomFS dir writes identical files as APFS clones.
- After an update, find every address the host or rewriter hard-codes for the old build (`CUTS` / `OBS` / `PARAMS` in `patch_nso.py`, `->base + 0x…` in the host) and carry it over with `dm/tools/nso_fnmap.py <old.orig.bin> <new.orig.bin> 0x…`: it matches functions with address bits masked and maps globals through their `adrp` references; check each result by disassembly (`sdis.py`). Also diff the imported SDK symbols: new imports that reach a system service need host implementations, or the real SDK aborts after connecting to `sm:`.
- **A cartridge dump (`.xci`) as the base game** (Monster Hunter Rise): the card header's magic `HEAD` sits at 0x100, and its root HFS0 holds the `update`, `logo`, `normal` and `secure` partitions; the game's NCAs are in `secure` (here the 7 GB program NCA, control, legal information, HTML manual and the meta NCA). Cartridge NCAs carry their key in the key area, so there is no ticket. `nx_extract` opens either kind as the base game (`OpenNsp`), and the NSP script takes `*.xci` beside `*.nsp`; the update and DLC stay NSPs.
- Decompressed NSO images for analysis: `dm/tools/nso.py <nso> <out.bin>` (lz4; use a venv that has `lz4`). `dm/tools/nso2elf.py` makes an ELF for Ghidra / REA / objdump.

**A damaged NSP** (an incomplete copy, a broken download) shows as a hash error while the RomFS is read. `nx_extract` lists every file whose data fails the NCA's hash check and exits with code 3; `--allow-damaged` (the NSP script's `ALLOW_DAMAGED` / `--allow-damaged`) writes them as read and only lists them. To check a whole NCA, its file name is the first 16 bytes of its SHA-256: Super Mario Galaxy's base program NCA hashed differently, with 12 MB runs of zeros near its end (147 MB of damaged RomFS: the two WebM prologue movies), while its update and the small NCAs matched their names.

## Workspace layout used so far

The work folder `$W` sits in the game's NSP folder, beside the NSP script's `<title>_build/`, never in the home folder:

```
<NSP folder>/<title>-work/
  build/nsp/            NCAs + tik/cert + nsp.log
  data/v0/{ExeFS,RomFS} extracted base game (v<ver> for updates)
  probe/                decompressed images (main.orig.bin, sdk.orig.bin), small experiments
  elf/                  nso2elf output
  census/               survey tables (imports, svc, NVN slots)
  build/patched_v0/     rewriter output (what the host loads)
  shader/               shader package directory + map + facts produced by shader_split.py
  build/cache/metal_shader_cache/b-<chain version>/   translated metallibs
  build/gfx/dmsh_xlate/ the shader translator build
  ghidra/proj           persistent Ghidra project (analysis takes ~35 min for a 28 MB main)
  run/                  boot.sh, logs, saves, screenshots
  dbg/                  lldb scripts
```

## Compressed RomFS content

- Newer EPD titles store most files as `*.zs` (plain zstd, no dictionary in Mario; Zelda TotK needs `ZsDic.pack` dictionaries). Check for `*dic*` files before assuming plain zstd.
- Older EPD titles (Super Mario 3D World + Bowser's Fury, a Wii U port) store almost everything as `*.szs`: Yaz0-compressed SARC. `shader_split.py` decompresses Yaz0 itself (`yaz0`, pure Python, about 20–45 MB/s per core; the whole 4.7 GB decompressed RomFS scans in about a minute). One of its SARCs (`SystemData/LayoutShader.szs`) is big-endian (BOM `FE FF`), which the SARC reader does not handle; it holds no shader container the game uses.
- `*.sarc` / `*.pack` / `*.blarc` / `*.bfarc` are SARC archives; `*.byml` / `*.bgyml` are BYML (version 7 in Mario). A minimal reader for both is short enough to write inline when needed (see `shader_split.py` for SARC). Unity titles: `dm/gfx/tools/unityfs.py` reads UnityFS bundles, serialized files and objects by type tree (`bundle_files`, `serialized_objects`).
- Capcom's RE Engine (Monster Hunter Rise) keeps everything in PAK archives: `re_chunk_000.pak` plus `re_chunk_000.pak.patch_001.pak` … `patch_016` (19.6 GB in all). A PAK is `KPKA`, u8 version 4, u8 0, u16 features (0: a plain entry table), u32 count, u32 fingerprint, then one 0x30-byte entry per file: u32 murmur hashes of the lower- and upper-case UTF-16 path, u64 offset, u64 stored length, u64 length, u64 attributes (bits 0–3: 0 stored, 1 raw deflate, 2 zstd), u64 checksum. File names are only hashes. The game reads all of them as one view: a path in a later patch replaces the same hash in earlier PAKs (`kpka_jobs` in `shader_split.py` takes only the newest copy). The first bytes of each file name its format (`MESH`, `TEX\0`, `SDF\0` shader definitions, `BKHD` / `AKPK` Wwise, `USR\0`, `PFB\0`, …).
- Koei Tecmo's KTGL (Hyrule Warriors: Age of Calamity) keeps everything in RDB archives: `asset/<name>.rdb` is the index (`_DRK0000` header, then one `IDRK0000` record per file), and `asset/<name>.rdb.bin*` plus `asset/data/0x<KTID>.file` hold the data as a run of `IDRK0000` entries: u64 entry length, u64 stored length, u64 length, u32 0, u32 file KTID, u32 type KTID, u32 flags, a few parameter words, then the stored data at the end of the entry. Entries follow each other directly, some after padding to 64 KB. Flag 0x100000 = zlib in chunks: u32 stored length + a zlib stream each, up to 16 KB inflated per chunk, a zero length ends. The first bytes of the inflated data name the format (`GT1G` textures, `_M1G` models, `_S2G` shaders, `KTSR` / `TSRS` / `ASRS` sound). The DLC folders add `.rdb.bin3_0` files of the same layout.
- The older KTGL of Fire Emblem: Three Houses uses a LINKDATA archive instead: `DATA0.bin` is an index of 32-byte entries `{u64 offset, u64 length, u64 stored length, u64 compressed}` into `DATA1.bin` (6.9 GB), and `patch1`–`patch4` hold loose overrides listed by `patchN/INFO0.bin` (0x120-byte entries ending in a `rom:/patchN/…` path). Its compressed entries and `*.gz` files are another chunked zlib: u32 chunk size (0x10000), u32 chunk count, u32 length, the stored length of each chunk, then the chunks at 0x80 alignment, each a u32 length + one zlib stream, or the plain bytes when the stored length equals the chunk's length (`kt_gz` in `shader_split.py`).
