"""Merged-container imports, catalogue upgrades and exact extraction selection.

All game data here is synthetic. Real player files never enter test fixtures.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Context, Failure, digest
import build, engine, library
from engine_fixture import make_engine

TITLE='0100000000010000'


def package(kind='base', version=0, title=TITLE, base=TITLE):
    return dict(titleId=title,baseId=base,type=kind,version=version,
                name='Synthetic game',display='1.0' if kind=='base' else '1.1',builds={'main':'synthetic'})


class ContainerMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='lumanx-container-')
        self.root=Path(self.tmp.name)
        self.c=Context(dict(operation='import',privateRoot=str(self.root/'private'),
            library=str(self.root/'library'),engineDir=str(make_engine(self.root/'engine'))))
        self.quiet(library.setup,self.c)
        self.c.keys.parent.mkdir();self.c.keys.write_text('header_key = '+'0'*64)
        self.source=self.root/'merged.xci';self.source.write_bytes(b'synthetic merged container')
        self.response=dict(schema=2,packages=[package(),package('update',65536,TITLE[:-3]+'800'),
            package('dlc',0,'0100000000011001')])
    def tearDown(self): self.tmp.cleanup()
    def quiet(self,fn,*args,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()): return fn(*args,**kwargs)
    def imported(self):
        with patch('library.inspect',return_value=self.response):
            return self.quiet(library.import_containers,self.c,[self.source])
    def test_one_container_keeps_base_update_dlc_and_copies_once(self):
        with patch('library.clone',wraps=library.clone) as copy:
            self.imported();self.assertEqual(copy.call_count,1)
        game=self.c.catalog()['games'][0]
        self.assertEqual([p['type'] for p in game['packages']],['base','dlc','update'])
        self.assertEqual(len({p['path'] for p in game['packages']}),1)
        self.assertEqual(game['display'],'1.1')
        self.assertTrue(all(p['metadataSchema']==2 for p in game['packages']))
        self.assertEqual(len(list((self.c.library/'sources').rglob('*.xci'))),1)
    def test_duplicate_reimport_repairs_legacy_single_package_record(self):
        with patch('library.inspect',return_value=package()):
            self.quiet(library.import_containers,self.c,[self.source])
        self.assertEqual(len(self.c.catalog()['games'][0]['packages']),1)
        self.assertFalse(self.imported()['imports'][0]['duplicate'])
        self.assertEqual(len(self.c.catalog()['games'][0]['packages']),3)
        self.assertTrue(self.imported()['imports'][0]['duplicate'])
        self.assertEqual(len(self.c.catalog()['games'][0]['packages']),3)
    def test_existing_managed_container_upgrades_once_without_copy(self):
        with patch('library.inspect',return_value=package()):
            self.quiet(library.import_containers,self.c,[self.source])
        with patch.object(self.c,'nx',return_value=Path('/reader')),patch('library.inspect',return_value=self.response) as inspect,patch('library.clone') as copy:
            self.quiet(library.refresh_container_metadata,self.c)
            self.quiet(library.refresh_container_metadata,self.c)
        self.assertEqual(inspect.call_count,1);copy.assert_not_called()
        self.assertEqual(len(self.c.catalog()['games'][0]['packages']),3)
    def test_unavailable_reader_preserves_old_catalogue_and_runtime(self):
        with patch('library.inspect',return_value=package()):
            self.quiet(library.import_containers,self.c,[self.source])
        before=self.c.catalog()
        with patch.object(self.c,'nx',side_effect=Failure('not ready')),patch('library.inspect') as inspect:
            self.quiet(library.refresh_container_metadata,self.c)
        self.assertEqual(self.c.catalog(),before);inspect.assert_not_called()
    def test_changed_managed_source_is_not_silently_reindexed(self):
        with patch('library.inspect',return_value=package()):
            self.quiet(library.import_containers,self.c,[self.source])
        before=self.c.catalog();managed=self.c.library/before['games'][0]['packages'][0]['path']
        managed.write_bytes(b'changed source')
        with patch.object(self.c,'nx',return_value=Path('/reader')),patch('library.inspect',return_value=self.response):
            self.quiet(library.refresh_container_metadata,self.c)
        self.assertEqual(self.c.catalog(),before)
    def test_refresh_preserves_hidden_game_in_shared_container(self):
        self.response['packages'].append(package(title='0100000000020000',base='0100000000020000'))
        self.imported();cat=self.c.catalog();cat['games'][1]['hidden']=True
        for game in cat['games']:
            for p in game['packages']:p.pop('metadataSchema',None)
        self.c.save_catalog(cat)
        with patch.object(self.c,'nx',return_value=Path('/reader')),patch('library.inspect',return_value=self.response):
            self.quiet(library.refresh_container_metadata,self.c)
        self.assertTrue(self.c.catalog()['games'][1]['hidden'])
    def test_bundle_can_contain_more_than_one_game(self):
        self.response['packages'].append(package(title='0100000000020000',base='0100000000020000'))
        result=self.imported()
        self.assertEqual(len(result['imports']),2)
        games=self.c.catalog()['games'];self.assertEqual(len(games),2)
        self.assertEqual(len({p['path'] for g in games for p in g['packages']}),1)
    def test_metadata_is_validated_before_catalog_or_copy_changes(self):
        self.response['packages'].append(package(title='../bad'))
        with self.assertRaises(Failure): self.imported()
        self.assertEqual(self.c.catalog()['games'],[])
        self.assertEqual(list((self.c.library/'sources').iterdir()),[])
    def test_clean_shared_container_keeps_other_games_including_hidden_ones(self):
        other='0100000000020000'
        self.response['packages'].append(package(title=other,base=other))
        self.imported();cat=self.c.catalog();cat['games'][1]['hidden']=True;self.c.save_catalog(cat)
        shared=self.c.library/cat['games'][0]['packages'][0]['path']
        self.c.r.update(gameId=TITLE,kind='sources')
        result=self.quiet(library.clean,self.c)
        self.assertEqual(result['retainedShared'],1)
        self.assertTrue(shared.exists())
        self.assertEqual(self.c.catalog()['games'][0]['packages'],[])
        self.assertEqual(len(self.c.catalog()['games'][1]['packages']),1)
        # The last owner can clean a container stored under a different title.
        self.c.r['gameId']=other;self.quiet(library.clean,self.c)
        self.assertFalse(shared.exists())
    def test_cancelled_source_cleanup_leaves_other_references_intact(self):
        self.imported();cat=self.c.catalog()
        source=self.c.library/cat['games'][0]['packages'][0]['path']
        self.c.r.update(gameId=TITLE,kind='sources')
        original=self.c.save_catalog
        def save_then_cancel(value):
            original(value);self.c.cancelled=True
        from core import Cancelled
        with patch.object(self.c,'save_catalog',side_effect=save_then_cancel):
            with self.assertRaises(Cancelled): self.quiet(library.clean,self.c)
        self.assertTrue(source.exists())
        self.assertEqual(self.c.catalog()['games'][0]['packages'],[])
    def test_source_cleanup_rejects_paths_outside_sources(self):
        self.imported();cat=self.c.catalog()
        save=self.c.library/'saves/keep';save.write_text('save')
        cat['games'][0]['packages'][0]['path']='saves/keep';self.c.save_catalog(cat)
        self.c.r.update(gameId=TITLE,kind='sources')
        with self.assertRaises(Failure): self.quiet(library.clean,self.c)
        self.assertEqual(save.read_text(),'save')
        self.assertEqual(self.c.catalog(),cat)
    def test_update_does_not_satisfy_another_required_profile_version(self):
        profile={'package':'v327680','shader_versions':'v0 v327680',
            'builds':{'v0':{'main':'synthetic'},'v327680':{'display':'1.2.1','main':'other'}}}
        missing=library.requirements({'packages':self.response['packages']},profile)
        self.assertEqual(missing,['缺少更新 v327680（1.2.1）'])
    def test_all_packages_use_their_own_icon(self):
        def inspect(c,src,**kw):
            for p in self.response['packages']:
                (kw['icon']/(p['titleId']+'.jpg')).write_bytes(p['type'].encode())
            return self.response
        with patch('library.inspect',side_effect=inspect):
            self.quiet(library.import_containers,self.c,[self.source])
        self.assertEqual((self.c.library/'games'/TITLE/'cover.jpg').read_bytes(),b'update')


class ContainerSelectionTests(unittest.TestCase):
    def test_runner_selects_exact_update_and_each_dlc_from_shared_path(self):
        calls=[];reader=Path('/private/reader/nx_extract')
        c=SimpleNamespace(nx=lambda:reader,run=lambda args,*a,**kw:calls.append(args))
        game={'id':TITLE,'packages':[package('dlc',42,'0100000000011002')]}
        run=build.container_runner(c,game)
        run([reader,'keys','shared.xci','-','/tmp/v0.partial'])
        run([reader,'keys','shared.xci','shared.xci','/tmp/v65536.partial'])
        run([reader,'keys','--aoc','shared.xci','/tmp/aoc.partial/2'])
        self.assertEqual(calls[0][-2:],[f'--lumanx-title={TITLE}','--lumanx-version=0'])
        self.assertEqual(calls[1][-2:],[f'--lumanx-title={TITLE}','--lumanx-version=65536'])
        self.assertEqual(calls[2][-2:],['--lumanx-title=0100000000011002','--lumanx-version=42'])
        run(['/usr/bin/python3','shader.py'])
        self.assertEqual(calls[-1],['/usr/bin/python3','shader.py'])
    def test_unrecognized_extraction_output_fails_before_running(self):
        c=SimpleNamespace(nx=lambda:Path('/nx_extract'),run=lambda *a:self.fail('must not run'))
        with self.assertRaises(Failure):
            build.container_runner(c,{'id':TITLE})([Path('/nx_extract'),'keys','base','-','/tmp/unknown'])
    def test_image_requests_preserve_launcher_folder_layout_and_dlc_selection(self):
        calls=[];reader=Path('/private/reader/nx_extract')
        c=SimpleNamespace(nx=lambda:reader,run=lambda args,*a,**kw:calls.append(args))
        game={'id':TITLE,'packages':[package('dlc',42,'0100000000011002')]}
        run=build.container_runner(c,game)
        run([reader,'keys','base.xci','update.nsp','/tmp/v65536.partial','--romfs-image'])
        run([reader,'keys','--aoc','shared.xci','/tmp/aoc.partial/2.img','--romfs-image'])
        self.assertNotIn('--romfs-image',calls[0])
        self.assertEqual(calls[0][4],'/tmp/v65536.partial')
        self.assertEqual(calls[0][-2:],[f'--lumanx-title={TITLE}','--lumanx-version=65536'])
        self.assertNotIn('--romfs-image',calls[1])
        self.assertEqual(Path(calls[1][4]),Path('/tmp/aoc.partial/2'))
        self.assertEqual(calls[1][-2:],['--lumanx-title=0100000000011002','--lumanx-version=42'])
    def test_bundled_extraction_stages_keep_launcher_romfs_and_dlc_directories(self):
        repo=Path(__file__).resolve().parents[1]/'Engine/nxnative'
        with tempfile.TemporaryDirectory() as temp, patch.object(sys,'path',list(sys.path)), contextlib.redirect_stdout(io.StringIO()):
            root=Path(temp);logs=root/'logs';logs.mkdir()
            source=root/'synthetic.xci';source.write_bytes(b'synthetic container')
            reader=Path('/private/reader/nx_extract');calls=[]
            def extract(args,*a,**kw):
                calls.append(args)
                self.assertNotIn('--romfs-image',args)
                out=Path(args[4]);out.mkdir(parents=True)
                if str(args[2]) == '--aoc': (out/'dlc.txt').write_text('synthetic DLC')
                else:
                    (out/'ExeFS').mkdir();(out/'ExeFS/main').write_bytes(b'synthetic NSO')
                    (out/'RomFS').mkdir();(out/'RomFS/marker').write_text('synthetic RomFS')
            c=SimpleNamespace(nx=lambda:reader,run=extract)
            game={'id':TITLE,'packages':[package('dlc',42,'0100000000011002')]}
            spec=importlib.util.spec_from_file_location('lumanx_extraction_test',repo/'scripts/build_ipa_from_nsp.py')
            up=importlib.util.module_from_spec(spec);spec.loader.exec_module(up)
            up.PROG=up.Progress('off');up.run=build.container_runner(c,game)
            up.extract(reader,root/'synthetic.keys',root/'extract','v0',source,None,None,logs,{'romfs_marker':'marker'})
            up.extract_aoc(reader,root/'synthetic.keys',repo,root,int(TITLE,16),{'dlc':[(int('0100000000011002',16),42,source)]},logs)
            self.assertTrue((root/'extract/v0/RomFS/marker').is_file())
            self.assertTrue((root/'aoc/2/dlc.txt').is_file())
            self.assertEqual(calls[-1][-2:],['--lumanx-title=0100000000011002','--lumanx-version=42'])
    def test_adapter_routes_each_extraction_to_cnmt_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=make_engine(Path(temp)/'engine');path=root/'dm/tools/nx_extract/Program.cs'
            path.write_text('static class P { static int Main(string[] a) { var b=OpenNsp(ks, a[1]); var u=OpenNsp(ks, a[2]); return 0; } void Aoc() { var p=OpenNsp(ks, nsp); } }')
            engine.adapt_snapshot(root)
            code=path.read_text()
            self.assertIn('LumaNXSelected(ks, a[1], "base")',code)
            self.assertIn('LumaNXSelected(ks, a[2], "update")',code)
            self.assertIn('LumaNXSelected(ks, nsp, "dlc")',code)
            self.assertIn('a = LumaNXArgs(a)',code)
    def test_bundled_reader_adapter_preserves_exact_selection_with_upstream_filter(self):
        repo=Path(__file__).resolve().parents[1]/'Engine/nxnative'
        with tempfile.TemporaryDirectory() as temp:
            root=make_engine(Path(temp)/'engine')
            for name in ('dm/tools/nx_extract/Program.cs','dm/gfx/tools/dmsh_chain.py','dm/gfx/tools/tool_lock.py'):
                (root/name).write_text((repo/name).read_text())
            engine.adapt_snapshot(root)
            path=root/'dm/tools/nx_extract/Program.cs';code=path.read_text()
            for source,kind in (('a[1]','base'),('a[2]','update'),('nsp','dlc')):
                self.assertIn(f'LumaNXSelected(ks, {source}, "{kind}")',code)
            engine.adapt_snapshot(root)
            self.assertEqual(path.read_text(),code)


if __name__=='__main__': unittest.main()
