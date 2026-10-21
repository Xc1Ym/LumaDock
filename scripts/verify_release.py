#!/usr/bin/env python3
"""Verify public artifacts without accessing a player library or key file."""
import hashlib
import json
import plistlib
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import zipfile
from product import ROOT, RELEASE, PRODUCT
from package import audit


def verify_icons():
    assets = ROOT/'Assets'
    ico = (assets/'LumaDock.ico').read_bytes()
    reserved, kind, count = struct.unpack_from('<HHH', ico)
    assert (reserved, kind, count) == (0, 1, 7), 'Invalid ICO directory'
    dimensions = []
    for index in range(count):
        w, h, _, _, planes, bits, length, offset = struct.unpack_from('<BBBBHHII', ico, 6+index*16)
        assert planes == 1 and bits == 32 and offset+length <= len(ico)
        data = ico[offset:offset+length]
        assert data.startswith(b'\x89PNG\r\n\x1a\n')
        width, height = struct.unpack_from('>II', data, 16)
        assert (width, height) == (w or 256, h or 256)
        dimensions.append(width)
    assert dimensions == [16, 24, 32, 48, 64, 128, 256]
    icns = (assets/'LumaDock.icns').read_bytes()
    assert icns[:4] == b'icns' and struct.unpack_from('>I', icns, 4)[0] == len(icns)


def verify_source(path):
    from source_archive import EXCLUDED,SOURCE_DIRS,SOURCE_FILES,SOURCE_ARTWORK
    banned = {'.keys', '.nsp', '.xci', '.nsz', '.ipa', '.metallib', '.pyc'}
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        for name in names:
            from pathlib import PurePosixPath
            rel = PurePosixPath(name)
            assert rel.parts[0] == PRODUCT['name'] and '..' not in rel.parts
            assert rel.parts[1] in SOURCE_DIRS | SOURCE_FILES, f'Unexpected source root: {name}'
            assert not (set(rel.parts[1:]) & EXCLUDED), f'Private build directory: {name}'
            assert rel.suffix.lower() not in banned and rel.name not in ('prod.keys', 'catalog.json', 'preferences.json')
            if rel.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.ico','.icns','.svg'):
                assert '/'.join(rel.parts[1:]) in SOURCE_ARTWORK, f'Unexpected artwork: {name}'
            assert archive.getinfo(name).file_size < 100*1024*1024, f'File exceeds GitHub size limit: {name}'
        for required in ('README.md', 'README.zh-CN.md', 'LICENSE', '.github/workflows/ci.yml', 'Assets/LumaDock.ico'):
            assert PRODUCT['name']+'/'+required in names, f'Missing source file: {required}'


def verify_dmg(path):
    """Check the shipped Finder layout and signed payload without launching the app."""
    from pathlib import Path
    from ds_store import DSStore
    from build_dmg import LAYOUT
    subprocess.run(['hdiutil','verify',str(path)],check=True,stdout=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix='dmg-verify-',dir=ROOT/'work') as directory:
        mount=Path(directory)/'volume';mount.mkdir()
        subprocess.run(['hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(mount),str(path)],check=True,stdout=subprocess.DEVNULL)
        try:
            assert {p.name for p in mount.iterdir() if not p.name.startswith('.')} == {PRODUCT['name']+'.app','Applications','Read me'}
            assert (mount/'Applications').is_symlink() and (mount/'Applications').readlink() == Path('/Applications')
            assert (mount/'.background.tiff').is_file() and (mount/'.VolumeIcon.icns').is_file()
            description=subprocess.check_output(['sips','-g','pixelWidth','-g','pixelHeight','-g','dpiWidth','-g','dpiHeight',str(mount/'.background.tiff')],text=True)
            pixels={line.strip().split(':',1)[0]:line.strip().split(':',1)[1].strip() for line in description.splitlines() if ':' in line}
            assert int(pixels['pixelWidth'])==LAYOUT['width']*2 and int(pixels['pixelHeight'])==LAYOUT['height']*2
            assert float(pixels['dpiWidth'])==144 and float(pixels['dpiHeight'])==144
            with DSStore.open(str(mount/'.DS_Store'),'r') as store:
                window=store['.']['bwsp'];view=store['.']['icvp']
                assert not window['ShowToolbar'] and not window['ShowSidebar']
                assert window['WindowBounds'] == '{{180, 160}, {%d, %d}}' % (LAYOUT['width'],LAYOUT['height']+32)
                assert view['backgroundType']==2 and view['backgroundImageAlias']
                assert view['arrangeBy']=='none' and view['iconSize']==LAYOUT['iconSize']
                for name,position in LAYOUT['iconPositions'].items():
                    assert store[name]['Iloc']==tuple(position), f'Wrong installer position: {name}'
                    assert 0<position[0]<LAYOUT['width'] and 0<position[1]<LAYOUT['height']-40
            for name in ('Getting-started.md','使用说明.md','Environment.md','环境要求.md','Third-party-licenses.md','第三方许可.md'):
                assert (mount/'Read me'/name).read_bytes()==(ROOT/'docs'/name).read_bytes()
            assert (mount/'Read me/LumaDock-LICENSE.txt').read_bytes()==(ROOT/'LICENSE').read_bytes()
            app=mount/(PRODUCT['name']+'.app')
            info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
            assert info['CFBundleShortVersionString']==PRODUCT['version']
            subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
            audit(mount)
        finally:
            subprocess.run(['hdiutil','detach',str(mount)],check=True,stdout=subprocess.DEVNULL)
    print('Verified installer: Finder layout, Retina background, documentation, Applications link, clean data and app signature')


def verify_runtime_relocation(app):
    """Run bundled tools from a renamed app in a different Unicode/space path."""
    from runtime_audit import verify_portable_runtime
    count=verify_portable_runtime(app/'Contents/Resources/Runtime')
    with tempfile.TemporaryDirectory(prefix='runtime-relocation-',dir=ROOT/'work') as directory:
        moved=Path(directory)/'中文 空格目录'/'Renamed LumaDock.app'
        moved.parent.mkdir()
        subprocess.run(['cp','-cR',str(app),str(moved)],check=True)
        resources=moved/'Contents/Resources'
        private=Path(directory)/'private'
        script='''
import sys,json,hashlib
from pathlib import Path
resources=Path(sys.argv[1]);sys.path.insert(0,str(resources/'Worker'))
from core import Context
from toolchain import probe
import capstone,lz4.block,fontTools
c=Context(dict(schema=1,operation='preflight',resources=str(resources),privateRoot=sys.argv[2]))
paths=[sys.executable,sys.base_prefix,capstone.__file__,lz4.block.__file__,fontTools.__file__]
assert all(Path(p).resolve().is_relative_to(c.runtime.resolve()) for p in paths),paths
assert lz4.block.decompress(lz4.block.compress(b'portable'))==b'portable'
assert next(capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM).disasm(bytes.fromhex('1f2003d5'),0)).mnemonic=='nop'
ok,dotnet=probe(c,[c.runtime/'bin/dotnet','--list-runtimes'])
assert ok and str(c.runtime/'dotnet/shared/Microsoft.NETCore.App') in dotnet,dotnet
assert c.engine is None
assert not (resources/'Vendor').exists()
assert not (c.runtime/'nx_extract').exists()
for name,args in [('spirv-cross',['--revision']),('zstd',['--version'])]:
 ok,text=probe(c,[c.runtime/'bin'/name,*args]);assert ok and text,text
print(json.dumps(dict(python=sys.version.split()[0],paths=paths,dotnet=dotnet)))
'''
        env=dict(os.environ,PATH='/usr/bin:/bin:/usr/sbin:/sbin',PYTHONHOME='/invalid-builder-python',PYTHONPATH='/invalid-builder-modules',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
        result=subprocess.run([resources/'Runtime/python/bin/python3','-B','-I','-c',script,str(resources),str(private)],env=env,text=True,capture_output=True,timeout=100)
        assert result.returncode==0,result.stderr+'\n'+result.stdout
        report=json.loads(result.stdout)
        assert all(str(moved) in path for path in report['paths'])
        assert str(moved) in report['dotnet']
    print(f'Verified runtime relocation: {count} native files, relative symlinks, Python/extensions, .NET and generic conversion tools; no bundled engine')


def main():
    verify_icons()
    app = RELEASE/(PRODUCT['name']+'.app')
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    assert info['CFBundleShortVersionString'] == PRODUCT['version']
    assert info['CFBundleIdentifier'] == PRODUCT['bundleIdentifier']
    assert info['CFBundleIconFile'] == 'LumaDock.icns'
    assert (app/'Contents/Resources'/info['CFBundleIconFile']).is_file()
    for name in ('README.md','README.zh-CN.md'):
        assert (app/'Contents/Resources'/name).read_bytes() == (ROOT/name).read_bytes(), f'Packaged documentation is stale: {name}'
    assert info['CFBundleDevelopmentRegion'] == 'en'
    assert info['CFBundleLocalizations'] == ['en','zh-Hans']
    bundle = app/'Contents/Resources/NSMac_NSMac.bundle'
    strings = next((p for p in (bundle/'Contents/Resources/Localizable.json',bundle/'Localizable.json') if p.is_file()),None)
    assert strings is not None, 'Missing packaged localization catalog'
    assert len(json.loads(strings.read_text())) > 350
    for language in ('en','zh-Hans'):
        assert (app/'Contents/Resources'/(language+'.lproj')/'InfoPlist.strings').is_file()
    files = audit(app)
    report = json.loads((RELEASE/'distribution-audit.json').read_text())
    assert report['privateData'] is False and report['fileCount'] == len(files)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', app], check=True)
    verify_runtime_relocation(app)
    source = RELEASE/f"{PRODUCT['name']}-{PRODUCT['version']}-source.zip"
    verify_source(source)
    dmg = RELEASE/f"{PRODUCT['name']}-{PRODUCT['version']}-arm64.dmg"
    verify_dmg(dmg)
    entries = dict(line.strip().split('  ', 1)[::-1] for line in (RELEASE/'SHA256SUMS').read_text().splitlines())
    assert set(entries) == {source.name, dmg.name}
    for path in (source, dmg):
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == entries[path.name]
    print(f"Verified {PRODUCT['name']} {PRODUCT['version']}: icons, {len(files)} app files, source ZIP, DMG, signatures and SHA-256")


if __name__ == '__main__':
    main()
