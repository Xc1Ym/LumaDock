"""Measured byte/file progress, cancellation and heartbeats for Python-only tasks."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Worker'))
from core import Context, Cancelled, atomic, clone, clone_tree
import library


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lumadock-progress-');self.root=Path(self.temp.name).resolve()
        self.request=dict(schema=1,operation='diagnostics',privateRoot=str(self.root/'private'),library=str(self.root/'library'))
        self.c=Context(self.request);self.c.library.mkdir()
    def tearDown(self):self.temp.cleanup()
    def capture(self,fn,*args):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):result=fn(*args)
        return result,[json.loads(line) for line in output.getvalue().splitlines()]

    def test_cross_volume_copy_emits_real_chunk_bytes_and_can_be_cancelled(self):
        source=self.root/'source';source.write_bytes(b'x'*(17 << 20));target=self.root/'target'
        values=[]
        with patch('core.ctypes.CDLL') as libc:
            libc.return_value.clonefile.return_value=-1
            clone(source,target,lambda done,total:values.append((done,total)))
        self.assertGreater(len(values),1);self.assertEqual(values[-1],(source.stat().st_size,source.stat().st_size))
        self.assertEqual(target.read_bytes(),source.read_bytes())
        def cancel(done,total):raise Cancelled()
        with patch('core.ctypes.CDLL') as libc:
            libc.return_value.clonefile.return_value=-1
            with self.assertRaises(Cancelled):clone(source,self.root/'cancelled',cancel)

    def test_tree_progress_uses_combined_file_sizes(self):
        source=self.root/'tree';source.mkdir();(source/'a').write_bytes(b'a'*3);(source/'b').write_bytes(b'b'*7)
        values=[];clone_tree(source,self.root/'copy',lambda done,total:values.append((done,total)))
        self.assertEqual(values[-1],(10,10))
        measured=[done for done,total in values if total]
        self.assertEqual(measured,sorted(measured))

    def test_diagnostics_export_has_file_progress_and_preserves_old_zip_on_cancel(self):
        logs=self.c.private/'logs';logs.mkdir();(logs/'a.log').write_text('one');(logs/'b.log').write_text('two')
        external=self.root/'external.log';external.write_text('do-not-export');(logs/'outside.log').symlink_to(external)
        output=self.root/'diagnostics.zip';self.c.r['path']=str(output)
        _,events=self.capture(library.diagnostics,self.c)
        progress=[e for e in events if e.get('unit')=='files']
        self.assertEqual(progress[-1]['done'],2);self.assertEqual(progress[-1]['total'],2)
        previous=output.read_bytes()
        with zipfile.ZipFile(output) as archive:self.assertNotIn(b'do-not-export',b''.join(archive.read(n) for n in archive.namelist()))
        emit=self.c.emit
        def cancel(kind='progress',*args,**kwargs):
            emit(kind,*args,**kwargs)
            if kwargs.get('unit')=='files':self.c.cancelled=True
        with patch.object(self.c,'emit',side_effect=cancel):
            with self.assertRaises(Cancelled):self.capture(library.diagnostics,self.c)
        self.assertEqual(output.read_bytes(),previous);self.assertFalse(list(self.root.glob('*.partial')))

    def test_cleanup_reports_counts_without_deleting_saves_or_runtime(self):
        self.c.save_catalog({'games':[{'id':'g','packages':[]}]});self.c.r.update(gameId='g',kind='cache')
        cache=self.c.library/'cache/g/nested';cache.mkdir(parents=True);(cache/'a').write_text('cache')
        save=self.c.library/'saves/g/slot';save.parent.mkdir(parents=True);save.write_text('save')
        _,events=self.capture(library.clean,self.c)
        self.assertFalse(cache.parent.exists());self.assertEqual(save.read_text(),'save')
        progress=[e for e in events if e.get('unit')=='files']
        self.assertEqual(progress[-1]['done'],progress[-1]['total'])

    def test_apple_download_percent_is_taken_from_tool_output(self):
        self.c.r['operation']='installMetal'
        script=self.root/'download.py';script.write_text("print('Downloading Metal Toolchain: 25.0%')\nprint('Downloading Metal Toolchain: 100%')\n")
        _,events=self.capture(self.c.run,[sys.executable,script])
        progress=[e for e in events if e.get('unit')=='%']
        self.assertEqual(progress[0]['done'],25);self.assertEqual(progress[-1]['done'],100)
        self.assertTrue(all(e['total']==100 for e in progress))

    def test_python_only_operations_emit_heartbeats_without_subprocesses(self):
        request=self.root/'request.json';atomic(request,self.request|{'operation':'setup'})
        wrapper=self.root/'worker.py'
        wrapper.write_text(f"import sys,time\nsys.path.insert(0,{str(ROOT/'Worker')!r})\nimport main as worker\nworker.library.setup=lambda c:time.sleep(2.2) or {{}}\nraise SystemExit(worker.main())\n")
        result=subprocess.run([sys.executable,'-B',str(wrapper),'--request',str(request)],capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(any(e['type']=='heartbeat' for e in events));self.assertEqual(events[-1]['state'],'completed')


if __name__=='__main__':unittest.main()
