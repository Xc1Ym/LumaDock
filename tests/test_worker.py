import contextlib,io,json,os,pathlib,signal,subprocess,sys,tempfile,time,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Worker'))
from core import *
import library,build,input_config,toolchain,engine
from engine_fixture import make_engine
class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.root=Path(self.tmp.name)
        self.ctx=Context({'schema':1,'taskId':'test','operation':'setup','privateRoot':str(self.root/'private'),'resources':str(ROOT),'engineDir':str(make_engine(self.root/'External 引擎')),'library':str(self.root/'中文 空格 游戏库')})
        self.ctx.engine=Path(self.ctx.r['engineDir'])
        with contextlib.redirect_stdout(io.StringIO()):library.setup(self.ctx)
    def tearDown(self):self.tmp.cleanup()
    def quiet(self,fn,*args):
        with contextlib.redirect_stdout(io.StringIO()):return fn(*args)
    def test_01_keys_private_and_invalid(self):
        p=self.root/'bad.keys';p.write_text('header_key = not-a-key')
        with self.assertRaises(Failure):validate_keys(p)
        p.write_text('header_key = '+'a'*64+'\nmaster_key_00 = '+'1'*32+'\nrsa_data = '+'1'*1056)
        self.ctx.r['path']=str(p);self.quiet(library.keys,self.ctx)
        self.assertEqual(self.ctx.keys.stat().st_mode & 0o777,0o600)
        self.assertNotIn('a'*64,self.ctx.jobpath.read_text())
    def test_02_import_content_metadata_and_duplicate(self):
        src=self.root/'renamed 任意.nsp';src.write_bytes(b'PFS0'+b'test'*100)
        self.ctx.keys.parent.mkdir();self.ctx.keys.write_text('header_key = '+'a'*64)
        info={'titleId':'01007EF00011E000','baseId':'01007EF00011E000','version':0,'type':'base','name':'内容识别','display':'1.0','builds':{}}
        self.ctx.r['paths']=[str(src)]
        with patch('library.inspect',return_value=info):
            self.quiet(library.import_games,self.ctx)
            self.ctx.r['gameId']=info['baseId'];self.quiet(library.remove,self.ctx)
            result=self.quiet(library.import_games,self.ctx)
        self.assertTrue(result['imports'][0]['duplicate']);g=self.ctx.catalog()['games'][0];self.assertFalse(g['hidden'])
        self.assertEqual(g['name'],'内容识别');managed=self.ctx.library/g['packages'][0]['path'];src.unlink();self.assertTrue(managed.is_file())
    def test_03_space_failure_preserves_source(self):
        src=self.root/'x.nsp';src.write_bytes(b'x');self.ctx.keys.parent.mkdir();self.ctx.keys.write_text('header_key = '+'a'*64);self.ctx.r['paths']=[str(src)]
        info={'titleId':'0100000000000000','baseId':'0100000000000000','version':0,'type':'base','name':'x','display':'','builds':{}}
        with patch('library.inspect',return_value=info),patch('library.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
            with self.assertRaises(Failure):self.quiet(library.import_games,self.ctx)
        self.assertEqual(src.read_bytes(),b'x')
    def test_04_missing_disk_does_not_recreate(self):
        self.ctx.r['libraryId']='not-this-disk'
        with self.assertRaises(Failure):self.ctx.check()
    def test_05_profiles_and_missing_version(self):
        ps=profiles(self.ctx.engine);self.assertEqual(len(ps),2);self.assertIn('01007EF00011E000',ps);self.assertIn('0100000000010000',ps)
        missing=library.requirements({'packages':[{'type':'base','version':0,'builds':{}}]},ps['01007EF00011E000'])
        self.assertTrue(any('v1114112' in s for s in missing))
        self.assertEqual(library.requirements({'packages':[]},None),['此游戏尚无原生适配配置'])
        self.assertTrue(all(p['compatibility'] in ('startup','experimental') for p in ps.values()))
    def test_06_stages_resume_verify_and_corruption(self):
        root=self.ctx.library/'cache/test';root.mkdir(parents=True);p=root/'artifact';n=[];s=build.Stages(self.ctx,root)
        def fn():n.append(1);p.write_bytes(b'complete')
        self.quiet(s.run,'rewrite',[p],fn);self.quiet(s.run,'rewrite',[p],fn);self.assertEqual(len(n),1)
        p.write_bytes(b'corrupt!');self.quiet(s.run,'rewrite',[p],fn);self.assertEqual(len(n),2)
    def test_07_partial_stage_never_checkpointed(self):
        root=self.ctx.library/'cache/test';root.mkdir(parents=True);p=root/'partial';s=build.Stages(self.ctx,root)
        def fn():p.write_text('half');raise Failure('failure')
        with self.assertRaises(Failure):self.quiet(s.run,'shader',[p],fn)
        self.assertEqual(s.saved,{})
    def test_08_unique_input_and_esc_reserved(self):
        v=input_config.defaults();input_config.validate(v)
        v['keyboard']['Y']=dict(v['keyboard']['A'])
        with self.assertRaises(Failure):input_config.validate(v)
        v=input_config.defaults();v['keyboard']['A']={'code':53}
        with self.assertRaises(Failure):input_config.validate(v)
        v=input_config.defaults();v['gamepad']['B']='east'
        with self.assertRaises(Failure):input_config.validate(v)
    def test_09_chords_and_axis_conflicts(self):
        v=input_config.defaults();v['keyboard']['A']={'code':14,'modifiers':3};input_config.validate(v)
        v['axes']['RX']['source']='leftX'
        with self.assertRaises(Failure):input_config.validate(v)
    def test_10_remove_retains_files_and_saves(self):
        self.ctx.save_catalog({'games':[{'id':'g','packages':[],'hidden':False}]});self.ctx.r['gameId']='g'
        save=self.ctx.library/'saves/g/slot';save.parent.mkdir();save.write_text('important')
        self.quiet(library.remove,self.ctx);self.assertTrue(self.ctx.catalog()['games'][0]['hidden']);self.assertEqual(save.read_text(),'important')
    def test_11_diagnostics_allowlist(self):
        logs=self.ctx.private/'logs';logs.mkdir();(logs/'tool.log').write_text('header_key = '+'a'*64+'\nhello')
        self.ctx.keys.parent.mkdir();self.ctx.keys.write_text('secret');self.ctx.r['path']=str(self.root/'diag.zip');self.quiet(library.diagnostics,self.ctx)
        import zipfile
        with zipfile.ZipFile(self.root/'diag.zip') as z:
            data=b''.join(z.read(n) for n in z.namelist());self.assertNotIn(b'a'*64,data);self.assertNotIn(b'secret',data);self.assertIn(b'hello',data)
    def test_12_cancellation_kills_descendant(self):
        script=self.root/'child.py';pidfile=self.root/'pid'
        script.write_text('import subprocess,time,sys\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(300)"])\nopen(sys.argv[1],"w").write(str(p.pid))\ntime.sleep(300)\n')
        p=subprocess.Popen([sys.executable,str(script),str(pidfile)],start_new_session=True);self.ctx.children.add(p)
        for _ in range(100):
            if pidfile.exists():break
            time.sleep(.02)
        child=int(pidfile.read_text());self.ctx.stop();p.wait(timeout=5)
        time.sleep(.1)
        try:os.kill(child,0);alive=True
        except ProcessLookupError:alive=False
        self.assertFalse(alive)
    def test_13_runtime_missing_is_rejected(self):
        p=self.root/'runtime';p.mkdir();atomic(p/'manifest.json',{'chain':'none'})
        with self.assertRaises(Failure):build.validate_runtime(p)
    def test_14_cache_identity_excludes_input(self):
        # Source/toolchain identity belongs to the build; mappings remain outside the cache tree.
        v=input_config.defaults();self.ctx.r['config']=v;self.quiet(input_config.save,self.ctx)
        self.assertTrue((self.ctx.private/'default-input.json').exists());self.assertFalse((self.ctx.library/'cache').glob('*.json').__next__() if list((self.ctx.library/'cache').glob('*.json')) else False)
    def test_15_failed_install_preserves_successful_release(self):
        gdir=self.ctx.library/'games/g';old=gdir/'releases/old';old.mkdir(parents=True);(old/'sentinel').write_text('working');(gdir/'current').symlink_to('releases/old')
        root=self.ctx.library/'cache/test';root.mkdir(parents=True);repo=root/'engine';profile=repo/'dm/games/g';profile.mkdir(parents=True)
        (repo/'dm/gfx/nvn').mkdir(parents=True);(repo/'dm/gfx/nvn/dmsh_chain.h').write_text('#define DMSH_CHAIN "testchain"')
        class Profile:
            id='g'
            def table(self,n):return profile/n
            def get(self,k,default=None):return {'graphics':'vulkan','package':'v0'}.get(k,default)
            def builds(self):return {'v0':{'display':'1.0'}}
        for name in ('romfs','modules','shaders','font'):
            (root/name).mkdir();(root/name/'file').write_text('data')
        (root/'dmhost').write_text('host')
        with patch('build.validate_runtime',side_effect=Failure('bad artifact')):
            with self.assertRaises(Failure):self.quiet(build.install,self.ctx,root,repo,Profile(),'newkey',root/'dmhost',root/'romfs',root/'modules',root/'shaders',None,root/'font')
        self.assertEqual((gdir/'current/sentinel').read_text(),'working')

    def test_16_shader_progress_counts_complete_pairs(self):
        repo=self.root/'repo';(repo/'dm/gfx/nvn').mkdir(parents=True);(repo/'dm/gfx/nvn/dmsh_chain.h').write_text('#define DMSH_CHAIN "abc"')
        d=self.root/'profile';d.mkdir();(d/'shader_map.tsv').write_text('x.bin\t0\t1\tkey1\tdata\nx.bin\t0\t1\tkey2\tdata\n')
        class G:
            def table(self,n):return d/n
        watch=build.ShaderProgress(G(),repo,self.root/'shaders');watch.path.mkdir(parents=True)
        (watch.path/'key2_b.json').write_text('{}');self.assertEqual(watch()['done'],0)
        (watch.path/'key2_b.metallib').write_bytes(b'library');self.assertEqual(watch()['done'],1);self.assertEqual(watch()['total'],2)

    def test_17_pipeline_records_use_a_persistent_file(self):
        self.ctx.engine=None # Prepared runtimes must not depend on the selected sources.
        self.ctx.save_catalog({'games':[{'id':'g','packages':[]}]});self.ctx.r['gameId']='g'
        seen=[]
        def run(args,log=None,env=None,cwd=None,on_line=None):
            record=Path(env['DM_PSO_USER']);self.assertTrue(record.parent.is_dir());self.assertFalse(record.is_dir());seen.append(record)
            with record.open('a') as f:f.write('pipeline\n')
        with patch('toolchain.require_launch_environment'),patch('build.validate_runtime'),patch.object(self.ctx,'run',side_effect=run):
            self.quiet(build.launch,self.ctx);self.quiet(build.launch,self.ctx)
        self.assertEqual(seen[0],seen[1]);self.assertEqual(seen[0].read_text().count('pipeline'),2)

    def test_18_key_status_ignores_stale_record(self):
        atomic(self.ctx.private/'keys/status.json',{'entries':10,'verified':True})
        self.assertFalse(self.quiet(library.catalog,self.ctx)['keys']['ready'])
        self.ctx.keys.write_text('not a key file')
        self.assertFalse(self.quiet(library.catalog,self.ctx)['keys']['ready'])
        self.ctx.keys.write_text('header_key = '+'a'*64)
        self.assertTrue(self.quiet(library.catalog,self.ctx)['keys']['ready'])
        self.ctx.keys.unlink()
        self.assertFalse(self.quiet(library.catalog,self.ctx)['keys']['ready'])

    def test_game_language_reaches_native_process_without_touching_runtime_or_cache(self):
        self.ctx.save_catalog({'games':[{'id':'g','packages':[]}]});self.ctx.r['gameId']='g'
        runtime=self.ctx.library/'games/g/current';runtime.mkdir(parents=True)
        atomic(runtime/'manifest.json',{'chain':'fixture'})
        cache=self.ctx.library/'cache/identity.json';atomic(cache,{'unchanged':True})
        before={p:p.read_bytes() for p in (runtime/'manifest.json',cache)}
        seen=[]
        def run(args,log=None,env=None,cwd=None,on_line=None):seen.append(env['DM_LANG'])
        codes=sorted(build.GAME_LANGUAGES)
        with patch('toolchain.require_launch_environment'),patch('build.validate_runtime'),patch.object(self.ctx,'run',side_effect=run),patch.dict(os.environ,{'DM_LANG':'ja'}):
            self.quiet(build.launch,self.ctx) # Old callers get a valid Simplified Chinese default.
            for code in codes:
                self.ctx.r['gameLanguage']=code;self.quiet(build.launch,self.ctx)
        self.assertEqual(seen,['zh-Hans']+codes)
        for p,data in before.items():self.assertEqual(p.read_bytes(),data)

    def test_invalid_game_language_is_rejected_before_starting_any_process(self):
        for invalid in ('zhHans','zh-Hans-CN','en',None,[],{},1,'ja\nDM_SAVE=/tmp/wrong'):
            with self.subTest(language=invalid),patch('toolchain.require_launch_environment') as check,patch.object(self.ctx,'run') as run:
                self.ctx.r['gameLanguage']=invalid
                with self.assertRaisesRegex(Failure,'游戏语言代码无效'):self.quiet(build.launch,self.ctx)
                check.assert_not_called();run.assert_not_called()

    def test_launcher_and_worker_accept_the_same_switch_language_codes(self):
        source=(ROOT/'Sources/LumaNX/GameLanguage.swift').read_text()
        codes=set(re.findall(r'\b\w+\s*=\s*"([a-z]{2}(?:-[A-Za-z0-9]+)?)"',source))
        self.assertEqual(codes,build.GAME_LANGUAGES)
        self.assertEqual(len(codes),18)

    def test_19_import_without_keys_does_not_scan_or_copy(self):
        src=self.root/'source.nsp';src.write_bytes(b'unchanged');self.ctx.r['paths']=[str(src)]
        with patch('library.inspect') as inspect_mock:
            with self.assertRaisesRegex(Failure,'请先导入'):
                self.quiet(library.import_games,self.ctx)
        inspect_mock.assert_not_called()
        self.assertEqual(src.read_bytes(),b'unchanged')
        self.assertEqual(self.ctx.catalog()['games'],[])

    def test_20_preflight_preserves_separate_prepare_and_launch_requirements(self):
        checks=[dict(name='Xcode',ok=False,requiredFor=['prepare']),dict(name='Python',ok=True,requiredFor=['prepare','launch']),dict(name='SDK',ok=False,requiredFor=[])]
        with patch('toolchain.inspect_environment',return_value=checks),patch('toolchain.supports_removal',return_value=False):
            result=self.quiet(library.preflight,self.ctx)
        self.assertFalse(result['ready']);self.assertTrue(result['launchReady'])
        self.assertEqual(result['checks'],checks)
        checks[0]['ok']=True
        with patch('toolchain.inspect_environment',return_value=checks),patch('toolchain.supports_removal',return_value=False):
            self.assertTrue(self.quiet(library.preflight,self.ctx)['ready'])

    def test_21_metal_removal_requires_confirmation_and_supported_xcode(self):
        with patch.object(self.ctx,'run') as run:
            with self.assertRaisesRegex(Failure,'确认'):
                self.quiet(toolchain.uninstall_metal,self.ctx)
            self.ctx.r['confirmed']=True
            with patch('toolchain.supports_removal',return_value=False):
                with self.assertRaisesRegex(Failure,'不支持'):
                    self.quiet(toolchain.uninstall_metal,self.ctx)
            run.assert_not_called()

    def test_22_metal_management_uses_apple_component_commands(self):
        self.ctx.r['confirmed']=True
        with patch.object(self.ctx,'run') as run,patch('toolchain.supports_removal',return_value=True):
            self.quiet(toolchain.uninstall_metal,self.ctx)
            run.assert_called_once_with(['xcodebuild','-deleteComponent','MetalToolchain'])
        with patch.object(self.ctx,'run') as run:
            self.quiet(toolchain.install_metal,self.ctx)
            run.assert_called_once_with(['xcodebuild','-downloadComponent','MetalToolchain'])

    def test_23_component_mutation_excludes_active_game_and_build_readers(self):
        with self.ctx.toolchain_lock():
            with self.ctx.toolchain_lock():pass
            with self.assertRaises(Failure):
                with self.ctx.toolchain_lock(exclusive=True):pass
        with self.ctx.toolchain_lock(exclusive=True):
            with self.assertRaises(Failure):
                with self.ctx.toolchain_lock():pass


    def test_24_engine_upgrade_marks_reprepare_but_keeps_working_runtime(self):
        tid='01007EF00011E000'
        self.ctx.save_catalog({'games':[{'id':tid,'name':'fixture','display':'1.9.0','packages':[],'hidden':False}]})
        runtime=self.ctx.library/'games'/tid/'current';runtime.mkdir(parents=True)
        (runtime/'sentinel').write_text('last successful version')
        manifest={'engine':'previous-engine','sourceHashes':[]}
        atomic(runtime/'manifest.json',manifest)
        game=self.quiet(library.catalog,self.ctx)['games'][0]
        self.assertTrue(game['ready']);self.assertTrue(game['needsPreparation'])
        atomic(runtime/'manifest.json',dict(manifest,engine=engine.inspect_source(self.ctx)['fingerprint']))
        self.assertFalse(self.quiet(library.catalog,self.ctx)['games'][0]['needsPreparation'])
        self.assertEqual((runtime/'sentinel').read_text(),'last successful version')

if __name__=='__main__':unittest.main(verbosity=2)
