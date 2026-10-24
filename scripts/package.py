#!/usr/bin/env python3
"""Create a clean, ad-hoc-signed distribution using an explicit resource allowlist."""
import hashlib,json,os,pathlib,plistlib,shutil,subprocess,sys
from product import ROOT, RELEASE, PRODUCT, checksums
from build_dmg import build_dmg
APP=RELEASE/(PRODUCT['name']+'.app')
def run(a,**kw):return subprocess.run([str(x) for x in a],check=True,**kw)
def macho(p):
    try:
        with p.open('rb') as f:return f.read(4) in (b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf')
    except OSError:return False

def audit(root):
    files=[]
    banned={'.nsp','.xci','.nsz','.xcz','.ipa','.keys','.metallib','.patched.bin'}
    for p in root.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(root)
        converter=next((index for index,part in enumerate(rel.parts) if part=='converter' and index>0 and rel.parts[index-1]=='Runtime'),None)
        if (any(part.lower() in ('nsc_builder','nsz') for part in rel.parts) or p.name in ('squirrel.py','nsz')) and converter is None:
            raise RuntimeError('Conversion code outside the bundled runtime: '+str(rel))
        if p.name=='keys.txt':raise RuntimeError('Player keys in distribution: '+str(rel))
        if any(part.lower() in ('vendor','nxnative','nx_extract','dmsh_xlate_bin') for part in rel.parts) or p.name in ('nx_extract.dll','dmsh_xlate.dll','Ryujinx.Graphics.Shader.dll','LibHac.dll'):
            raise RuntimeError('Bundled external engine in distribution: '+str(rel))
        if p.suffix.lower() in banned or p.name in ('prod.keys','catalog.json','preferences.json','control.nacp','romfs_manifest.tsv') or any(x in rel.parts for x in ('romfs','RomFS','ExeFS','save','saves','pso_user','shader','extract')):
            raise RuntimeError('Private data in distribution: '+str(rel))
        if p.suffix.lower() in ('.jpg','.jpeg','.png','.webp') and 'Runtime' not in rel.parts: raise RuntimeError('Unexpected artwork in release: '+str(rel))
        files.append({'path':str(rel),'size':p.stat().st_size})
    return files

def main():
    env=dict(os.environ,CLANG_MODULE_CACHE_PATH=str(ROOT/'work/clang-cache'),SWIFTPM_MODULECACHE_OVERRIDE=str(ROOT/'work/swift-cache'))
    selected=pathlib.Path(env.get('DEVELOPER_DIR') or subprocess.check_output(['xcode-select','-p'],text=True).strip())
    if 'DEVELOPER_DIR' not in env and not (selected/'Platforms/MacOSX.platform').is_dir():
        selected=pathlib.Path('/Applications/Xcode.app/Contents/Developer')
    if not (selected/'Platforms/MacOSX.platform').is_dir():raise RuntimeError('Select a full Xcode installation with DEVELOPER_DIR; standalone Command Line Tools cannot build this app.')
    env['DEVELOPER_DIR']=str(selected)
    if not (ROOT/'work/Runtime/versions.json').is_file():raise RuntimeError('Run scripts/bundle_runtime.py first; a bundled runtime is required.')
    if not (ROOT/'work/Runtime/converter/manifest.json').is_file():raise RuntimeError('Bundled conversion backend is missing; rebuild the runtime.')
    if not (ROOT/'Assets/LumaDock.icns').is_file():raise RuntimeError('Run swift scripts/make_icons.swift first.')
    if '--skip-build' not in sys.argv:run(['swift','build','--disable-sandbox','--cache-path',ROOT/'work/spm-cache','-c','release'],cwd=ROOT,env=env)
    result=subprocess.check_output(['swift','build','--disable-sandbox','--cache-path',str(ROOT/'work/spm-cache'),'-c','release','--show-bin-path'],cwd=ROOT,env=env,text=True).strip()
    RELEASE.mkdir(exist_ok=True)
    if APP.exists():shutil.rmtree(APP)
    contents=APP/'Contents';resources=contents/'Resources';(contents/'MacOS').mkdir(parents=True);resources.mkdir()
    shutil.copy2(pathlib.Path(result)/PRODUCT['executable'],contents/'MacOS'/PRODUCT['executable'])
    info={'CFBundleName':PRODUCT['name'],'CFBundleDisplayName':PRODUCT['name'],'CFBundleIdentifier':PRODUCT['bundleIdentifier'],'CFBundleExecutable':PRODUCT['executable'],'CFBundlePackageType':'APPL','CFBundleShortVersionString':PRODUCT['version'],'CFBundleVersion':PRODUCT['build'],'CFBundleIconFile':'LumaDock.icns','LSMinimumSystemVersion':PRODUCT['minimumSystemVersion'],'LSApplicationCategoryType':'public.app-category.games','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication','CFBundleDevelopmentRegion':'en','CFBundleLocalizations':['en','zh-Hans'],'NSGameControllerUsageDescription':'Use connected controllers for input configuration and gameplay.'}
    (contents/'Info.plist').write_bytes(plistlib.dumps(info))
    ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git','gen','bin','obj','dmhost')
    shutil.copytree(ROOT/'Worker',resources/'Worker',ignore=ignore)
    shutil.copytree(ROOT/'work/Runtime',resources/'Runtime',symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(ROOT/'docs',resources/'docs',ignore=shutil.ignore_patterns('screenshots'))
    shutil.copytree(pathlib.Path(result)/'NSMac_NSMac.bundle',resources/'NSMac_NSMac.bundle')
    for language,display in [('en','LumaDock'),('zh-Hans','璃游 LumaDock')]:
        folder=resources/(language+'.lproj');folder.mkdir()
        usage='Use connected controllers for input configuration and gameplay.' if language=='en' else '在输入配置和游戏中使用玩家连接的手柄。'
        (folder/'InfoPlist.strings').write_text('"NSGameControllerUsageDescription" = "'+usage+'";\n"CFBundleName" = "'+display+'";\n"CFBundleDisplayName" = "'+display+'";\n')
    shutil.copy2(ROOT/'Assets/LumaDock.icns',resources/'LumaDock.icns')
    for name in ('LICENSE','README.md','README.zh-CN.md','product.json'):shutil.copy2(ROOT/name,resources/name)
    # Sign every nested native executable/library before sealing the outer app.
    native=[p for p in APP.rglob('*') if p.is_file() and not p.is_symlink() and macho(p)]
    for p in sorted(native,key=lambda p:len(p.parts),reverse=True):run(['codesign','--force','--sign','-',p],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    # Python's framework launcher is itself a nested application.
    for p in sorted(APP.rglob('*.app'),key=lambda p:len(p.parts),reverse=True):run(['codesign','--force','--sign','-',p],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    run(['codesign','--force','--sign','-',APP],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    run(['codesign','--verify','--deep','--strict',APP])
    files=audit(APP)
    (RELEASE/'distribution-audit.json').write_text(json.dumps({'product':PRODUCT['name'],'version':PRODUCT['version'],'engineMode':PRODUCT['engineMode'],'fileCount':len(files),'privateData':False,'files':files},indent=2))
    # Verify the packaged Python from its final location with user site packages disabled.
    run([resources/'Runtime/python/bin/python3','-B','-I','-c','import capstone,lz4.block,fontTools; print("Packaged runtime OK")'],env=dict(env,PYTHONNOUSERSITE='1'))
    run(['codesign','--verify','--deep','--strict',APP])
    if '--app-only' in sys.argv:return
    dmg=build_dmg(APP,RELEASE/f"{PRODUCT['name']}-{PRODUCT['version']}-arm64.dmg");checksums()
    print('Created:',dmg)
if __name__=='__main__':main()
