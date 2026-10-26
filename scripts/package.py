#!/usr/bin/env python3
"""Create a clean, ad-hoc-signed distribution using an explicit resource allowlist."""
import argparse,hashlib,json,os,pathlib,plistlib,shutil,subprocess,sys,tempfile
from product import ROOT, RELEASE, PRODUCT, checksums
from build_dmg import build_dmg
def run(a,**kw):return subprocess.run([str(x) for x in a],check=True,**kw)
def macho(p):
    try:
        with p.open('rb') as f:return f.read(4) in (b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf')
    except OSError:return False

def audit(root):
    files=[]
    sys.path.insert(0,str(ROOT/'Worker'))
    from bundled_engine import verify_bundle
    engine_roots=list(root.glob('**/Resources/Engine/nxnative'))
    for engine_root in engine_roots:
        verify_bundle(engine_root)
        reader_root=engine_root.parent/'reader'
        if reader_root.exists():
            record=json.loads((reader_root/'manifest.json').read_text())
            actual={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in reader_root.iterdir() if p.is_file() and p.name!='manifest.json'}
            if not actual or actual!=record.get('files') or any(p.is_dir() or p.is_symlink() for p in reader_root.iterdir()):raise RuntimeError('Bundled reader integrity check failed')
    banned={'.nsp','.xci','.nsz','.xcz','.ipa','.keys','.metallib','.patched.bin'}
    for p in root.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(root)
        if any(p.is_relative_to(engine_root) for engine_root in engine_roots):
            files.append({'path':str(rel),'size':p.stat().st_size});continue
        reader = any(p.parent == engine_root.parent/'reader' for engine_root in engine_roots)
        converter=next((index for index,part in enumerate(rel.parts) if part=='converter' and index>0 and rel.parts[index-1]=='Runtime'),None)
        if (any(part.lower() in ('nsc_builder','nsz') for part in rel.parts) or p.name in ('squirrel.py','nsz')) and converter is None:
            raise RuntimeError('Conversion code outside the bundled runtime: '+str(rel))
        if p.name=='keys.txt':raise RuntimeError('Player keys in distribution: '+str(rel))
        if not reader and (any(part.lower() in ('vendor','nxnative','nx_extract','dmsh_xlate_bin') for part in rel.parts) or p.name in ('nx_extract.dll','dmsh_xlate.dll','Ryujinx.Graphics.Shader.dll','LibHac.dll')):
            raise RuntimeError('Bundled external engine in distribution: '+str(rel))
        if p.suffix.lower() in banned or p.name in ('prod.keys','catalog.json','preferences.json','control.nacp','romfs_manifest.tsv') or any(x in rel.parts for x in ('romfs','RomFS','ExeFS','save','saves','pso_user','shader','extract')):
            raise RuntimeError('Private data in distribution: '+str(rel))
        if p.suffix.lower() in ('.jpg','.jpeg','.png','.webp') and 'Runtime' not in rel.parts: raise RuntimeError('Unexpected artwork in release: '+str(rel))
        files.append({'path':str(rel),'size':p.stat().st_size})
    return files

def require_inactive(app):
    """Never remove tools or resources from a bundle a process is using."""
    if not app.exists(): return
    result=subprocess.run(['/bin/ps','-ww','-axo','comm='],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('Cannot check running applications; choose a new --output-dir instead of replacing an existing app.')
    prefix=str(app.resolve())+os.sep
    for line in result.stdout.splitlines():
        executable=line.strip()
        if executable.startswith(prefix) or executable.startswith('/') and pathlib.Path(executable).resolve().is_relative_to(app.resolve()):
            raise RuntimeError('The output app is running. Keep its files intact; quit it or choose a new --output-dir: '+str(app))


def publish_app(staged,target,validate=None):
    require_inactive(target)
    backup=staged.parent/'previous.app'
    existed=target.exists()
    if existed: target.rename(backup)
    try:
        staged.rename(target)
        if validate: validate(target)
    except BaseException:
        if not staged.exists() and target.exists(): target.rename(staged)
        if existed: backup.rename(target)
        raise


def verify_app_runtime(app,env):
    resources=app/'Contents/Resources';runtime=resources/'Runtime'
    # Match the worker's GUI environment; a system/Homebrew tool must not hide a
    # missing bundled executable. Exercise the same Python -> child lookup.
    smoke_env=dict(env,PATH=os.pathsep.join([str(runtime/'bin'),str(runtime/'python/bin'),'/usr/bin','/bin','/usr/sbin','/sbin']),PYTHONNOUSERSITE='1')
    code="import capstone,lz4.block,fontTools,pathlib,shutil,subprocess,sys; p=shutil.which('spirv-cross'); assert p and pathlib.Path(p).parent==pathlib.Path(sys.argv[1]), 'Bundled spirv-cross missing'; subprocess.run(['spirv-cross','--revision'],check=True,stdout=subprocess.DEVNULL); print('Packaged Python and spirv-cross child OK')"
    run([runtime/'python/bin/python3','-B','-I','-c',code,runtime/'bin'],env=smoke_env)
    run(['codesign','--verify','--deep','--strict',app])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-only',action='store_true')
    parser.add_argument('--skip-build',action='store_true')
    parser.add_argument('--output-dir',type=pathlib.Path,default=RELEASE,help='Build into a separate directory when another copy is running.')
    args=parser.parse_args()
    output=args.output_dir.resolve();target=output/(PRODUCT['name']+'.app')
    require_inactive(target)
    env=dict(os.environ,CLANG_MODULE_CACHE_PATH=str(ROOT/'work/clang-cache'),SWIFTPM_MODULECACHE_OVERRIDE=str(ROOT/'work/swift-cache'))
    selected=pathlib.Path(env.get('DEVELOPER_DIR') or subprocess.check_output(['xcode-select','-p'],text=True).strip())
    if 'DEVELOPER_DIR' not in env and not (selected/'Platforms/MacOSX.platform').is_dir():
        selected=pathlib.Path('/Applications/Xcode.app/Contents/Developer')
    if not (selected/'Platforms/MacOSX.platform').is_dir():raise RuntimeError('Select a full Xcode installation with DEVELOPER_DIR; standalone Command Line Tools cannot build this app.')
    env['DEVELOPER_DIR']=str(selected)
    if not (ROOT/'work/Runtime/versions.json').is_file():raise RuntimeError('Run scripts/bundle_runtime.py first; a bundled runtime is required.')
    if not (ROOT/'work/Runtime/converter/manifest.json').is_file():raise RuntimeError('Bundled conversion backend is missing; rebuild the runtime.')
    if not (ROOT/'Assets/LumaDock.icns').is_file():raise RuntimeError('Run swift scripts/make_icons.swift first.')
    if not args.skip_build:run(['swift','build','--disable-sandbox','--cache-path',ROOT/'work/spm-cache','-c','release'],cwd=ROOT,env=env)
    result=subprocess.check_output(['swift','build','--disable-sandbox','--cache-path',str(ROOT/'work/spm-cache'),'-c','release','--show-bin-path'],cwd=ROOT,env=env,text=True).strip()
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.lumadock-package-',dir=output) as directory:
        app=pathlib.Path(directory)/(PRODUCT['name']+'.app')
        contents=app/'Contents';resources=contents/'Resources';(contents/'MacOS').mkdir(parents=True);resources.mkdir()
        shutil.copy2(pathlib.Path(result)/PRODUCT['executable'],contents/'MacOS'/PRODUCT['executable'])
        info={'CFBundleName':PRODUCT['name'],'CFBundleDisplayName':PRODUCT['name'],'CFBundleIdentifier':PRODUCT['bundleIdentifier'],'CFBundleExecutable':PRODUCT['executable'],'CFBundlePackageType':'APPL','CFBundleShortVersionString':PRODUCT['version'],'CFBundleVersion':PRODUCT['build'],'CFBundleIconFile':'LumaDock.icns','LSMinimumSystemVersion':PRODUCT['minimumSystemVersion'],'LSApplicationCategoryType':'public.app-category.games','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication','CFBundleDevelopmentRegion':'en','CFBundleLocalizations':['en','zh-Hans'],'NSGameControllerUsageDescription':'Use connected controllers for input configuration and gameplay.'}
        (contents/'Info.plist').write_bytes(plistlib.dumps(info))
        ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git','gen','bin','obj','dmhost')
        shutil.copytree(ROOT/'Worker',resources/'Worker',ignore=ignore)
        shutil.copytree(ROOT/'work/Runtime',resources/'Runtime',symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copytree(ROOT/'Engine/nxnative',resources/'Engine/nxnative')
        if not (ROOT/'work/EngineReader/manifest.json').is_file(): raise RuntimeError('Run scripts/bundle_engine.py first.')
        shutil.copytree(ROOT/'work/EngineReader',resources/'Engine/reader')
        shutil.copytree(ROOT/'docs',resources/'docs',ignore=shutil.ignore_patterns('screenshots'))
        shutil.copytree(pathlib.Path(result)/'NSMac_NSMac.bundle',resources/'NSMac_NSMac.bundle')
        for language,display in [('en','LumaDock'),('zh-Hans','璃游 LumaDock')]:
            folder=resources/(language+'.lproj');folder.mkdir()
            usage='Use connected controllers for input configuration and gameplay.' if language=='en' else '在输入配置和游戏中使用玩家连接的手柄。'
            (folder/'InfoPlist.strings').write_text('"NSGameControllerUsageDescription" = "'+usage+'";\n"CFBundleName" = "'+display+'";\n"CFBundleDisplayName" = "'+display+'";\n')
        shutil.copy2(ROOT/'Assets/LumaDock.icns',resources/'LumaDock.icns')
        for name in ('LICENSE','README.md','README.zh-CN.md','product.json'):shutil.copy2(ROOT/name,resources/name)
        # Sign every nested native executable/library before sealing the outer app.
        native=[p for p in app.rglob('*') if p.is_file() and not p.is_symlink() and macho(p)]
        for p in sorted(native,key=lambda p:len(p.parts),reverse=True):
            # Keep the pinned engine and reader hashes stable. Their .NET apphosts
            # already carry valid ad-hoc signatures from the upstream/SDK build.
            if p.is_relative_to(resources/'Engine'):
                run(['codesign','--verify','--strict',p])
            else: run(['codesign','--force','--sign','-',p],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        # Python's framework launcher is itself a nested application.
        for p in sorted(app.rglob('*.app'),key=lambda p:len(p.parts),reverse=True):run(['codesign','--force','--sign','-',p],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        run(['codesign','--force','--sign','-',app],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        run(['codesign','--verify','--deep','--strict',app])
        files=audit(app)
        verify_app_runtime(app,env)
        publish_app(app,target,lambda final:verify_app_runtime(final,env))
        (output/'distribution-audit.json').write_text(json.dumps({'product':PRODUCT['name'],'version':PRODUCT['version'],'engineMode':PRODUCT['engineMode'],'fileCount':len(files),'privateData':False,'files':files},indent=2))
    if args.app_only:return
    dmg=build_dmg(target,output/f"{PRODUCT['name']}-{PRODUCT['version']}-arm64.dmg");checksums(output)
    print('Created:',dmg)
if __name__=='__main__':main()
