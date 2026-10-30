"""Daily engine synchronization uses committed sources and preserves good data on failure."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'Worker'),str(ROOT/'scripts')]
from bundled_engine import inventory, verify_bundle
from engine_fixture import make_engine
from sync_engine import sync, patch_sdk_compatibility


class EngineSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=make_engine(self.root/'upstream');self.target=self.root/'Engine/nxnative'
        (self.source/'LICENSE').write_text('Synthetic license fixture')
        self.front=self.source/'dm/host/front_mac.m'
        self.front.write_text('#include "haptics_apple.h"\nK(g.buttonB, DM_BTN_A); K(g.buttonA, DM_BTN_B); K(g.buttonY, DM_BTN_X); K(g.buttonX, DM_BTN_Y);   // by position: right A, bottom B, top X, left Y\n')
        ios=self.source/'dm/ios/Sources/DmGamepad.m';ios.parent.mkdir(parents=True)
        ios.write_text('#include "haptics_apple.h"\nK(g.buttonB, B_A); K(g.buttonA, B_B); K(g.buttonY, B_X); K(g.buttonX, B_Y);   // by position: right A, bottom B, top X, left Y\n')
        self.git('init','-q');self.commit()

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.source),*args],text=True,stderr=subprocess.STDOUT)

    def commit(self):
        self.git('add','.');self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Synthetic upstream fixture')

    def tearDown(self):self.tmp.cleanup()

    def test_sync_uses_committed_bytes_and_reapplies_both_frontends(self):
        self.front.write_text('Uncommitted builder mutation must not be imported')
        (self.source/'untracked.keys').write_text('Synthetic private data')
        record=sync(self.source,self.target)
        self.assertEqual(record['revision'],self.git('rev-parse','HEAD').strip())
        self.assertEqual(record,verify_bundle(self.target))
        for name in ('dm/host/front_mac.m','dm/ios/Sources/DmGamepad.m'):
            self.assertIn('luma_face_buttons(g)',(self.target/name).read_text())
        self.assertFalse((self.target/'untracked.keys').exists())

    def test_interface_drift_preserves_previous_snapshot(self):
        sync(self.source,self.target);before=inventory(self.target)
        self.front.write_text('Upstream interface changed');self.commit()
        with self.assertRaisesRegex(RuntimeError,'interface changed'):sync(self.source,self.target)
        self.assertEqual(inventory(self.target),before)
        verify_bundle(self.target)

    def test_binary_fuzz_corpus_is_omitted_but_harness_is_preserved(self):
        corpus=self.source/'dm/tools/fuzz/corpus/nso'
        corpus.mkdir(parents=True)
        (corpus/'huge-segment.nso').write_bytes(b'Synthetic parser input')
        (corpus/'other.bin').write_bytes(b'Synthetic parser input')
        harness=self.source/'dm/tools/fuzz/fuzz_nso.py'
        harness.write_text('# Synthetic harness source\n')
        self.commit()
        record=sync(self.source,self.target)
        self.assertFalse((self.target/'dm/tools/fuzz/corpus').exists())
        self.assertEqual((self.target/'dm/tools/fuzz/fuzz_nso.py').read_text(),harness.read_text())
        self.assertEqual(record,verify_bundle(self.target))

    def test_private_asset_outside_corpus_still_rejects_sync(self):
        sync(self.source,self.target);before=inventory(self.target)
        (self.source/'dm/unexpected.nso').write_bytes(b'Synthetic forbidden input')
        self.commit()
        with self.assertRaisesRegex(ValueError,'Private/generated engine asset'):
            sync(self.source,self.target)
        self.assertEqual(inventory(self.target),before)
        verify_bundle(self.target)

    def test_phone_motion_sdk_guard_survives_sync_and_reapplication(self):
        ios=self.source/'dm/ios/Sources/DmGamepad.m'
        statement='    if (@available(iOS 27.0, *)) { g_motion.deviceMotionBody = body; g_motion_body = YES; LOG("front end: the phone\'s motion comes in the pad view\'s frame (deviceMotionBody)"); }'
        ios.write_text(ios.read_text()+statement+'\n');self.commit()
        sync(self.source,self.target)
        imported=self.target/'dm/ios/Sources/DmGamepad.m';before=imported.read_text()
        self.assertIn('#if defined(__IPHONE_OS_VERSION_MAX_ALLOWED) && __IPHONE_OS_VERSION_MAX_ALLOWED >= 270000\n'+statement,before)
        self.assertIn('#else\n    (void)body;',before)
        patch_sdk_compatibility(self.target);self.assertEqual(imported.read_text(),before)
        verify_bundle(self.target)

    def test_changed_phone_motion_interface_preserves_previous_snapshot(self):
        sync(self.source,self.target);before=inventory(self.target)
        ios=self.source/'dm/ios/Sources/DmGamepad.m'
        ios.write_text(ios.read_text()+'g_motion.deviceMotionBody = body; // changed upstream interface\n');self.commit()
        with self.assertRaisesRegex(RuntimeError,'phone motion interface changed'):sync(self.source,self.target)
        self.assertEqual(inventory(self.target),before);verify_bundle(self.target)

    def test_reformatted_phone_motion_interface_preserves_previous_snapshot(self):
        sync(self.source,self.target);before=inventory(self.target)
        ios=self.source/'dm/ios/Sources/DmGamepad.m';original=ios.read_text()
        for statement in ('g_motion.deviceMotionBody=body;',
                          'g_motion.deviceMotionBody =\n    body;',
                          'g_motion . deviceMotionBody = body;'):
            with self.subTest(statement=statement):
                ios.write_text(original+statement+'\n');self.commit()
                with self.assertRaisesRegex(RuntimeError,'phone motion interface changed'):
                    sync(self.source,self.target)
                self.assertEqual(inventory(self.target),before);verify_bundle(self.target)

    @unittest.skipUnless(sys.platform=='darwin','Objective-C SDK compatibility check needs Apple clang')
    def test_phone_motion_compiles_with_and_without_sdk27_declaration(self):
        ios=self.source/'dm/ios/Sources/DmGamepad.m'
        ios.write_text('    if (@available(iOS 27.0, *)) { g_motion.deviceMotionBody = body; g_motion_body = YES; LOG("front end: the phone\'s motion comes in the pad view\'s frame (deviceMotionBody)"); }\n')
        patch_sdk_compatibility(self.source);guarded=ios.read_text()
        for sdk in (260500,270000):
            with self.subTest(sdk=sdk):
                declaration='@property void *deviceMotionBody;' if sdk>=270000 else ''
                source=(f'#define __IPHONE_OS_VERSION_MAX_ALLOWED {sdk}\n#define YES 1\n#define LOG(...) ((void)0)\n'
                    '@interface CMMotionManager\n'+declaration+'\n@end\n'
                    'static CMMotionManager *g_motion; static int g_motion_body;\n'
                    'void phone_motion_start(void *body) {\n'+guarded+'}\n')
                result=subprocess.run(['xcrun','clang','-target','arm64-apple-ios26.0','-x','objective-c','-fsyntax-only','-'],
                    input=source,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
