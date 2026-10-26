"""Integrity and private-data boundary for the shipped nxnative source snapshot."""
import hashlib
import json
from pathlib import Path
import re

PRIVATE_SUFFIXES = {'.nsp', '.xci', '.nsz', '.xcz', '.nca', '.nso', '.nro', '.tik', '.cert', '.sav', '.keys', '.ipa', '.metallib', '.pyc', '.jpg', '.jpeg', '.png', '.webp'}
PRIVATE_NAMES = {'prod.keys', 'keys.txt', 'catalog.json', 'preferences.json', 'control.nacp', 'romfs_manifest.tsv', 'dmhost'}
PRIVATE_DIRS = {'.git', '__pycache__', 'gen', 'obj', 'bin', 'romfs', 'exefs', 'saves', 'save', 'backups', 'cache', 'pso_user'}


def inventory(root):
    root = Path(root)
    files = {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if path.is_symlink(): raise ValueError('Engine symlink: '+str(rel))
        if not path.is_file() or rel == Path('manifest.json'): continue
        if path.suffix.lower() in PRIVATE_SUFFIXES or path.name.lower() in PRIVATE_NAMES or set(p.lower() for p in rel.parts) & PRIVATE_DIRS:
            raise ValueError('Private/generated engine asset: '+str(rel))
        if path.stat().st_size >= 100*1024*1024: raise ValueError('Oversized engine file: '+str(rel))
        files[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def verify_bundle(root):
    root = Path(root)
    record = json.loads((root/'manifest.json').read_text())
    if record.get('schema') != 1 or record.get('repository') != 'https://github.com/seedds/nxnative.git' or not re.fullmatch('[0-9a-f]{40}', record.get('revision', '')):
        raise ValueError('Invalid bundled engine provenance')
    files = inventory(root)
    if not files or files != record.get('files'): raise ValueError('Bundled engine content differs from manifest')
    for name in ('LICENSE', 'dm/host/front_mac.m', 'dm/host/controller_native.h', 'scripts/build_ipa_from_nsp.py'):
        if name not in files: raise ValueError('Missing bundled engine source: '+name)
    return record
