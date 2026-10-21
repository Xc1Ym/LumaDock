import pathlib
import sys
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from package import audit
from product import PRODUCT
from verify_release import verify_icons, verify_source
from runtime_audit import check_load_paths, rpaths, verify_portable_runtime


class DistributionTests(unittest.TestCase):
    def test_runtime_audit_rejects_builder_dependencies_and_search_paths(self):
        good='binary:\n\t@loader_path/../lib/liblz4.dylib (compatibility version 1.0.0)\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)'
        commands='cmd LC_RPATH\n cmdsize 48\n path @loader_path/../lib (offset 12)'
        check_load_paths('fixture',good,commands)
        check_load_paths('fixture',good+'\n/Users/builder/project/tool (architecture arm64):\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)',commands)
        self.assertEqual(rpaths(commands),['@loader_path/../lib'])
        with self.assertRaisesRegex(RuntimeError,'dependency'):
            check_load_paths('fixture',good+'\n\t/opt/homebrew/lib/libbad.dylib (compatibility version 1.0.0)','')
        with self.assertRaisesRegex(RuntimeError,'search path'):
            check_load_paths('fixture',good,commands.replace('@loader_path/../lib','/Users/builder/project/lib'))

    def test_runtime_audit_rejects_external_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);(root/'tool').symlink_to('/usr/bin/true')
            with self.assertRaisesRegex(RuntimeError,'symlink'):verify_portable_runtime(root)

    def test_multi_resolution_icons(self):
        verify_icons()

    def test_release_audit_rejects_private_data_and_game_art(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for name in ('prod.keys', 'game.nsp', 'cache/shaders.metallib', 'saves/slot.dat', 'cover.png'):
                path = root/name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b'private-fixture')
                with self.assertRaises(RuntimeError, msg=name):
                    audit(root)
                path.unlink()
            (root/'LumaDock.icns').write_bytes(b'icon')
            self.assertEqual(len(audit(root)), 1)

    def test_source_audit_rejects_hidden_private_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('work/key.txt', 'Runtime/lib.txt', 'game.nsp', '../outside.txt'):
                archive = pathlib.Path(directory)/'test.zip'
                with zipfile.ZipFile(archive, 'w') as output:
                    output.writestr(PRODUCT['name']+'/'+name, 'fixture')
                with self.assertRaises(AssertionError, msg=name):
                    verify_source(archive)


    def test_source_audit_rejects_unlisted_game_screenshot(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=pathlib.Path(directory)/'test.zip'
            with zipfile.ZipFile(archive,'w') as output:
                for name in ('README.md','README.zh-CN.md','LICENSE','.github/workflows/ci.yml','Assets/LumaDock.ico','Vendor/nxnative/LICENSE'):
                    output.writestr(PRODUCT['name']+'/'+name,'fixture')
                output.writestr(PRODUCT['name']+'/docs/screenshots/game-cover.jpg','private artwork')
            with self.assertRaises(AssertionError): verify_source(archive)

if __name__ == '__main__':
    unittest.main()
