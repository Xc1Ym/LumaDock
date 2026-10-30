"""Synthetic end-to-end derived-version builds; no player code or resources."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Context, Failure, Cancelled, atomic, digest, read
import build, derived, library

TITLE='0100000000010000'
STAMP='abc123abc123'
SOURCE_FLAGS={key: [False,'synthetic'] for key in ('glslc_capture','vk_capture','gl_capture','ue_decode','oodle_packs','ue_legacy')}
SOURCE_FLAGS['graphics']=['nvn','synthetic']


class Profile:
    def __init__(self,folder): self.dir=Path(folder);self.id=self.dir.name
    def table(self,name): return self.dir/name
    def rows(self):
        return [line.split('\t') for line in self.table('game.tsv').read_text().splitlines() if line and not line.startswith('#')]
    def get(self,key,default=None): return next(('\t'.join(r[1:]) for r in self.rows() if r[0]==key),default)
    def words(self,key,default=None): return self.get(key,default).split()
    def builds(self):
        return {r[1]:dict(display=r[2],**dict(v.split('=',1) for v in r[3:])) for r in self.rows() if r[0]=='build'}


class DerivedPlanTests(unittest.TestCase):
    def profile(self):
        return {'package':'v327680','shader_versions':'v0 v327680','builds':{
            'v0':{'main':'base','display':'1.0.0'},'v327680':{'main':'update','display':'1.2.1'}}}
    def game(self,version=65536):
        return {'packages':[{'type':'base','version':0,'builds':{'main':'base'}}]+(
            [{'type':'update','version':version,'builds':{'main':'update' if version==327680 else 'other'}}] if version else [])}
    def test_unregistered_update_and_base_alone_use_only_their_own_version(self):
        for version in (0,65536):
            with self.subTest(version=version):
                result=derived.plan(self.game(version),self.profile(),True)
                self.assertEqual(result,dict(mode='derived',version=f'v{version}',versions=[f'v{version}']))
                self.assertEqual(library.requirements(self.game(version),self.profile(),True),[])
    def test_registered_complete_inputs_keep_registered_pipeline(self):
        result=derived.plan(self.game(327680),self.profile(),True)
        self.assertEqual(result['mode'],'registered');self.assertEqual(result['versions'],['v0','v327680'])
    def test_registered_latest_build_preserves_registered_fixes_when_default_differs(self):
        profile=self.profile();profile['package']='v0'
        result=derived.plan(self.game(327680),profile,True)
        self.assertEqual(result['mode'],'registered');self.assertEqual(result['version'],'v327680')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/TITLE;folder.mkdir()
            (folder/'game.tsv').write_text('package\tv0\nmodules\tmain\nbuild\tv0\t1.0\tmain=base\n')
            (folder/'patches.py').write_text('registered fixes')
            selected=derived.select_registered(Profile(folder),'v327680')
            self.assertEqual(selected.get('package'),'v327680')
            self.assertEqual(selected.table('patches.py').read_text(),'registered fixes')
    def test_build_id_mismatch_derives_instead_of_using_registered_fixes(self):
        g=self.game(327680);g['packages'][1]['builds']['main']='different'
        self.assertEqual(derived.plan(g,self.profile(),True)['mode'],'derived')
    def test_older_engine_keeps_strict_version_gate_and_dlc_cannot_replace_base(self):
        self.assertTrue(library.requirements(self.game(),self.profile(),False))
        self.assertIn('缺少本体 v0',library.requirements({'packages':[{'type':'dlc','version':0}]},self.profile(),True))
    def test_no_profile_is_not_silently_treated_as_derived(self):
        self.assertTrue(library.requirements(self.game(),None,True))
    def test_capability_requires_complete_upstream_derived_api(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);script=root/'scripts/build_ipa_from_nsp.py';script.parent.mkdir()
            script.write_text('\n'.join('def '+n+'('+('provisional=False' if n=='split_shaders' else '')+'): pass' for n in derived.REQUIRED))
            for name in ('dm/games/profile_guess.py','dm/tools/nacp.py','dm/gfx/tools/own_compilers.py','dm/gfx/tools/cb_extent.py'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# synthetic')
            self.assertTrue(derived.supported(root))
            (root/'dm/gfx/tools/own_compilers.py').unlink();self.assertFalse(derived.supported(root))


class SourceDetectionTests(unittest.TestCase):
    def test_repeated_detection_keeps_one_tools_search_path(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(sys,'path',list(sys.path)):
            repo=Path(temp);path=repo/'dm/games/profile_guess.py';path.parent.mkdir(parents=True)
            path.write_text('def build_sources(exefs,romfs,modules): return {"modules":modules}\n')
            profile=SimpleNamespace(words=lambda key:['main','sdk']);up=SimpleNamespace()
            for _ in range(3):
                self.assertEqual(derived.detect_sources(up,repo,repo/'extract',profile),{'modules':['main','sdk']})
                self.assertEqual(sys.path.count(str(repo/'dm/tools')),1)


class DerivedPipelineTests(unittest.TestCase):
    def pipeline(self,target='macos',fail=None):
        with tempfile.TemporaryDirectory(prefix='luma-derived-') as temp:
            folder=Path(temp);library_root=folder/'library';library_root.mkdir()
            c=Context(dict(operation='build',gameId=TITLE,library=str(library_root),privateRoot=str(folder/'private')))
            source=library_root/'merged.xci';source.write_bytes(b'synthetic container')
            game=dict(id=TITLE,name='Synthetic game',packages=[dict(type=kind,version=version,titleId=TITLE,
                path=source.name,size=source.stat().st_size,sha256=digest(source)) for kind,version in [('base',0),('update',65536)]])
            c.save_catalog(dict(games=[game]));work=library_root/'cache'/target;repo=work/'engine'
            profile=repo/'dm/games'/TITLE;profile.mkdir(parents=True)
            profile.joinpath('game.tsv').write_text('package\tv327680\nshader_versions\tv0 v327680\nmodules\tmain\nromfs_marker\tmarker\nbuild\tv327680\t1.2.1\tmain=old\n')
            profile.joinpath('shader_map.tsv').write_text('OLD TABLE MUST NOT BE REUSED')
            profile.joinpath('patches.py').write_text('OLD PATCH MUST NOT BE REUSED')
            for name,source_text in [('nacp.py','def version(path): return "1.0.1"'),
                ('../games/profile_guess.py','def build_sources(*args): return '+repr(SOURCE_FLAGS))]:
                p=repo/'dm/tools'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source_text)
            header=repo/'dm/gfx/nvn/dmsh_chain.h';header.parent.mkdir(parents=True);header.write_text('#define DMSH_CHAIN "test"')
            strategy=dict(mode='derived',version='v65536',versions=['v65536'])
            atomic(work/'identity.json',dict(preparation=strategy,sources=['synthetic']))
            calls=[];attempts=[]
            def extract(nx,keys,dst,version,base,update,extra,logs,gp):
                calls.append('extract');self.assertEqual(version,'v65536');self.assertEqual(base,update)
                (dst/version/'RomFS').mkdir(parents=True);(dst/version/'RomFS/marker').write_text('new')
                (dst/version/'ExeFS').mkdir();(dst/version/'ExeFS/main').write_text('new code')
            def derive(gp,dst,version,selected,modules):
                calls.append('derive');dst.mkdir(parents=True)
                (dst/'game.tsv').write_text('package\tv65536\nshader_versions\tv65536\nmodules\tmain\nromfs_marker\tmarker\ngraphics\tnvn\nbuild\tv65536\t1.0.1\tmain=new\n')
            def set_keys(gp,changes,section):
                with gp.table('game.tsv').open('a') as f:
                    for key,(value,why) in changes.items(): f.write(key+'\t'+value+'\n')
                return Profile(gp.dir)
            def rewrite(py,engine,exefs,out,env,logs,gp):
                calls.append('rewrite');self.assertEqual(env['DM_GAMES_FIRST'],'1')
                self.assertEqual(Path(env['DM_GAMES_DIR']),work/'profiles')
                self.assertFalse(gp.table('patches.py').exists());self.assertEqual(gp.get('package'),'v65536')
                out.mkdir()
                for ext in ('patched.bin','fixups.tsv','gates.tsv'): (out/('main.'+ext)).write_text('new '+ext)
            def refine(gp,*args):
                if gp.get('mem_used') is None: return set_keys(gp,{'mem_used':('42','synthetic')},'refine')
                return gp
            def split(py,engine,roms,mains,pkg,env,logs,gp,provisional=False,oodle=None):
                calls.append('split');self.assertTrue(provisional)
                self.assertEqual(len(roms),1);self.assertIn('v65536',str(roms[0]))
                pkg.mkdir();(pkg/'own.bin').write_bytes(b'new shaders')
                for name in derived.TABLES: gp.table(name).write_text('OWN TABLE v65536\n')
            def shaders(py,engine,sh,xlate,env,logs,gp,pkg_key=None,mac=False):
                calls.append('shaders');attempts.append(1);self.assertEqual(mac,target=='macos')
                if fail in ('error','cancel') and len(attempts)==1: raise Cancelled() if fail=='cancel' else Failure('synthetic failure')
                outputs=[sh/'cache']+([sh/'ios'] if not mac else [])
                for output in outputs:
                    libs=output/'b-test';libs.mkdir(parents=True)
                    atomic(libs/'new_b.json',dict(chain='test',chain_metal='iphoneos' if output.name=='ios' and not (fail=='ios_platform' and len(attempts)==1) else 'macosx'))
                    (libs/'new_b.metallib').write_text('new library')
                    (libs/'inputs.tsv').write_text('game\t'+TITLE+'\ninputs\t'+STAMP+'\n')
                for name in ('c1_full.tsv','cb_extent.tsv'): gp.table(name).write_text('# chain b-test inputs '+('WRONG' if fail=='stamp' and len(attempts)==1 else STAMP)+' generated\n')
            def host(*args):
                calls.append('host');p=work/'tools/dmhost';p.parent.mkdir(parents=True,exist_ok=True);p.write_text('host');return p
            def run(args,*a,**kw):
                self.assertNotIn('c1_generate.py',str(args))
                if str(args[1]).endswith('make_ext_font.py'): Path(args[2]).write_text('font')
            up=SimpleNamespace(extract=extract,derive_profile=derive,set_keys=set_keys,
                provisional_prep=lambda *a:None,refine_after_rewrite=refine,rewrite=rewrite,
                split_shaders=split,build_shaders=shaders)
            old=library_root/'games'/TITLE/'releases/old';old.mkdir(parents=True);(old/'sentinel').write_text('keep')
            current=old.parent.parent/'current';current.symlink_to('releases/old')
            prepared=(work,repo,c.env(),up,Profile(profile),'synthetic')
            def pack(c,root,repo,env,gp,selected,patched,shaders,aoc,up=None):
                self.assertEqual(gp.get('package'),'v65536');self.assertEqual(gp.get('mem_used'),'42')
                self.assertEqual(env['DM_GAMES_FIRST'],'1');derived.validate_tables(root/'shader/cache',gp,'test')
                self.assertTrue((shaders/'b-test/new_b.metallib').is_file());return {'outputPath':'synthetic.ipa'}
            with contextlib.redirect_stdout(io.StringIO()),patch.object(sys,'path',list(sys.path)),patch('build.prepare',return_value=prepared),patch.object(c,'nx',return_value=Path('/nx_extract')),patch.object(c,'run',side_effect=run),patch('build.compile_host',side_effect=host),patch('build.shutil.disk_usage',return_value=SimpleNamespace(free=100*2**30)),patch('ipa.package',side_effect=pack):
                if fail:
                    with self.assertRaises(Cancelled if fail=='cancel' else Failure): build.build(c,target)
                    self.assertEqual(current.resolve(),old.resolve());self.assertEqual((old/'sentinel').read_text(),'keep')
                result=build.build(c,target)
                build.build(c,target)
                self.assertEqual(sys.path.count(str(repo/'dm/tools')),1)
            self.assertEqual(calls.count('extract'),1);self.assertEqual(calls.count('derive'),1)
            self.assertEqual(calls.count('rewrite'),1);self.assertEqual(calls.count('split'),1)
            self.assertEqual(calls.count('shaders'),2 if fail else 1)
            self.assertEqual(profile.joinpath('shader_map.tsv').read_text(),'OLD TABLE MUST NOT BE REUSED')
            if target=='macos':
                m=read(current/'manifest.json');self.assertEqual(m['version'],'1.0.1');self.assertEqual(m['preparationMode'],'derived')
                self.assertTrue((current/'profile/cb_extent.tsv').is_file())
                self.assertEqual((current/'profile/shader_map.tsv').read_text(),'OWN TABLE v65536\n')
                # Runtime validation rejects a table stamped for another build.
                (current/'profile/cb_extent.tsv').write_text('# chain b-test inputs OTHER generated\n')
                with self.assertRaises(Failure): build.validate_runtime(current)
    def test_mac_derived_pipeline_and_cached_retry(self): self.pipeline()
    def test_ios_derived_pipeline_and_cached_retry(self): self.pipeline('ios')
    def test_failed_shader_build_keeps_previous_runtime_and_retries(self): self.pipeline(fail='error')
    def test_cancellation_keeps_previous_runtime_and_retries(self): self.pipeline(fail='cancel')
    def test_wrong_stamp_is_not_checkpointed_and_can_retry(self): self.pipeline(fail='stamp')
    def test_wrong_ios_shader_platform_is_not_checkpointed_and_can_retry(self): self.pipeline('ios',fail='ios_platform')


if __name__=='__main__': unittest.main()
