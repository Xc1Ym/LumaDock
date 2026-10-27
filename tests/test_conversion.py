"""Real subprocess conversion protocol with original containers; no player content."""
import contextlib, io, json, os, signal, struct, subprocess, sys, tempfile, threading, time, unittest, venv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Context, Failure, Cancelled, digest
import conversion, library

SCRIPT = r'''
import json, os, struct, sys
from pathlib import Path
args=sys.argv[1:]
config=Path(__file__).with_name('fixture.json')
mode=json.loads(config.read_text()).get('behavior','ok') if config.exists() else 'ok'
out=Path(args[args.index('-o')+1])
if '-tfile' in args:
    inputs=Path(args[args.index('-tfile')+1]).read_text().splitlines()
else: inputs=[args[-1]]
assert all('/converter/work/' in path for path in inputs), inputs
assert all(Path(path).suffix==Path(path).suffix.lower() for path in inputs)
if '-t' in args:
    assert 'header_key' in Path('keys.txt').read_text()
    ext='nsp' if args[args.index('-t')+1] in ('nsp','cnsp') else 'xci'
elif '-C' in args: ext='nsz' if Path(inputs[0]).suffix.lower()=='.nsp' else 'xcz'
else: ext='nsp' if Path(inputs[0]).suffix.lower()=='.nsz' else 'xci'
print(json.dumps({'type':'progress','file':inputs[0],'step':'convert','percent':25}),flush=True)
if mode=='slow':
    import time
    time.sleep(30)
if mode=='nonzero': print('Error: fixture conversion failed',flush=True);raise SystemExit(2)
if mode=='exit_zero_error': print('Traceback: fixture failure',flush=True)
if mode=='empty': raise SystemExit(0)
name='merged' if '-tfile' in args else Path(inputs[0]).stem
destination=out/(name+'.'+ext)
payload=json.dumps({'args':args,'home':os.environ['HOME'],'inputs':inputs}).encode()
if mode=='symlink': destination.symlink_to(inputs[0]);raise SystemExit(0)
if ext in ('nsp','nsz'):
    names=b'original.txt\0'
    data=b'PFS0'+struct.pack('<III',1,len(names),0)+struct.pack('<QQII',0,len(payload),0,0)+names+payload
else:
    header=bytearray(0xf000);header[0x100:0x104]=b'HEAD'
    names=b'secure\0';root=b'HFS0'+struct.pack('<III',1,len(names),0)+struct.pack('<QQII',0,len(payload),0,0)+b'\0'*40+names
    struct.pack_into('<QQ',header,0x130,0xf000,len(root));data=bytes(header)+root+payload
destination.write_bytes(b'invalid' if mode=='invalid' else data)
print(json.dumps({'type':'complete','file':str(destination)}),flush=True)
'''


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="lumanx-conversion-中文's-")
        self.root=Path(self.temp.name).resolve();self.resource=self.root/'resources'
        self.backend=self.resource/'Runtime/converter';self.backend.mkdir(parents=True)
        venv.EnvBuilder(with_pip=False).create(self.resource/'Runtime/python')
        self.sites=self.backend/'python/nsz';self.sites.mkdir(parents=True)
        (self.backend/'nsz.py').write_text(SCRIPT)
        self.ztools=self.backend/'NSC_BUILDER/ztools';self.ztools.mkdir(parents=True)
        (self.ztools/'squirrel.py').write_text(SCRIPT)
        (self.ztools/'keys.txt').write_text('external backend key must not change')
        self.source=self.root/"原始 游戏's.nsp";self.source.write_bytes(b'original synthetic input')
        self.c=Context(dict(operation='convertFiles',privateRoot=str(self.root/'private'),
            library=str(self.root/'library'),resources=str(self.resource),
            conversion=dict(mode='convert',target='nsp',paths=[str(self.source)],level=18,verify=True,outputDirectory=str(self.root/'output'))))
        self.c.keys.parent.mkdir();self.c.keys.write_text('header_key = '+'ab'*32+'\n')
        self.before=digest(self.source)
    def tearDown(self):self.temp.cleanup()
    def quiet(self, fn, *args):
        self.events=io.StringIO()
        with contextlib.redirect_stdout(self.events):return fn(*args)
    def run_conversion(self):return self.quiet(conversion.convert,self.c)
    def behavior(self, value):
        for folder in (self.ztools,self.backend): (folder/'fixture.json').write_text(json.dumps({'behavior':value}))
    def assert_isolated(self):
        self.assertEqual(digest(self.source),self.before)
        self.assertEqual((self.ztools/'keys.txt').read_text(),'external backend key must not change')
        self.assertEqual(list((self.c.private/'converter/work').glob('*')),[])

    def import_fixture(self, paths):
        self.c=Context(self.c.r|{'operation':'import','taskId':'import-fixture','paths':list(map(str,paths))})
        self.quiet(library.setup,self.c)
        def inspect(c,path,key=None,icon=None):
            if path.suffix.lower() not in {'.nsp','.xci'}: raise AssertionError('Only native containers may reach the engine reader')
            if '/converter/import/' in str(path): conversion.validate_output(path)
            return dict(baseId='0100000000000000',titleId='0100000000000000',name='Synthetic import',display='1.0',type='base',version=0,builds={})
        return patch.object(library,'inspect',side_effect=inspect)

    def test_mixed_folder_import_converts_in_private_storage_then_registers_all_content(self):
        folder=self.root/'mixed';nested=folder/'nested';nested.mkdir(parents=True)
        paths=[folder/'base.XCI',nested/'update.NSZ',nested/'extra.xcz',folder/'direct.nsp']
        for index,path in enumerate(paths): path.write_bytes(f'synthetic input {index}'.encode())
        before={p:digest(p) for p in paths}
        with self.import_fixture([folder]):
            result=self.quiet(library.import_games,self.c)
        self.assertEqual(len(result['imports']),4)
        self.assertTrue(all(not item['duplicate'] for item in result['imports']))
        packages=self.c.catalog()['games'][0]['packages'];self.assertEqual(len(packages),4)
        self.assertTrue(all((self.c.library/p['path']).is_file() for p in packages))
        self.assertEqual(sorted(Path(p['path']).suffix for p in packages),['.nsp','.nsp','.xci','.xci'])
        self.assertEqual(before,{p:digest(p) for p in paths})
        self.assertEqual(list((self.c.private/'converter/import').iterdir()),[])
        self.assert_isolated()
        self.assertNotIn('outputFiles',self.c.job)
        self.assertEqual(self.c.job['importPaths'],[str(folder)])
        events=[json.loads(line) for line in self.events.getvalue().splitlines()]
        self.assertTrue(any(event.get('unit')=='%' and event.get('done')==25 for event in events))

    def test_nsp_and_xci_import_do_not_require_or_invoke_the_converter(self):
        cartridge=self.root/'base.XCI';cartridge.write_text('synthetic native cartridge')
        with self.import_fixture([self.source,cartridge]),patch.object(conversion,'_convert',side_effect=AssertionError('Native containers must bypass conversion')):
            result=self.quiet(library.import_games,self.c)
        self.assertEqual(len(result['imports']),2)
        self.assertTrue(any(p['path'].endswith('.xci') for p in self.c.catalog()['games'][0]['packages']))
        self.assertFalse((self.c.private/'converter/import').exists())

    def test_automatic_conversion_uses_library_keys_instead_of_independent_converter_keys(self):
        source=self.root/'base.nsz';source.write_text('synthetic compressed package')
        with self.import_fixture([source]):
            dedicated=self.c.private/'converter/keys/prod.keys';dedicated.parent.mkdir(parents=True)
            dedicated.write_text('invalid dedicated converter key')
            self.assertFalse(conversion.status(self.c)['keysReady'])
            result=self.quiet(library.import_games,self.c)
        self.assertEqual(len(result['imports']),1)
        package=self.c.library/self.c.catalog()['games'][0]['packages'][0]['path']
        data=package.read_bytes();payload=json.loads(data[40+struct.unpack_from('<I',data,8)[0]:])
        self.assertEqual(payload['args'][payload['args'].index('--keys')+1],str(self.c.keys))
        self.assertEqual(dedicated.read_text(),'invalid dedicated converter key')
        self.assert_isolated()

    def test_failed_conversion_does_not_register_partial_mixed_import_or_leave_temporary_output(self):
        source=self.root/'base.nsz';source.write_text('synthetic compressed package')
        self.behavior('exit_zero_error')
        with self.import_fixture([self.source,source]) as inspect:
            with self.assertRaises(Failure): self.quiet(library.import_games,self.c)
            inspect.assert_not_called()
        self.assertEqual(self.c.catalog()['games'],[])
        self.assertEqual(list((self.c.private/'converter/import').iterdir()),[])
        self.assert_isolated()

    def test_cancelled_conversion_cleans_import_staging_and_does_not_register_content(self):
        source=self.root/'base.xcz';source.write_text('synthetic compressed cartridge')
        with self.import_fixture([source]) as inspect,patch.object(self.c,'run',side_effect=Cancelled):
            with self.assertRaises(Cancelled): self.quiet(library.import_games,self.c)
            inspect.assert_not_called()
        self.assertEqual(self.c.catalog()['games'],[])
        self.assertEqual(list((self.c.private/'converter/import').iterdir()),[])
        self.assert_isolated()

    def test_import_waits_for_existing_build_and_waiting_can_be_cancelled(self):
        source=self.root/'base.nsz';source.write_text('synthetic compressed package')
        with self.import_fixture([source]):
            owner=Context(self.c.r|{'taskId':'lock-owner'})
            locked=threading.Event();release=threading.Event()
            def hold():
                with owner.toolchain_lock():
                    locked.set();release.wait(5)
            thread=threading.Thread(target=hold);thread.start();self.assertTrue(locked.wait(2))
            timer=threading.Timer(.4,release.set);timer.start()
            try: result=self.quiet(library.import_games,self.c)
            finally: release.set();thread.join();timer.cancel()
            self.assertEqual(len(result['imports']),1)
            events=[json.loads(line) for line in self.events.getvalue().splitlines()]
            self.assertTrue(any(event.get('stage')=='等待游戏或工具链任务结束' for event in events))
            begin=self.c.begin
            def cancel_wait(stage,*args):
                begin(stage,*args)
                if stage=='等待游戏或工具链任务结束': self.c.cancelled=True
            with owner.toolchain_lock(),patch.object(self.c,'begin',side_effect=cancel_wait):
                with self.assertRaises(Cancelled): self.quiet(library.import_games,self.c)
        self.assertEqual(list((self.c.private/'converter/import').iterdir()),[])

    def test_real_child_converts_private_copies_and_preserves_previous_output(self):
        old=self.root/'output/old.nsp';old.parent.mkdir();old.write_text('previous result')
        result=self.run_conversion();self.assertEqual(old.read_text(),'previous result')
        path=Path(result['outputFiles'][0]);conversion.validate_output(path)
        self.assertTrue(path.is_relative_to(self.root/'output'))
        self.assertEqual(self.c.job['outputPath'],result['outputPath'])
        self.assertEqual(self.c.job['conversion'],self.c.r['conversion'])
        self.assertNotIn(str(self.source).encode(),path.read_bytes())
        events=[json.loads(line) for line in self.events.getvalue().splitlines()]
        self.assertTrue(any(event.get('unit')=='%' and event.get('done')==25 for event in events))
        self.assert_isolated()

    def test_compress_decompress_convert_xci_and_merge_protocols(self):
        for mode,target,source_ext,expected in [('compress','nsp','nsp','nsz'),('decompress','nsp','xcz','xci'),('convert','xci','NSZ','xci'),('merge','nsp','nsp','nsp'),('merge','xci','nsp','xci')]:
            with self.subTest(mode=mode,target=target):
                source=self.root/('input.'+source_ext);source.write_text('synthetic archive')
                paths=[str(source)]
                if mode=='merge':
                    extra=self.root/'update.nsp';extra.write_text('synthetic update');paths.append(str(extra))
                self.c.r['conversion'].update(mode=mode,target=target,paths=paths)
                result=self.run_conversion()
                self.assertEqual(Path(result['outputFiles'][0]).suffix,'.'+expected)
                conversion.validate_output(Path(result['outputFiles'][0]))
                self.assert_isolated()

    def test_success_exit_with_errors_empty_invalid_or_linked_output_never_publishes(self):
        old=self.root/'output/existing';old.mkdir(parents=True);(old/'keep').write_text('keep')
        for mode in ('exit_zero_error','empty','invalid','symlink','nonzero'):
            with self.subTest(behavior=mode):
                self.behavior(mode)
                with self.assertRaises(Failure):self.run_conversion()
                self.assertEqual(list((self.root/'output').iterdir()),[old]);self.assert_isolated()

    def test_duplicate_output_names_never_replace_another_result(self):
        paths=[]
        for index,name in enumerate(['same.nsp','2-same.nsp','same.nsp']):
            path=self.root/str(index)/name;path.parent.mkdir();path.write_text('original fixture '+str(index));paths.append(str(path))
        self.c.r['conversion']['paths']=paths
        result=self.run_conversion();outputs=[Path(path) for path in result['outputFiles']]
        self.assertEqual(len({path.name for path in outputs}),3)
        self.assertEqual(len({path.read_bytes() for path in outputs}),3)
        self.assert_isolated()

    def test_cancellation_removes_temporary_outputs_and_key_snapshot(self):
        emit=self.c.emit
        def cancel_after_progress(*args,**kwargs):
            emit(*args,**kwargs)
            if kwargs.get('unit')=='%' and kwargs.get('done')==25:self.c.cancelled=True
        self.c.emit=cancel_after_progress
        with self.assertRaises(Cancelled):self.run_conversion()
        self.assertEqual(list((self.root/'output').iterdir()),[]);self.assert_isolated()

    def test_invalid_options_and_protected_paths_fail_before_backend_runs(self):
        options=self.c.r['conversion'];original=options.copy()
        for change in ({'mode':'delete'},{'level':True},{'paths':[]},{'mode':'merge'},{'outputDirectory':str(self.c.keys.parent)}, {'outputDirectory':str(self.c.library)}, {'outputDirectory':str(self.backend)}):
            self.c.r['conversion']=original|change
            with patch.object(self.c,'run') as run,self.assertRaises(Failure):self.run_conversion()
            run.assert_not_called()
        self.c.r['conversion']=original
        link=self.root/'link.nsp';link.symlink_to(self.source);self.c.r['conversion']['paths']=[str(link)]
        with self.assertRaises(Failure):self.run_conversion()

    def test_low_disk_space_and_external_backend_links_fail_without_changing_data(self):
        with patch('conversion.shutil.disk_usage',return_value=SimpleNamespace(free=0)),self.assertRaises(Failure):self.run_conversion()
        (self.ztools/'outside.py').symlink_to(self.source)
        with self.assertRaises(Failure):self.run_conversion()
        self.assert_isolated()

    def test_conversion_keys_are_private_and_do_not_replace_library_or_backend_keys(self):
        new=self.root/'new.keys';new.write_text('header_key = '+'cd'*32+'\n')
        self.c.r['path']=str(new)
        status=self.quiet(conversion.import_keys,self.c)
        self.assertTrue(status['keysReady']);self.assertEqual(status['keySource'],'使用转换专用密钥')
        self.assertEqual(self.c.keys.read_text(),'header_key = '+'ab'*32+'\n')
        self.assertEqual(conversion.key_path(self.c).stat().st_mode&0o777,0o600)
        new.write_text('bad')
        with self.assertRaises(Failure):self.quiet(conversion.import_keys,self.c)
        self.assertTrue(conversion.status(self.c)['keysReady'])

    def test_machine_and_tqdm_progress_reject_unknown_or_nonfinite_totals(self):
        events=[];self.c.emit=lambda *args,**kwargs:events.append(kwargs)
        parser=conversion.Progress(self.c)
        for line in ('{"type":"progress","percent":"25","file":"a","step":"b"}', ' 75%|done', '{"type":"progress","percent":"NaN"}', '{"type":"progress","percent":150}'):
            parser(line)
        self.assertEqual([e['done'] for e in events if 'done' in e],[25,75])
        parser('{"type":"error","message":"failed"}');self.assertTrue(parser.error)

    def test_container_file_table_bounds_and_overlaps_are_rejected(self):
        for body in (b'PFS0'+struct.pack('<III',1,5,0),b'PFS0'+struct.pack('<III',9999999,1,0)+b'x'):
            path=self.root/'bad.nsp';path.write_bytes(body)
            with self.assertRaises(Failure):conversion.validate_output(path)
        names=b'a\0b\0'
        for ext,entry_size in [('nsp',24),('xci',64)]:
            entries=b''.join(struct.pack('<QQII',offset,8,index*2,0)+b'\0'*(entry_size-24) for index,offset in enumerate([0,4]))
            table=(b'PFS0' if ext=='nsp' else b'HFS0')+struct.pack('<III',2,len(names),0)+entries+names+b'original payload'
            if ext=='xci':
                header=bytearray(0x200);header[0x100:0x104]=b'HEAD';struct.pack_into('<Q',header,0x130,0x200);table=bytes(header)+table
            path=self.root/('overlap.'+ext);path.write_bytes(table)
            with self.assertRaises(Failure):conversion.validate_output(path)

    def test_invalid_backend_keys_are_classified_and_kek_values_redacted(self):
        import diagnostics
        diagnostic=diagnostics.failure(self.c,'Error: CRC32 mismatch\naes_kek_generation_source = 00112233445566778899aabbccddeeff',status=1)
        self.assertEqual(diagnostic['code'],'conversion_keys_invalid')
        self.assertNotIn('00112233445566778899aabbccddeeff',diagnostic['detail'])

    def test_export_copy_failure_keeps_previous_outputs_and_removes_staging(self):
        old=self.root/'output/existing.nsp';old.parent.mkdir();old.write_text('previous result')
        real_clone=conversion.clone
        def fail_on_export(source,destination,progress=None):
            if Path(destination).parent.name=='result':raise OSError('No space left on device')
            return real_clone(source,destination,progress)
        with patch('conversion.clone',side_effect=fail_on_export),self.assertRaises(OSError):self.run_conversion()
        self.assertEqual(list(old.parent.iterdir()),[old]);self.assertEqual(old.read_text(),'previous result');self.assert_isolated()

    def test_worker_sigterm_is_cancelled_and_does_not_leave_outputs_or_key_snapshots(self):
        self.behavior('slow')
        request=self.root/'cancel-request.json'
        request.write_text(json.dumps(self.c.r|{'schema':1,'taskId':'signal-cancel'}));request.chmod(0o600)
        worker=Path(__file__).resolve().parents[1]/'Worker/main.py'
        process=subprocess.Popen([sys.executable,'-B','-I',str(worker),'--request',str(request)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        try:
            received=False;deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                line=process.stdout.readline()
                if not line:break
                event=json.loads(line)
                if event.get('unit')=='%' and event.get('done')==25:received=True;break
            self.assertTrue(received)
            process.terminate();output,_=process.communicate(timeout=10)
            self.assertEqual(process.returncode,130,output)
            record=json.loads((self.c.private/'jobs/signal-cancel.json').read_text())
            self.assertEqual(record['state'],'cancelled')
            self.assertFalse(record.get('diagnostics'))
            self.assertEqual(list((self.root/'output').iterdir()),[]);self.assert_isolated()
        finally:
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()

    def test_duplicate_group_signal_permission_error_reaps_or_signals_the_owned_child(self):
        from core import signal_process
        process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
        try:
            with patch('core.os.killpg',side_effect=PermissionError('already exiting group')):
                signal_process(process,signal.SIGTERM);process.wait(timeout=3)
                signal_process(process,signal.SIGTERM)
        finally:
            if process.poll() is None:process.kill();process.wait()


if __name__=='__main__':unittest.main()
