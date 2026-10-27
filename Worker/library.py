from __future__ import annotations
import json, os, re, shutil, subprocess, tempfile, time, uuid, zipfile
from pathlib import Path
from core import *

def setup(c):
    c.begin('创建游戏库',1,1)
    if not c.library.is_dir(): c.library.mkdir(parents=True)
    mark = c.library / '.nsmac-library.json'; info = read(mark)
    if info is None:
        if any(p.name != '.DS_Store' for p in c.library.iterdir()): raise Failure('请选择空文件夹或已有 LumaNX 游戏库，避免混入其他文件。')
        info = {'schema':1,'id':uuid.uuid4().hex}; atomic(mark,info)
    for name in ['sources','games','cache','saves','temp','mappings']: (c.library/name).mkdir(exist_ok=True)
    if not (c.library/'catalog.json').exists(): c.save_catalog({'schema':1,'games':[]})
    return {'library':str(c.library),'libraryId':info['id']}

def preflight(c):
    c.begin('检查系统与工具链',1,1)
    from toolchain import inspect_environment, supports_removal
    checks = inspect_environment(c)
    from engine import inspect_source
    try: engine_info=inspect_source(c)
    except Failure: engine_info=None
    return {'engineInfo':engine_info,'checks':checks,'ready':all(x['ok'] for x in checks if 'prepare' in x['requiredFor']),
            'launchReady':all(x['ok'] for x in checks if 'launch' in x['requiredFor']),
            'canUninstallMetal':supports_removal(c)}

def keys(c):
    c.begin('导入玩家密钥',1,1); src=Path(c.r['path']); count=validate_keys(src)
    c.keys.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Validate the candidate against an existing managed NSP before replacing a working key.
    candidate=c.keys.with_suffix('.candidate'); candidate.write_bytes(src.read_bytes()); os.chmod(candidate,0o600)
    verified=False
    try:
        packages=[p for g in c.catalog()['games'] for p in g['packages']]
        if packages:
            inspect(c,c.library/packages[0]['path'],candidate); verified=True
        os.replace(candidate,c.keys); os.chmod(c.keys,0o600)
    finally:
        candidate.unlink(missing_ok=True)
    atomic(c.private/'keys/status.json',{'entries':count,'verified':verified,'imported':time.time()})
    return {'entries':count,'verified':verified,'message':'已验证解密能力' if verified else '格式检查通过；首次读取 NSP 时验证解密能力'}

def inspect(c,path,key=None,icon=None):
    lines=[]
    reader=c.nx()
    try: c.run([reader,key or c.keys,'--inspect',path]+([icon] if icon else []),on_line=lines.append)
    except Failure: raise Failure('无法解密或验证游戏元数据，请检查密钥、文件完整性及引擎格式支持。')
    try: return json.loads(next(l for l in reversed(lines) if l.startswith('{')))
    except (StopIteration,ValueError): raise Failure('无法识别游戏元数据，请检查密钥、文件完整性和文件类型。')

def requirements(g,p,derived_profiles=False):
    if not p: return ['此游戏尚无原生适配配置']
    if derived_profiles and any(x['type']=='base' and x['version']==0 for x in g['packages']): return []
    packages=g['packages']; need=['v0']+list(dict.fromkeys([p['package']]+p.get('shader_versions',p['package']).split()))
    have={f"v{x['version']}" for x in packages if x['type'] in ('base','update')}
    missing=['缺少本体 v0' if v=='v0' else f'缺少更新 {v}（{p["builds"].get(v,{}).get("display","配置指定版本")}）' for v in need if v not in have]
    for x in packages:
        ver=f"v{x['version']}"
        if x['type'] in ('base','update') and ver in need and ver in p['builds']:
            for mod,bid in p['builds'][ver].items():
                if mod!='display' and x.get('builds',{}).get(mod)!=bid: missing.append(f'{ver} 的 {mod} 构建标识与已适配版本不同')
    return missing

def import_games(c):
    import conversion
    if not c.keys.exists(): raise Failure('请先导入玩家自己的 prod.keys。')
    validate_keys(c.keys); files=[];c.begin('扫描游戏文件',1,1)
    for s in c.r['paths']:
        p=Path(s).expanduser()
        if p.is_symlink(): raise Failure('不接受指向游戏库之外的符号链接。')
        p=p.resolve()
        if p.is_dir(): files.extend(x for x in sorted(p.rglob('*')) if x.suffix.lower()[1:] in conversion.FORMATS and x.is_file() and not x.is_symlink())
        elif p.suffix.lower()[1:] in conversion.FORMATS: files.append(p)
        else: raise Failure('请选择 NSP、XCI、NSZ、XCZ 文件或包含这些文件的文件夹。')
    files=list(dict.fromkeys(files))
    if not files: raise Failure('所选位置没有支持的游戏文件。')
    with conversion.import_packages(c,files) as packages:
        return import_containers(c,packages)


def container_packages(info):
    # Legacy reader responses remain readable; all new snapshots emit schema 2.
    if not isinstance(info,dict): raise Failure('无法识别游戏元数据，请检查密钥、文件完整性和文件类型。')
    packages=info.get('packages') if info.get('schema')==2 else [info]
    if not isinstance(packages,list) or not packages: raise Failure('无法识别游戏元数据，请检查密钥、文件完整性和文件类型。')
    identities=set()
    for package in packages:
        if not isinstance(package,dict) or any(not isinstance(package.get(k),str) or not re.fullmatch('[0-9A-F]{16}',package[k]) for k in ('titleId','baseId')):
            raise Failure('无效的游戏标识。')
        if package.get('type') not in ('base','update','dlc') or type(package.get('version')) is not int or not 0<=package['version']<=0xffffffff:
            raise Failure('无法识别游戏元数据，请检查密钥、文件完整性和文件类型。')
        identity=(package['titleId'],package['version'],package['type'])
        if identity in identities: raise Failure('无法识别游戏元数据，请检查密钥、文件完整性和文件类型。')
        identities.add(identity)
    return packages


def import_containers(c, files, *, unhide=True, expected_hashes=None):
    from derived import supported
    dynamic=supported(c.engine)
    ps=profiles(c.engine); results=[]
    for i,src in enumerate(files):
        c.begin(f'读取游戏元数据（{i+1}/{len(files)}）',i*5+1,len(files)*5)
        with tempfile.TemporaryDirectory(prefix='metadata-',dir=c.private) as directory:
            icons=Path(directory); info=inspect(c,src,icon=icons); packages=container_packages(info)
            metadata_schema=2 if info.get('schema')==2 else 1
            c.begin('正在校验源文件内容',i*5+2,len(files)*5); sha=digest(src,c.progress)
            if expected_hashes is not None and expected_hashes[str(src)]!=sha:
                raise Failure('托管源文件已丢失或内容发生改变，请重新导入。')
            with c.lock():
                cat=c.catalog()
                previous=[p for g in cat['games'] for p in g['packages'] if p['sha256']==sha]
                old_ids={(p['titleId'],p['version'],p['type']) for p in previous}
                new_ids={(p['titleId'],p['version'],p['type']) for p in packages}
                duplicate=bool(previous) and old_ids==new_ids
                # A merged container is copied once; every logical package points at it.
                first=packages[0]
                dest=contained(c.library,c.library/previous[0]['path']) if previous else c.library/'sources'/first['baseId']/f'{first["titleId"]}_v{first["version"]}_{sha[:12]}{src.suffix.lower()}'
                if not dest.is_file() or dest.resolve()!=src.resolve():
                    free=shutil.disk_usage(c.library).free
                    reserve=512*2**20 if src.stat().st_dev==c.library.stat().st_dev else src.stat().st_size+512*2**20
                    if free<reserve: raise Failure('游戏库可用空间不足，复制尚未开始。')
                    tmp=dest.with_suffix('.partial'); tmp.parent.mkdir(parents=True,exist_ok=True); tmp.unlink(missing_ok=True)
                    try:
                        c.begin('复制游戏文件到游戏库',i*5+3,len(files)*5);clone(src,tmp,c.progress)
                        c.begin('校验托管副本',i*5+4,len(files)*5)
                        if digest(tmp,c.progress)!=sha: raise Failure('复制后校验失败，原始文件未改动。')
                        c.check(); os.replace(tmp,dest)
                    finally: tmp.unlink(missing_ok=True)
                c.begin('登记游戏内容',i*5+5,len(files)*5)
                for g in cat['games']:
                    g['packages']=[p for p in g['packages'] if p['sha256']!=sha]
                for package in sorted(packages,key=lambda p:p['version']):
                    tid=package['baseId']; g=next((g for g in cat['games'] if g['id']==tid),None)
                    if g is None:
                        g={'id':tid,'name':package.get('name') or ps.get(tid,{}).get('name',tid),'display':'','packages':[],'hidden':False}; cat['games'].append(g)
                    if unhide: g['hidden']=False
                    g['packages'].append(package|{'path':str(dest.relative_to(c.library)),'size':dest.stat().st_size,'sha256':sha,'metadataSchema':metadata_schema})
                    if package.get('name'): g['name']=package['name']
                    selected=max((p for p in g['packages'] if p['type'] in ('base','update')),key=lambda p:p['version'],default={})
                    g['display']=selected.get('display','')
                    icon=c.library/'games'/tid/'cover.jpg'; candidate=icons/(package['titleId']+'.jpg')
                    if candidate.is_file():
                        icon.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(candidate,icon)
                    g['compatibility']=ps.get(tid,{}).get('compatibility','unsupported'); g['missing']=requirements(g,ps.get(tid),dynamic); g['cover']=str(icon.relative_to(c.library)) if icon.exists() else ''
                c.save_catalog(cat)
                for tid in dict.fromkeys(p['baseId'] for p in packages): results.append({'name':src.name,'duplicate':duplicate,'id':tid})
    atomic(c.private/'keys/status.json',read(c.private/'keys/status.json',{})|{'verified':True})
    return {'imports':results}


def refresh_container_metadata(c):
    # Upgrade already imported merged files once the new private reader is ready.
    cat=c.catalog()
    pending={p['path']:p['sha256'] for g in cat['games'] for p in g['packages'] if p.get('metadataSchema',0)<2 and not g.get('hidden')}
    if not pending or not c.keys.is_file(): return
    try: c.nx()
    except Failure: return
    for path in sorted(pending):
        try:
            source=contained(c.library,c.library/path)
            if source.is_file(): import_containers(c,[source],unhide=False,expected_hashes={str(source):pending[path]})
        except Failure:
            # Keep the last successful catalogue when a disk/key is unavailable.
            continue


def key_status(c):
    if not c.keys.is_file():
        return {'ready':False,'verified':False,'message':'尚未导入 prod.keys'}
    try:
        count=validate_keys(c.keys)
    except (Failure,OSError,UnicodeError):
        return {'ready':False,'verified':False,'message':'密钥文件不可用，请重新导入 prod.keys'}
    status=read(c.private/'keys/status.json',{})
    verified=status.get('verified') is True
    return {'ready':True,'entries':count,'verified':verified,'message':'已验证解密能力' if verified else '格式通过，首次导入游戏时验证解密能力'}

def catalog(c):
    from engine import inspect_source
    try: selected_engine = inspect_source(c)
    except Failure: selected_engine = None
    if selected_engine: refresh_container_metadata(c)
    c.begin('读取游戏库',1,1); cat=c.catalog(); ps=profiles(c.engine) if selected_engine else {}
    for g in cat['games']:
        g['missing']=requirements(g,ps.get(g['id']),bool(selected_engine and selected_engine.get('derivedProfiles'))); g['compatibility']=ps.get(g['id'],{}).get('compatibility','unsupported')
        p=ps.get(g['id'])
        from derived import plan
        strategy=plan(g,p,bool(selected_engine and selected_engine.get('derivedProfiles'))) if p else {}
        g['preparationMode']=strategy.get('mode','registered')
        g['preparationVersion']=strategy.get('version','')
        selected=next((x for x in g['packages'] if p and f"v{x['version']}"==strategy.get('version',p.get('package')) and x['type'] in ('base','update')),None)
        if selected: g['display']=selected['display'] or p['builds'].get(strategy.get('version',p['package']),{}).get('display',strategy.get('version',''))
        manifest=read(c.library/'games'/g['id']/'current/manifest.json',{})
        cover=c.library/'games'/g['id']/'cover.jpg'; g['cover']=str(cover) if cover.exists() else ''
        g['ready']=bool(manifest)
        g['runtimeVersion']=manifest.get('version','')
        g['inputConfig']=manifest.get('inputConfig',True) if manifest else bool(selected_engine and selected_engine['inputConfig'])
        g['needsPreparation']=bool(manifest) and (selected_engine is not None and manifest.get('engine') != selected_engine['fingerprint'] or manifest.get('sourceHashes') != sorted(x['sha256'] for x in g['packages']))
    cat['profiles']=[{'id':x['id'],'name':x['name'],'compatibility':x['compatibility'],'version':x['builds'].get(x['package'],{}).get('display','')} for x in ps.values()]
    cat['jobs']=[read(p) for p in (c.private/'jobs').glob('*.json') if p!=c.jobpath]
    cat['keys']=key_status(c)
    return cat

def remove(c):
    c.begin('移出游戏库',1,1)
    with c.lock():
        cat=c.catalog(); g=next(g for g in cat['games'] if g['id']==c.r['gameId'])
        g['hidden']=True; c.save_catalog(cat)
    return {}

def clean(c):
    with c.lock('execution'), c.lock():
        g=c.game(); kind=c.r['kind']
        if kind=='sources':
            c.begin('删除托管 NSP 副本',1,1)
            cat=c.catalog()
            game=next(x for x in cat['games'] if x['id']==g['id'])
            if (c.library/'sources').is_symlink(): raise Failure('托管源文件路径无效，未执行清理。')
            sources=contained(c.library,c.library/'sources')
            def source_path(package):
                return contained(sources,c.library/package['path'])
            candidates={source_path(p) for p in game['packages']}
            # Hidden games still own their files. A container may live under another title.
            shared={source_path(p) for other in cat['games'] if other['id']!=g['id'] for p in other['packages']}
            paths=sorted(candidates-shared)
            if any(p.is_dir() for p in paths): raise Failure('托管源文件路径无效，未执行清理。')
            c.check()
            # Detach references first: cancellation can leave orphans, never dangling
            # references belonging to another game or a partially deleted catalogue.
            game['packages']=[]
            c.save_catalog(cat)
            for index,path in enumerate(paths,1):
                c.check();path.unlink(missing_ok=True)
                c.emit(done=index,total=len(paths),unit='files')
            return {'retainedShared':len(candidates & shared)}
        if kind=='cache':
            cache=c.library/'cache';path=cache/g['id']
            if cache.is_symlink() or path.is_symlink(): raise Failure('托管源文件路径无效，未执行清理。')
            paths=[contained(cache,path)]
        else: raise Failure('无效的清理范围。')
        c.begin('清理构建缓存' if kind=='cache' else '删除托管 NSP 副本',1,1)
        for p in paths:
            if p.exists():
                p=contained(c.library,p)
                entries=sorted(p.rglob('*'),key=lambda path:len(path.parts),reverse=True)+[p]
                for index,path in enumerate(entries,1):
                    c.check()
                    if path.is_symlink() or path.is_file():path.unlink()
                    else:path.rmdir()
                    c.emit(done=index,total=len(entries),unit='files')
    return {}

def diagnostics(c):
    from diagnostics import redact
    c.begin('收集诊断日志',1,2)
    out=Path(c.r['path'])
    candidates=[]
    for base in (c.private/'logs',c.library/'cache'):
        if base.exists():
            for path in base.rglob('*.log'):
                c.check()
                if not path.is_symlink() and path.resolve().is_relative_to(base.resolve()) and path.stat().st_size<=8*2**20:candidates.append(path)
    c.begin('导出诊断',2,2)
    temporary=out.with_name('.'+out.name+'.'+uuid.uuid4().hex+'.partial')
    # Allowlist only status records and text logs; never requests, sources, keys, saves, or cache.
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('system.json',json.dumps({'schema':1,'engine':'external','jobs':[{k:redact(v,c) if isinstance(v,str) else v for k,v in read(p,{}).items() if k in ('id','state','operation','stage','message')} for p in (c.private/'jobs').glob('*.json')]}))
            for index,p in enumerate(candidates,1):
                c.check();text=redact(p.read_text(errors='replace'),c,limit=None)
                z.writestr('logs/'+hashlib.sha256(str(p).encode()).hexdigest()[:12]+'.log',text)
                c.emit(done=index,total=len(candidates),unit='files')
        c.check();os.replace(temporary,out)
    finally:temporary.unlink(missing_ok=True)
    return {'path':str(out)}
