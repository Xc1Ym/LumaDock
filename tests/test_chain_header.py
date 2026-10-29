"""Chain header guard regression for the issue #9 follow-up; synthetic files only."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Failure, chain_of
import build
import engine
import ipa
from engine_fixture import make_engine

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
    def test_split_tool_lock_updates_and_verifies_before_using_chain_header(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory);tools=repo/'dm/gfx/tools';tools.mkdir(parents=True)
            (tools/'tool_lock.py').write_text('# Synthetic split tool interface')
            calls=[]
            def run(args,log,env):
                calls.append((Path(args[1]).name,args[-1]))
                if args[-1]=='--update-lock': (tools/'dmsh_chain.lock').write_text('synthetic lock')
            build.chain_tools(SimpleNamespace(run=run),repo,{},repo)
            self.assertEqual(calls,[('tool_lock.py','--update-lock'),('dmsh_chain.py','--header'),('tool_lock.py','--check-tools')])

    def test_shared_header_wins_over_stale_profile_header(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory); profile=repo/'dm/games'/GAME; profile.mkdir(parents=True)
            gp=SimpleNamespace(table=lambda name:profile/name)
            shared=repo/HEADER; shared.parent.mkdir(parents=True); shared.write_text(CHAIN)
            gp.table('dmsh_chain.h').write_text('#define DMSH_CHAIN "stale"')
            self.assertEqual(chain_of(repo,gp),'b0')

    def test_legacy_header_uses_only_selected_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory); profile=repo/'dm/games'/GAME; profile.mkdir(parents=True)
            other=profile.with_name('another-game'); other.mkdir()
            (other/'dmsh_chain.h').write_text('#define DMSH_CHAIN "other"')
            gp=SimpleNamespace(table=lambda name:profile/name)
            self.assertIsNone(chain_of(repo,gp))
            gp.table('dmsh_chain.h').write_text(CHAIN)
            self.assertEqual(chain_of(repo,gp),'b0')

    def test_invalid_shared_header_does_not_use_stale_profile_header(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory); profile=repo/'dm/games'/GAME; profile.mkdir(parents=True)
            gp=SimpleNamespace(table=lambda name:profile/name)
            shared=repo/HEADER; shared.parent.mkdir(parents=True); shared.write_text('truncated header')
            gp.table('dmsh_chain.h').write_text(CHAIN)
            self.assertIsNone(chain_of(repo,gp))

    def prepare_layout(self, legacy):
        """Run prepare's real header commands, then consume the resulting chain on Mac and iOS."""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=make_engine(root/'source')
            script=source/'scripts/build_ipa_from_nsp.py'
            script.write_text(script.read_text()+'\nclass Progress:\n    def __init__(self,mode): pass\n')
            (source/'dm/games/game.py').write_text(
                'class Profile:\n'
                '    def __init__(self,ident): self.id=ident\n'
                '    def table(self,name): return HERE/self.id/name\n'
                '    def get(self,key,default=None): return default\n'
                'def load(ident): return Profile(ident)\n')
            header=f'dm/games/{GAME}/dmsh_chain.h' if legacy else HEADER
            (source/'dm/gfx/tools/dmsh_chain.py').write_text(
                'from pathlib import Path\nimport sys\n'
                'repo=Path(__file__).resolve().parents[3]\n'
                f'header=repo/{header!r}\n'
                "if sys.argv[-1]=='--update-lock':\n"
                "    (repo/'dm/gfx/tools/dmsh_chain.lock').write_text('ok')\n"
                "elif sys.argv[-1]=='--header':\n"
                '    header.parent.mkdir(parents=True,exist_ok=True)\n'
                f'    header.write_text({CHAIN!r})\n')
            profile=source/'dm/games'/GAME
            (profile/'shader_map.tsv').write_text('main.rodata@0\t0\t1\tkey\tsynthetic\n')
            # prepared_tools returns an immutable source snapshot, not the game workspace.
            prepared=root/'prepared'; shutil.copytree(source,prepared/'source')
            calls=[]
            def run(args,log,env):
                calls.append(args[-1])
                subprocess.run([str(a) for a in args],env=env,check=True,capture_output=True,text=True)
            c=SimpleNamespace(engine=source,library=root/'library',run=run,
                env=lambda ident,work:dict(os.environ,DM_GAME=ident))
            game={'id':GAME,'packages':[
                {'type':'base','version':0,'sha256':'base'},
                {'type':'update','version':1114112,'sha256':'update','builds':{'main':'fixture-build'}}]}
            prior=sys.modules.pop('game',None); before=list(sys.path)
            try:
                with patch.object(build,'tools',return_value={'engineSource':'fixture'}),patch.object(engine,'prepared_tools',return_value=prepared):
                    work,repo,env,up,gp,key=build.prepare(c,game)
                self.assertEqual(calls,['--update-lock','--header','--check-tools'])
                self.assertEqual(chain_of(repo,gp),'b0')
                self.assertEqual((repo/HEADER).exists(),not legacy)
                watch=build.ShaderProgress(gp,repo,work/'shader/cache')
                self.assertEqual(watch.path,work/'shader/cache/b-b0')
                watch.path.mkdir(parents=True)
                (watch.path/'key_b.json').write_text('{}')
                self.assertEqual(watch()['done'],0)
                (watch.path/'key_b.metallib').write_text('synthetic')
                self.assertEqual(watch()['done'],1)
                ios=work/'shader/ios/b-b0'; ios.mkdir(parents=True)
                (ios/'key_b.json').write_text('{"chain":"b0","chain_metal":"iphoneos"}')
                (ios/'key_b.metallib').write_text('synthetic')
                ipa.validate_shaders(ios.parent,gp,repo)
                self.assertFalse((source/header).exists())
            finally:
                sys.path[:]=before; sys.modules.pop('game',None)
                if prior is not None: sys.modules['game']=prior

    def test_prepare_and_shader_consumers_with_shared_header(self):
        self.prepare_layout(legacy=False)

    def test_prepare_and_shader_consumers_with_legacy_header(self):
        self.prepare_layout(legacy=True)

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
