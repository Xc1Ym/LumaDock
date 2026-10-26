"""Private local storage and versioned worker protocol. No network or shell execution."""
from __future__ import annotations
import contextlib, ctypes, fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys, threading, time, uuid
from pathlib import Path
SCHEMA = 1
class Failure(Exception):
    def __init__(self,message,diagnostic=None):
        super().__init__(message);self.diagnostic=diagnostic
class Cancelled(Exception): pass

def signal_process(process, sig):
    """Signal our child group; macOS can report EPERM while an exited group is reaped."""
    try: os.killpg(process.pid, sig)
    except ProcessLookupError: pass
    except PermissionError:
        # Popen reaps and rechecks its own child PID before signalling. Do not let
        # a duplicate cleanup signal replace the original cancellation error.
        process.send_signal(sig)

def atomic(path, obj, mode=0o600):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'w') as f: json.dump(obj, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists(): tmp.unlink()

def read(path, default=None):
    try: return json.loads(Path(path).read_text())
    except FileNotFoundError: return default

def chain_of(repo,gp=None):
    """Read the shared chain header, or the selected profile's header on older engines."""
    header=Path(repo)/'dm/gfx/nvn/dmsh_chain.h'
    if not header.exists() and gp is not None: header=gp.table('dmsh_chain.h')
    try: return re.search(r'#define DMSH_CHAIN "(.*?)"', header.read_text())[1]
    except (OSError, TypeError): return None

def digest(path, progress=None):
    h = hashlib.sha256(); n = 0; total = Path(path).stat().st_size
    with open(path, 'rb') as f:
        while b := f.read(8 << 20):
            h.update(b); n += len(b)
            if progress: progress(n, total)
    return h.hexdigest()

def clone(src, dst, progress=None):
    src, dst = Path(src), Path(dst); dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink(): raise Failure('不接受指向游戏库之外的符号链接。')
    total=src.stat().st_size
    if sys.platform == 'darwin' and ctypes.CDLL(None, use_errno=True).clonefile(os.fsencode(src), os.fsencode(dst), 0) == 0:
        if progress: progress(total,total)
        return
    if progress:
        done=0
        with src.open('rb') as source,dst.open('wb') as destination:
            while block:=source.read(8 << 20):
                destination.write(block);done+=len(block);progress(done,total)
    else: shutil.copyfile(src, dst)
    shutil.copymode(src,dst)

def clone_tree(src, dst, tick=None):
    src, dst = Path(src), Path(dst)
    if tick: tick(0,0)
    files = sorted(p for p in src.rglob('*') if p.is_file()); total = sum(p.stat().st_size for p in files); done = 0
    dst.mkdir(parents=True, exist_ok=True)
    for p in files:
        clone(p, dst / p.relative_to(src),(lambda n,t:tick(done+n,total)) if tick else None); done += p.stat().st_size
        if tick: tick(done, total)

def contained(root, child):
    root, child = Path(root).resolve(), Path(child).resolve()
    if root == child or root not in child.parents: raise Failure('操作路径不属于托管游戏库。')
    return child

class Context:
    def __init__(self, request):
        self.r = request; self.task = request.get('taskId', uuid.uuid4().hex); self.stage = ''; self.number = 0; self.count = 0
        self.t0 = time.monotonic(); self.stage_t = self.t0; self.last = 0; self.cancelled = False; self.children = set(); self.guard = threading.RLock()
        self.last_log = None
        self.private = Path(request['privateRoot']).expanduser().resolve(); self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.private, 0o700)
        self.jobpath = self.private / 'jobs' / (self.task + '.json')
        self.job = read(self.jobpath, {}) | {'schema': 1, 'id': self.task, 'operation': request['operation'], 'gameId': request.get('gameId'), 'state': 'running', 'started': time.time()}
        for field in ('backupId','releaseId','libraryId'):
            if field in request: self.job[field]=request[field]
        if request['operation'] == 'exportIPA': self.job['outputPath'] = request.get('outputPath')
        if request['operation'] == 'convertFiles': self.job['conversion'] = request.get('conversion')
        if request['operation'] == 'import': self.job['importPaths'] = request.get('paths')
        for field in ('ended','message','done','total','elapsed','diagnostics'): self.job.pop(field,None)
        atomic(self.jobpath, self.job)
        self.resource = Path(request.get('resources', Path(__file__).resolve().parents[1])).resolve()
        selected = request.get('engineDir', '').strip()
        bundled = self.resource/'Engine/nxnative'
        # The shipped engine is authoritative, including for old preferences that
        # still point to an external checkout. Source-only fixtures may opt out.
        self.engine = bundled if bundled.exists() else Path(selected).expanduser().resolve() if selected else None
        self.runtime = self.resource / 'Runtime'
        if not self.runtime.exists() and (self.resource/'work/Runtime/versions.json').is_file():
            self.runtime = self.resource/'work/Runtime'
        self.keys = self.private / 'keys/prod.keys'
        self.library = Path(request.get('library', self.private / 'library')).expanduser().resolve()
    def emit(self, kind='progress', message='', done=None, total=None, **kw):
        with self.guard:
            if kind == 'stage' or kw.get('resetProgress'): self.last = 0
            if kind == 'progress':
                if time.monotonic() - self.last < .2 and done != total: return
                self.last = time.monotonic()
            event = {'schema': 1, 'taskId': self.task, 'operation':self.r['operation'],'gameId':self.r.get('gameId'),'started':self.job['started'],'type': kind, 'stage': self.stage, 'stageIndex': self.number, 'stageCount': self.count, 'message': message, 'elapsed': time.monotonic()-self.stage_t}
            if done is not None: event['done'] = done
            if total and total > 0: event['total'] = total
            event.update(kw)
            if getattr(self,'milestones',None):
                event['milestone']=self.milestone
                event['milestoneCached']=sorted(self.milestone_cached)
                if kind in ('stage','plan'):event['milestoneStarted']=dict(self.milestone_started)
            print(json.dumps(event, ensure_ascii=False), flush=True)
    def begin(self, name, number=None, count=None):
        self.check(); self.stage = name; self.stage_t = time.monotonic()
        ids=[row['id'] for row in getattr(self,'milestones',[])]
        if getattr(self,'milestone',None) in ids:
            self.number=ids.index(self.milestone)+1;self.count=len(ids)
        else:
            if number is not None: self.number = number
            else: self.number += 1
            if count is not None: self.count = count
        self.job.update(stage=name, stageIndex=self.number, stageCount=self.count); atomic(self.jobpath, self.job)
        self.emit('stage', name)
    def check(self):
        if self.cancelled: raise Cancelled()
        if self.r.get('libraryId') and read(self.library / '.nsmac-library.json', {}).get('id') != self.r['libraryId']:
            raise Failure('游戏库磁盘已断开或位置发生变化，请重新连接后重试。')
    def progress(self, done, total): self.check(); self.emit(done=done, total=total, unit='B')
    def report(self, diagnostic):
        with self.guard:
            records=self.job.setdefault('diagnostics',[])
            if diagnostic in records: return
            identity=lambda d:(d['code'],d.get('logPath'),d.get('stage'),d['summary'])
            existing=next((i for i,d in enumerate(records) if identity(d)==identity(diagnostic)),None)
            if existing is None:records.append(diagnostic)
            else:records[existing]=diagnostic
            self.job['diagnostics']=records[-24:]
            atomic(self.jobpath,self.job)
            self.emit('diagnostic',diagnostic=diagnostic)
    def finish(self, state, message='', result=None):
        if state=='completed' and any(d['severity']=='warning' for d in self.job.get('diagnostics',[])):
            message='操作完成，但有警告，请查看任务详情。'
        self.job.update(state=state, message=message, ended=time.time()); atomic(self.jobpath, self.job)
        self.emit('result', message, state=state, result=result or {},diagnostics=self.job.get('diagnostics',[]))
    def stop(self):
        self.cancelled = True; self.job['state'] = 'cancelling'; atomic(self.jobpath, self.job)
        for p in list(self.children):
            if p.poll() is None:
                signal_process(p, signal.SIGTERM)
        def kill():
            for p in list(self.children):
                if p.poll() is None:
                    signal_process(p, signal.SIGKILL)
        threading.Timer(3, kill).start()
    def env(self, game=None, root=None):
        env = dict(os.environ)
        env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
        env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONNOUSERSITE']='1'
        for k in list(env):
            if k.startswith(('DM_', 'IOSOUT', 'XLATE', 'DMSH')): env.pop(k)
        env['PATH'] = str(self.runtime / 'bin') + ':' + str(self.runtime / 'python/bin') + ':/usr/bin:/bin:/usr/sbin:/sbin'
        if not self.runtime.exists(): env['PATH'] = str(Path(sys.executable).parent) + ':/opt/homebrew/bin:' + env['PATH']
        env['DEVELOPER_DIR'] = self.r.get('developerDir') or '/Applications/Xcode.app/Contents/Developer'
        env['DOTNET_ROOT'] = str(self.runtime / 'dotnet') if self.runtime.exists() else '/usr/local/share/dotnet'
        env['DOTNET_ROOT_ARM64'] = env['DOTNET_ROOT']; env['DOTNET_MULTILEVEL_LOOKUP'] = '0'
        env['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'; env['DOTNET_SYSTEM_GLOBALIZATION_INVARIANT'] = '1'
        if game: env['DM_GAME'] = game
        env['DM_MAC_ONLY'] = '1'
        if root:
            env.update(DM_ROOT=str(root), WORK=str(Path(root)/'tmp'), TMPDIR=str(Path(root)/'tmp'), PYTHONUNBUFFERED='1')
            Path(env['WORK']).mkdir(parents=True, exist_ok=True)
        return env
    def nx(self):
        from engine import prepared_tools
        return prepared_tools(self) / 'tools/nx_extract/nx_extract'
    def run(self, args, log=None, env=None, cwd=None, on_line=None):
        self.check(); log = Path(log or self.private / 'logs' / (self.task + '.log')); log.parent.mkdir(parents=True, exist_ok=True)
        self.last_log=log
        import diagnostics
        output=diagnostics.Output();tool=diagnostics.component(args)
        with log.open('a') as f:
            try:
                p = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', env=env or self.env(), cwd=cwd, start_new_session=True)
            except OSError as error:
                diagnostic=diagnostics.failure(self,error,log=log,tool=tool)
                self.report(diagnostic);raise Failure(diagnostic['summary'],diagnostic) from error
            self.children.add(p)
            try:
                for line in p.stdout:
                    f.write(line); f.flush(); self.check()
                    output.feed(line)
                    if line.startswith('NSMAC_PROGRESS '):
                        v = json.loads(line[15:]); self.emit(done=v['done'], total=v['total'], unit=v.get('unit',''))
                    elif self.r['operation'] in ('installMetal','uninstallMetal'):
                        match=re.search(r'(\d+(?:\.\d+)?)\s*%',line)
                        if match and 0<=float(match[1])<=100: self.emit(done=float(match[1]),total=100,unit='%')
                    if on_line: on_line(line.rstrip())
                code = p.wait(); self.check()
                if code:
                    diagnostic=diagnostics.failure(self,output.text,log=log,tool=tool,status=code)
                    self.report(diagnostic);raise Failure(diagnostic['summary'],diagnostic)
                diagnostic=diagnostics.shader_result(self,output,log,tool)
                if diagnostic:
                    self.report(diagnostic)
                    if diagnostic['severity']=='error': raise Failure(diagnostic['summary'],diagnostic)
            finally:
                if p.poll() is None:
                    signal_process(p, signal.SIGTERM)
                    try: p.wait(timeout=3)
                    except subprocess.TimeoutExpired: signal_process(p, signal.SIGKILL); p.wait()
                p.stdout.close();self.children.discard(p)
        return log
    @contextlib.contextmanager
    def toolchain_lock(self, exclusive=False, wait=False):
        self.check()
        with (self.private / '.toolchain.lock').open('a') as f:
            announced=False
            while True:
                self.check()
                try:
                    fcntl.flock(f, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not wait: raise Failure('工具链正在使用中，请等待游戏运行、准备或组件管理任务结束后重试。')
                    if not announced:
                        self.begin('等待游戏或工具链任务结束',1,1);announced=True
                    time.sleep(.2)
            try: yield
            finally: fcntl.flock(f, fcntl.LOCK_UN)
    @contextlib.contextmanager
    def lock(self, name='catalog'):
        self.check(); self.library.mkdir(parents=True, exist_ok=True)
        with (self.library / ('.'+name+'.lock')).open('a') as f:
            try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise Failure('另一个任务正在使用游戏库，请稍后重试。')
            yield
    def catalog(self): return read(self.library / 'catalog.json', {'schema': 1, 'games': []})
    def save_catalog(self, cat): atomic(self.library / 'catalog.json', cat)
    def game(self):
        self.check()
        for g in self.catalog()['games']:
            if g['id'] == self.r.get('gameId'): return g
        raise Failure('游戏未登记在当前游戏库中。')

def profiles(engine):
    result = {}
    if engine is None: return result
    for path in sorted((Path(engine) / 'dm/games').glob('*/game.tsv')):
        rows = [l.split('\t') for l in path.read_text().splitlines() if l.strip() and not l.startswith('#')]
        g = {r[0]: '\t'.join(r[1:]) for r in rows}; g['builds'] = {r[1]: {'display': r[2], **dict(m.split('=',1) for m in r[3:])} for r in rows if r[0]=='build'}
        g['id'] = path.parent.name; g['compatibility'] = 'experimental'; result[g['id']] = g
    return result

def validate_keys(path):
    if Path(path).stat().st_size > 1024*1024: raise Failure('密钥文件过大，请选择 prod.keys 文本文件。')
    text = Path(path).read_text(encoding='utf-8-sig'); entries = {}
    for line in text.splitlines():
        line = line.split('#',1)[0].strip()
        if not line: continue
        m = re.fullmatch(r'([a-zA-Z0-9_]+)\s*=\s*((?:0x)?[0-9a-fA-F]{2,2048})', line)
        if not m or len(m[2].removeprefix('0x')) % 2: raise Failure('密钥文件格式无效，请检查是否选择了正确的文本文件。')
        if m[1] in entries and entries[m[1]] != m[2]: raise Failure('密钥文件存在冲突条目。')
        entries[m[1]] = m[2].removeprefix('0x')
    if len(entries.get('header_key','')) != 64: raise Failure('缺少有效的 header_key，无法读取 NSP。')
    return len(entries)
