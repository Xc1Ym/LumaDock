"""Reduce a staged ARM64 runtime without removing runtime modules or notices."""
from pathlib import Path
import shutil
import subprocess


def compact_runtime(runtime):
    """Only call on a staging copy, before dependency rewriting and signing."""
    runtime = Path(runtime)
    before = payload_size(runtime)
    # The framework's Python.app, stdlib, extension modules and package metadata
    # are runtime inputs. Homebrew's development examples are not.
    shutil.rmtree(runtime/'python/share/doc', ignore_errors=True)
    # fontTools wheels ship generated C beside their Python/native modules.
    # Keep all executable modules, data, dist-info and license files.
    fonttools = runtime/'python/lib/python3.14/site-packages/fontTools'
    for path in fonttools.rglob('*.c'):
        path.unlink()
    shutil.rmtree(runtime/'converter/python/Crypto/SelfTest', ignore_errors=True)
    thinned = 0
    for path in runtime.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
            # Fail if a wheel has no ARM64 slice; do not ship a broken runtime.
            subprocess.run(['lipo', str(path), '-thin', 'arm64', '-output', str(path)], check=True)
            thinned += 1
    report = dict(removedBytes=before-payload_size(runtime), thinnedBinaries=thinned)
    print('Runtime size optimization:', report)
    return report


def payload_size(root):
    return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file() and not p.is_symlink())
