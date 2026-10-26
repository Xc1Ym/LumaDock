#!/usr/bin/env python3
"""Compile the bundled engine's metadata reader before packaging the app."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Worker'))
from core import Context, digest
from engine import prepare
from bundled_engine import verify_bundle


def main():
    verify_bundle(ROOT/'Engine/nxnative')
    c = Context(dict(operation='prepareEngine', resources=str(ROOT), privateRoot=str(ROOT/'work/engine-build')))
    result = prepare(c)
    source = Path(result['path'])/'tools/nx_extract'
    output = ROOT/'work/EngineReader'
    if output.exists(): shutil.rmtree(output)
    shutil.copytree(source, output)
    shutil.copy2(ROOT/'docs/licenses/LibHac-LICENSE.txt', output/'LibHac-LICENSE.txt')
    (output/'manifest.json').write_text(json.dumps(dict(fingerprint=result['fingerprint'], files={p.name:digest(p) for p in output.iterdir() if p.is_file()}), indent=2)+'\n')
    print('Bundled reader:', output)


if __name__ == '__main__': main()
