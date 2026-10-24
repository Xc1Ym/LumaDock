"""Local file conversion, adapted from SAK-Mac's AppModel.swift (MIT).

Copyright (c) 2026 ggaoph-lab. Upstream c8e0baa59a168d9efaa0b556af70e0a08bda51de.
See docs/licenses/SAK-Mac-LICENSE.txt. Pinned backends and dependencies are bundled in Runtime/converter.
"""
from __future__ import annotations
import fcntl, json, math, os, re, shutil, struct, tempfile, uuid
from pathlib import Path
from core import Failure, atomic, clone, digest, validate_keys
import diagnostics

FORMATS = {'nsp', 'xci', 'nsz', 'xcz'}
MODES = {'convert', 'compress', 'decompress', 'merge'}


def fail(c, code, message, suggestion):
    raise Failure(message, diagnostics.make(c, code, message, suggestion, log=c.last_log))


def backend_root(c):
    return c.runtime/'converter'


def key_path(c):
    own = c.private/'converter/keys/prod.keys'
    return own if own.is_file() else c.keys


def status(c):
    root = backend_root(c)
    python = c.runtime/'python/bin/python3'
    nscb = root/'NSC_BUILDER/ztools/squirrel.py'
    runtime = python.is_file() and os.access(python, os.X_OK)
    keys = key_path(c)
    try: validate_keys(keys); keys_ready = True
    except (Failure, OSError, UnicodeError): keys_ready = False
    return {'path': str(root), 'conversionReady': runtime and nscb.is_file(),
            'compressionReady': runtime and (root/'nsz.py').is_file(),
            'keysReady': keys_ready, 'keySource': '使用转换专用密钥' if keys != c.keys else '使用游戏库密钥'}


def import_keys(c):
    c.begin('导入转换密钥', 1, 1)
    source = Path(c.r['path']).expanduser()
    validate_keys(source)
    destination = c.private/'converter/keys/prod.keys'
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_name(uuid.uuid4().hex+'.partial')
    try:
        with temporary.open('xb') as output:
            os.chmod(temporary, 0o600)
            output.write(source.read_bytes())
        c.check(); os.replace(temporary, destination)
    finally: temporary.unlink(missing_ok=True)
    return status(c)


def options(c):
    value = c.r.get('conversion')
    if not isinstance(value, dict): raise Failure('转换参数无效。')
    mode, target = value.get('mode'), value.get('target')
    if mode not in MODES or target not in {'nsp','xci'}: raise Failure('转换参数无效。')
    level = value.get('level', 18)
    if type(level) is not int or not 1 <= level <= 22 or type(value.get('verify', True)) is not bool:
        raise Failure('转换参数无效。')
    paths = value.get('paths')
    if not isinstance(paths, list) or not 1 <= len(paths) <= 256 or any(not isinstance(p,str) for p in paths):
        raise Failure('请选择要转换的文件。')
    allowed = {'nsp','xci'} if mode == 'compress' else {'nsz','xcz'} if mode == 'decompress' else FORMATS
    files = []
    for raw in paths:
        path = Path(raw).expanduser()
        if '\n' in str(path) or '\r' in str(path) or path.is_symlink(): raise Failure('转换输入不能使用符号链接或包含换行的路径。')
        path = path.resolve()
        if not path.is_file() or path.suffix.lower()[1:] not in allowed: raise Failure('所选文件格式与转换操作不匹配。')
        if path.stat().st_size == 0: raise Failure('输入文件为空。')
        if path not in files: files.append(path)
    if mode == 'merge' and len(files) < 2: raise Failure('合并至少需要两个文件。')
    raw_output = value.get('outputDirectory')
    if not isinstance(raw_output, str) or not raw_output.strip(): raise Failure('请选择输出文件夹。')
    output = Path(raw_output).expanduser().resolve()
    protected = [c.private, c.library, c.engine, backend_root(c)]
    if any(root and (output == root.resolve() or output.is_relative_to(root.resolve())) for root in protected):
        raise Failure('输出位置必须位于游戏库、私有数据、引擎和转换后端目录之外。')
    if output.exists() and not output.is_dir(): raise Failure('输出位置不是文件夹。')
    return value, files, output


class Progress:
    """SAK-Mac's machine-readable/tqdm progress and exit-zero error detection."""
    def __init__(self, c): self.c=c; self.error=False; self.identity=None
    def __call__(self, line):
        text = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        try: event = json.loads(text)
        except (ValueError, TypeError): event = {}
        if isinstance(event, dict):
            kind = event.get('type')
            if kind == 'error': self.error=True
            if kind == 'progress':
                identity = (event.get('file'), event.get('step'))
                if identity != self.identity:
                    self.c.emit('message', resetProgress=True); self.identity=identity
                try: percent = float(event.get('percent'))
                except (ValueError, TypeError): return
                if math.isfinite(percent) and 0 <= percent <= 100: self.c.emit(done=percent,total=100,unit='%')
                return
        match = re.search(r'(\d{1,3}(?:\.\d+)?)%\|', text)
        if match and 0 <= float(match[1]) <= 100:
            self.c.emit(done=float(match[1]),total=100,unit='%')
        lower = text.lower()
        if any(s in lower for s in ('traceback','exception','missing from keys','filename: unknown')) or lower.startswith(('error:', 'error ', 'failed:')):
            self.error=True


def snapshot(c, root, destination):
    source = root/'NSC_BUILDER'
    if source.is_symlink(): raise Failure('转换后端源码目录不能使用符号链接。')
    excluded = {'keys.txt','prod.keys','title.keys','DB','__pycache__','bin','web','.git'}
    files=[]
    for folder, dirs, names in os.walk(source):
        c.check()
        dirs[:] = [d for d in dirs if d not in excluded]
        for name in dirs+names:
            if (Path(folder)/name).is_symlink(): raise Failure('转换后端包含目录外链接，请重新安装后端。')
        for name in names:
            path=Path(folder)/name
            if name not in excluded and not ('key' in name.lower() and path.suffix.lower()!='.py') and path.suffix.lower() not in {'.pyc','.exe','.bat','.nsp','.xci','.nsz','.xcz','.keys'}:
                files.append((path,path.stat().st_size,path.stat().st_mtime_ns))
    total=sum(size for _,size,_ in files)
    if total > 256*2**20: raise Failure('转换后端目录过大，请选择 SAK-Mac 安装的后端目录。')
    done=0
    for source,size,mtime in files:
        c.check(); target=destination/source.relative_to(root/'NSC_BUILDER')
        clone(source,target,lambda n,t:c.progress(done+n,total));done+=size
        if source.stat().st_size != size or source.stat().st_mtime_ns != mtime: raise Failure('转换后端在复制时发生变化，请重试。')
    keys=destination/'ztools/keys.txt';keys.parent.mkdir(parents=True,exist_ok=True)
    keys.write_bytes(key_path(c).read_bytes());os.chmod(keys,0o600)
    return destination/'ztools'


def validate_output(path):
    """Container structure only; not a claim of game/device compatibility."""
    size=path.stat().st_size
    with path.open('rb') as stream:
        header=stream.read(16)
        if path.suffix.lower() in ('.nsp','.nsz'):
            if len(header)!=16 or header[:4]!=b'PFS0': raise Failure('转换产物不是有效的 PFS0 容器。')
            count,strings=struct.unpack_from('<II',header,4)
            data_start=16+count*24+strings
            if not 0<count<=100000 or strings>16*2**20 or data_start>=size: raise Failure('转换产物的文件表无效。')
            entries=stream.read(count*24);names=stream.read(strings);ranges=[]
            for i in range(count):
                offset,length,name_offset=struct.unpack_from('<QQI',entries,i*24)
                if name_offset>=strings or b'\0' not in names[name_offset:] or offset+length>size-data_start:
                    raise Failure('转换产物的文件表无效。')
                ranges.append((offset,offset+length))
            ranges.sort()
            if any(a[1]>b[0] for a,b in zip(ranges,ranges[1:])): raise Failure('转换产物的文件表无效。')
        else:
            stream.seek(0x100)
            if size<0x200 or stream.read(4)!=b'HEAD': raise Failure('转换产物不是有效的 XCI 容器。')
            stream.seek(0x130);root=struct.unpack('<Q',stream.read(8))[0]
            if not 0x200<=root<=size-16: raise Failure('转换产物不是有效的 XCI 容器。')
            stream.seek(root);table=stream.read(16)
            count,strings=struct.unpack_from('<II',table,4)
            if table[:4]!=b'HFS0' or not 0<count<=100000 or strings>16*2**20 or root+16+count*64+strings>=size:
                raise Failure('转换产物的文件表无效。')
            data_start=root+16+count*64+strings
            entries=stream.read(count*64);names=stream.read(strings);ranges=[]
            for index in range(count):
                offset,length=struct.unpack_from('<QQ',entries,index*64)
                name_offset=struct.unpack_from('<I',entries,index*64+16)[0]
                if name_offset>=strings or b'\0' not in names[name_offset:] or offset+length>size-data_start: raise Failure('转换产物的文件表无效。')
                ranges.append((offset,offset+length))
            ranges.sort()
            if any(a[1]>b[0] for a,b in zip(ranges,ranges[1:])): raise Failure('转换产物的文件表无效。')


def convert(c):
    value, inputs, output=options(c)
    info=status(c);mode=value['mode'];target=value['target']
    needed='compressionReady' if mode in ('compress','decompress') else 'conversionReady'
    if not info[needed]: fail(c,'conversion_backend_missing','转换后端不可用。','重新安装完整的 LumaDock 应用，内置转换组件缺失或损坏。')
    if not info['keysReady']: fail(c,'conversion_keys_missing','转换密钥不可用。','导入自己的有效 prod.keys；转换密钥独立保存，不会覆盖已有游戏库密钥。')
    root=backend_root(c);python=c.runtime/'python/bin/python3'
    output.mkdir(parents=True,exist_ok=True)
    reserve=sum(p.stat().st_size for p in inputs)*2+512*2**20
    if shutil.disk_usage(output).free<reserve: raise Failure('输出磁盘空间不足，转换尚未开始。')
    work_root=c.private/'converter/work';work_root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if shutil.disk_usage(work_root).free<reserve: raise Failure('临时文件磁盘空间不足，转换尚未开始。')
    with (c.private/'.conversion.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Failure('另一个转换任务正在运行，请稍后重试。')
        with tempfile.TemporaryDirectory(prefix='job-',dir=work_root) as private_work:
            work=Path(private_work);os.chmod(work,0o700)
            count=(len(inputs) if mode!='merge' else 1)+4
            c.begin('准备转换工作区',1,count)
            ztools=snapshot(c,root,work/'NSC_BUILDER') if mode in ('convert','merge') else None
            env=c.env();env.update(HOME=str(work),TMPDIR=str(work),PYTHONUNBUFFERED='1',PYTHONIOENCODING='utf-8')
            c.begin('复制并校验转换输入',2,count)
            copies=[]
            for index,path in enumerate(inputs):
                copied=work/'inputs'/str(index)/(path.stem+path.suffix.lower())
                c.emit('message',path.name,resetProgress=True);clone(path,copied,c.progress)
                c.emit('message',resetProgress=True);source_hash=digest(path,c.progress)
                c.emit('message',resetProgress=True)
                if source_hash!=digest(copied,c.progress): raise Failure('输入文件在复制时发生变化，请重试。')
                copies.append(copied)
            produced=[];items=[copies] if mode=='merge' else [[p] for p in copies]
            for index,files in enumerate(items,1):
                c.begin('合并文件' if mode=='merge' else '转换文件',index+2,count)
                c.emit('message',Path(files[0]).name)
                folder=work/f'output-{index}';folder.mkdir()
                if mode in ('compress','decompress'):
                    script="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));p=sys.argv.pop(1);sys.argv[0]=p;runpy.run_path(p,run_name='__main__')"
                    args=['-c',script,str(root/'python'),str(root/'nsz.py'),'--machine-readable','-C' if mode=='compress' else '-D']
                    if mode=='compress':
                        args+=['-l',str(value.get('level',18))]
                        if value.get('verify',True): args+=['-V']
                    args+=['--keys',str(key_path(c)),'-o',str(folder),str(files[0])]
                    expected={'.nsz' if files[0].suffix.lower()=='.nsp' else '.xcz'} if mode=='compress' else {'.nsp' if files[0].suffix.lower()=='.nsz' else '.xci'}
                else:
                    # Command composition is adapted from SAK-Mac AppModel.startConvert/startMerge.
                    script="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));p=sys.argv.pop(1);sys.path.insert(0,p);sys.argv[0]=p+'/squirrel.py';runpy.run_path(sys.argv[0],run_name='__main__')"
                    args=['-c',script,str(root/'python'),str(ztools),'-o',str(folder),'-t','cnsp' if mode=='merge' and target=='nsp' else target]
                    if mode=='merge':
                        listing=work/'inputs.txt';listing.write_text('\n'.join(map(str,files))+'\n')
                        args+=['-tfile',str(listing),'-dmul','calculate']
                    else: args+=['-dc',str(files[0])]
                    expected={'.'+target}
                progress=Progress(c)
                c.run([python,'-I','-B',*args],cwd=ztools or work,env=env,on_line=progress)
                if progress.error: fail(c,'conversion_backend_failed','转换工具报告错误，产物未导出。','检查自己的密钥、输入文件和转换后端依赖；查看任务日志后重试。')
                candidates=[]
                for path in folder.rglob('*'):
                    c.check()
                    if path.is_symlink(): raise Failure('转换工具生成了符号链接，产物未导出。')
                    if path.is_file() and path.suffix.lower() in expected:
                        validate_output(path);candidates.append(path)
                if not candidates: fail(c,'conversion_no_output','转换工具没有生成有效产物。','检查自己的密钥与输入格式，查看任务日志中的转换错误后重试。')
                produced.extend(candidates)
            c.begin('校验并导出转换产物',len(items)+3,count)
            final=output/('LumaDock-'+uuid.uuid4().hex[:12])
            # Copy on the destination disk, then rename the whole result directory atomically.
            with tempfile.TemporaryDirectory(prefix='.lumadock-',dir=output) as staged:
                stage=Path(staged)/'result';stage.mkdir();names=set();report=[]
                for path in produced:
                    name=path.name;counter=2
                    while name in names:
                        name=f'{counter}-{path.name}';counter+=1
                    names.add(name)
                    dest=stage/name;clone(path,dest,c.progress)
                    if digest(path,c.progress)!=digest(dest,c.progress): raise Failure('导出校验失败，原文件保持不变。')
                    report.append(name)
                c.check();os.rename(stage,final)
            c.stage='文件转换完成';c.number=count;c.count=count;c.emit('stage',c.stage);c.emit(done=1,total=1)
            paths=[str(final/name) for name in report]
            c.job.update(outputPath=str(final),outputFiles=paths);atomic(c.jobpath,c.job)
            return {'outputPath':str(final),'outputFiles':paths}
