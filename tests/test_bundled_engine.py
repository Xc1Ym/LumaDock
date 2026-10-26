"""Bundled source integrity, migration and offline reader preparation fixtures."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Worker'))
from core import Context, Failure, digest
from bundled_engine import inventory, verify_bundle
import engine
from engine_fixture import make_engine


class BundledEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.resources = self.root/'Moved 中文.app/Contents/Resources'
        self.source = make_engine(self.resources/'Engine/nxnative')
        (self.source/'LICENSE').write_text('Synthetic MIT license fixture')
        (self.source/'dm/host/controller_native.h').write_text('// synthetic controller contract')
        self.record = dict(schema=1, repository='https://github.com/seedds/nxnative.git', revision='1'*40, files=inventory(self.source))
        (self.source/'manifest.json').write_text(json.dumps(self.record))
        self.c = Context(dict(operation='prepareEngine', resources=str(self.resources), privateRoot=str(self.root/'private'), engineDir='/offline/legacy-engine'))

    def tearDown(self): self.tmp.cleanup()

    def reader(self):
        shipped = self.resources/'Engine/reader'; shipped.mkdir()
        for name in ('nx_extract', 'nx_extract.dll', 'LibHac.dll', 'nx_extract.runtimeconfig.json'):
            (shipped/name).write_text("#!/bin/sh\necho 'usage: nx_extract <prod.keys>'\n" if name == 'nx_extract' else 'fixture')
        (shipped/'nx_extract').chmod(0o755)
        (shipped/'manifest.json').write_text(json.dumps(dict(fingerprint=engine.inspect_source(self.c)['fingerprint'], files={p.name:digest(p) for p in shipped.iterdir()})))
        return shipped

    def test_bundled_engine_replaces_stale_preferences_and_tracks_content(self):
        self.assertEqual(self.c.engine, self.source.resolve())
        info = engine.inspect_source(self.c)
        self.assertTrue(info['fingerprint'].startswith('bundled-')); self.assertTrue(info['nativeControllers'])
        (self.source/'dm/host/front_mac.m').write_text('modified')
        with self.assertRaises(Failure): engine.inspect_source(self.c)

    def test_added_private_files_and_symlinks_are_rejected(self):
        for name in ('game.nsp', 'game.xcz', 'prod.keys', 'saves/slot.dat', 'cover.jpg'):
            p = self.source/name; p.parent.mkdir(exist_ok=True); p.write_text('fixture')
            with self.assertRaises(ValueError): verify_bundle(self.source)
            p.unlink()
        (self.source/'outside').symlink_to('/tmp')
        with self.assertRaises(ValueError): verify_bundle(self.source)

    def test_offline_reader_preparation_needs_no_sdk_and_preserves_bundle(self):
        self.reader(); before = inventory(self.source)
        with patch('engine.find_sdk', side_effect=AssertionError('SDK must not be used')), patch.object(self.c, 'run', side_effect=AssertionError('No compilation')), contextlib.redirect_stdout(io.StringIO()):
            result = engine.prepare(self.c)
        self.assertTrue((Path(result['path'])/'tools/nx_extract/nx_extract').is_file())
        self.assertEqual(inventory(self.source), before)
        self.assertEqual(engine.prepared_tools(self.c), Path(result['path']))

    def test_corrupt_or_stale_shipped_reader_fails_without_fallback(self):
        shipped = self.reader(); (shipped/'LibHac.dll').write_text('corrupt')
        with patch('engine.find_sdk', side_effect=AssertionError('No SDK fallback')), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(Failure): engine.prepare(self.c)
        self.assertFalse(list(self.c.private.glob('engines/.partial-*')))
        record = json.loads((shipped/'manifest.json').read_text()); record['fingerprint'] = 'old'
        (shipped/'manifest.json').write_text(json.dumps(record))
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(Failure): engine.prepare(self.c)

    def test_checked_in_engine_has_matching_manifest_and_licenses(self):
        record = verify_bundle(ROOT/'Engine/nxnative')
        self.assertGreater(len(record['files']), 1000)
        self.assertIn('dm/third_party/ryujinx/LICENSE.txt', record['files'])


if __name__ == '__main__': unittest.main()
