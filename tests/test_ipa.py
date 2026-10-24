"""Original synthetic iOS protocol fixtures; no games, keys or engine binaries."""
import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Context, Failure, Cancelled, atomic, digest
import build
import engine
import ipa
from engine_fixture import make_engine


def archive(path, *, platform='iPhoneOS', resources=True, corrupt=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as z:
        z.writestr('Payload/Fixture.app/Info.plist', plistlib.dumps(dict(
            CFBundleExecutable='Fixture', CFBundlePackageType='APPL', CFBundleSupportedPlatforms=[platform])))
        z.writestr('Payload/Fixture.app/Fixture', b'synthetic executable')
        if resources:
            z.writestr('Payload/Fixture.app/romfs/marker', b'synthetic resources')
            z.writestr('Payload/Fixture.app/msl/vk/test.metallib', b'synthetic shader')
    if corrupt:
        data=path.read_bytes().replace(b'synthetic resources',b'corrupted resources',1)
        path.write_bytes(data)


class IPATests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="lumadock-ipa-中文's-")
        self.root=Path(self.temp.name)
        self.engine=make_engine(self.root/'engine')
        for name in ipa.IOS_FILES:
            path=self.engine/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
        self.c=Context(dict(operation='exportIPA', privateRoot=str(self.root/'private'),
            library=str(self.root/'library'), engineDir=str(self.engine), resources=str(self.root/'resources'),
            gameId='0100000000010000', outputPath=str(self.root/'测试 游戏.ipa')))
        self.c.library.mkdir()
        self.g={'id':self.c.r['gameId'],'name':'Synthetic game','packages':[]}
        self.c.save_catalog({'games':[self.g]})
        self.work=self.c.library/'cache/ios';self.work.mkdir(parents=True)
        self.selected=self.work/'extract/v0'
        (self.selected/'RomFS').mkdir(parents=True)
        (self.selected/'RomFS/marker').write_text('synthetic')
        self.profile=self.engine/'dm/games'/self.g['id']
        (self.engine/'dm/gfx/nvn').mkdir(parents=True,exist_ok=True)
        (self.engine/'dm/gfx/nvn/dmsh_chain.h').write_text('#define DMSH_CHAIN "fixture"')
        self.graphics='vulkan'
        self.gp=SimpleNamespace(id=self.g['id'],
            get=lambda key,default=None:{'package':'v0','graphics':self.graphics}.get(key,default),
            words=lambda key,default=None:[default] if key=='shader_versions' else ['main'],
            table=lambda name:self.profile/name, builds=lambda:{'v0':{'display':'1.0'}})
        self.shaders=self.work/'shader/ios';(self.shaders/'vk').mkdir(parents=True)
        (self.shaders/'vk/vk_shaders.metallib').write_text('synthetic iOS shaders')

    def tearDown(self): self.temp.cleanup()
    def quiet(self, fn, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()): return fn(*args,**kwargs)
    def package(self):
        return self.quiet(ipa.package,self.c,self.work,self.engine,self.c.env(),self.gp,
            self.selected,self.work/'patched',self.shaders,self.work/'aoc')

    def test_output_path_checks_precede_build_and_protect_managed_data(self):
        for value in ('relative.ipa',str(self.root/'bad.zip'),str(self.c.library/'save.ipa'),str(self.c.private/'key.ipa'),str(self.engine/'engine.ipa')):
            self.c.r['outputPath']=value
            with patch('build.build') as run, self.assertRaises(Failure): ipa.export(self.c)
            run.assert_not_called()
        target=self.root/'target.ipa';target.write_text('old')
        link=self.root/'link.ipa';link.symlink_to(target)
        self.c.r['outputPath']=str(link)
        with self.assertRaises(Failure): ipa.destination(self.c)
        self.assertEqual(target.read_text(),'old')

    def test_ios_environment_requires_optional_tools_without_changing_mac_environment(self):
        with patch('ipa.shutil.which',return_value=None):
            with self.assertRaisesRegex(Failure,'XcodeGen'): ipa.environment(self.c)
        tool=self.root/'xcodegen';tool.write_text('synthetic tool')
        with patch('ipa.shutil.which',return_value=str(tool)),patch('toolchain.probe',return_value=(True,'fixture version')):
            env,identity=ipa.environment(self.c)
        self.assertNotIn('DM_MAC_ONLY',env)
        self.assertEqual(self.c.env()['DM_MAC_ONLY'],'1')
        self.assertIn('xcodegenHash',identity)
        with patch('ipa.shutil.which',return_value=str(tool)),patch('toolchain.probe',return_value=(False,'SDK unavailable')):
            with self.assertRaisesRegex(Failure,'iOS 构建环境'): ipa.environment(self.c)
        (self.engine/ipa.IOS_FILES[0]).unlink()
        with self.assertRaisesRegex(Failure,'iOS 打包组件'): ipa.environment(self.c)

    def test_validator_rejects_mac_app_missing_resources_and_crc_corruption(self):
        output=self.root/'sample.ipa'
        for options in ({'platform':'MacOSX'},{'resources':False},{'corrupt':True}):
            archive(output,**options)
            with self.assertRaises(Failure): self.quiet(ipa.validate,output,self.c)
        archive(output);self.quiet(ipa.validate,output,self.c)

    def test_success_exports_verified_unsigned_archive_and_records_destination(self):
        output=ipa.destination(self.c);output.write_text('old export')
        def run(args,log=None,env=None,**kw):
            self.assertEqual(env['ROMFS'],str(self.selected/'RomFS'))
            self.assertEqual(env['MSL_IOS'],str(self.shaders))
            self.assertNotIn('prod.keys',str(env))
            archive(Path(args[-1]))
        with patch.object(self.c,'run',side_effect=run): result=self.package()
        self.assertFalse(result['signed']);self.assertEqual(result['sha256'],digest(output))
        self.assertEqual(result['outputPath'],str(output))
        self.assertEqual(Path(json.loads(self.c.jobpath.read_text())['outputPath']).resolve(),output)
        self.assertFalse(list(self.root.glob('*.partial')))

    def test_failure_and_cancellation_preserve_previous_export_and_mac_runtime(self):
        output=ipa.destination(self.c);output.write_text('previous IPA')
        runtime=self.c.library/'games'/self.g['id']/'current';runtime.mkdir(parents=True)
        (runtime/'sentinel').write_text('working Mac version')
        with patch.object(self.c,'run',side_effect=Failure('compiler failed')):
            with self.assertRaises(Failure): self.package()
        with patch.object(self.c,'run',side_effect=lambda args,*a,**kw:archive(Path(args[-1]),resources=False)):
            with self.assertRaises(Failure): self.package()
        def cancel_during_hash(path,progress):
            self.c.cancelled=True;progress(1,2)
        with patch.object(self.c,'run',side_effect=lambda args,*a,**kw:archive(Path(args[-1]))),patch('ipa.digest',side_effect=cancel_during_hash):
            with self.assertRaises(Cancelled): self.package()
        self.assertEqual(output.read_text(),'previous IPA')
        self.assertEqual((runtime/'sentinel').read_text(),'working Mac version')
        self.assertFalse(list(self.root.glob('*.partial')))

    def test_wrong_platform_shaders_are_rejected_before_checkpoint(self):
        self.graphics='nvn';directory=self.shaders/'b-fixture';directory.mkdir()
        reflection=directory/'key_b.json';(directory/'key_b.metallib').write_text('synthetic')
        atomic(reflection,dict(chain='fixture',chain_metal='xcrun -sdk macosx metal'))
        with self.assertRaises(Failure): ipa.validate_shaders(self.shaders,self.gp,self.engine)
        atomic(reflection,dict(chain='fixture',chain_metal='xcrun -sdk iphoneos metal'))
        ipa.validate_shaders(self.shaders,self.gp,self.engine)
        (directory/'key_b.metallib').unlink()
        with self.assertRaises(Failure): ipa.validate_shaders(self.shaders,self.gp,self.engine)

    def test_mac_and_ios_cache_keys_and_chain_environments_are_separate(self):
        self.g['packages']=[dict(type='base',version=0,sha256='base'),dict(type='update',version=1114112,sha256='update',builds={'main':'fixture-build'})]
        script=self.engine/'scripts/build_ipa_from_nsp.py'
        script.write_text(script.read_text()+'\nclass Progress:\n    def __init__(self, mode): pass\n')
        (self.engine/'dm/games/game.py').write_text(
            'from pathlib import Path\n'
            'class Profile:\n'
            '    def __init__(self,ident,folder): self.id=ident; self.folder=folder\n'
            '    def table(self,name): return Path(self.folder)/self.id/name\n'
            'def load(game_id): return Profile(game_id,HERE)\n')
        (self.engine/'dm/gfx/tools/dmsh_chain.lock').write_text('fixture lock')
        prepared=self.root/'prepared';shutil.copytree(self.engine,prepared/'source')
        before=engine.source_hash(self.engine)
        prior=sys.modules.pop('game',None)
        def ios_env(c,env=None):
            env=dict(env or c.env());env.pop('DM_MAC_ONLY',None);return env,{}
        try:
            with patch('build.tools',return_value={'engineSource':'fixture'}),patch('engine.prepared_tools',return_value=prepared),patch.object(self.c,'run'),patch('ipa.environment',side_effect=ios_env):
                mac=self.quiet(build.prepare,self.c,self.g,'macos')
                ios=self.quiet(build.prepare,self.c,self.g,'ios')
            self.assertNotEqual(mac[-1],ios[-1]);self.assertNotEqual(mac[0],ios[0])
            self.assertEqual(mac[2]['DM_MAC_ONLY'],'1');self.assertNotIn('DM_MAC_ONLY',ios[2])
            self.assertEqual(json.loads((ios[0]/'identity.json').read_text())['target'],'ios')
            self.assertEqual(engine.source_hash(self.engine),before)
        finally:
            sys.modules.pop('game',None)
            if prior is not None: sys.modules['game']=prior

    def test_vulkan_pipeline_builds_ios_shaders_without_installing_mac_runtime(self):
        self.pipeline('vulkan')

    def test_nvn_pipeline_builds_ios_shaders_without_installing_mac_runtime(self):
        self.pipeline('nvn')

    def pipeline(self, graphics):
        self.graphics=graphics
        source=self.c.library/'sources/base.nsp';source.parent.mkdir();source.write_text('original synthetic NSP')
        self.g['packages']=[dict(type='base',version=0,path='sources/base.nsp',sha256=digest(source),size=source.stat().st_size)]
        self.c.save_catalog({'games':[self.g]})
        def extract(nx,keys,root,ver,*args):
            (root/ver/'RomFS').mkdir(parents=True,exist_ok=True)
            (root/ver/'RomFS/marker').write_text('synthetic')
        def rewrite(py,repo,exefs,out,*args):
            out.mkdir();(out/'main.patched.bin').write_text('synthetic')
        def split(py,repo,roms,mains,out,*args):
            out.mkdir(parents=True);(out/'shader.bin').write_text('synthetic shader package')
        (self.profile/'shader_map.tsv').write_text('main.bin\t0\t0\tkey\tfixture\n')
        upstream=SimpleNamespace(extract=extract,rewrite=rewrite,split_shaders=split,PROG=SimpleNamespace(stage=lambda *a,**kw:None,watch=lambda *a:None))
        calls=[];environments=[]
        def run(args,*a,**kw):
            calls.append([str(x) for x in args]);environments.append(a[1])
            if graphics=='vulkan':
                (self.work/'shader/vk').mkdir(exist_ok=True)
                (self.work/'shader/vk/vk_shaders.metallib').write_text('synthetic Mac shader')
                (self.shaders/'vk').mkdir(parents=True,exist_ok=True)
                (self.shaders/'vk/vk_shaders.metallib').write_text('synthetic iOS shader')
            else:
                for path,sdk in [(self.work/'shader/cache','macosx'),(self.shaders,'iphoneos')]:
                    directory=path/'b-fixture';directory.mkdir(parents=True)
                    (directory/'key_b.metallib').write_text('synthetic shader')
                    atomic(directory/'key_b.json',dict(chain='fixture',chain_metal='xcrun -sdk '+sdk))
        prepared=(self.work,self.engine,self.c.env(),upstream,self.gp,'ios-fixture')
        with patch('build.prepare',return_value=prepared) as prepare,patch.object(self.c,'nx',return_value=self.root/'reader'),patch.object(self.c,'run',side_effect=run),patch('ipa.package',return_value={'signed':False}) as package,patch('build.install') as install:
            result=self.quiet(build.build,self.c,target='ios')
        self.assertFalse(result['signed'])
        if graphics=='vulkan': self.assertIn('--ios',calls[0])
        else: self.assertEqual(environments[0]['IOSOUT'],str(self.shaders))
        self.assertEqual(prepare.call_args.args[-1],'ios');package.assert_called_once();install.assert_not_called()
        checkpoints=json.loads((self.work/'checkpoints.json').read_text())
        self.assertTrue(any('/ios/' in p for p in checkpoints['转换并编译 Vulkan 着色器' if graphics=='vulkan' else '转换并编译 Metal 着色器']))


if __name__=='__main__': unittest.main()
