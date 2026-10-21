from __future__ import annotations
import json, os, re, shutil, subprocess, time, uuid, zipfile
from pathlib import Path
from core import *

def setup(c):
    c.begin('创建游戏库',1,1)
    if not c.library.is_dir(): c.library.mkdir(parents=True)
    mark = c.library / '.nsmac-library.json'; info = read(mark)
    if info is None:
        if any(p.name != '.DS_Store' for p in c.library.iterdir()): raise Failure('请选择空文件夹或已有璃游（NS Mac）游戏库，避免混入其他文件。')
        info = {'schema':1,'id':uuid.uuid4().hex}; atomic(mark,info)
    for name in ['sources','games','cache','saves','temp','mappings']: (c.library/name).mkdir(exist_ok=True)
    if not (c.library/'catalog.json').exists(): c.save_catalog({'schema':1,'games':[]})
    return {'library':str(c.library),'libraryId':info['id']}

def preflight(c):
    c.begin('检查系统与工具链',1,1)
    from toolchain import inspect_environment, supports_removal
    checks = inspect_environment(c)
    return {'checks':checks,'ready':all(x['ok'] for x in checks),
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
    try: c.run([c.nx(),key or c.keys,'--inspect',path]+([icon] if icon else []),on_line=lines.append)
    except Failure: raise Failure('无法解密或验证 NSP 元数据，请检查密钥是否正确、文件是否完整。')
    try: return json.loads(next(l for l in reversed(lines) if l.startswith('{')))
    except (StopIteration,ValueError): raise Failure('无法识别 NSP 元数据，请检查密钥、文件完整性和文件类型。')

def requirements(g,p):
    if not p: return ['此游戏尚无原生适配配置']
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
    if not c.keys.exists(): raise Failure('请先导入玩家自己的 prod.keys。')
    validate_keys(c.keys); files=[]
    for s in c.r['paths']:
        p=Path(s).expanduser().resolve()
        if p.is_dir(): files.extend(x for x in p.rglob('*') if x.suffix.lower()=='.nsp' and x.is_file() and not x.is_symlink())
        elif p.suffix.lower()=='.nsp': files.append(p)
        else: raise Failure('首版只接受 NSP 文件或包含 NSP 的文件夹。')
    files=list(dict.fromkeys(files))
    if not files: raise Failure('所选位置没有 NSP 文件。')
    ps=profiles(c.engine); results=[]
    for i,src in enumerate(files):
        c.begin(f'读取 NSP 元数据（{i+1}/{len(files)}）',i+1,len(files))
        info=inspect(c,src); tid=info['baseId']
        if not re.fullmatch('[0-9A-F]{16}',tid): raise Failure('无效的游戏标识。')
        c.emit('message','正在校验源文件内容'); sha=digest(src,c.progress)
        with c.lock():
            cat=c.catalog(); g=next((g for g in cat['games'] if g['id']==tid),None)
            if not g:
                g={'id':tid,'name':info['name'] or ps.get(tid,{}).get('name',tid),'display':info['display'],'packages':[],'hidden':False}; cat['games'].append(g)
            g['hidden']=False
            if any(x['sha256']==sha for x in g['packages']):
                c.save_catalog(cat); results.append({'name':src.name,'duplicate':True}); continue
            dest=c.library/'sources'/tid/f'{info["titleId"]}_v{info["version"]}_{sha[:12]}.nsp'
            free=shutil.disk_usage(c.library).free
            reserve=512*2**20 if src.stat().st_dev==c.library.stat().st_dev else src.stat().st_size+512*2**20
            if free<reserve: raise Failure('游戏库可用空间不足，复制尚未开始。')
            tmp=dest.with_suffix('.partial'); tmp.parent.mkdir(parents=True,exist_ok=True); tmp.unlink(missing_ok=True)
            try:
                clone(src,tmp)
                if digest(tmp,c.progress)!=sha: raise Failure('复制后校验失败，原始文件未改动。')
                c.check(); os.replace(tmp,dest)
            finally: tmp.unlink(missing_ok=True)
            icon=c.library/'games'/tid/'cover.jpg'; icon.parent.mkdir(parents=True,exist_ok=True)
            inspect(c,dest,icon=icon)
            package=info|{'path':str(dest.relative_to(c.library)),'size':dest.stat().st_size,'sha256':sha}
            g['packages'].append(package)
            if info['name']: g['name']=info['name']
            if info['display']: g['display']=info['display']
            g['compatibility']=ps.get(tid,{}).get('compatibility','unsupported'); g['missing']=requirements(g,ps.get(tid)); g['cover']=str(icon.relative_to(c.library)) if icon.exists() else ''
            c.save_catalog(cat)
            results.append({'name':src.name,'duplicate':False,'id':tid})
    atomic(c.private/'keys/status.json',read(c.private/'keys/status.json',{})|{'verified':True})
    return {'imports':results}

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
    c.begin('读取游戏库',1,1); cat=c.catalog(); ps=profiles(c.engine)
    for g in cat['games']:
        g['missing']=requirements(g,ps.get(g['id'])); g['compatibility']=ps.get(g['id'],{}).get('compatibility','unsupported')
        p=ps.get(g['id']); selected=next((x for x in g['packages'] if p and f"v{x['version']}"==p.get('package') and x['type'] in ('base','update')),None)
        if selected: g['display']=selected['display'] or p['builds'].get(p['package'],{}).get('display','')
        manifest=read(c.library/'games'/g['id']/'current/manifest.json',{})
        cover=c.library/'games'/g['id']/'cover.jpg'; g['cover']=str(cover) if cover.exists() else ''
        g['ready']=bool(manifest)
        g['needsPreparation']=bool(manifest) and (manifest.get('engine') != ENGINE_REV or manifest.get('sourceHashes') != sorted(x['sha256'] for x in g['packages']))
    cat['profiles']=[{'id':x['id'],'name':x['name'],'compatibility':x['compatibility'],'version':x['builds'].get(x['package'],{}).get('display','')} for x in ps.values()]
    cat['jobs']=[read(p) for p in (c.private/'jobs').glob('*.json') if p!=c.jobpath]
    cat['keys']=key_status(c)
    return cat

def remove(c):
    with c.lock():
        cat=c.catalog(); g=next(g for g in cat['games'] if g['id']==c.r['gameId'])
        g['hidden']=True; c.save_catalog(cat)
    return {}

def clean(c):
    with c.lock('execution'), c.lock():
        g=c.game(); kind=c.r['kind']
        if kind=='cache': paths=[c.library/'cache'/g['id']]
        elif kind=='sources': paths=[c.library/'sources'/g['id']]
        else: raise Failure('无效的清理范围。')
        for p in paths:
            if p.exists(): shutil.rmtree(contained(c.library,p))
        if kind=='sources':
            cat=c.catalog(); next(x for x in cat['games'] if x['id']==g['id'])['packages']=[]; c.save_catalog(cat)
    return {}

def diagnostics(c):
    c.begin('导出诊断',1,1)
    out=Path(c.r['path'])
    # Allowlist only status records and text logs; never requests, sources, keys, saves, or cache.
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('system.json',json.dumps({'schema':1,'engine':ENGINE_REV,'jobs':[{k:v for k,v in read(p,{}).items() if k in ('id','state','operation','stage','message')} for p in (c.private/'jobs').glob('*.json')]}))
        for base in (c.private/'logs',c.library/'cache'):
            if not base.exists(): continue
            for p in base.rglob('*.log'):
                if p.stat().st_size>8*2**20: continue
                text=p.read_text(errors='replace')
                text=re.sub(r'(?i)([a-z0-9_]*(?:key|secret|token)[a-z0-9_]*\s*=\s*)\S+',r'\1[REDACTED]',text)
                text=text.replace(str(Path.home()),'~').replace(str(c.library),'[LIBRARY]').replace(str(c.private),'[PRIVATE]')
                z.writestr('logs/'+hashlib.sha256(str(p).encode()).hexdigest()[:12]+'.log',text)
    return {'path':str(out)}
