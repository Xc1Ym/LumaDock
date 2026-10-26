"""NSP script Mac app (scripts/build_ipa_from_nsp.py --platform mac-app, dm/mac/pack_app.py, dm/mac/launcher.c): the bundle's layout, Info.plist and ad-hoc signature without the hardened
runtime; the launcher's environment for the host (the bundle's files, the save, temporary files and log in the player's Library), the previous log kept, environment files, the host's exit
code returned and SIGTERM forwarded to it, an alert when the game data is missing; the script's options and its pack_app.py command line.
No game files, keys or Xcode needed: a stand-in host compiled here records what it was given (temporary files only in a temporary folder)."""
import contextlib
import importlib.util
import io
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / 'scripts/build_ipa_from_nsp.py'
spec = importlib.util.spec_from_file_location('build_ipa_from_nsp', SCRIPT)
nsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(nsp)
spec = importlib.util.spec_from_file_location('pack_app', REPO / 'dm/mac/pack_app.py')
pack_app = importlib.util.module_from_spec(spec); spec.loader.exec_module(pack_app)
TID = '01008CF01BAAC000'

HOST_C = r'''#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
extern char **environ;
static void term(int s) { (void)s; _exit(3); }
int main(int argc, char **argv) {
    char p[1024]; snprintf(p, sizeof p, "%s/host_run.txt", getenv("HOME")); FILE *f = fopen(p, "w");
    for (char **e = environ; *e; e++) fprintf(f, "%s\n", *e);
    for (int i = 0; i < argc; i++) fprintf(f, "argv%d=%s\n", i, argv[i]);
    char cwd[1024]; fprintf(f, "cwd=%s\n", getcwd(cwd, sizeof cwd)); fclose(f);
    printf("standin host output\n"); fflush(stdout);
    if (getenv("STANDIN_WAIT")) { signal(SIGTERM, term); for (;;) pause(); }
    return 7;
}
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('codesign'), 'needs macOS (clang, codesign, sips, iconutil)')
class App(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        t = cls.tmp
        (t / 'host.c').write_text(HOST_C)
        subprocess.run(['xcrun', 'clang', '-arch', 'arm64', '-o', t / 'dmhost', t / 'host.c'], check=True)
        for d in ('patched', 'romfs/region_common/audio', 'cache/b-0123456789ab', 'profile', 'font', 'aoc/1', 'bin', 'home'): (t / d).mkdir(parents=True)
        for n, b in (('main.patched.bin', b'code'), ('main.fixups.tsv', b'f'), ('main.gates.tsv', b'g'), ('main.cuts.tsv', b'c'), ('main.obs.tsv', b'o'), ('main.sites.tsv', b's'), ('build_src.sha256', b'h')):
            (t / 'patched' / n).write_bytes(b)
        (t / 'romfs/region_common/audio/edward.bfsar').write_bytes(b'snd')
        (t / 'cache/b-0123456789ab/k_b.metallib').write_bytes(b'lib'); (t / 'cache/b-0123456789ab/inputs.tsv').write_text('# stamp\n')
        (t / 'cache/cas').mkdir()   # the Metal compile cache: not for the app
        for n in ('shader_map.tsv', 'pso_manifest.tsv', 'c1_full.tsv', 'game.tsv'): (t / 'profile' / n).write_text(n)
        (t / 'font/nintendo_ext.ttf').write_bytes(b'ttf')
        (t / 'aoc/1/x').write_bytes(b'dlc')
        (t / 'env.txt').write_text('# baked in\nDM_BAKED=1\nDM_BOTH=bundle\n')
        subprocess.run(['sips', '-s', 'format', 'jpeg', '-z', '256', '256', '/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns',
                        '--out', t / 'icon.jpg'], check=True, capture_output=True)
        (t / 'bin/osascript').write_text('#!/bin/sh\necho "$@" > "$HOME/alert.txt"\nprintf "%s\\0" "$@" > "$HOME/alert.args"\n'
                                       '/usr/bin/osacompile -o "$HOME/alert.scpt" "$1" "$2" 2> "$HOME/alert.error"\n')
        (t / 'bin/osascript').chmod(0o755)
        cls.app = t / 'Game - Test.app'
        cls.args = pack_app.parse([str(cls.app), '--host', str(t / 'dmhost'), '--patched', str(t / 'patched'), '--romfs', str(t / 'romfs'), '--msl', str(t / 'cache/b-0123456789ab'),
                                   '--tables', str(t / 'profile'), '--font', str(t / 'font'), '--aoc', str(t / 'aoc'), '--env-file', str(t / 'env.txt'), '--title-id', TID.lower(),
                                   '--name', 'Game: Test', '--version', '1.0.1', '--lang', 'fr', '--marker', 'region_common/audio/edward.bfsar', '--icon', str(t / 'icon.jpg'),
                                   '--category', 'public.app-category.games'])
        with contextlib.redirect_stdout(io.StringIO()): pack_app.pack(cls.args)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.tmp)

    def launch(self, wait=False, **env):
        home = self.tmp / 'home'
        e = dict(HOME=str(home), PATH=f'{self.tmp / "bin"}:/usr/bin:/bin', **env)
        if wait: e['STANDIN_WAIT'] = '1'
        return subprocess.Popen([self.app / 'Contents/MacOS/nxnative'], env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def host_run(self):
        out = {}
        for ln in (self.tmp / 'home/host_run.txt').read_text().splitlines():
            k, _, v = ln.partition('='); out[k] = v
        return out

    def test_layout(self):
        c = self.app / 'Contents'
        self.assertFalse(self.app.with_name(self.app.name + '.partial').exists())
        self.assertEqual(sorted(p.name for p in (c / 'MacOS').iterdir()), ['dmhost', 'nxnative'])
        self.assertEqual(sorted(p.name for p in (c / 'Resources/dm').iterdir()),
                         ['c1_full.tsv', 'env.txt', 'font', 'main.cuts.tsv', 'main.fixups.tsv', 'main.gates.tsv', 'main.obs.tsv', 'main.patched.bin', 'pso_manifest.tsv', 'shader_map.tsv'])
        self.assertEqual([p.name for p in (c / 'Resources/msl').iterdir()], ['b-0123456789ab'])   # the libraries only, not the compile cache
        self.assertEqual((c / 'Resources/msl/b-0123456789ab/k_b.metallib').read_bytes(), b'lib')
        self.assertTrue((c / 'Resources/romfs/region_common/audio/edward.bfsar').is_file())
        self.assertTrue((c / 'Resources/aoc/1/x').is_file()); self.assertTrue((c / 'Resources/dm/font/nintendo_ext.ttf').is_file())
        self.assertEqual((c / 'Resources/AppIcon.icns').read_bytes()[:4], b'icns')

    def test_info_plist(self):
        p = plistlib.loads((self.app / 'Contents/Info.plist').read_bytes())
        self.assertEqual((p['CFBundleExecutable'], p['CFBundleName'], p['CFBundleIdentifier'], p['CFBundleShortVersionString']), ('nxnative', 'Game: Test', 'org.nxnative.01008cf01baac000', '1.0.1'))
        self.assertEqual((p['DMTitleID'], p['DMLanguage'], p['DMRomfsMarker'], p['CFBundleIconFile']), (TID, 'fr', 'region_common/audio/edward.bfsar', 'AppIcon'))

    def test_signed(self):   # ad-hoc, both the host and the bundle, never the hardened runtime (it refuses the executable memory the host makes for the game's code)
        for target in (self.app, self.app / 'Contents/MacOS/dmhost'):
            subprocess.run(['codesign', '--verify', '--strict', target], check=True, capture_output=True)
            d = subprocess.run(['codesign', '-dv', target], capture_output=True, text=True).stderr
            self.assertIn('Signature=adhoc', d); self.assertNotIn('runtime', d.split('CodeDirectory', 1)[1].split('\n')[0])

    def test_launch(self):
        home = self.tmp / 'home'; sup = home / f'Library/Application Support/nxnative/{TID}'; logs = home / 'Library/Logs/nxnative'
        sup.mkdir(parents=True, exist_ok=True); (sup / 'env.txt').write_text('DM_BOTH=player\n')
        p = self.launch(DM_LANG='ja'); p.communicate(timeout=30)
        self.assertEqual(p.returncode, 7)   # the host's exit code
        r, res = self.host_run(), self.app / 'Contents/Resources'
        self.assertEqual(r['argv0'], str(self.app / 'Contents/MacOS/dmhost')); self.assertEqual(r['argv1'], str(res / 'dm'))
        self.assertEqual((r['DM_ROMFS'], r['DM_MSL_DIR'], r['DM_NVN_SHMAP'], r['DM_FONT_DIR'], r['DM_AOC_DIR']),
                         (str(res / 'romfs'), str(res / 'msl'), str(res / 'dm/shader_map.tsv'), str(res / 'dm/font'), str(res / 'aoc')))
        self.assertEqual((r['DM_SAVE'], r['DM_TEMP'], r['DM_ROOT'], r['cwd']), (str(sup / 'save'), str(sup / 'temp'), str(sup), str(sup)))   # pso_user.tsv goes beside save/
        self.assertEqual((r['DM_WINDOW'], r['DM_AUDIO'], r['DM_LANG']), ('1', '1', 'ja'))   # the caller's DM_LANG wins over the packed language
        self.assertEqual((r['DM_BAKED'], r['DM_BOTH']), ('1', 'player'))   # the player's env.txt before the bundle's
        self.assertTrue((sup / 'save').is_dir()); self.assertTrue((sup / 'temp').is_dir())
        self.assertIn('standin host output', (logs / f'{TID}.log').read_text())
        p = self.launch(); p.communicate(timeout=30)
        self.assertIn('standin host output', (logs / f'{TID}.prev.log').read_text())
        self.assertEqual(self.host_run()['DM_LANG'], 'fr')   # Info.plist DMLanguage

    def test_sigterm(self):   # forwarded to the host, whose exit code comes back
        p = self.launch(wait=True)
        for _ in range(100):
            if (self.tmp / 'home/host_run.txt').exists() and 'STANDIN_WAIT' in self.host_run(): break
            time.sleep(0.05)
        time.sleep(0.2)
        p.send_signal(signal.SIGTERM); p.communicate(timeout=30)
        self.assertEqual(p.returncode, 3)

    def test_missing_data(self):
        broken = self.tmp / 'Broken.app'; shutil.rmtree(broken, ignore_errors=True)
        subprocess.run(['/bin/cp', '-R', self.app, broken], check=True)
        shutil.rmtree(broken / 'Contents/Resources/romfs')
        (self.tmp / 'home/alert.txt').unlink(missing_ok=True)
        p = subprocess.run([broken / 'Contents/MacOS/nxnative'], env=dict(HOME=str(self.tmp / 'home'), PATH=f'{self.tmp / "bin"}:/usr/bin:/bin'), capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 1)
        self.assertIn('game data inside this app is missing', (self.tmp / 'home/alert.txt').read_text())

    def test_missing_modules(self):
        for missing in (('main.patched.bin',), ('main.fixups.tsv',), ('main.patched.bin', 'main.fixups.tsv')):
            with self.subTest(missing=missing):
                broken = self.tmp / 'Missing module.app'; shutil.rmtree(broken, ignore_errors=True)
                shutil.copytree(self.app, broken)
                for name in missing: (broken / 'Contents/Resources/dm' / name).unlink()
                home = self.tmp / 'home'
                for name in ('alert.txt', 'host_run.txt'): (home / name).unlink(missing_ok=True)
                p = subprocess.run([broken / 'Contents/MacOS/nxnative'], env=dict(HOME=str(home), PATH=f'{self.tmp / "bin"}:/usr/bin:/bin'),
                                   capture_output=True, text=True, timeout=30)
                self.assertEqual(p.returncode, 1)
                self.assertFalse((home / 'host_run.txt').exists())
                self.assertIn('game data inside this app is missing', (home / 'alert.txt').read_text())

    def test_alert_title(self):
        broken = self.tmp / 'Quoted name.app'; shutil.copytree(self.app, broken)
        title = 'Game "Test" \\ Edition'
        plist = broken / 'Contents/Info.plist'
        info = plistlib.loads(plist.read_bytes()); info['CFBundleName'] = title; plist.write_bytes(plistlib.dumps(info))
        shutil.rmtree(broken / 'Contents/Resources/romfs')
        home = self.tmp / 'home'
        (home / 'alert.scpt').unlink(missing_ok=True)
        p = subprocess.run([broken / 'Contents/MacOS/nxnative'], env=dict(HOME=str(home), PATH=f'{self.tmp / "bin"}:/usr/bin:/bin'),
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 1)
        self.assertTrue((home / 'alert.scpt').exists(), (home / 'alert.error').read_text())
        args = (home / 'alert.args').read_bytes().decode().split('\0')[:-1]
        self.assertEqual(args[2], title)   # data is passed separately from the compiled script
        self.assertIn('game data inside this app is missing', args[3])

    def test_relocated(self):   # run with the entire build folder unavailable
        with tempfile.TemporaryDirectory() as dst:
            dst = Path(dst).resolve(); moved = dst / self.app.name; home = dst / 'home'; home.mkdir()
            self.app.rename(moved)
            hidden = self.tmp.with_name(self.tmp.name + '.unavailable')
            try:
                self.tmp.rename(hidden)
                p = subprocess.run([moved / 'Contents/MacOS/nxnative'], env=dict(HOME=str(home), PATH='/usr/bin:/bin'), capture_output=True, timeout=30)
                self.assertEqual(p.returncode, 7)
                ran = (home / 'host_run.txt').read_text()
                self.assertIn(f'argv1={moved}/Contents/Resources/dm\n', ran)
                self.assertIn(f'DM_MSL_DIR={moved}/Contents/Resources/msl\n', ran)
                self.assertNotIn(str(self.tmp), ran)
            finally:
                if hidden.exists(): hidden.rename(self.tmp)
                moved.rename(self.app)

    def test_pack_missing_fixups(self):
        with tempfile.TemporaryDirectory() as src:
            src = Path(src); (src / 'main.patched.bin').write_bytes(b'code')
            a = types.SimpleNamespace(**vars(self.args)); a.patched = str(src); a.out = str(self.tmp / 'Incomplete.app')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(SystemExit, 'no rewriter fixups'):
                pack_app.pack(a)
            self.assertFalse(Path(a.out).exists())

    def test_copies(self):   # another volume (no APFS clone): plain copies, the same layout; a new app replaces the old one whole
        with mock.patch.object(pack_app, 'can_clone', lambda *a: False), mock.patch.object(pack_app, 'sign', lambda *a: None), mock.patch('sys.stdout'):
            a = types.SimpleNamespace(**vars(self.args)); a.out = str(self.tmp / 'Copy.app'); a.icon = None
            (self.tmp / 'Copy.app/Contents/stale').mkdir(parents=True)
            pack_app.pack(a)
        self.assertTrue((self.tmp / 'Copy.app/Contents/Resources/romfs/region_common/audio/edward.bfsar').is_file())
        self.assertFalse((self.tmp / 'Copy.app/Contents/stale').exists()); self.assertFalse((self.tmp / 'Copy.app/Contents/Resources/AppIcon.icns').exists())


class Script(unittest.TestCase):
    def test_options(self):
        a = nsp.parse_args(['--platform', 'mac-app', '--mac-sign', 'Developer ID Application: X (T)', '-o', '/tmp/x.app'])
        self.assertEqual((a.platform, a.mac_sign, a.out), ('mac-app', 'Developer ID Application: X (T)', '/tmp/x.app'))

    def test_app_name(self):
        self.assertEqual(nsp.mac_app_name('The Legend of Zelda: Echoes of Wisdom'), 'The Legend of Zelda - Echoes of Wisdom')
        self.assertEqual(nsp.mac_app_name('AC/DC'), 'AC - DC'); self.assertEqual(nsp.mac_app_name(':'), 'nxnative')

    def pack_cmd(self, gfx, **kw):
        ran, tmp = [], Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, tmp)
        out = tmp / 'G.app'
        def fake_run(cmd, log, env=None, cwd=None, on_line=None):
            ran.append([str(c) for c in cmd]); (out / 'Contents/MacOS').mkdir(parents=True); (out / 'Contents/MacOS/dmhost').write_bytes(b'x')
            on_line('step: launcher and host (clones of the game files)')
        g = types.SimpleNamespace(table=lambda n: tmp / 'profile' / n, get={'app_category': 'public.app-category.games', 'romfs_marker': 'a/b'}.get)
        with mock.patch.object(nsp, 'run', fake_run), mock.patch.object(nsp, 'PROG', mock.Mock()), mock.patch.object(nsp, 'chain_of', lambda repo: '0123456789ab'):
            clones = nsp.mac_app(sys.executable, REPO, out, 0x01008CF01BAAC000, tmp, tmp / 'ex', tmp / 'patched', tmp / 'dmhost', tmp / 'font', tmp / 'shader/cache' if gfx == 'nvn' else tmp / 'shader',
                                 kw.get('aoc'), gfx, 'en-US', g, 'Game', '1.0.0', 'org.nxnative.01008cf01baac000', None, kw.get('sign', ''), {}, tmp)
        self.assertTrue(clones)
        c = ran[0]; return {c[i]: c[i + 1] for i in range(3, len(c) - 1) if c[i].startswith('--')}, tmp

    def test_pack_command(self):
        o, tmp = self.pack_cmd('nvn')
        self.assertEqual((o['--msl'], o['--romfs'], o['--tables'], o['--title-id'], o['--sign'], o['--marker']),
                         (str(tmp / 'shader/cache/b-0123456789ab'), str(tmp / 'ex/RomFS'), str(tmp / 'profile'), TID, '-', 'a/b'))
        self.assertNotIn('--aoc', o); self.assertNotIn('--icon', o)
        o, tmp = self.pack_cmd('vulkan', aoc=Path('/x/aoc'), sign='Developer ID Application: X (T)')
        self.assertEqual((o['--msl'], o['--aoc'], o['--sign']), (str(tmp / 'shader/vk'), '/x/aoc', 'Developer ID Application: X (T)'))


if __name__ == '__main__':
    unittest.main()
