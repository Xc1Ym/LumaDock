"""Recovery uses synthetic saves and runtime files; no engine/game/device acceptance."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Worker'))
from core import Cancelled, Context, Failure, atomic, read
import build
import library
import recovery

TITLE='0100000000010000'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lumanx-recovery-')
        self.root=Path(self.temp.name)
        self.c=Context(dict(operation='backupSave',privateRoot=str(self.root/'private'),
                            library=str(self.root/'中文 游戏库'),gameId=TITLE))
        self.quiet(library.setup,self.c)
        self.c.r['libraryId']=read(self.c.library/'.nsmac-library.json')['id']
        self.c.save_catalog({'games':[{'id':TITLE,'packages':[],'hidden':False}]})
        self.save=self.c.library/'saves'/TITLE;self.save.mkdir()
        (self.save/'slot').write_bytes(b'synthetic save v1')
        (self.save/'empty').mkdir()

    def tearDown(self): self.temp.cleanup()

    def quiet(self,fn,*args,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()): return fn(*args,**kwargs)

    def backup(self): return self.quiet(recovery.backup,self.c)['backup']

    def snapshot_path(self,record): return self.c.library/'backups'/TITLE/record['id']

    def release(self,name,version='1.0'):
        path=self.c.library/'games'/TITLE/'releases'/name;path.mkdir(parents=True)
        (path/'dmhost').write_text('synthetic, never executed')
        (path/'romfs').mkdir();(path/'romfs/resource').write_bytes(b'synthetic romfs')
        (path/'modules').mkdir()
        for suffix in ('patched.bin','fixups.tsv','gates.tsv'): (path/'modules'/('main.'+suffix)).write_text('synthetic')
        (path/'shaders/vk').mkdir(parents=True);(path/'shaders/vk/vk_shaders.metallib').write_bytes(b'synthetic')
        atomic(path/'manifest.json',dict(schema=1,gameId=TITLE,version=version,engine='synthetic-engine',graphics='vulkan',created=1))
        return path

    def test_backup_is_independent_verified_and_keeps_empty_directories(self):
        record=self.backup();path=self.snapshot_path(record)
        self.assertEqual(record['gameId'],TITLE)
        self.assertEqual(record['reason'],'manual')
        self.assertEqual((path/'data/slot').read_bytes(),b'synthetic save v1')
        self.assertTrue((path/'data/empty').is_dir())
        self.assertEqual(path.stat().st_mode & 0o777,0o700)
        (self.save/'slot').write_bytes(b'new save')
        self.assertEqual((path/'data/slot').read_bytes(),b'synthetic save v1')
        report=self.quiet(recovery.list_recovery,self.c)
        self.assertEqual(report['backups'][0]['size'],len(b'synthetic save v1'))

    def test_restore_swaps_complete_directory_and_saves_pre_restore_snapshot(self):
        record=self.backup();(self.save/'slot').write_bytes(b'new save');(self.save/'extra').write_bytes(b'extra')
        self.c.r['backupId']=record['id']
        result=self.quiet(recovery.restore,self.c)
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')
        self.assertFalse((self.save/'extra').exists());self.assertTrue((self.save/'empty').is_dir())
        safety=read(self.c.library/'backups'/TITLE/result['safetyBackupId']/'manifest.json')
        self.assertEqual(safety['reason'],'beforeRestore')
        self.assertEqual((self.snapshot_path(safety)/'data/slot').read_bytes(),b'new save')
        self.assertEqual(list(self.save.parent.glob('.restore-*')),[])

    def test_restore_works_when_save_directory_is_missing(self):
        record=self.backup();import shutil;shutil.rmtree(self.save)
        self.c.r['backupId']=record['id'];result=self.quiet(recovery.restore,self.c)
        self.assertIsNone(result['safetyBackupId'])
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')

    def test_corrupt_or_extra_backup_file_never_replaces_current_save(self):
        for extra in (False,True):
            record=self.backup();path=self.snapshot_path(record)/'data'
            (path/('extra' if extra else 'slot')).write_bytes(b'corrupt')
            self.c.r['backupId']=record['id']
            with self.assertRaises(Failure): self.quiet(recovery.restore,self.c)
            self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')

    def test_restore_rejects_manifest_escape_and_wrong_game(self):
        record=self.backup();path=self.snapshot_path(record)/'manifest.json'
        original=read(path)
        for change in ({'gameId':'0100000000020000'},{'files':{'../../escape':next(iter(original['files'].values()))}},{'directories':['../escape']}):
            atomic(path,original|change);self.c.r['backupId']=record['id']
            with self.assertRaises(Failure): self.quiet(recovery.restore,self.c)
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')

    def test_restore_and_backup_refuse_symlinks(self):
        outside=self.root/'outside';outside.write_text('private')
        (self.save/'link').symlink_to(outside)
        with self.assertRaises(Failure): self.backup()
        (self.save/'link').unlink();record=self.backup()
        slot=self.snapshot_path(record)/'data/slot';slot.unlink();slot.symlink_to(outside)
        self.c.r['backupId']=record['id']
        with self.assertRaises(Failure): self.quiet(recovery.restore,self.c)
        self.assertEqual(outside.read_text(),'private')

    def test_backup_refuses_special_files(self):
        os.mkfifo(self.save/'pipe')
        with self.assertRaises(Failure): self.backup()

    def test_backup_detects_save_changes_during_copy(self):
        original=recovery.clone
        def changed(source,target,progress):
            original(source,target,progress);(self.save/'slot').write_bytes(b'changed during backup')
        with patch('recovery.clone',side_effect=changed):
            with self.assertRaises(Failure): self.backup()
        self.assertEqual(list((self.c.library/'backups'/TITLE).iterdir()),[])

    def test_failed_copy_and_cancel_leave_no_partial_backup(self):
        for error in (OSError('copy failed'),Cancelled()):
            with patch('recovery.clone',side_effect=error):
                with self.assertRaises(type(error)): self.backup()
            self.assertEqual(list((self.c.library/'backups'/TITLE).iterdir()),[])
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')

    def test_low_space_preserves_save(self):
        with patch('recovery.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
            with self.assertRaises(Failure): self.backup()
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')

    def test_restore_commit_failure_preserves_original_and_safety_backup(self):
        record=self.backup();(self.save/'slot').write_bytes(b'current save')
        self.c.r['backupId']=record['id']
        with patch('recovery.exchange',side_effect=Failure('unsupported disk')):
            with self.assertRaises(Failure): self.quiet(recovery.restore,self.c)
        self.assertEqual((self.save/'slot').read_bytes(),b'current save')
        self.assertEqual(len(self.quiet(recovery.list_recovery,self.c)['backups']),2)

    def test_restore_cancelled_before_switch_keeps_original(self):
        record=self.backup();(self.save/'slot').write_bytes(b'current save');self.c.r['backupId']=record['id']
        original=recovery.snapshot
        def cancelled(*args,**kwargs):
            value=original(*args,**kwargs);self.c.cancelled=True;return value
        with patch('recovery.snapshot',side_effect=cancelled):
            with self.assertRaises(Cancelled): self.quiet(recovery.restore,self.c)
        self.assertEqual((self.save/'slot').read_bytes(),b'current save')

    def test_all_mutations_exclude_active_game_or_build(self):
        record=self.backup();self.c.r.update(backupId=record['id'],releaseId='old')
        with self.c.lock('execution'):
            for operation in (recovery.backup,recovery.restore,recovery.activate):
                with self.assertRaises(Failure): self.quiet(operation,self.c)

    def test_missing_library_disk_is_not_recreated(self):
        self.c.r['libraryId']='disconnected'
        with self.assertRaises(Failure): self.backup()
        self.assertFalse((self.c.library/'backups').exists())

    def test_activate_release_keeps_save_and_snapshots_it_before_switch(self):
        old=self.release('old');new=self.release('new','2.0');current=old.parent.parent/'current';current.symlink_to('releases/new')
        self.c.r['releaseId']='old';result=self.quiet(recovery.activate,self.c)
        self.assertEqual(current.resolve(),old)
        self.assertTrue(new.is_dir())
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')
        safety=read(self.c.library/'backups'/TITLE/result['safetyBackupId']/'manifest.json')
        self.assertEqual(safety['reason'],'beforeVersionChange')
        report=self.quiet(recovery.list_recovery,self.c)
        self.assertEqual([r['id'] for r in report['releases'] if r['current']],['old'])

    def test_invalid_runtime_cannot_replace_current_version(self):
        old=self.release('old');bad=self.release('bad');(bad/'shaders/vk/vk_shaders.metallib').unlink()
        current=old.parent.parent/'current';current.symlink_to('releases/old');self.c.r['releaseId']='bad'
        with self.assertRaises(Failure): self.quiet(recovery.activate,self.c)
        self.assertEqual(current.resolve(),old)
        self.assertFalse((self.c.library/'backups').exists())

    def test_runtime_links_and_unknown_release_are_rejected(self):
        old=self.release('old');(old.parent/'linked').symlink_to(old,target_is_directory=True)
        for identifier in ('linked','../old','missing'):
            self.c.r['releaseId']=identifier
            with self.assertRaises(Failure): self.quiet(recovery.activate,self.c)
        (old/'romfs/link').symlink_to(self.root)
        self.c.r['releaseId']='old'
        with self.assertRaises(Failure): self.quiet(recovery.activate,self.c)

    def test_corrupt_records_do_not_hide_valid_backup_or_release(self):
        record=self.backup();old=self.release('old')
        broken=self.snapshot_path(record).parent/('f'*32);broken.mkdir();(broken/'manifest.json').write_text('{bad')
        bad=old.parent/'bad';bad.mkdir();(bad/'manifest.json').write_text('{bad')
        array_backup=broken.parent/('e'*32);array_backup.mkdir();atomic(array_backup/'manifest.json',[])
        array_release=old.parent/'array';array_release.mkdir();atomic(array_release/'manifest.json',[])
        report=self.quiet(recovery.list_recovery,self.c)
        self.assertEqual([b['id'] for b in report['backups']],[record['id']])
        self.assertEqual([r['id'] for r in report['releases']],['old'])

    def test_symlinked_storage_category_is_rejected(self):
        import shutil
        shutil.rmtree(self.save.parent);self.save.parent.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(Failure): self.backup()

    def test_source_and_cache_cleanup_keep_backups(self):
        record=self.backup();path=self.snapshot_path(record)
        self.c.r['kind']='sources';self.quiet(library.clean,self.c)
        cache=self.c.library/'cache'/TITLE;cache.mkdir();(cache/'cached').write_bytes(b'derived data')
        self.c.r['kind']='cache';self.quiet(library.clean,self.c)
        self.assertFalse(cache.exists())
        self.assertEqual((path/'data/slot').read_bytes(),b'synthetic save v1')
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')

    def test_cache_cleanup_cannot_follow_a_link_into_backups(self):
        record=self.backup();path=self.snapshot_path(record)
        (self.c.library/'cache'/TITLE).symlink_to(path,target_is_directory=True)
        self.c.r['kind']='cache'
        with self.assertRaises(Failure): self.quiet(library.clean,self.c)
        self.assertEqual((path/'data/slot').read_bytes(),b'synthetic save v1')

    def test_install_auto_backup_failure_keeps_previous_current(self):
        old=self.release('old');current=old.parent.parent/'current';current.symlink_to('releases/old')
        root=self.root/'build';root.mkdir();repo=root/'engine';(repo/'dm/gfx/nvn').mkdir(parents=True)
        (repo/'dm/gfx/nvn/dmsh_chain.h').write_text('#define DMSH_CHAIN "synthetic"')
        class Profile:
            id=TITLE
            def table(self,name): return repo/'profile'/name
            def get(self,key,default=None): return {'graphics':'vulkan','package':'v0','romfs_marker':'resource'}.get(key,default)
            def words(self,key): return ['main']
            def builds(self): return {'v0':{'display':'1.0'}}
        font=root/'font';font.mkdir();(font/'font').write_text('synthetic')
        with patch('recovery.snapshot',side_effect=Failure('cannot backup')):
            with self.assertRaises(Failure): self.quiet(build.install,self.c,root,repo,Profile(),'new',old/'dmhost',old/'romfs',old/'modules',old/'shaders',None,font)
        self.assertEqual(current.resolve(),old)

    def test_successful_install_backs_up_saves_before_publishing(self):
        old=self.release('old');current=old.parent.parent/'current';current.symlink_to('releases/old')
        root=self.root/'build';root.mkdir();repo=root/'engine';(repo/'dm/gfx/nvn').mkdir(parents=True)
        (repo/'dm/gfx/nvn/dmsh_chain.h').write_text('#define DMSH_CHAIN "synthetic"')
        class Profile:
            id=TITLE
            def table(self,name): return repo/'profile'/name
            def get(self,key,default=None): return {'graphics':'vulkan','package':'v0','romfs_marker':'resource'}.get(key,default)
            def words(self,key): return ['main']
            def builds(self): return {'v0':{'display':'2.0'}}
        font=root/'font';font.mkdir();(font/'font').write_text('synthetic')
        result=self.quiet(build.install,self.c,root,repo,Profile(),'new',old/'dmhost',old/'romfs',old/'modules',old/'shaders',None,font)
        self.assertEqual(current.resolve(),Path(result['path']))
        self.assertTrue(old.exists())
        backups=self.quiet(recovery.list_recovery,self.c)['backups']
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0]['reason'],'beforeVersionChange')
        self.assertEqual((self.save/'slot').read_bytes(),b'synthetic save v1')

    def test_worker_protocol_persists_recovery_identifiers_and_library(self):
        import json,subprocess
        record=self.backup();self.c.r.update(operation='restoreSave',backupId=record['id'],taskId='protocol',schema=1)
        request=self.root/'request.json';atomic(request,self.c.r)
        worker=Path(__file__).resolve().parents[1]/'Worker/main.py'
        result=subprocess.run([sys.executable,'-I','-B',str(worker),'--request',str(request)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[-1]['state'],'completed')
        job=read(self.c.private/'jobs/protocol.json')
        self.assertEqual(job['backupId'],record['id'])
        self.assertEqual(job['libraryId'],self.c.r['libraryId'])


if __name__=='__main__': unittest.main()
