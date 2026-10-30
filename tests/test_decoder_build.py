"""Registered shader decoding uses synthetic resources and never runs game code."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Context, Failure, digest, read
import build


class DecoderBuildTests(unittest.TestCase):
    def pipeline(self,target,source='oodle_packs',retry=None):
        with tempfile.TemporaryDirectory(prefix="lumanx-decoder-中文's-") as temp:
            root=Path(temp)
            c=Context(dict(operation='exportIPA' if target=='ios' else 'build',gameId='0100000000010000',
                privateRoot=str(root/'private'),library=str(root/'library')))
            c.library.mkdir();container=c.library/'base.nsp';container.write_text('synthetic container')
            c.save_catalog(dict(games=[dict(id=c.r['gameId'],packages=[dict(type='base',version=0,
                path=container.name,size=container.stat().st_size,sha256=digest(container))])]))
            work=c.library/'cache'/target;repo=work/'engine';profile=repo/'dm/games'/c.r['gameId']
            profile.mkdir(parents=True);(profile/'shader_map.tsv').write_text('main.bin\t0\t0\tkey\tfixture\n')
            header=repo/'dm/gfx/nvn/dmsh_chain.h';header.parent.mkdir(parents=True)
            header.write_text('#define DMSH_CHAIN "fixture"')
            gp=SimpleNamespace(id=c.r['gameId'],table=lambda name:profile/name,
                get=lambda key,default=None:{'package':'v0','graphics':'nvn'}.get(key,default),
                words=lambda key,default=None:['main','sdk'] if key=='modules' else [default])
            flags={key:(key==source,'synthetic') for key in ('oodle_packs','ue_legacy','ue_decode')}
            if source!='old_engine':
                (profile.parent/'profile_guess.py').write_text(
                    'def build_sources(exefs, romfs, modules):\n'
                    '    assert (exefs / "main").is_file() and (romfs / "marker").is_file()\n'
                    '    assert modules == ["main", "sdk"]\n'
                    '    return '+repr(flags)+'\n')
            selected=work/'extract/v0';patched=work/'patched_v0';host=work/'tools/dmhost'
            events=[];attempts={'host':0,'split':0}
            def extract(nx,keys,dst,version,*args):
                (dst/version/'RomFS').mkdir(parents=True);(dst/version/'RomFS/marker').write_text('synthetic')
                (dst/version/'ExeFS').mkdir();(dst/version/'ExeFS/main').write_text('synthetic code')
            def rewrite(py,engine,exefs,out,*args):
                out.mkdir();(out/'main.patched.bin').write_text('synthetic rewritten module')
            def write_host():
                host.parent.mkdir(parents=True,exist_ok=True);host.write_text('synthetic host, never executed');return host
            def decoder_host(engine,out,env,logs,game):
                events.append('host');attempts['host']+=1
                self.assertEqual((engine,out,logs,game),(repo,host,work/'logs',gp))
                self.assertTrue((patched/'main.patched.bin').is_file())
                if retry=='host' and attempts['host']==1: raise Failure('synthetic host failure')
                return write_host()
            def decode(engine,dirs,version,modules,build_root,env,logs,game):
                events.append('decode')
                self.assertEqual((dirs,version,modules,build_root),({'v0':selected},'v0',patched,work))
                (selected/'ue_shaders').mkdir();(selected/'ue_shaders/archive.ushaderbytecode').write_text('synthetic decoded shaders')
            def split(py,engine,roms,mains,pkg,env,logs,game,provisional=False,oodle=None):
                attempts['split']+=1
                self.assertFalse(provisional)   # Registered tables stay strict.
                self.assertEqual((roms,mains),([selected/'RomFS'],[selected/'ExeFS/main']))
                if source in ('oodle_packs','ue_legacy'):
                    self.assertIsNotNone(oodle)
                    decoder=oodle()
                    self.assertEqual(decoder,dict(DM_OODLE_HOST=str(host),DM_OODLE_MODULES=str(patched)))
                    self.assertTrue(Path(decoder['DM_OODLE_HOST']).is_file())
                else: self.assertIsNone(oodle)
                self.assertNotIn('DM_OODLE_HOST',env);self.assertNotIn('DM_OODLE_MODULES',env)
                if source=='ue_decode': self.assertTrue((selected/'ue_shaders/archive.ushaderbytecode').is_file())
                events.append('split')
                if retry=='split' and attempts['split']==1: raise Failure('synthetic split failure')
                pkg.mkdir(parents=True);(pkg/'shader.bin').write_text('synthetic shaders')
            def run(args,log,env,*a,**kw):
                events.append('shaders')
                for folder in [work/'shader/cache']+([work/'shader/ios'] if target=='ios' else []):
                    folder.mkdir(parents=True,exist_ok=True);(folder/'fixture.metallib').write_text('synthetic library')
            upstream=SimpleNamespace(extract=extract,rewrite=rewrite,split_shaders=split,
                build_mac_host=decoder_host,decode_ue_shaders=decode,PROG=SimpleNamespace(stage=lambda *a,**kw:None,watch=lambda *a:None))
            with contextlib.redirect_stdout(io.StringIO()),patch('build.prepare',return_value=(work,repo,c.env(),upstream,gp,'fixture')),\
                 patch.object(c,'nx',return_value=root/'reader'),patch.object(c,'run',side_effect=run),\
                 patch('build.shutil.disk_usage',return_value=SimpleNamespace(free=100*2**30)),\
                 patch('build.compile_host',side_effect=lambda *a:write_host()),patch('build.install',return_value={}) as install,\
                 patch('ipa.package',return_value={}) as package,patch('ipa.validate_shaders'):
                if retry:
                    with self.assertRaisesRegex(Failure,'synthetic '+retry+' failure'):build.build(c,target)
                    self.assertNotIn('提取并核对着色器',read(work/'checkpoints.json',{}))
                    install.assert_not_called();package.assert_not_called()
                build.build(c,target);before=list(events);build.build(c,target)
                self.assertEqual(events,before)   # Successful decoding is checkpointed.
            self.assertEqual(events[-1],'shaders')
            if source in ('oodle_packs','ue_legacy'):self.assertLess(events.index('host'),events.index('split'))
            if source=='ue_decode':self.assertLess(events.index('decode'),events.index('split'))

    def test_registered_trinity_mac_and_ios(self):
        for target in ('macos','ios'):
            with self.subTest(target=target):self.pipeline(target)

    def test_registered_legacy_paks_mac_and_ios(self):
        for target in ('macos','ios'):
            with self.subTest(target=target):self.pipeline(target,'ue_legacy')

    def test_registered_unreal_archive_decode_precedes_split(self):
        for target in ('macos','ios'):
            with self.subTest(target=target):self.pipeline(target,'ue_decode')

    def test_host_and_split_failures_remain_retryable(self):
        for target in ('macos','ios'):
            for stage in ('host','split'):
                with self.subTest(target=target,stage=stage):self.pipeline(target,retry=stage)

    def test_plain_and_old_engines_do_not_build_decoder(self):
        for source in ('plain','old_engine'):
            with self.subTest(source=source):self.pipeline('ios',source)


if __name__=='__main__':unittest.main()
