"""Managed save snapshots and validated runtime switching, serialized with gameplay."""
from __future__ import annotations
import ctypes
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
import uuid

from core import Failure, atomic, clone, contained, digest, read


def game_root(c, category, game_id):
    # IDs originate in the catalogue; reject damaged records before constructing paths.
    if not re.fullmatch(r'[0-9A-F]{16}',game_id): raise Failure('无效的游戏标识。')
    base=c.library/category
    if base.is_symlink(): raise Failure('恢复目录包含符号链接，操作已停止。')
    path=base/game_id
    if path.is_symlink(): raise Failure('恢复目录包含符号链接，操作已停止。')
    contained(c.library,path)
    return path


def inventory(c, root):
    if root.is_symlink() or not root.is_dir(): raise Failure('存档或运行目录不可用。')
    files={}; directories=[]
    for folder, dirs, names in os.walk(root,followlinks=False):
        c.check()
        for name in sorted(dirs+names):
            path=Path(folder)/name; mode=path.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise Failure('恢复目录包含符号链接或特殊文件，操作已停止。')
            relative=path.relative_to(root).as_posix()
            if stat.S_ISDIR(mode): directories.append(relative)
            else: files[relative]={'size':path.stat().st_size,'sha256':digest(path,c.progress)}
    return {'files':files,'directories':sorted(directories)}


def copy_verified(c, source, target, expected):
    target.mkdir(mode=0o700)
    for name in expected['directories']: (target/name).mkdir(parents=True,exist_ok=True,mode=0o700)
    for name in expected['files']:
        c.check(); destination=target/name
        clone(source/name,destination,c.progress)
        with destination.open('rb') as stream: os.fsync(stream.fileno())
    if inventory(c,target)!=expected: raise Failure('存档校验失败，当前存档未改动。')


def space(c, path, snapshot):
    needed=sum(item['size'] for item in snapshot['files'].values())+64*2**20
    if shutil.disk_usage(path).free<needed: raise Failure('存档备份或恢复所需空间不足，当前存档未改动。')


def snapshot(c, game_id, reason='manual', optional=False):
    source=game_root(c,'saves',game_id)
    if not source.exists():
        if optional: return None
        raise Failure('尚无可备份的存档。')
    c.begin('备份并校验存档',1,1)
    expected=inventory(c,source)
    root=game_root(c,'backups',game_id);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    space(c,root,expected)
    identifier=uuid.uuid4().hex
    manifest={'schema':1,'id':identifier,'gameId':game_id,'created':time.time(),'reason':reason,**expected}
    with tempfile.TemporaryDirectory(prefix='.backup-',dir=root) as temporary:
        stage=Path(temporary)/'snapshot';stage.mkdir(mode=0o700)
        copy_verified(c,source,stage/'data',expected)
        # Refuse an inconsistent snapshot if another program edited the source mid-copy.
        if inventory(c,source)!=expected: raise Failure('备份期间存档发生变化，请退出游戏后重试。')
        atomic(stage/'manifest.json',manifest)
        c.check();os.rename(stage,root/identifier)
    return manifest


def backup(c):
    with c.lock('execution'):
        return {'backup':snapshot(c,c.game()['id'])}


def backup_manifest(path, game_id):
    try:
        if path.is_symlink() or (path/'manifest.json').is_symlink(): raise ValueError()
        m=read(path/'manifest.json',{})
        if not isinstance(m,dict): raise ValueError()
        if m.get('schema')!=1 or m.get('id')!=path.name or m.get('gameId')!=game_id: raise ValueError()
        if type(m.get('created')) not in (int,float) or not math.isfinite(m['created']) or not isinstance(m.get('reason'),str): raise ValueError()
        files=m['files'];directories=m['directories']
        if not isinstance(files,dict) or not isinstance(directories,list): raise ValueError()
        for name in [*files,*directories]:
            p=PurePosixPath(name)
            if not name or p.is_absolute() or '..' in p.parts or p.as_posix()!=name or name=='.': raise ValueError()
        for item in files.values():
            if type(item['size']) is not int or item['size']<0 or not re.fullmatch('[0-9a-f]{64}',item['sha256']): raise ValueError()
        return m
    except (OSError,ValueError,TypeError,KeyError):
        raise Failure('存档备份记录无效，当前存档未改动。')


def exchange(left, right):
    # Both directories stay on the library volume. No moment with missing saves,
    # including if the launcher or worker exits while committing the restore.
    libc=ctypes.CDLL(None,use_errno=True)
    if sys.platform=='darwin':
        fn=libc.renamex_np;fn.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint]
        result=fn(os.fsencode(left),os.fsencode(right),2) # RENAME_SWAP
    elif hasattr(libc,'renameat2'):
        fn=libc.renameat2;fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        result=fn(-100,os.fsencode(left),-100,os.fsencode(right),2)
    else: raise Failure('磁盘不支持原子存档恢复，当前存档未改动。')
    if result: raise Failure('磁盘不支持原子存档恢复，当前存档未改动。')


def restore(c):
    with c.lock('execution'):
        game_id=c.game()['id'];identifier=c.r.get('backupId','')
        if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):
            raise Failure('存档备份记录无效，当前存档未改动。')
        source=game_root(c,'backups',game_id)/identifier
        manifest=backup_manifest(source,game_id)
        expected={k:manifest[k] for k in ('files','directories')}
        c.begin('校验待恢复存档',1,3)
        if inventory(c,source/'data')!=expected: raise Failure('存档校验失败，当前存档未改动。')
        save=game_root(c,'saves',game_id);save.parent.mkdir(parents=True,exist_ok=True)
        space(c,save.parent,expected)
        with tempfile.TemporaryDirectory(prefix='.restore-',dir=save.parent) as temporary:
            stage=Path(temporary)/'data'
            copy_verified(c,source/'data',stage,expected)
            safety=snapshot(c,game_id,'beforeRestore',optional=True)
            c.begin('切换存档',3,3);c.check()
            if save.exists(): exchange(stage,save)
            else: os.replace(stage,save)
        return {'backupId':identifier,'safetyBackupId':safety['id'] if safety else None}


def releases(c, game_id):
    root=game_root(c,'games',game_id);folder=root/'releases'
    if folder.is_symlink(): raise Failure('恢复目录包含符号链接，操作已停止。')
    current=(root/'current').resolve()
    result=[]
    if folder.is_dir():
        for path in folder.iterdir():
            c.check()
            if path.is_symlink() or not path.is_dir() or (path/'manifest.json').is_symlink(): continue
            try: m=read(path/'manifest.json',{})
            except (OSError,ValueError): continue
            if not isinstance(m,dict): continue
            if m.get('gameId')!=game_id or type(m.get('created')) not in (int,float) or not math.isfinite(m['created']): continue
            result.append({'id':path.name,'version':str(m.get('version','')),'engine':str(m.get('engine','')),
                           'created':m['created'],'current':path.resolve()==current})
    return sorted(result,key=lambda r:r['created'],reverse=True)


def list_recovery(c):
    game_id=c.game()['id'];c.begin('读取存档备份与运行版本',1,1)
    root=game_root(c,'backups',game_id);backups=[]
    if root.is_dir():
        for path in root.iterdir():
            c.check()
            if not re.fullmatch('[0-9a-f]{32}',path.name): continue
            try:
                m=backup_manifest(path,game_id)
                backups.append({k:m[k] for k in ('id','created','reason')} | {'size':sum(p['size'] for p in m['files'].values())})
            except Failure: continue
    return {'backups':sorted(backups,key=lambda r:r['created'],reverse=True),'releases':releases(c,game_id)}


def activate(c):
    from build import validate_runtime
    with c.lock('execution'):
        game_id=c.game()['id'];identifier=c.r.get('releaseId','')
        if not isinstance(identifier,str) or identifier not in {r['id'] for r in releases(c,game_id)}:
            raise Failure('运行版本不可用，请刷新列表后重试。')
        root=game_root(c,'games',game_id);target=root/'releases'/identifier
        contained(root/'releases',target)
        c.begin('校验运行版本',1,3)
        inventory(c,target) # Refuse links or special files before validating runtime resources.
        validate_runtime(target)
        safety=snapshot(c,game_id,'beforeVersionChange',optional=True)
        c.begin('切换运行版本',3,3);c.check()
        link=root/('current-'+uuid.uuid4().hex+'.next')
        try:
            link.symlink_to(target.relative_to(root),target_is_directory=True)
            os.replace(link,root/'current')
        finally: link.unlink(missing_ok=True)
        return {'releaseId':identifier,'safetyBackupId':safety['id'] if safety else None}
