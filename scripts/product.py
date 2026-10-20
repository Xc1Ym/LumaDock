"""Shared release identity; internal IDs stay stable for existing player libraries."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = json.loads((ROOT / 'product.json').read_text())
RELEASE = ROOT / 'release'

def checksums():
    files = sorted(p for p in RELEASE.iterdir() if p.is_file()
                   and p.name.startswith(f"{PRODUCT['name']}-{PRODUCT['version']}-") and p.suffix in ('.dmg', '.zip'))
    lines = []
    for path in files:
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        lines.append(f'{digest}  {path.name}\n')
    (RELEASE / 'SHA256SUMS').write_text(''.join(lines))
