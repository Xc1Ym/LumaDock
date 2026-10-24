"""Chain header guard regression for the issue #9 follow-up; synthetic files only."""
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Failure, chain_of
import build
import engine

GAME='0100000000010000'
GOOD='DMSH_CHAIN_HEADER_OK'
CHAIN='#define DMSH_CHAIN "b0"'
HEADER='dm/gfx/nvn/dmsh_chain.h'

def source_tree(root, good=True):
    """A private engine-tool cache whose source generates the header only when healthy."""
    source=root/'prepared'/'source'
    tool=source/'dm/gfx/tools/dmsh_chain.py'; tool.parent.mkdir(parents=True)
    tool.write_text(GOOD if good else 'broken header generator')
    (source/'dm/gfx/nvn').mkdir(parents=True, exist_ok=True)
    game=source/'dm/games'/GAME; game.mkdir(parents=True)
    (game/'shader_map.tsv').write_text('synthetic table')
    return source

class Runner:
    """Simulate dmsh_chain.py: always exit 0, write the shared header only from healthy tool source."""
    def __init__(self, repo): self.repo=repo; self.calls=[]
    def __call__(self, args, log=None, env=None, cwd=None):
        self.calls.append(args[-1])
        if '--update-lock' in args: (self.repo/'dm/gfx/tools/dmsh_chain.lock').write_text('ok')
        if '--header' in args and GOOD in (self.repo/'dm/gfx/tools/dmsh_chain.py').read_text():
            (self.repo/HEADER).write_text(CHAIN)

class ChainHeaderTests(unittest.TestCase):
    def guard(self, root, good_source):
        source=source_tree(root, good=good_source)
        repo=root/'cache'/'engine'
        with patch.object(engine, 'prepared_tools', return_value=source.parent):
            c=SimpleNamespace(run=Runner(repo))
            tc={'engineSource':'fingerprint'}
            build.ensure_chain_header(c, root/'cache', repo, {}, tc)
        return c, repo

    def test_healthy_copy_needs_single_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=source_tree(root)
            repo=root/'cache'/'engine'
            with patch.object(engine, 'prepared_tools', return_value=source.parent):
                build.refresh_engine(SimpleNamespace(), root/'cache', {'engineSource':'fingerprint'})
            c=SimpleNamespace(run=Runner(repo))
            build.chain_tools(c, repo, {}, root/'cache')
            marker=(repo/HEADER).read_text()
            build.ensure_chain_header(c, root/'cache', repo, {}, {'engineSource':'fingerprint'})
            self.assertEqual(c.run.calls, ['--update-lock','--header','--check-tools'])
            self.assertEqual((repo/HEADER).read_text(), marker)

    def test_damaged_copy_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=source_tree(root)
            repo=root/'cache'/'engine'
            with patch.object(engine, 'prepared_tools', return_value=source.parent):
                build.refresh_engine(SimpleNamespace(), root/'cache', {'engineSource':'fingerprint'})
            (repo/'dm/gfx/tools/dmsh_chain.py').write_text('hand-patched tool')
            (repo/'hand-patched.marker').write_text('local edit')
            c=SimpleNamespace(run=Runner(repo))
            build.chain_tools(c, repo, {}, root/'cache')
            self.assertIsNone(chain_of(repo))
            with patch.object(engine, 'prepared_tools', return_value=source.parent):
                build.ensure_chain_header(c, root/'cache', repo, {}, {'engineSource':'fingerprint'})
            self.assertNotIn('hand-patched.marker', [p.name for p in repo.iterdir()])
            self.assertIn(GOOD, (repo/'dm/gfx/tools/dmsh_chain.py').read_text())
            self.assertEqual((repo/HEADER).read_text(), CHAIN)
            self.assertEqual(c.run.calls.count('--header'), 2)

    def test_incompatible_tool_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaisesRegex(Failure, '着色器链头文件'):
                c, repo=self.guard(root, good_source=False)
            self.assertTrue((root/'cache'/'engine'/'.source-ready').is_file())
            self.assertNotIn(GOOD, (root/'cache'/'engine'/'dm/gfx/tools/dmsh_chain.py').read_text())

    def test_missing_lock_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=source_tree(root)
            repo=root/'cache'/'engine'
            def silent(args, log=None, env=None, cwd=None): pass
            with patch.object(engine, 'prepared_tools', return_value=source.parent):
                build.refresh_engine(SimpleNamespace(), root/'cache', {'engineSource':'fingerprint'})
            with self.assertRaisesRegex(Failure, 'Metal 工具链不可用'):
                build.chain_tools(SimpleNamespace(run=silent), repo, {}, root/'cache')


if __name__=='__main__': unittest.main()
