#!/usr/bin/env python3
"""Collect a relocatable runtime on an Apple Silicon release builder.

Requires Homebrew python@3.14/spirv-cross/zstd and .NET 10 SDK on PATH.
Players do not install these dependencies. Paths are discovered automatically.
"""
import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
from product import ROOT
from runtime_audit import SYSTEM_PATHS, rpaths, verify_portable_runtime


def run(args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)


def output(args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()


def cp(src, dst):
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(
            '__pycache__', 'test', 'tests', 'idlelib', 'tkinter', 'ensurepip', 'site-packages'))
    else:
        shutil.copy2(src, dst)


def macho(p):
    try:
        with p.open('rb') as f:
            return f.read(4) in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf')
    except OSError:
        return False


def build(out):
    brew = shutil.which('brew')
    dotnet_bin = shutil.which('dotnet')
    if not brew or not dotnet_bin:
        raise RuntimeError('Release builder requires Homebrew and .NET 10 SDK on PATH.')
    prefixes = {name:pathlib.Path(output([brew, '--prefix', name])).resolve()
                for name in ('python@3.14', 'spirv-cross', 'zstd')}
    python_bin = prefixes['python@3.14']/'bin/python3.14'
    python = pathlib.Path(output([python_bin, '-I', '-c', 'import sys; print(sys.base_prefix)']))
    installed = pathlib.Path(os.environ.get('LUMADOCK_SITE_PACKAGES', str(ROOT/'work/python-venv/lib/python3.14/site-packages')))
    if not (python/'Python').is_file() or not installed.is_dir():
        raise RuntimeError('Expected Homebrew framework Python and work/python-venv; see README.')
    dotnet = pathlib.Path(os.environ.get('DOTNET_ROOT', str(pathlib.Path(dotnet_bin).resolve().parent)))
    runtimes = [p for p in (dotnet/'shared/Microsoft.NETCore.App').glob('10.*') if re.fullmatch(r'10\.\d+\.\d+',p.name)]
    if not runtimes:
        raise RuntimeError('The selected DOTNET_ROOT has no .NET 10 runtime.')
    version = max(runtimes, key=lambda p:tuple(int(x) for x in p.name.split('.')))
    cp(python, out/'python')
    site = out/'python/lib/python3.14/site-packages'
    site.mkdir(parents=True, exist_ok=True)
    for p in installed.iterdir():
        if p.name.startswith(('capstone', 'lz4', 'fontTools', 'fonttools-')):
            cp(p, site/p.name)
    (out/'python/bin/python3').unlink(missing_ok=True)
    (out/'python/bin/python3').symlink_to('python3.14')
    (out/'bin').mkdir()
    for name in ('spirv-cross', 'zstd'):
        cp(prefixes[name]/'bin'/name, out/'bin'/name)
    cp(version, out/'dotnet/shared/Microsoft.NETCore.App'/version.name)
    cp(dotnet/'host', out/'dotnet/host')
    cp(dotnet/'dotnet', out/'dotnet/dotnet')
    (out/'bin/dotnet').symlink_to('../dotnet/dotnet')
    libs = out/'lib'
    libs.mkdir()
    todo = [p for root in (out/'python', out/'bin') for p in root.rglob('*')
            if p.is_file() and not p.is_symlink() and macho(p)]
    seen = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        for line in output(['otool', '-L', p]).splitlines()[1:]:
            dep = line.strip().split(' (')[0]
            target = None
            if dep.startswith(('/opt/homebrew/', '/usr/local/')):
                if dep.endswith('/Python'):
                    target = out/'python/Python'
                else:
                    source = pathlib.Path(dep).resolve()
                    target = libs/source.name
                    if not target.exists():
                        shutil.copy2(source, target)
                        todo.append(target)
            elif dep.startswith('@rpath/') and p.name == 'zstd':
                source = prefixes['zstd']/'lib'/pathlib.Path(dep).name
                target = libs/source.name
                if not target.exists():
                    shutil.copy2(source.resolve(), target)
                    todo.append(target)
            if target:
                run(['install_name_tool', '-change', dep, '@loader_path/'+os.path.relpath(target, p.parent), p],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.suffix == '.dylib' or p.name == 'Python':
            run(['install_name_tool', '-id', '@loader_path/'+p.name, p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for search in dict.fromkeys(rpaths(output(['otool','-l',p]))):
            if search.startswith('/') and not search.startswith(SYSTEM_PATHS):
                run(['install_name_tool','-delete_rpath',search,p],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        run(['codesign', '--force', '--sign', '-', p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(out/'python/include', ignore_errors=True)
    (out/'python/Headers').unlink(missing_ok=True)
    for p in (out/'python/bin').iterdir():
        if p.name not in ('python3', 'python3.14'):
            p.unlink()
    # Resources/Python.app is required by the framework launcher.
    env = dict(os.environ, DOTNET_ROOT=str(out/'dotnet'), PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    run([out/'python/bin/python3', '-B', '-I', '-c', 'import capstone,lz4.block,fontTools,ctypes,zlib,hashlib; print("Portable Python dependencies OK")'], env=env)
    run([out/'bin/dotnet', '--list-runtimes'], env=env)
    licenses = out/'licenses'
    licenses.mkdir()
    for src, name in [(prefixes['python@3.14']/'LICENSE', 'Python-LICENSE.txt'),
                      (dotnet/'LICENSE.txt', 'dotnet-LICENSE.txt'), (dotnet/'ThirdPartyNotices.txt', 'dotnet-ThirdPartyNotices.txt'),
                      (prefixes['spirv-cross']/'LICENSE', 'SPIRV-Cross-LICENSE.txt'),
                      (prefixes['zstd']/'LICENSE', 'Zstandard-LICENSE.txt')]:
        shutil.copy2(src, licenses/name)
    dependencies = output([brew, 'deps', '--installed', 'python@3.14', 'spirv-cross', 'zstd']).splitlines()
    for name in set(dependencies):
        prefix = pathlib.Path(output([brew, '--prefix', name]))
        for p in prefix.glob('*'):
            if p.is_file() and any(x in p.name.upper() for x in ('LICENSE', 'COPYING', 'NOTICE')):
                shutil.copy2(p, licenses/(name+'-'+p.name))
    versions = json.loads(output([out/'python/bin/python3', '-B', '-I', '-c',
        'import json,sys,importlib.metadata as m; print(json.dumps(dict(python=sys.version.split()[0], **{p:m.version(p) for p in ["capstone","lz4","fonttools"]})))']))
    versions.update(dotnet=version.name, spirvCross=output([brew, 'list', '--versions', 'spirv-cross']), zstd=output([brew, 'list', '--versions', 'zstd']))
    (out/'versions.json').write_text(json.dumps(versions, indent=2))
    print('Portable native runtime files:',verify_portable_runtime(out))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, default=ROOT/'work/Runtime')
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('An Apple Silicon Mac is required for the release runtime.')
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT/'work'):
        raise RuntimeError('Runtime output must be inside the ignored work/ directory.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(prefix='runtime-', dir=destination.parent))
    try:
        build(staging)
        backup = destination.with_name(destination.name+'.previous')
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            destination.rename(backup)
        staging.rename(destination)
        shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print('Runtime ready:', destination)


if __name__ == '__main__':
    main()
