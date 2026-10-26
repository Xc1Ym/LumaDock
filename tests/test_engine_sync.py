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
from sync_engine import sync


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


if __name__=='__main__':unittest.main()
