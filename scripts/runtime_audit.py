"""Reject runtime links to a release builder's Homebrew or checkout."""
from pathlib import Path
import re
import subprocess

SYSTEM_PATHS=('/usr/lib/','/System/Library/')


def macho(path):
    with path.open('rb') as stream:
        return stream.read(4) in (b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf')


def rpaths(commands):
    return re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset',commands)


def check_load_paths(path,dependencies,commands):
    for line in dependencies.splitlines():
        # Universal binaries repeat a filename/architecture header for each slice.
        if ' (compatibility version' not in line:
            continue
        value=line.strip().split(' (compatibility')[0]
        if value.startswith('/') and not value.startswith(SYSTEM_PATHS):
            raise RuntimeError(f'External runtime dependency in {path}: {value}')
    for value in rpaths(commands):
        if value.startswith('/') and not value.startswith(SYSTEM_PATHS):
            raise RuntimeError(f'External runtime search path in {path}: {value}')


def verify_portable_runtime(runtime):
    runtime=Path(runtime).resolve();count=0
    for path in runtime.rglob('*'):
        if path.is_symlink():
            if path.readlink().is_absolute() or not path.resolve().is_relative_to(runtime):
                raise RuntimeError(f'External runtime symlink: {path}')
        elif path.is_file() and macho(path):
            architectures=subprocess.check_output(['lipo','-archs',path],text=True).strip()
            if architectures != 'arm64':
                raise RuntimeError(f'Expected ARM64-only runtime binary in {path}: {architectures}')
            dependencies=subprocess.check_output(['otool','-L',path],text=True)
            commands=subprocess.check_output(['otool','-l',path],text=True)
            check_load_paths(path,dependencies,commands);count+=1
    return count
