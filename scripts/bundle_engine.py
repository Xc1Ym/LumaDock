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
from bundled_engine import inventory
from runtime_audit import macho
import subprocess


def stage_signed_engine(source, output):
    """Sign a build copy; the checked-in upstream snapshot remains byte-for-byte intact."""
    record = verify_bundle(source)
    if output.exists(): shutil.rmtree(output)
    shutil.copytree(source, output)
    signed = {}
    for path in sorted(output.rglob('*')):
        if not path.is_file() or not macho(path): continue
        check = subprocess.run(['codesign', '--verify', '--strict', path], capture_output=True)
        if check.returncode == 0: continue
        # Universal tools may have only their ARM64 slice linker-signed. Seal
        # every slice in this verified build copy before the app is assembled.
        rel = path.relative_to(output).as_posix()
        signed[rel] = record['files'][rel]
        subprocess.run(['codesign', '--force', '--sign', '-', path], check=True, capture_output=True)
        subprocess.run(['codesign', '--verify', '--strict', path], check=True, capture_output=True)
    if signed:
        record['adHocSignedFiles'] = signed
        record['files'] = inventory(output)
        (output/'manifest.json').write_text(json.dumps(record, indent=2, sort_keys=True)+'\n')
    verify_bundle(output)


def main():
    resources = ROOT/'work/engine-resources'
    stage_signed_engine(ROOT/'Engine/nxnative', resources/'Engine/nxnative')
    c = Context(dict(operation='prepareEngine', resources=str(resources), privateRoot=str(ROOT/'work/engine-build')))
    if (ROOT/'work/Runtime/versions.json').is_file(): c.runtime = ROOT/'work/Runtime'
    result = prepare(c)
    source = Path(result['path'])/'tools/nx_extract'
    output = ROOT/'work/EngineReader'
    if output.exists(): shutil.rmtree(output)
    shutil.copytree(source, output)
    shutil.copy2(ROOT/'docs/licenses/LibHac-LICENSE.txt', output/'LibHac-LICENSE.txt')
    (output/'manifest.json').write_text(json.dumps(dict(fingerprint=result['fingerprint'], files={p.name:digest(p) for p in output.iterdir() if p.is_file()}), indent=2)+'\n')
    print('Bundled reader:', output)


if __name__ == '__main__': main()
