#!/usr/bin/env python3
"""Import a pinned public nxnative tree and reapply the local controller policy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Worker'))
from bundled_engine import inventory, verify_bundle

UPSTREAM = 'https://github.com/seedds/nxnative.git'
OMIT_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.pdb'}


def patch_controller(root):
    header = ROOT/'scripts/patches/controller_native.h'
    shutil.copy2(header, root/'dm/host/controller_native.h')
    for name, old in (
        ('dm/host/front_mac.m', 'K(g.buttonB, DM_BTN_A); K(g.buttonA, DM_BTN_B); K(g.buttonY, DM_BTN_X); K(g.buttonX, DM_BTN_Y);'),
        ('dm/ios/Sources/DmGamepad.m', 'K(g.buttonB, B_A); K(g.buttonA, B_B); K(g.buttonY, B_X); K(g.buttonX, B_Y);'),
    ):
        path = root/name
        text = path.read_text()
        if text.count(old) != 1:
            raise RuntimeError('Upstream controller interface changed: '+name)
        text = text.replace('#include "haptics_apple.h"', '#include "haptics_apple.h"\n#include "controller_native.h"')
        text = text.replace(old+'   // by position: right A, bottom B, top X, left Y', 'm |= luma_face_buttons(g);   // automatic Nintendo / Xbox / PS semantics')
        text = text.replace('// Controllers: buttons by position as on the iPhone (right A, bottom B, top X, left Y),', '// Controllers: automatic Nintendo / Xbox / PS face-button semantics,')
        text = text.replace('map by position: bottom = B, right = A, left = Y, top = X (same positions as on a Switch controller).', 'use automatic Nintendo / Xbox / PS semantics (controller_native.h).')
        if old in text or text.count('luma_face_buttons(g)') != 1:
            raise RuntimeError('Controller patch did not apply cleanly: '+name)
        path.write_text(text)


def sync(checkout, target):
    checkout, target = Path(checkout).resolve(), Path(target).resolve()
    sha = subprocess.check_output(['git', '-C', checkout, 'rev-parse', 'HEAD'], text=True).strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.nxnative-', dir=target.parent) as directory:
        stage = Path(directory)/'source'; stage.mkdir()
        paths = subprocess.check_output(['git', '-C', checkout, 'ls-files', '-z']).decode().split('\0')
        for name in filter(None, paths):
            rel = Path(name)
            if rel.parts[0] not in {'dm', 'scripts', 'docs', 'LICENSE', 'README.md'} or rel.name == 'AGENTS.md' or rel.suffix.lower() in OMIT_SUFFIXES:
                continue
            if (checkout/rel).is_symlink(): raise RuntimeError('Upstream symlink is not allowed: '+name)
            # Read committed bytes, never a builder's modified working copy.
            data = subprocess.check_output(['git', '-C', checkout, 'show', sha+':'+name])
            dest = stage/rel; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
            if (checkout/rel).stat().st_mode & 0o111: dest.chmod(0o755)
        patch_controller(stage)
        record = dict(schema=1, repository=UPSTREAM, revision=sha,
                      controllerPatch=hashlib.sha256((ROOT/'scripts/patches/controller_native.h').read_bytes()).hexdigest(), files=inventory(stage))
        (stage/'manifest.json').write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
        verify_bundle(stage)
        backup = Path(directory)/'previous'
        if target.exists(): target.rename(backup)
        try: stage.rename(target)
        except BaseException:
            if backup.exists(): backup.rename(target)
            raise
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'Engine/nxnative')
    args = parser.parse_args()
    if args.checkout:
        record = sync(args.checkout, args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='lumanx-upstream-') as directory:
            subprocess.run(['git', 'clone', '--depth', '1', UPSTREAM, directory], check=True)
            record = sync(directory, args.output)
    print('Imported nxnative '+record['revision']+' ('+str(len(record['files']))+' files)')


if __name__ == '__main__': main()
