"""Version-specific nxnative profiles built only in each game's private cache."""
from __future__ import annotations
import ast
import importlib.util
import re
import sys
from pathlib import Path
from core import Failure, atomic, chain_of, digest

REQUIRED = {'derive_profile','provisional_prep','refine_after_rewrite','split_shaders',
            'build_shaders','chain_tables','set_keys','capture_shaders','decode_ue_shaders'}
TABLES = ('shader_map.tsv','shader_facts.tsv','shader_pairs.tsv')
PROFILE_STAGE = '生成版本配置'


def supported(engine):
    if engine is None: return False
    root=Path(engine)
    try:
        tree=ast.parse((root/'scripts/build_ipa_from_nsp.py').read_text())
        functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
        return REQUIRED<=functions.keys() and 'provisional' in [a.arg for a in functions['split_shaders'].args.args] and all(
            (root/p).is_file() for p in ('dm/games/profile_guess.py','dm/tools/nacp.py',
                'dm/gfx/tools/own_compilers.py','dm/gfx/tools/cb_extent.py'))
    except (OSError,SyntaxError): return False


def plan(game, profile, enabled=False):
    packages=[p for p in game['packages'] if p['type'] in ('base','update')]
    selected=max(packages,key=lambda p:p['version'],default=None) if enabled else None
    version=f"v{selected['version']}" if selected else profile['package']
    versions=list(dict.fromkeys(profile.get('shader_versions',profile['package']).split()+[version]))
    have={f"v{p['version']}" for p in packages}
    mismatch=any(any(p.get('builds',{}).get(m)!=bid for m,bid in profile['builds'].get(f"v{p['version']}",{}).items() if m!='display')
        for p in packages if f"v{p['version']}" in versions)
    own=enabled and (version not in profile['builds'] or not set(versions)<=have or mismatch)
    return dict(mode='derived' if own else 'registered',version=version,versions=[version] if own else versions)


def select_registered(gp,version):
    # This is the per-build private engine snapshot, never the player's checkout.
    path=gp.table('game.tsv')
    text,count=re.subn(r'^package\t[^\n]+',lambda m:'package\t'+version,path.read_text(),count=1,flags=re.M)
    if count!=1: raise Failure('版本配置与着色器产物不一致，请重新准备游戏。')
    path.write_text(text)
    return type(gp)(gp.dir)


def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def prepare_profile(c, st, up, registered, root, repo, env, selected, version):
    folder=root/'profiles'/registered.id
    # Upstream initializes these modules in main(); LumaDock calls its stages directly.
    sys.path.insert(0,str(repo/'dm/tools'))
    up.nacp=module(repo/'dm/tools/nacp.py','lumadock_nacp')
    up.pg=module(repo/'dm/games/profile_guess.py','lumadock_profile_guess')
    st.run(PROFILE_STAGE,[folder],lambda:up.derive_profile(registered,folder,version,selected,
        registered.words('modules')),milestone='profile')
    gp=type(registered)(folder)
    env.update(DM_GAMES_DIR=str(folder.parent),DM_GAMES_FIRST='1')
    up.provisional_prep(sys.executable,repo,env,root/'logs',gp)
    sources=up.pg.build_sources(selected/'ExeFS',selected/'RomFS',gp.words('modules'))
    changes={'graphics':(sources['graphics'][0],'Detected from the selected game build')}
    for flag,key in (('shader_glslc_capture','glslc_capture'),('shader_vk_capture','vk_capture'),
                     ('shader_gl_capture','gl_capture'),('shader_ue_decode','ue_decode')):
        changes[flag]=('on' if sources[key][0] else 'off','Detected from the selected game build')
    # Avoid rewriting the table on every retry when detection has not changed.
    if any(gp.get(k,'')!=v[0] for k,v in changes.items()): gp=up.set_keys(gp,changes,'Selected build')
    seal_profile(st,gp)
    return gp,sources


def seal_profile(st,gp):
    # The upstream refinement may update game.tsv; generated shader tables have
    # their own checkpoints and must not make the profile stage discard them.
    path=gp.table('game.tsv');key=str(path.relative_to(st.root))
    st.saved[PROFILE_STAGE][key]=[path.stat().st_size,digest(path)]
    atomic(st.file,st.saved)


def shaders(c,st,up,repo,root,env,gp,selected,patched,dirs,sources,target):
    logs=root/'logs';sh=root/'shader';sh.mkdir(exist_ok=True)
    graphics=sources['graphics'][0]
    if sources['glslc_capture'][0]:
        st.run('采集运行时 GLSLC 着色器',[selected/'glslc_capture'],lambda:up.capture_glslc(repo,dirs,gp.get('package'),patched,root,env,logs,gp),milestone='capture_gl')
    if sources['ue_decode'][0]:
        st.run('解码游戏着色器',[selected/'ue_shaders'],lambda:up.decode_ue_shaders(repo,dirs,gp.get('package'),patched,root,env,logs,gp))
    capture=None
    api='vk' if graphics=='vulkan' else 'gl'
    if graphics in ('vulkan','gl') and sources[api+'_capture'][0]:
        capture=selected/(api+'_capture')
        st.run('采集运行时着色器',[capture],lambda:up.capture_shaders(repo,selected,patched,root,env,logs,gp,api))
    if graphics in ('vulkan','gl'):
        roots=[selected/'RomFS']+([selected/'ExeFS/main'] if graphics=='gl' else [])+([capture] if capture else [])
        paths=[sh/api]+([sh/'ios'/api] if target=='ios' else [])
        def layer():
            getattr(up,'build_'+api+'_shaders')(sys.executable,repo,roots,sh,env,logs,gp,reuse=False,mac=target=='macos')
            if target=='ios':
                from ipa import validate_shaders
                validate_shaders(sh/'ios',gp,repo)
        st.run('转换并编译 Metal 着色器',paths,layer,milestone='shaders')
    else:
        oodle=None
        if sources['oodle_packs'][0] or sources['ue_legacy'][0]:
            oodle=lambda:{'DM_OODLE_HOST':str(up.build_mac_host(repo,root/'tools/dmhost',env,logs,gp)), 'DM_OODLE_MODULES':str(patched)}
        st.run('提取并核对着色器',[sh/'pkg',*[gp.table(t) for t in TABLES]],lambda:up.split_shaders(
            sys.executable,repo,[d/'RomFS' for d in dirs.values()],[d/'ExeFS/main' for d in dirs.values()],
            sh/'pkg',env,logs,gp,provisional=True,oodle=oodle),milestone='extract')
        outputs=[sh/'cache',gp.table('c1_full.tsv'),gp.table('cb_extent.tsv')]+([sh/'ios'] if target=='ios' else [])
        def nvn():
            up.build_shaders(sys.executable,repo,sh,repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate',env,logs,gp,mac=target=='macos')
            validate_tables(sh/'cache',gp,chain_of(repo,gp))
            if target=='ios':
                from ipa import validate_shaders
                validate_shaders(sh/'ios',gp,repo)
        st.run('转换并编译 Metal 着色器',outputs,nvn,milestone='shaders')
        validate_tables(sh/'cache',gp,chain_of(repo,gp))
    return sh


def validate_tables(cache,gp,chain):
    lib=Path(cache)/('b-'+chain)
    try:
        stamp=dict(line.split('\t',1) for line in (lib/'inputs.tsv').read_text().splitlines() if '\t' in line and not line.startswith('#'))
        if stamp.get('game')!=gp.id or not stamp.get('inputs') or stamp['inputs']=='none': raise ValueError('inputs')
        head=f"# chain b-{chain} inputs {stamp['inputs']} "
        if not all(gp.table(t).read_text().startswith(head) for t in ('c1_full.tsv','cb_extent.tsv')): raise ValueError('tables')
    except (OSError,ValueError): raise Failure('版本配置与着色器产物不一致，请重新准备游戏。')
