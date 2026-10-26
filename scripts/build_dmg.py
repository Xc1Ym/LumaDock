#!/usr/bin/env python3
"""Create a Finder-ready installer without GUI scripting or touching the signed app."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile

from product import ROOT, PRODUCT

LAYOUT = json.loads((ROOT/'scripts/dmg_layout.json').read_text())


def build_dmg(app, output):
    try:
        import dmgbuild
    except ImportError as exc:
        raise SystemExit('Install maintainer tools first: python -m pip install -r requirements-build.txt') from exc
    app, output = Path(app).resolve(), Path(output).resolve()
    if not (app/'Contents/Info.plist').is_file():
        raise ValueError('A complete signed LumaDock.app is required')
    identity=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if app.name != PRODUCT['name']+'.app' or identity['CFBundleShortVersionString'] != PRODUCT['version']:
        raise ValueError('The installer application must match product.json')
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if not env.get('DEVELOPER_DIR'):
        env['DEVELOPER_DIR'] = '/Applications/Xcode.app/Contents/Developer'
    with tempfile.TemporaryDirectory(prefix='.dmg-design-', dir=output.parent) as directory:
        work = Path(directory)
        guides = work/'Read me'; guides.mkdir()
        for name in ('Getting-started.md','使用说明.md','Environment.md','环境要求.md','Third-party-licenses.md','第三方许可.md'):
            shutil.copy2(ROOT/'docs'/name, guides/name)
        shutil.copy2(ROOT/'LICENSE', guides/'LumaDock-LICENSE.txt')
        shutil.copytree(ROOT/'docs/licenses',guides/'licenses')
        subprocess.run(['xcrun','swift',str(ROOT/'scripts/make_dmg_background.swift'),str(work),PRODUCT['version']],cwd=ROOT,env=env,check=True)
        settings = {
            # LZMA materially reduces the bundled engine/runtime download size.
            # The supported macOS 26+ systems can mount this format directly.
            'format':'ULMO', 'filesystem':'HFS+',
            'files':[str(app),str(guides)], 'symlinks':{'Applications':'/Applications'},
            'icon':str(ROOT/'Assets/LumaDock.icns'),
            'background':str(work/'installer-background.tiff'),
            'icon_locations':{name:tuple(position) for name,position in LAYOUT['iconPositions'].items()},
            # Finder's title and optional global bottom bars must not cover the footer.
            # Hiding an app extension adds FinderInfo and breaks strict signature verification.
            'hide_extensions':[], 'window_rect':((180,160),(LAYOUT['width'],LAYOUT['height']+32)),
            'default_view':'icon-view', 'include_icon_view_settings':True,
            'show_toolbar':False, 'show_sidebar':False, 'show_status_bar':False,
            'show_tab_view':False, 'show_pathbar':False, 'show_icon_preview':False,
            'arrange_by':None, 'grid_spacing':80, 'scroll_position':(0,0),
            'icon_size':LAYOUT['iconSize'], 'text_size':13, 'label_pos':'bottom',
            'create_hook':lambda mount,_:subprocess.run(['codesign','--verify','--deep','--strict',str(Path(mount)/app.name)],check=True),
        }
        # Build beside the destination and replace it only after hdiutil validation.
        temporary = work/'installer.dmg'
        dmgbuild.build_dmg(str(temporary),'LumaDock Installer',settings=settings)
        subprocess.run(['hdiutil','verify',str(temporary)],check=True)
        os.replace(temporary,output)
    return output


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,default=ROOT/'release/LumaDock.app')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print('Created:',build_dmg(args.app,args.output))
