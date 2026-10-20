#!/usr/bin/env python3
"""Verify public artifacts without accessing a player library or key file."""
import hashlib
import json
import plistlib
import struct
import subprocess
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
        for required in ('README.md', 'README.zh-CN.md', 'LICENSE', '.github/workflows/ci.yml', 'Assets/LumaDock.ico', 'Vendor/nxnative/LICENSE'):
            assert PRODUCT['name']+'/'+required in names, f'Missing source file: {required}'


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
    source = RELEASE/f"{PRODUCT['name']}-{PRODUCT['version']}-source.zip"
    verify_source(source)
    dmg = RELEASE/f"{PRODUCT['name']}-{PRODUCT['version']}-arm64.dmg"
    subprocess.run(['hdiutil', 'verify', dmg], check=True, stdout=subprocess.DEVNULL)
    entries = dict(line.strip().split('  ', 1)[::-1] for line in (RELEASE/'SHA256SUMS').read_text().splitlines())
    assert set(entries) == {source.name, dmg.name}
    for path in (source, dmg):
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == entries[path.name]
    print(f"Verified {PRODUCT['name']} {PRODUCT['version']}: icons, {len(files)} app files, source ZIP, DMG, signatures and SHA-256")


if __name__ == '__main__':
    main()
