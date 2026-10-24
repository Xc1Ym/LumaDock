"""DLC build protocol regression for issue #9; synthetic files only."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Context, Failure, digest, read
import build


class DLCBuildTests(unittest.TestCase):
    def pipeline(self, target, *, dlc=True, retry=False):
        with tempfile.TemporaryDirectory(prefix="lumadock-dlc-中文's-") as directory:
            root=Path(directory)
            c=Context(dict(operation='exportIPA' if target=='ios' else 'build',
                privateRoot=str(root/'private'), library=str(root/'library'),
                resources=str(root/'resources'), gameId='0100000000010000'))
            work=c.library/'cache'/target;work.mkdir(parents=True)
            repo=work/'engine';repo.mkdir()
            game=dict(id=c.r['gameId'], packages=[])
            for name,kind,tid,version in [('base','base',game['id'],0)]+([
                ('dlc-one','dlc','0100000000011001',0),
                ('dlc-two','dlc','0100000000011002',65536)] if dlc else []):
                path=c.library/(name+'.nsp');path.write_text('synthetic '+name)
                game['packages'].append(dict(type=kind,titleId=tid,version=version,
                    path=path.name,size=path.stat().st_size,sha256=digest(path)))
            c.save_catalog({'games':[game]})
            gp=SimpleNamespace(id=game['id'],
                get=lambda key,default=None:{'package':'v0','graphics':'vulkan'}.get(key,default),
                words=lambda key,default=None:[default])
            expected=[(int(p['titleId'],16),p['version'],c.library/p['path'])
                for p in game['packages'] if p['type']=='dlc']
            calls=[]

            def extract(nx,keys,dst,version,base,update,extra,logs,profile):
                (dst/version/'RomFS').mkdir(parents=True)
                (dst/version/'RomFS/marker').write_text('synthetic base')

            # Keep the real seven-argument protocol: a variadic stub hides #9.
            def extract_aoc(nx,keys,engine,build_root,app,family,logs):
                self.assertEqual((nx,keys,engine,build_root,app,logs),
                    (root/'reader',c.keys,repo,work,int(game['id'],16),work/'logs'))
                self.assertEqual(family,{'dlc':expected})
                calls.append(family)
                for tid,version,path in family['dlc']:
                    dst=build_root/'aoc'/str(tid-app-0x1000)
                    dst.mkdir(parents=True);(dst/'marker').write_text(path.read_text())
                    if retry and len(calls)==1: raise Failure('synthetic DLC failure')

            def rewrite(py,engine,exefs,out,env,logs,profile):
                out.mkdir();(out/'main.patched.bin').write_text('synthetic code')

            def shaders(*args,**kwargs):
                for dst in [work/'shader/vk']+([work/'shader/ios/vk'] if target=='ios' else []):
                    dst.mkdir(parents=True,exist_ok=True)
                    (dst/'vk_shaders.metallib').write_text('synthetic shader')

            def host(*args):
                path=work/'tools/dmhost';path.parent.mkdir(parents=True)
                path.write_text('synthetic host');return path

            upstream=SimpleNamespace(extract=extract,extract_aoc=extract_aoc,rewrite=rewrite)
            prepared=(work,repo,c.env(),upstream,gp,'fixture')
            with contextlib.redirect_stdout(io.StringIO()), \
                 patch('build.prepare',return_value=prepared), \
                 patch.object(c,'nx',return_value=root/'reader'), \
                 patch.object(c,'run',side_effect=shaders), \
                 patch('build.shutil.disk_usage',return_value=SimpleNamespace(free=100*2**30)), \
                 patch('build.compile_host',side_effect=host), \
                 patch('build.install',return_value={'path':'installed'}) as install, \
                 patch('ipa.validate_shaders'), \
                 patch('ipa.package',return_value={'path':'exported'}) as package:
                if retry:
                    with self.assertRaisesRegex(Failure,'synthetic DLC failure'): build.build(c,target)
                    self.assertNotIn('处理 DLC',read(work/'checkpoints.json',{}))
                    install.assert_not_called();package.assert_not_called()
                build.build(c,target)
                consumer=package if target=='ios' else install
                self.assertEqual(consumer.call_args.args[-1],work/'aoc')
                other=install if target=='ios' else package
                other.assert_not_called()
                if dlc:
                    self.assertEqual((work/'aoc/1/marker').read_text(),'synthetic dlc-one')
                    self.assertEqual((work/'aoc/2/marker').read_text(),'synthetic dlc-two')
                else: self.assertEqual((work/'aoc/.empty').read_text(),'no DLC')
                self.assertIn('处理 DLC',read(work/'checkpoints.json',{}))
                build.build(c,target)
                self.assertEqual(len(calls),2 if retry else int(dlc))

    def test_mac_dlc_arguments_install_and_cache(self): self.pipeline('macos')
    def test_ios_dlc_arguments_export_and_cache(self): self.pipeline('ios')
    def test_mac_without_dlc(self): self.pipeline('macos',dlc=False)
    def test_ios_without_dlc(self): self.pipeline('ios',dlc=False)
    def test_mac_failed_dlc_can_retry(self): self.pipeline('macos',retry=True)
    def test_ios_failed_dlc_can_retry(self): self.pipeline('ios',retry=True)


if __name__=='__main__': unittest.main()
