"""Keep offline runtime inputs while reducing the signed distribution payload."""
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from runtime_size import compact_runtime, payload_size


class RuntimeSizeTests(unittest.TestCase):
    def test_pruning_preserves_modules_data_notices_and_sources_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            removed = ['python/share/doc/python/examples/demo.py',
                       'python/lib/python3.14/site-packages/fontTools/misc/generated.c',
                       'converter/python/Crypto/SelfTest/test_AES.py']
            retained = ['python/Resources/Python.app/Contents/MacOS/Python',
                        'python/lib/python3.14/config-3.14-darwin/Makefile',
                        'python/lib/python3.14/site-packages/fontTools/misc/bezierTools.py',
                        'python/lib/python3.14/site-packages/fonttools.dist-info/licenses/LICENSE',
                        'converter/python/Crypto/Cipher/AES.py',
                        'converter/python/pykakasi/data/kanwadict4.db',
                        'converter/sources/pykakasi.tar.gz', 'licenses/Python-LICENSE.txt']
            for name in removed + retained:
                p = runtime/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'fixture')
            before = payload_size(runtime)
            compact_runtime(runtime)
            self.assertTrue(all(not (runtime/p).exists() for p in removed))
            self.assertTrue(all((runtime/p).read_bytes() == b'fixture' for p in retained))
            self.assertEqual(before-payload_size(runtime), len(removed)*len(b'fixture'))
            self.assertEqual(compact_runtime(runtime)['removedBytes'], 0)

    @unittest.skipUnless(sys.platform == 'darwin' and platform.machine() == 'arm64', 'Mach-O execution needs Apple Silicon')
    def test_real_universal_executable_keeps_working_after_thinning(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            p = runtime/'tool with spaces'
            source = runtime/'fixture.c'
            source.write_text('int main(void) { return 0; }')
            subprocess.run(['xcrun', 'clang', '-arch', 'arm64', '-arch', 'x86_64', source, '-o', p],
                           check=True, capture_output=True)
            self.assertIn('arm64', subprocess.check_output(['lipo', '-archs', p], text=True))
            before = p.stat().st_size
            report = compact_runtime(runtime)
            self.assertEqual(subprocess.check_output(['lipo', '-archs', p], text=True).strip(), 'arm64')
            self.assertGreater(report['thinnedBinaries'], 0)
            self.assertLess(p.stat().st_size, before)
            subprocess.run(['codesign', '--force', '--sign', '-', p], check=True, capture_output=True)
            subprocess.run([p], check=True)
            self.assertEqual(compact_runtime(runtime)['thinnedBinaries'], 0)
