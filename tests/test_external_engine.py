"""External engine selection, source isolation and cache invalidation."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Worker'))
from core import Context, Failure, atomic, digest
import engine, library
from engine_fixture import make_engine, mark_prepared

class ExternalEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lumanx-external-');self.root=Path(self.temp.name)
        self.source=make_engine(self.root/"下载 中文's nxnative")
        self.c=Context(dict(operation='preflight',privateRoot=str(self.root/'private'),resources=str(self.root/'resources'),engineDir=str(self.source)))
    def tearDown(self):self.temp.cleanup()
    def test_unconfigured_never_falls_back_to_bundled_source_or_reader(self):
        c=Context(dict(operation='preflight',privateRoot=str(self.root/'other'),resources=str(self.root/'resources')))
        (c.resource/'Vendor/nxnative').mkdir(parents=True)
        (c.runtime/'nx_extract').mkdir(parents=True)
        self.assertIsNone(c.engine)
        with self.assertRaisesRegex(Failure,'尚未选择'): c.nx()
    def test_missing_deleted_or_incompatible_directory_is_actionable(self):
        self.assertTrue(engine.inspect_source(self.c)['fingerprint'].startswith('external-'))
        (self.source/'dm/host/Makefile').unlink()
        with self.assertRaisesRegex(Failure,'缺少'):engine.inspect_source(self.c)
        self.c.engine=self.root/'offline'
        with self.assertRaisesRegex(Failure,'目录不可用'):engine.inspect_source(self.c)
        self.assertFalse(self.c.engine.exists())
    def test_content_change_invalidates_tools_and_catalog_without_removing_old_runtime(self):
        ready=mark_prepared(self.c);old=engine.inspect_source(self.c)['fingerprint']
        self.assertEqual(self.c.nx(),ready/'tools/nx_extract/nx_extract')
        (self.source/'dm/host/front_mac.m').write_text('changed source')
        self.assertNotEqual(old,engine.inspect_source(self.c)['fingerprint'])
        with self.assertRaisesRegex(Failure,'尚未准备'):self.c.nx()
        self.assertTrue(ready.exists())
    def test_half_or_corrupt_tool_cache_never_counts_as_ready(self):
        ready=mark_prepared(self.c)
        (ready/'tools/nx_extract/LibHac.dll').write_text('corrupted')
        with self.assertRaisesRegex(Failure,'不完整'):self.c.nx()
    def test_external_symlinks_are_rejected(self):
        (self.source/'dm/escape').symlink_to(self.root/'outside')
        with self.assertRaisesRegex(Failure,'符号链接'):engine.inspect_source(self.c)
    def test_adapter_writes_only_the_private_snapshot(self):
        import shutil
        original=engine.source_hash(self.source)
        snapshot=self.root/'snapshot';shutil.copytree(self.source,snapshot)
        engine.adapt_snapshot(snapshot)
        self.assertEqual(original,engine.source_hash(self.source))
        self.assertIn('LumaNXInspect', (snapshot/'dm/tools/nx_extract/Program.cs').read_text())
        self.assertTrue((snapshot/'dm/tools/nx_extract/LumaNXMetadata.cs').is_file())
        chain=(snapshot/'dm/gfx/tools/dmsh_chain.py').read_text()
        self.assertIn('DM_MAC_ONLY',chain)
        self.assertIn('iphoneos',chain)
        # Execute both branches of the adapted loop without any Apple tools.
        for value,expected in [('1',['macosx']),('0',['macosx','iphoneos'])]:
            instrumented=chain.replace('pass','seen.append(sdk)')
            scope={'seen':[]}
            with patch.dict(os.environ,{'DM_MAC_ONLY':value}):
                exec(instrumented,scope);scope['tools_now']()
            self.assertEqual(scope['seen'],expected)
    def test_missing_sdk_fails_without_touching_source(self):
        before=engine.source_hash(self.source)
        with patch('engine.find_sdk',return_value=(None,'')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(Failure,'SDK'):engine.prepare(self.c)
        self.assertEqual(before,engine.source_hash(self.source))
        self.assertFalse(list(self.c.private.glob('engines/.partial-*')))

    def test_split_tool_lock_adapter_keeps_mac_and_ios_sdk_selection(self):
        tools=self.source/'dm/gfx/tools'
        (tools/'dmsh_chain.py').rename(tools/'tool_lock.py')
        (tools/'dmsh_chain.py').write_text('# Synthetic chain version module\n')
        engine.adapt_snapshot(self.source)
        text=(tools/'tool_lock.py').read_text()
        engine.adapt_snapshot(self.source)
        self.assertEqual((tools/'tool_lock.py').read_text(),text)
        for value,expected in [('1',['macosx']),('0',['macosx','iphoneos'])]:
            scope={'seen':[]}
            with patch.dict(os.environ,{'DM_MAC_ONLY':value}):
                exec(text.replace('pass','seen.append(sdk)'),scope);scope['tools_now']()
            self.assertEqual(scope['seen'],expected)
    def test_complete_cache_is_reused_without_sdk_or_compilation(self):
        mark_prepared(self.c)
        with patch('engine.find_sdk') as sdk,patch.object(self.c,'run') as run,contextlib.redirect_stdout(io.StringIO()):
            result=engine.prepare(self.c)
        self.assertTrue(result['reused']);sdk.assert_not_called();run.assert_not_called()
    def test_relocation_is_based_on_content_and_input_capability_is_explicit(self):
        import shutil
        info=engine.inspect_source(self.c);self.assertFalse(info['inputConfig'])
        other=self.root/'Moved 引擎';shutil.copytree(self.source,other)
        self.c.engine=other
        self.assertEqual(info,engine.inspect_source(self.c))
        (other/'dm/host/input_config_mac.h').write_text('// DM_INPUT_CONFIG')
        self.assertFalse(engine.inspect_source(self.c)['inputConfig'])
        (other/'dm/host/front_mac.m').write_text('#include "input_config_mac.h"')
        self.assertTrue(engine.inspect_source(self.c)['inputConfig'])
    def test_preparation_failure_keeps_existing_cache_and_cleans_partial(self):
        before=engine.source_hash(self.source)
        with patch('engine.find_sdk',return_value=(Path('/sdk/dotnet'),'10.0.101')),patch.object(self.c,'run',side_effect=Failure('compile failure')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(Failure,'compile failure'):engine.prepare(self.c)
        self.assertEqual(before,engine.source_hash(self.source))
        self.assertFalse(list(self.c.private.glob('engines/.partial-*')))

if __name__=='__main__':unittest.main()
