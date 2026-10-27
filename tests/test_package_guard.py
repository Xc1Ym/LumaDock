"""Prevent a release rebuild from deleting a live app's runtime dependencies."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import package


class PackageGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='luma-package-')
        self.root=Path(self.tmp.name).resolve();self.target=self.root/'App With Spaces.app'
        (self.target/'Contents/MacOS').mkdir(parents=True)
        (self.target/'sentinel').write_text('old working app')
        self.staged=self.root/'staging/LumaNX.app';self.staged.mkdir(parents=True)
        (self.staged/'sentinel').write_text('new validated app')
    def tearDown(self): self.tmp.cleanup()
    def ps(self,code=0,executables=''):
        return patch('package.subprocess.run',return_value=SimpleNamespace(returncode=code,stdout=executables))
    def test_native_app_or_runtime_child_blocks_replacement(self):
        for path in ('Contents/MacOS/LumaNX','Contents/Resources/Runtime/python/bin/python3.14','Contents/Resources/Runtime/bin/spirv-cross'):
            with self.subTest(path=path),self.ps(executables=str(self.target/path)+'\n'):
                with self.assertRaisesRegex(RuntimeError,'running'): package.publish_app(self.staged,self.target)
                self.assertEqual((self.target/'sentinel').read_text(),'old working app')
                self.assertTrue((self.staged/'sentinel').is_file())
    def test_process_check_failure_keeps_old_app(self):
        with self.ps(code=1):
            with self.assertRaisesRegex(RuntimeError,'Cannot check'): package.publish_app(self.staged,self.target)
        self.assertTrue((self.target/'sentinel').is_file())
    def test_other_app_with_same_name_does_not_block(self):
        with self.ps(executables=str(self.root/'unrelated'/self.target.name/'Contents/MacOS/LumaNX')):
            package.publish_app(self.staged,self.target)
        self.assertEqual((self.target/'sentinel').read_text(),'new validated app')
        self.assertEqual((self.root/'staging/previous.app/sentinel').read_text(),'old working app')
    def test_publish_failure_restores_previous_app(self):
        rename=Path.rename
        def fail_selected(path,target):
            if path==self.staged: raise OSError('simulated publication failure')
            return rename(path,target)
        with self.ps(),patch.object(Path,'rename',fail_selected):
            with self.assertRaisesRegex(OSError,'publication failure'):package.publish_app(self.staged,self.target)
        self.assertEqual((self.target/'sentinel').read_text(),'old working app')
    def test_failed_relocated_runtime_check_restores_previous_app(self):
        def invalid(app): raise RuntimeError('relocated runtime failed')
        with self.ps():
            with self.assertRaisesRegex(RuntimeError,'relocated runtime'): package.publish_app(self.staged,self.target,invalid)
        self.assertEqual((self.target/'sentinel').read_text(),'old working app')
        self.assertEqual((self.staged/'sentinel').read_text(),'new validated app')
    def test_failed_staging_keeps_existing_target(self):
        source=self.root/'source';bin_dir=self.root/'bin';bin_dir.mkdir()
        (bin_dir/package.PRODUCT['executable']).write_text('synthetic executable')
        for file in ('work/Runtime/versions.json','work/Runtime/converter/manifest.json','Assets/LumaNX.icns'):
            p=source/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
        xcode=self.root/'Xcode.app/Contents/Developer';(xcode/'Platforms/MacOSX.platform').mkdir(parents=True)
        output=self.root/'separate output';target=output/(package.PRODUCT['name']+'.app');target.mkdir(parents=True)
        (target/'sentinel').write_text('keep this app')
        with patch.object(package,'ROOT',source),patch.object(package,'require_inactive'),patch('sys.argv',['package.py','--app-only','--skip-build','--output-dir',str(output)]),patch.dict(os.environ,DEVELOPER_DIR=str(xcode)),patch('package.subprocess.check_output',return_value=str(bin_dir)),patch('package.shutil.copytree',side_effect=OSError('simulated copy failure')):
            with self.assertRaisesRegex(OSError,'copy failure'):package.main()
        self.assertEqual((target/'sentinel').read_text(),'keep this app')
        self.assertFalse(list(output.glob('.lumanx-package-*')))
    @unittest.skipUnless(sys.platform=='darwin','macOS process path format')
    @unittest.skipUnless(shutil.which('cc'),'needs a C compiler')
    def test_real_running_bundle_executable_is_detected(self):
        # Copied macOS platform binaries can be killed before the process check.
        source=self.root/'fixture-sleeper.c'
        source.write_text('#include <unistd.h>\nint main(void) { for (;;) pause(); }\n')
        executable=self.target/'Contents/MacOS/fixture-sleeper'
        subprocess.run(['cc',str(source),'-o',str(executable)],check=True)
        child=subprocess.Popen([str(executable)])
        try:
            with self.assertRaisesRegex(RuntimeError,'running'):package.require_inactive(self.target)
            self.assertEqual((self.target/'sentinel').read_text(),'old working app')
        finally:
            child.terminate();child.wait(timeout=5)
