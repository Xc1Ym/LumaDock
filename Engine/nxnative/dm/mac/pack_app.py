#!/usr/bin/env python3
# Pack a self-contained, double-clickable Mac app of a game (the NSP script's --platform mac-app): the launcher (dm/mac/launcher.c, compiled here) as CFBundleExecutable, the Mac host beside it,
# and in Contents/Resources what the IPA carries (dm/ios/tools/build_ipa.sh): romfs/ (the RomFS), msl/<b-chain | vk | gl>/ (the Mac shader libraries, the folder named as in the IPA),
# aoc/<index>/ (DLC), and dm/ (the rewritten modules and their rewriter tables, nro.tsv, the profile's shader_map.tsv / pso_manifest.tsv / c1_full.tsv / cb_extent.tsv, font/, env.txt),
# plus AppIcon.icns from the game's icon (sips, iconutil) and the Info.plist keys the launcher reads (DMTitleID, DMRomfsMarker, DMLanguage).
# The large folders are APFS clones (cp -c) when the app is on the same APFS volume as the build, so they take no space; plain copies otherwise.
# Signing: the inner host first, then the bundle (codesign --force --sign <identity>; '-' = ad-hoc), without the hardened runtime: the host maps the game's code executable, which the hardened
# runtime refuses without entitlements, and so the app cannot be notarized.
# Usage: pack_app.py <out.app> --host <dmhost> --patched <dir> --romfs <dir> --msl <dir> --tables <profile dir> --font <dir> --title-id <id> --name <name> [options]
#   Writes <out.app>.partial and swaps it in at the end (the old app stays as it was on failure); prints one line per step ("step: ...")
import argparse, ctypes, os, plistlib, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_FILES = ('*.patched.bin', '*.fixups.tsv', '*.gates.tsv', '*.cuts.tsv', '*.obs.tsv', 'nro.tsv')   # what the host reads from the module folder (build_ipa.sh copies the same tables)
TABLES = ('shader_map.tsv', 'pso_manifest.tsv', 'c1_full.tsv', 'cb_extent.tsv')   # read beside DM_NVN_SHMAP; any of them may be absent (a Vulkan or GL game has no c1_full.tsv)
EXE = 'nxnative'   # the launcher's file name (Contents/MacOS/nxnative)
ICON_SIZES = (16, 32, 128, 256, 512)


def step(msg): print(f'step: {msg}', flush=True)


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode: raise SystemExit(f'{Path(str(cmd[0])).name} failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-1500:]}')
    return r.stdout


def first_file(d):
    for root, _, files in os.walk(d):
        if files: return Path(root) / files[0]
    return None


def can_clone(src, dst_dir):   # whether a file of src can be cloned into dst_dir (the same APFS volume)
    f = first_file(src)
    if f is None: return False
    t = dst_dir / '.clone_test'
    try:
        if t.exists(): t.unlink()
        return ctypes.CDLL(None, use_errno=True).clonefile(str(f).encode(), str(t).encode(), 0) == 0
    finally:
        if t.exists(): t.unlink()


def tree_bytes(d):
    return sum((Path(r) / f).stat().st_size for r, _, fs in os.walk(d) for f in fs)


def copy(srcs, dst, clone):   # cp -R of each source to dst (a new path for one folder, an existing folder for files); -c clones
    run(['/bin/cp', '-R'] + (['-c'] if clone else []) + list(srcs) + [dst])


def min_os(host):   # the host's deployment target (LC_BUILD_VERSION minos): the launcher is built for the same and Info.plist says it
    m = re.search(r'cmd LC_BUILD_VERSION.*?minos (\S+)', run(['otool', '-l', host]), re.S)
    return m.group(1) if m else '14.0'


def build_launcher(out, minos):
    run(['xcrun', 'clang', '-arch', 'arm64', f'-mmacosx-version-min={minos}', '-O2', '-Wall', '-o', out, HERE / 'launcher.c', '-framework', 'CoreFoundation'])


def make_icns(jpg, out):   # the game's icon (256x256 JPEG) at every size an .icns holds
    with tempfile.TemporaryDirectory() as t:
        s = Path(t) / 'AppIcon.iconset'; s.mkdir()
        for n in ICON_SIZES:
            for k, suffix in ((1, ''), (2, '@2x')):
                run(['sips', '-s', 'format', 'png', '-z', n * k, n * k, jpg, '--out', s / f'icon_{n}x{n}{suffix}.png'])
        run(['iconutil', '-c', 'icns', s, '-o', out])


def info_plist(a, minos, icon):
    p = {'CFBundleName': a.name, 'CFBundleDisplayName': a.name, 'CFBundleIdentifier': a.bundle_id or f'org.nxnative.{a.title_id.lower()}',
         'CFBundleVersion': a.version or '1.0', 'CFBundleShortVersionString': a.version or '1.0', 'CFBundlePackageType': 'APPL', 'CFBundleExecutable': EXE,
         'CFBundleInfoDictionaryVersion': '6.0', 'LSMinimumSystemVersion': minos, 'LSArchitecturePriority': ['arm64'], 'NSHighResolutionCapable': True,
         'LSApplicationCategoryType': a.category or 'public.app-category.games', 'DMTitleID': a.title_id.upper(), 'DMRomfsMarker': a.marker or '', 'DMLanguage': a.lang or 'en-US'}
    if icon: p['CFBundleIconFile'] = 'AppIcon'
    return p


def sign(app, identity):   # the inner host first, then the bundle (its resources and the launcher); no --options runtime (see the top)
    host = app / 'Contents/MacOS/dmhost'
    for target in (host, app):
        try: run(['codesign', '--force', '--sign', identity, target])
        except SystemExit as e:
            if 'detritus' not in str(e): raise
            run(['xattr', '-cr', app]); run(['codesign', '--force', '--sign', identity, target])   # Finder information or resource forks on copied files: codesign refuses them


def pack(a):
    out = Path(a.out).resolve()
    if out.suffix != '.app': raise SystemExit(f'the output must end in .app: {out}')
    tmp = out.with_name(out.name + '.partial')
    shutil.rmtree(tmp, ignore_errors=True)
    c = tmp / 'Contents'; mac, res = c / 'MacOS', c / 'Resources'; dm = res / 'dm'
    for d in (mac, dm / 'font'): d.mkdir(parents=True)
    romfs, msl, aoc = Path(a.romfs), Path(a.msl), Path(a.aoc) if a.aoc else None
    if a.marker and not (romfs / a.marker).exists(): raise SystemExit(f'no RomFS at {romfs} (missing {a.marker})')
    if not msl.is_dir(): raise SystemExit(f'no shader libraries at {msl}')
    clone = can_clone(romfs, res)
    big = [romfs, msl] + ([aoc] if aoc else [])
    if not clone:
        need, free = sum(tree_bytes(d) for d in big), shutil.disk_usage(res).free
        if need + (1 << 30) > free: raise SystemExit(f'the app needs {need / 2**30:.1f} GB on the volume of {out.parent} (no APFS clones from the build there) and {free / 2**30:.1f} GB are free')
    step(f'launcher and host ({"clones" if clone else "copies"} of the game files)')
    minos = min_os(a.host)
    build_launcher(mac / EXE, minos)
    shutil.copy2(a.host, mac / 'dmhost')
    mods = sorted({p for pat in MODULE_FILES for p in Path(a.patched).glob(pat)})
    if not any(p.name.endswith('.patched.bin') for p in mods): raise SystemExit(f'no rewritten module in {a.patched}')
    for p in mods:
        if p.name.endswith('.patched.bin') and not p.with_name(p.name.removesuffix('.patched.bin') + '.fixups.tsv').is_file():
            raise SystemExit(f'no rewriter fixups for {p}')
    copy(mods, dm, clone)
    tables = [Path(a.tables) / n for n in TABLES if (Path(a.tables) / n).is_file()]
    if tables: copy(tables, dm, False)
    fonts = sorted(Path(a.font).glob('*.ttf'))
    if fonts: copy(fonts, dm / 'font', False)
    if a.env_file: shutil.copyfile(a.env_file, dm / 'env.txt')
    step('shader libraries'); (res / 'msl').mkdir(); copy([msl], res / 'msl' / (a.msl_name or msl.name), clone)
    if aoc: step('add-on content'); copy([aoc], res / 'aoc', clone)
    step('game files'); copy([romfs], res / 'romfs', clone)
    icon = bool(a.icon and Path(a.icon).is_file())
    if icon: step('icon'); make_icns(a.icon, res / 'AppIcon.icns')
    info = info_plist(a, minos, icon)
    info['DMModuleFiles'] = [p.name for p in mods]
    (c / 'Info.plist').write_bytes(plistlib.dumps(info))
    (c / 'PkgInfo').write_text('APPL????')
    step(f'signing ({"ad-hoc" if a.sign == "-" else a.sign})'); sign(tmp, a.sign)
    old = out.with_name(out.name + '.old')
    shutil.rmtree(old, ignore_errors=True)
    if out.exists(): out.rename(old)
    tmp.rename(out)
    shutil.rmtree(old, ignore_errors=True)
    print(f'app: {out}', flush=True)


def parse(argv):
    ap = argparse.ArgumentParser(prog='pack_app.py', description='Pack a self-contained Mac app of a game')
    ap.add_argument('out', help='the app (<name>.app)')
    ap.add_argument('--host', required=True, help='the Mac host built for the profile')
    ap.add_argument('--patched', required=True, help='the rewritten modules (patch_nso.py output)')
    ap.add_argument('--romfs', required=True, help='the RomFS of the packed version')
    ap.add_argument('--msl', required=True, help='the Mac shader libraries: <shader>/cache/b-<chain>, or a Vulkan or GL game\'s <shader>/vk or gl')
    ap.add_argument('--msl-name', help='its folder name in the app (default: its own)')
    ap.add_argument('--tables', required=True, help='the game profile folder (shader_map.tsv and the tables beside it)')
    ap.add_argument('--font', required=True, help='the folder of the shared-font stand-ins (nintendo_ext.ttf)')
    ap.add_argument('--aoc', help='the DLC RomFS folders by index')
    ap.add_argument('--env-file', help='environment switches baked in (Resources/dm/env.txt)')
    ap.add_argument('--title-id', required=True); ap.add_argument('--name', required=True)
    ap.add_argument('--version'); ap.add_argument('--bundle-id'); ap.add_argument('--category'); ap.add_argument('--lang'); ap.add_argument('--marker', help='the profile\'s romfs_marker')
    ap.add_argument('--icon', help='the game icon (icon.jpg from the control data)')
    ap.add_argument('--sign', default='-', help='codesign identity (default: - = ad-hoc)')
    return ap.parse_args(argv)


if __name__ == '__main__':
    pack(parse(sys.argv[1:]))
