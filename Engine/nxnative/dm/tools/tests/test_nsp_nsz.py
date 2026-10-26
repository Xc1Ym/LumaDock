"""NSP script: NSZ / XCZ files in the NSP folder are listed by their ticket like NSPs (scan_nsps) and converted once with nsz -D into <title ID>_build/nsp/ (decompress_nsz):
a conversion is moved in only when nsz exits 0 and made the file, and reused while its source is unchanged. nsz itself is stood in for (no game files, keys or nsz needed)."""
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('build_ipa_from_nsp', REPO / 'scripts/build_ipa_from_nsp.py')
nsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(nsp)

APP = 0x010020D01AD24000


def pfs0(path, names):   # a PFS0 holding empty files with these names (enough for title_of)
    strs = b''.join(n.encode() + b'\0' for n in names); ent, o = b'', 0
    for n in names: ent += struct.pack('<QQII', 0, 0, o, 0); o += len(n) + 1
    path.write_bytes(b'PFS0' + struct.pack('<III', len(names), len(strs), 0) + ent + strs)


class Nsz(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        self.base = self.tmp / 'Game [v0].nsz'; pfs0(self.base, [f'{APP:016x}0000000000000011.tik', 'a.ncz'])
        self.upd = self.tmp / 'Game [v65536].nsz'; pfs0(self.upd, [f'{APP | 0x800:016x}0000000000000011.tik', 'b.ncz'])
        self.runs, self.fail = [], False
        for cm in (mock.patch.object(nsp, 'PROG', mock.Mock()), mock.patch.object(nsp, 'say', lambda m: None), mock.patch.object(nsp, 'run', self.fake_nsz),
                   mock.patch.object(importlib.util, 'find_spec', lambda m, *a: object() if m == 'nsz' else None)):
            cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)

    def fake_nsz(self, cmd, log, env=None, cwd=None, on_line=None):   # nsz -D --keys K -o OUT SRC: writes OUT/<stem>.nsp, or a partial one and a non-zero exit
        src, out = Path(cmd[-1]), Path(cmd[cmd.index('-o') + 1])
        self.runs.append(src.name)
        (out / (src.stem + '.nsp')).write_bytes(b'partial' if self.fail else b'nsp of ' + src.name.encode())
        if self.fail: raise nsp.BuildError('nsz exit code 1')

    def test_scan_and_convert(self):
        app, fam = nsp.scan_nsps(self.tmp)
        self.assertEqual((app, fam['base'], fam['updates']), (APP, self.base, [(65536, self.upd)]))
        fam = nsp.decompress_nsz(self.tmp, app, fam, self.tmp / 'prod.keys', {})
        out = self.tmp / f'{APP:016X}_build' / 'nsp'
        self.assertEqual((fam['base'], fam['updates']), (out / 'Game [v0].nsp', [(65536, out / 'Game [v65536].nsp')]))
        self.assertEqual(fam['base'].read_bytes(), b'nsp of Game [v0].nsz')
        self.assertFalse((out / 'partial').exists())
        nsp.decompress_nsz(self.tmp, app, nsp.scan_nsps(self.tmp)[1], self.tmp / 'prod.keys', {})   # unchanged sources: reused
        self.assertEqual(len(self.runs), 2)
        os.utime(self.upd, ns=(0, 0))   # a changed source: converted again
        nsp.decompress_nsz(self.tmp, app, nsp.scan_nsps(self.tmp)[1], self.tmp / 'prod.keys', {})
        self.assertEqual(self.runs[2:], [self.upd.name])

    def test_failed_conversion_is_not_kept(self):
        app, fam = nsp.scan_nsps(self.tmp); self.fail = True
        with self.assertRaises(nsp.BuildError): nsp.decompress_nsz(self.tmp, app, fam, self.tmp / 'prod.keys', {})
        out = self.tmp / f'{APP:016X}_build' / 'nsp'
        self.assertEqual(sorted(p.name for p in out.iterdir()), [])   # neither the partial file nor a key
        self.fail = False
        nsp.decompress_nsz(self.tmp, app, fam, self.tmp / 'prod.keys', {})
        self.assertEqual((out / 'Game [v0].nsp').read_bytes(), b'nsp of Game [v0].nsz')

    def test_an_nsp_beside_wins_and_nsps_need_no_nsz(self):
        pfs0(self.tmp / 'Game [v0].nsp', [f'{APP:016x}0000000000000011.tik']); self.upd.unlink()
        app, fam = nsp.scan_nsps(self.tmp)
        self.assertEqual((fam['base'], fam['updates']), (self.tmp / 'Game [v0].nsp', []))
        with mock.patch.object(importlib.util, 'find_spec', lambda m, *a: None):
            self.assertIs(nsp.decompress_nsz(self.tmp, app, fam, self.tmp / 'prod.keys', {}), fam)

    def test_missing_nsz(self):
        app, fam = nsp.scan_nsps(self.tmp)
        with mock.patch.object(importlib.util, 'find_spec', lambda m, *a: None), self.assertRaisesRegex(nsp.BuildError, 'pip install nsz'):
            nsp.decompress_nsz(self.tmp, app, fam, self.tmp / 'prod.keys', {})


if __name__ == '__main__':
    unittest.main()
