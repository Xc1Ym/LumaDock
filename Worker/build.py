"""Build macOS runtime files directly using supported game profiles."""
from __future__ import annotations
import importlib.util, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from core import *
from library import requirements, inspect

class ShaderProgress:
    """Count only finished reflection/library pairs; do not infer progress from queue order."""
    def __init__(self,g,repo,cache):
        self.keys=set()
        for line in g.table('shader_map.tsv').read_text().splitlines():
            columns=line.split('\t')
            if len(columns)>4 and (columns[0].endswith('.bin') or columns[0].startswith('main.rodata@')):self.keys.add(columns[3])
        chain=chain_of(repo,g)
        self.path=Path(cache)/('b-'+chain)
    def __call__(self):
        names=set(os.listdir(self.path)) if self.path.is_dir() else set()
        done=sum(k+'_b.json' in names and k+'_b.metallib' in names for k in self.keys)
        return {'done':done,'total':len(self.keys),'unit':'shaders','step':'编译并验证 Metal 库'}

class Stages:
    def __init__(self,c,root):
        self.c=c; self.root=root; self.file=root/'checkpoints.json'; self.saved=read(self.file,{})
        self.warningfile=root/'checkpoint-warnings.json';self.warnings=read(self.warningfile,{})
    def snapshot(self,paths):
        out={};files=[]
        for path in paths:
            path=Path(path)
            files.extend(p for p in (sorted(path.rglob('*')) if path.is_dir() else [path]) if p.is_file())
        total=sum(p.stat().st_size for p in files);done=0
        self.c.emit('message','验证阶段产物')
        for p in files:
            self.c.check();size=p.stat().st_size
            out[str(p.relative_to(self.root))]=[size,digest(p,lambda n,t:self.c.progress(done+n,total))];done+=size
        if not out: raise Failure('阶段没有生成完整产物，未记录成功缓存。')
        return out
    def run(self,name,paths,fn):
        self.c.begin(name)
        old=self.saved.get(name)
        valid=bool(old);done=0;total=sum(v[0] for v in old.values()) if old else 0
        if old:
            for p,v in old.items():
                self.c.check();path=self.root/p
                if not path.is_file() or path.stat().st_size!=v[0] or digest(path,lambda n,t:self.c.progress(done+n,total))!=v[1]:valid=False;break
                done+=v[0]
        if valid:
            for warning in self.warnings.get(name,[]): self.c.report(warning)
            self.c.emit('cache','已验证并复用完成阶段',done=1,total=1); return
        for p in paths:
            if Path(p).is_dir(): shutil.rmtree(p)
            elif Path(p).exists(): Path(p).unlink()
        fn(); self.c.check(); self.saved[name]=self.snapshot(paths)
        self.warnings[name]=[d for d in self.c.job.get('diagnostics',[]) if d.get('stage')==name and d['severity']=='warning']
        atomic(self.warningfile,self.warnings);atomic(self.file,self.saved)
        self.c.emit('stageComplete','阶段完成',done=1,total=1)

def tools(c,target='macos'):
    from toolchain import require_environment
    require_environment(c)
    env=c.env(); result={}
    for key,args in [('clang',['xcrun','clang','--version']),('metal',['xcrun','-sdk','macosx','metal','--version'])]:
        p=subprocess.run(args,env=env,capture_output=True,text=True)
        if p.returncode or (key=='metal' and 'Apple metal version' not in p.stdout): raise Failure('Apple 工具链不完整，请在设置中安装 Xcode 和 Metal 编译组件。')
        result[key]=p.stdout.strip()
    sc=shutil.which('spirv-cross',path=env['PATH'])
    if not sc: raise Failure('着色器转换组件缺失，请重新安装完整应用。')
    result['spirv-cross']=digest(sc)
    result['runtime']=digest(c.runtime/'versions.json')
    result['macos-sdk']=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-version'],env=env,text=True).strip()
    from engine import inspect_source, prepared_tools
    info = inspect_source(c)
    prepared = prepared_tools(c,info)
    result['engineSource'] = info['fingerprint']; result['engine'] = info['fingerprint']
    result['inputConfig'] = info['inputConfig']
    result['reader'] = digest(prepared/'tools/nx_extract/nx_extract.dll')
    if target == 'ios':
        from ipa import environment
        result['ios'] = environment(c)[1]
    return result


def refresh_engine(c,root,tc):
    """Rebuild the private engine copy; the marker ties it to the current source fingerprint."""
    repo=root/'engine'; tmp=root/'engine.partial'; shutil.rmtree(tmp,ignore_errors=True)
    from engine import prepared_tools
    shutil.copytree(prepared_tools(c)/'source',tmp,ignore=shutil.ignore_patterns('bin','obj','gen','__pycache__','.git','dmhost'))
    (tmp/'.source-ready').write_text(tc['engineSource'])
    if repo.exists(): shutil.rmtree(repo)
    tmp.rename(repo)

def chain_tools(c,repo,env,root):
    # Tool changes produce a new private lock, chain, shader output, c1 table and host together.
    c.run([sys.executable,repo/'dm/gfx/tools/dmsh_chain.py','--update-lock'],root/'logs/toolchain.log',env)
    c.run([sys.executable,repo/'dm/gfx/tools/dmsh_chain.py','--header'],root/'logs/toolchain.log',env)
    c.run([sys.executable,repo/'dm/gfx/tools/dmsh_chain.py','--check-tools'],root/'logs/toolchain.log',env)
    lock=repo/'dm/gfx/tools/dmsh_chain.lock'
    if not lock.is_file() or 'missing' in lock.read_text(): raise Failure('Metal 工具链不可用，无法创建一致的着色器链。')

def ensure_chain_header(c,root,repo,env,tc,gp=None):
    """A hand-patched or damaged engine copy can exit cleanly without writing the header (issue #9)."""
    if chain_of(repo,gp): return
    refresh_engine(c,root,tc); chain_tools(c,repo,env,root)
    if not chain_of(repo,gp): raise Failure('着色器链头文件仍未生成，请查看 toolchain.log；若 nxnative 与当前版本不兼容，请更新后删除该游戏缓存重试。')


def prepare(c,g,target='macos'):
    from engine import inspect_source
    inspect_source(c)
    ps=profiles(c.engine); profile=ps.get(g['id']); missing=requirements(g,profile)
    if missing: raise Failure('；'.join(missing))
    tc=tools(c,target); identity={'tools':tc,'sources':sorted(x['sha256'] for x in g['packages']),'game':g['id'],'target':target,'schema':1}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:24]
    root=c.library/'cache'/g['id']/key; root.mkdir(parents=True,exist_ok=True)
    repo=root/'engine'
    if not (repo/'.source-ready').exists(): refresh_engine(c,root,tc)
    env=c.env(g['id'],root); env['MACOSX_DEPLOYMENT_TARGET']='26.0'; env['J']=str(min(os.cpu_count() or 4,8))
    if target == 'ios':
        from ipa import environment
        env=environment(c,env)[0]
    chain_tools(c,repo,env,root)
    atomic(root/'identity.json',identity)
    spec=importlib.util.spec_from_file_location('nsmac_upstream',repo/'scripts/build_ipa_from_nsp.py'); up=importlib.util.module_from_spec(spec); spec.loader.exec_module(up)
    sys.path.insert(0,str(repo/'dm/games')); import game
    game.HERE=repo/'dm/games'; gp=game.load(g['id'])
    ensure_chain_header(c,root,repo,env,tc,gp)
    class Bridge(up.Progress):
        def __init__(self): super().__init__('off')
        def stage(self,name,poll=None,**kw):
            super().stage(name,poll=poll,**kw)
            c.emit(resetProgress=True)
        def _out(self,text): pass
        def set(self,**kw):
            super().set(**kw)
            if self.cur:
                st=self.cur
                # Estimated totals are intentionally indeterminate in the UI.
                c.emit(message=st.step,done=st.done,total=None if st.est else st.total,unit=st.unit)
        def say(self,msg): c.emit('message',msg)
    up.PROG=Bridge(); up.run=c.run
    return root,repo,env,up,gp,key

def compile_host(c,up,repo,env,root,gp):
    host=up.build_mac_host(repo,root/'tools/dmhost',env,root/'logs',gp)
    c.run(['codesign','--force','--sign','-',host],root/'logs/sign.log',env)
    c.run(['codesign','--verify','--strict',host],root/'logs/sign.log',env)
    return host

def install(c,root,repo,gp,key,host,romfs,modules,shader,aoc=None,font=None):
    dst=c.library/'games'/gp.id; releases=dst/'releases'; releases.mkdir(parents=True,exist_ok=True)
    stage=dst/'install.partial'; shutil.rmtree(stage,ignore_errors=True); stage.mkdir()
    def cp(src,name):
        if src and Path(src).exists(): clone_tree(src,stage/name,c.progress)
    cp(romfs,'romfs'); cp(modules,'modules'); cp(shader,'shaders'); cp(aoc,'aoc')
    clone(host,stage/'dmhost'); os.chmod(stage/'dmhost',0o755)
    (stage/'profile').mkdir()
    for name in ['shader_map.tsv','pso_manifest.tsv']:
        if gp.table(name).exists(): clone(gp.table(name),stage/'profile'/name)
    chain=chain_of(repo,gp)
    if gp.get('graphics','nvn')!='vulkan':
        c.run([sys.executable,Path(__file__).parent/'c1_generate.py',repo/'dm/gfx/tools/c1_guard.py',stage/'shaders'/('b-'+chain),stage/'profile/c1_full.tsv'],root/'logs/c1.log',c.env(gp.id,root))
        if not (stage/'profile/c1_full.tsv').read_text().startswith('# chain b-'+chain+' '): raise Failure('着色器常量表版本不一致。')
    if font: cp(font,'font')
    else:
        (stage/'font').mkdir()
        fontpath=next((p for p in [Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),Path('/System/Library/Fonts/Helvetica.ttc')] if p.exists()),None)
        if not fontpath: raise Failure('找不到本机系统字体。')
        clone(fontpath,stage/'font/standard.ttf')
        c.run([sys.executable,repo/'dm/tools/make_ext_font.py',stage/'font/nintendo_ext.ttf'],root/'logs/font.log',c.env(gp.id,root))
    manifest={'schema':1,'gameId':gp.id,'engine':read(root/'identity.json',{}).get('tools',{}).get('engine','external'),'cacheKey':key,'sourceHashes':read(root/'identity.json',{}).get('sources',[]),'chain':chain,'graphics':gp.get('graphics','nvn'),'version':gp.builds()[gp.get('package')]['display'],'inputConfig':read(root/'identity.json',{}).get('tools',{}).get('inputConfig',False),'created':time.time()}
    atomic(stage/'manifest.json',manifest)
    validate_runtime(stage,gp)
    # A symlink switch is atomic; the old successful release remains intact on every failure.
    target=releases/(key+'-'+str(time.time_ns())); stage.rename(target)
    link=dst/'current.next'; link.unlink(missing_ok=True); link.symlink_to(target.relative_to(dst),target_is_directory=True); os.replace(link,dst/'current')
    return {'path':str(target),'cacheKey':key,'version':manifest['version']}

def validate_runtime(path,gp=None):
    path=Path(path); m=read(path/'manifest.json',{})
    if not (path/'dmhost').is_file() or not (path/'romfs').is_dir(): raise Failure('运行目录不完整。')
    mods=gp.words('modules') if gp else [p.name.split('.')[0] for p in (path/'modules').glob('*.patched.bin')]
    if not mods: raise Failure('运行目录缺少代码模块。')
    for mod in mods:
        for ext in ('patched.bin','fixups.tsv','gates.tsv'):
            if not (path/'modules'/f'{mod}.{ext}').is_file(): raise Failure('重写代码模块不完整。')
    if gp and not (path/'romfs'/gp.get('romfs_marker')).exists(): raise Failure('游戏资源缺少配置指定的文件。')
    if m.get('graphics')=='vulkan':
        if not (path/'shaders/vk/vk_shaders.metallib').is_file(): raise Failure('Vulkan 着色器库缺失。')
    else:
        b=path/'shaders'/('b-'+m['chain']); reflected=list(b.glob('*_b.json'))
        if not reflected: raise Failure('Metal 着色器缓存缺失。')
        for p in reflected:
            r=read(p,{})
            if r.get('chain')!=m['chain'] or not p.with_suffix('.metallib').is_file(): raise Failure('Metal 着色器缓存不完整或版本不一致。')

def build(c,target='macos'):
    with c.lock('execution'):
        g=c.game(); c.begin('验证游戏、工具链与缓存',1,10)
        root,repo,env,up,gp,key=prepare(c,g,target); logs=root/'logs'; logs.mkdir(exist_ok=True); st=Stages(c,root)
        versions=list(dict.fromkeys(gp.words('shader_versions',gp.get('package'))+[gp.get('package')]))
        capture_gl=gp.get('shader_glslc_capture','off')=='on'; capture_vk=gp.get('shader_vk_capture','off')=='on'; vk=gp.get('graphics','nvn')=='vulkan'
        c.count=1+len(versions)+1+1+int(capture_gl)+int(capture_vk)+(1 if vk else 2)+1+1
        c.count+=1
        if target=='ios': c.count+=3
        base=next(x for x in g['packages'] if x['type']=='base' and x['version']==0)
        c.begin('校验游戏源文件');source_total=sum(x['size'] for x in g['packages']);source_done=0
        for x in g['packages']:
            c.check(); p=c.library/x['path']
            if not p.is_file() or digest(p,lambda n,t:c.progress(source_done+n,source_total))!=x['sha256']: raise Failure('托管源文件已丢失或内容发生改变，请重新导入。')
            source_done+=x['size']
        needed=sum(x['size'] for x in g['packages'])*2+(10 if target=='ios' else 3)*2**30
        if shutil.disk_usage(c.library).free<needed and not st.saved: raise Failure(f'准备游戏需要约 {needed/2**30:.0f} GB 可用空间。')
        dirs={}
        for ver in versions:
            upd=next((c.library/x['path'] for x in g['packages'] if x['type']=='update' and f"v{x['version']}"==ver),None)
            d=root/'extract'/ver; dirs[ver]=d
            st.run('解包与合并 '+ver,[d],lambda ver=ver,upd=upd: up.extract(c.nx(),c.keys,root/'extract',ver,c.library/base['path'],upd,None,logs,gp))
        aoc=root/'aoc'; dlcs=[(int(x['titleId'],16),x['version'],c.library/x['path']) for x in g['packages'] if x['type']=='dlc']
        def dlc():
            if dlcs: up.extract_aoc(c.nx(),c.keys,repo,root,int(gp.id,16),{'dlc':dlcs},logs)
            else: aoc.mkdir(); (aoc/'.empty').write_text('no DLC')
        st.run('处理 DLC',[aoc],dlc)
        patched=root/('patched_'+gp.get('package')); selected=dirs[gp.get('package')]
        st.run('重写原生代码',[patched],lambda:up.rewrite(sys.executable,repo,selected/'ExeFS',patched,env,logs,gp))
        if capture_gl: st.run('采集运行时 GLSLC 着色器',[selected/'glslc_capture'],lambda:up.capture_glslc(repo,dirs,gp.get('package'),patched,root,env,logs,gp))
        if capture_vk: st.run('采集运行时 Vulkan 着色器',[selected/'vk_capture'],lambda:up.capture_vk(repo,selected,patched,root,env,logs,gp))
        sh=root/'shader'; sh.mkdir(exist_ok=True)
        if vk:
            roots=[selected/'RomFS']+([selected/'vk_capture'] if capture_vk else [])
            def vulkan_shaders():
                c.run([sys.executable,repo/'dm/gfx/tools/vk_shaders.py',*roots,sh]+(['--ios',sh/'ios'] if target=='ios' else []),logs/'vk_shaders.log',env)
                if target=='ios':
                    from ipa import validate_shaders
                    validate_shaders(sh/'ios',gp,repo)
            st.run('转换并编译 Vulkan 着色器',[sh/'vk']+([sh/'ios'] if target=='ios' else []),vulkan_shaders)
        else:
            st.run('提取并核对着色器',[sh/'pkg'],lambda:up.split_shaders(sys.executable,repo,[d/'RomFS' for d in dirs.values()]+[d/'glslc_capture' for d in dirs.values() if (d/'glslc_capture').exists()],[d/'ExeFS/main' for d in dirs.values()],sh/'pkg',env,logs,gp))
            def shaders():
                up.PROG.stage('iOS shaders' if target=='ios' else 'Mac shaders',poll=ShaderProgress(gp,repo,sh/'cache'))
                try: c.run([sys.executable,repo/'dm/gfx/tools/dmsh_build.py',sh/'pkg',sh/'cache'],logs/'dmsh_build.log',dict(env,IOSOUT=str(sh/'ios')) if target=='ios' else env)
                finally: up.PROG.watch(None)
                if target=='ios':
                    from ipa import validate_shaders
                    validate_shaders(sh/'ios',gp,repo)
            st.run('转换并编译 Metal 着色器',[sh/'cache']+([sh/'ios'] if target=='ios' else []),shaders)
        if target == 'ios':
            from ipa import package
            c.begin('编译 iOS 应用并生成 IPA')
            return package(c,root,repo,env,gp,selected,patched,sh/'ios',aoc,up=up)
        st.run('编译 Mac 主程序',[root/'tools/dmhost'],lambda:compile_host(c,up,repo,env,root,gp))
        c.begin('检查并安装运行版本')
        return install(c,root,repo,gp,key,root/'tools/dmhost',selected/'RomFS',patched,sh if vk else sh/'cache',aoc)

def migrate(c):
    with c.lock('execution'):
        g=c.game()
        if g['id']!='01007EF00011E000': raise Failure('首版迁移仅支持已有《旷野之息》Mac 构建目录。')
        c.begin('验证迁移来源',1,4); root,repo,env,up,gp,key=prepare(c,g)
        src=Path(c.r['path']).resolve(); app=src/'ZeldaBreathOfTheWild.app/Contents/Resources'
        old=src/(g['id']+'_build'); m=read(src/'mac-work/build-manifest.json',{})
        chain=chain_of(repo,gp)
        oldchain=m.get('shader_chain','')
        if m.get('game')!=g['id'] or not re.fullmatch('[0-9a-f]{12}',oldchain): raise Failure('迁移来源没有有效的游戏与着色器构建记录。')
        patched=old/('patched_'+gp.get('package')); shader=old/'shader/cache'
        if not (app/'romfs'/gp.get('romfs_marker')).exists(): raise Failure('迁移目录缺少完整 Mac 游戏资源。')
        for mod,bid in gp.builds()[gp.get('package')].items():
            if mod=='display': continue
            f=patched/(mod+'.fixups.tsv')
            if not f.is_file() or bid not in f.read_text()[:4096]: raise Failure('迁移代码模块构建标识不匹配。')
        testmanifest={'chain':oldchain,'graphics':'nvn'}
        # Validate reflection, modules and resources before accepting the legacy cache.
        check=root/'migration-check'; shutil.rmtree(check,ignore_errors=True); check.mkdir()
        for name,p in [('dmhost',src/'ZeldaBreathOfTheWild.app/Contents/MacOS/dmhost'),('romfs',app/'romfs'),('modules',patched),('shaders',shader)]: (check/name).symlink_to(p)
        atomic(check/'manifest.json',testmanifest); validate_runtime(check,gp)
        if up.data_rows((app/'profile/shader_map.tsv').read_bytes()) != up.data_rows(gp.table('shader_map.tsv').read_bytes()): raise Failure('迁移来源的着色器映射表与当前配置不同。')
        if oldchain != chain:
            c.begin('为当前工具链更新着色器缓存',2,5)
            current=c.library/'games'/g['id']/'current'
            if read(current/'manifest.json',{}).get('chain')==chain:
                validate_runtime(current,gp);shader=current/'shaders'
            else:
                pkg=old/'shader/pkg'
                if not pkg.is_dir(): raise Failure('工具链已变化且迁移目录没有着色器包，请执行正常准备流程。')
                out=root/'migration-shader';out.mkdir(exist_ok=True)
                up.PROG.stage('migrate shaders',poll=ShaderProgress(gp,repo,out))
                try:c.run([sys.executable,repo/'dm/gfx/tools/dmsh_build.py',pkg,out],root/'logs/migration-shaders.log',dict(env,DMSH_PREFILL=str(shader)))
                finally:up.PROG.watch(None)
                shader=out
        c.begin('复用已验证资源')
        c.emit('message','源目录保持原样；运行版本使用克隆副本。')
        c.begin('重新编译配置化 Mac 主程序'); host=compile_host(c,up,repo,env,root,gp)
        c.begin('安装独立运行版本')
        return install(c,root,repo,gp,key,host,app/'romfs',patched,shader,app/'aoc',app/'font')

# nn::settings::LanguageCode values; no arbitrary host locale or UI language tags.
GAME_LANGUAGES=frozenset(('ja','en-US','fr','de','it','es','zh-CN','ko','nl','pt','ru','zh-TW','en-GB','fr-CA','es-419','zh-Hans','zh-Hant','pt-BR'))

def launch(c):
    language=c.r.get('gameLanguage','zh-Hans')
    if not isinstance(language,str) or language not in GAME_LANGUAGES:
        raise Failure('游戏语言代码无效，请在游戏详情中重新选择启动语言。')
    from toolchain import require_launch_environment
    require_launch_environment(c)
    with c.lock('execution'):
        g=c.game(); runtime=c.library/'games'/g['id']/'current'; validate_runtime(runtime)
        c.begin('游戏运行中',1,1)
        save=c.library/'saves'/g['id']; temp=c.library/'temp'/g['id']; pso=c.library/'games'/g['id']/'pso_user/pipelines.tsv'
        for p in (save,temp,pso.parent): p.mkdir(parents=True,exist_ok=True)
        config=c.r.get('inputConfig') or read(c.library/'mappings'/f"{g['id']}.json") or read(c.private/'default-input.json')
        if read(runtime/'manifest.json',{}).get('inputConfig') is False: config=None
        if config:
            from input_config import validate
            validate(config); cfg=c.private/'runtime-input'/f'{g["id"]}.json'; atomic(cfg,config)
        else: cfg=None
        env=c.env(g['id'],temp); env.update(DM_WINDOW='1',DM_AUDIO='1',DM_LANG=language,DM_ROMFS=str(runtime/'romfs'),DM_SAVE=str(save),DM_TEMP=str(temp),DM_AOC_DIR=str(runtime/'aoc'),DM_FONT_DIR=str(runtime/'font'),DM_MSL_DIR=str(runtime/'shaders'),DM_NVN_SHMAP=str(runtime/'profile/shader_map.tsv'),DM_PSO_USER=str(pso))
        if cfg: env['DM_INPUT_CONFIG']=str(cfg)
        log=c.private/'logs'/f'game-{g["id"]}.log'
        try: c.run([runtime/'dmhost',runtime/'modules'],log,env,cwd=temp)
        except Failure as error:
            with log.open('rb') as f:
                f.seek(max(0,log.stat().st_size-16384)); tail=f.read().decode(errors='replace')
            summary='游戏进程异常退出，启动器仍可使用。请查看日志或重试。'
            if 'no Metal device' in tail: summary='系统未提供可用的 Metal 设备。请确认使用 Apple Silicon 并在本机图形会话中启动。'
            elif 'chain' in tail and ('mismatch' in tail or 'expected' in tail): summary='运行时着色器链不一致，请重新准备游戏。'
            elif 'unimplemented' in tail or '[RED]' in tail: summary='游戏运行遇到引擎兼容问题。请查看日志；实验性配置可能尚不能正常运行。'
            raise Failure(summary,error.diagnostic)
        return {'gameId':g['id']}
