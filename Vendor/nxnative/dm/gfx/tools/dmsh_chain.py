#!/usr/bin/env python3
# Translation chain version of the B shader library (the build result must be determined by source alone).
# Chain version V = first 12 digits of the sha256 of the contents of the following in-repo files + the translation options: this script, dmsh_build.py, dmsh_fetch.py (readable-tile version), the dmsh_xlate sources (Program.cs, csproj),
# from the current game profile (dm/games/<id>/, chosen by DM_GAME, default smbw) the mapping table (including the conflict table), the vertex / pixel pair table (shader_pairs.tsv, used by vs_pad), the answer table for translation queries (dmsh_facts.py and shader_facts.tsv),
# the keys of the profile's game.tsv that affect the build (nvn_*, shader_*), the iOS compile convention ios_metal.py, and the tool lock dmsh_chain.lock (measured fingerprints of the Ryujinx shader dll / spirv-cross / metal compiler). The tables differ per game, so V does too.
# The build (dmsh_build.py) writes into <cache dir>/b-<V>/ and the reflection json records chain = V; at compile time the host takes V from the game profile's dmsh_chain.h, loads only from b-<V>/ and verifies each json.
# Usage: dmsh_chain.py                 print V (default options)
#       dmsh_chain.py --header        rewrite the game profile's dmsh_chain.h (run after changing any file listed above)
#       dmsh_chain.py --check-tools   verify that the actual tools match the lock file; on mismatch print [RED] lines and exit 1
#       dmsh_chain.py --update-lock   rewrite the lock file from the actual tools (run after changing Ryujinx / spirv-cross / Xcode; committed to the repo)
# Environment: XLATE_DEBUG / XLATE_REDUCED (same meaning as in dmsh_build.py, default 1 / 1; non-default options yield a different V, which the host will not load)
import os, sys, hashlib, subprocess
DM_ROOT = os.environ.get('DM_ROOT') or os.path.expanduser('~/dm-work')   # Workspace root (game files, build outputs and run artifacts are all under it)
HERE = os.path.dirname(os.path.abspath(__file__)); GFX = os.path.dirname(HERE); HOME = os.path.expanduser('~')
sys.path.insert(0, os.path.join(GFX, '../games')); import game as _game   # game profiles
GAME = _game.load()
FILES = ['tools/dmsh_chain.py', 'tools/dmsh_build.py', 'tools/dmsh_fetch.py', 'tools/dmsh_facts.py', 'tools/dmsh_xlate/Program.cs', 'tools/dmsh_xlate/dmsh_xlate.csproj', '../ios/tools/ios_metal.py', 'tools/dmsh_chain.lock']
TABLES = ['shader_facts.tsv', 'shader_map.tsv', 'shader_map.tsv.conflicts.tsv', 'shader_pairs.tsv']   # in the game profile folder
LOCK = os.path.join(HERE, 'dmsh_chain.lock'); HEADER = str(GAME.table('dmsh_chain.h'))
# the translator defaults to the in-repo build that matches the lock file (a rebuilt dll has different fingerprints)
XLATE_DIR = os.path.dirname(os.environ.get('XLATE', os.path.join(HERE, 'dmsh_xlate_bin/dmsh_xlate')))

def options():
    return 'debug=%s reduced=%s' % (os.environ.get('XLATE_DEBUG', '1') != '0', os.environ.get('XLATE_REDUCED', '1') == '1')

def version():
    h = hashlib.sha256()
    for f in FILES:
        h.update(f.encode() + b'\0' + open(os.path.join(GFX, f), 'rb').read() + b'\0')
    for f in TABLES:
        h.update(f'game/{f}'.encode() + b'\0' + GAME.table(f).read_bytes() + b'\0')
    h.update(''.join(f'{k}\t{chr(9).join(v)}\n' for k, v in GAME.rows if k.startswith(('nvn_', 'shader_'))).encode())   # the profile keys that affect the build
    h.update(options().encode())
    return h.hexdigest()[:12]

def sha16(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16]

def tools_now():
    """Actual tool fingerprints: translator dll (including the Ryujinx shader library), spirv-cross, metal compiler (macOS / iOS)"""
    t = {}
    for dll in ('dmsh_xlate.dll', 'Ryujinx.Graphics.Shader.dll', 'Ryujinx.Common.dll'): t[dll] = sha16(os.path.join(XLATE_DIR, dll))
    t['xlate_source'] = subprocess.run([os.path.join(XLATE_DIR, 'dmsh_xlate'), '--source-sha'], capture_output=True, text=True).stdout.strip()
    sc = subprocess.run(['which', 'spirv-cross'], capture_output=True, text=True).stdout.strip()
    t['spirv-cross'] = sha16(sc) if sc else 'missing'
    for sdk in ('macosx', 'iphoneos'):
        t['metal_' + sdk] = subprocess.run(['xcrun', '-sdk', sdk, 'metal', '--version'], capture_output=True, text=True).stdout.splitlines()[0:1] or ['missing']
        t['metal_' + sdk] = t['metal_' + sdk][0]
    return t

def xlate_source_sha():   # same convention as dmsh_xlate --source-sha: the embedded Program.cs and csproj concatenated in that order
    return hashlib.sha256(b''.join(open(os.path.join(HERE, 'dmsh_xlate', f), 'rb').read() for f in ('Program.cs', 'dmsh_xlate.csproj'))).hexdigest()[:16]

def check_tools():
    want = dict(l.rstrip('\n').split('\t', 1) for l in open(LOCK) if '\t' in l and not l.startswith('#'))
    now = tools_now(); bad = [f'{k}: lock {want.get(k)} / actual {v}' for k, v in now.items() if want.get(k) != v]
    if now['xlate_source'] != xlate_source_sha(): bad.append(f'the translator was not built from the in-repo source: embedded source {now["xlate_source"]} / in repo {xlate_source_sha()} (rebuild dmsh_xlate)')
    return bad

if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['--update-lock']:
        t = tools_now()
        if t['xlate_source'] != xlate_source_sha(): sys.exit(f'[RED] the translator was not built from the in-repo source (embedded {t["xlate_source"]} / in repo {xlate_source_sha()}): rebuild dmsh_xlate first')
        open(LOCK, 'w').write('# Translation chain tool fingerprints (written by dmsh_chain.py --update-lock; regenerate after changing tools and commit it)\n' + ''.join(f'{k}\t{v}\n' for k, v in t.items()))
        print('wrote', LOCK)
    elif a == ['--check-tools']:
        bad = check_tools()
        for b in bad: print('[RED] translation chain tools do not match the lock file: ' + b)
        sys.exit(1 if bad else 0)
    elif a == ['--header']:
        open(HEADER, 'w').write(f'// Generated file (dm/gfx/tools/dmsh_chain.py --header, game {GAME.id}): the B shader library translation chain version this source tree expects (default options); the host loads only <library dir>/b-<V>/\n'
                                f'#define DMSH_CHAIN "{version()}"\n')
        print(version())
    elif not a: print(version())
    else: sys.exit(__doc__ if __doc__ else 'usage: see the file header')
