"""Milestone protocol/history checks with synthetic metadata and deterministic clocks."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Context, atomic, read, Cancelled
from build import Stages
import milestones as ms


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.c=Context(dict(operation='build',privateRoot=str(self.root/'private')))
        self.game=dict(id='original-fixture',packages=[dict(size=2_000_000_000)])
        self.profile=SimpleNamespace(get=lambda key,default=None: {'graphics':'nvn'}.get(key,default))
        self.output=io.StringIO();self.redirect=contextlib.redirect_stdout(self.output);self.redirect.__enter__()
    def tearDown(self):self.redirect.__exit__(None,None,None);self.temp.cleanup()
    def plan(self,target='macos',identity=None):
        ms.plan(self.c,self.game,target,['v0','v1'],self.profile,identity or {'tools':{'engine':'synthetic'}})
    def events(self):return [json.loads(line) for line in self.output.getvalue().splitlines()]

    def test_plans_only_contain_executed_stages_for_each_target(self):
        self.plan();ids=[row['id'] for row in self.c.milestones]
        self.assertEqual(ids,['verify','unpack-0','unpack-1','dlc','rewrite','extract','shaders','host','install'])
        self.assertTrue(all(row['source']=='default' for row in self.c.milestones))
        self.assertNotIn('sh_pipeline',ids)
        self.plan('ios');self.assertEqual([row['id'] for row in self.c.milestones][-3:],['ipa','ipa_check','ipa_export'])
        self.profile=SimpleNamespace(get=lambda key,default=None:{'graphics':'vulkan','shader_vk_capture':'on'}.get(key,default))
        self.plan();ids=[row['id'] for row in self.c.milestones]
        self.assertIn('capture_vk',ids);self.assertNotIn('extract',ids)

    def test_local_history_uses_valid_size_scaled_median_and_is_scoped_to_tools_target(self):
        self.plan();path=ms.history_path(self.c)
        atomic(path,[dict(size_gb=2,seconds={'shaders':100,'rewrite':40}),dict(size_gb=1,seconds={'shaders':30,'rewrite':60}),dict(size_gb=0,seconds={'shaders':999}),dict(size_gb=True,seconds={'shaders':9})])
        self.game['packages'][0]['size']=4_000_000_000;self.plan()
        rows={row['id']:row for row in self.c.milestones}
        self.assertEqual(rows['shaders']['expected'],160);self.assertEqual(rows['shaders']['samples'],2)
        self.assertEqual(rows['rewrite']['expected'],50);self.assertEqual(rows['shaders']['source'],'history')
        self.plan('ios');self.assertNotEqual(ms.history_path(self.c),path)
        self.plan(identity={'tools':{'engine':'changed'}});self.assertNotEqual(ms.history_path(self.c),path)

    def test_stage_events_persist_timing_and_keep_one_index_for_substeps(self):
        self.plan();clock=[100.0]
        with patch('milestones.time.monotonic',side_effect=lambda:clock[0]),patch('milestones.time.time',side_effect=lambda:clock[0]+1000):
            ms.enter(self.c,'verify','verify input');clock[0]=110
            self.c.begin('verify another file');self.c.emit(done=5,total=10)
            self.assertEqual(self.c.number,1)
            ms.enter(self.c,'unpack-0','unpack');self.c.emit('heartbeat')
        stage=[event for event in self.events() if event['type']=='stage'][-1]
        self.assertEqual(stage['milestone'],'unpack-0');self.assertEqual(stage['stageIndex'],2)
        self.assertEqual(stage['milestoneStarted'],{'verify':1100,'unpack-0':1110})
        saved=read(self.c.jobpath);self.assertEqual(saved['milestoneStarted'],stage['milestoneStarted'])
        self.assertEqual(self.events()[-1]['milestone'],'unpack-0')

    def test_checkpoint_hits_are_excluded_from_history_and_calibration_protocol(self):
        self.plan();artifact=self.root/'work/artifact';artifact.parent.mkdir()
        stages=Stages(self.c,artifact.parent);clock=[100.0]
        def produce():artifact.write_text('original fixture');clock[0]=120
        with patch('milestones.time.monotonic',side_effect=lambda:clock[0]):
            stages.run('rewrite',[artifact],produce,milestone='rewrite')
            stages.run('rewrite',[artifact],lambda:self.fail('cache should be reused'),milestone='rewrite')
            ms.enter(self.c,'install');clock[0]=130;ms.record(self.c)
        row=read(ms.history_path(self.c))[-1]
        self.assertEqual(row['seconds'],{'install':10})
        self.assertIn('rewrite',[event for event in self.events() if event['type']=='cache'][-1]['milestoneCached'])

    def test_corrupt_or_unwritable_estimation_history_does_not_break_work(self):
        self.plan();path=ms.history_path(self.c);path.parent.mkdir();path.write_text('{broken')
        self.plan();self.assertTrue(all(row['source']=='default' for row in self.c.milestones))
        ms.enter(self.c,'verify')
        with patch('milestones.atomic',side_effect=OSError('disk full')):ms.record(self.c)

    def test_cancelled_stage_cannot_advance_or_write_successful_history(self):
        self.plan();ms.enter(self.c,'verify');self.c.cancelled=True
        with self.assertRaises(Cancelled):ms.enter(self.c,'unpack-0')
        ms.record(self.c)
        self.assertEqual(self.c.milestone,'verify');self.assertFalse(ms.history_path(self.c).exists())


if __name__=='__main__':unittest.main()
