#!/usr/bin/env python3
# The game name and display version from the NSP's control data (control.nacp, saved in the extraction folder by nx_extract): the iOS app name and version come from them (shared by the packing script and build_ipa.sh).
# Usage: nacp.py <control.nacp> (prints the game name), nacp.py --version <control.nacp> (prints the display version); each prints an empty line and exits 1 when none can be read. From Python: import nacp; nacp.name(path), nacp.version(path)
import re, struct, sys, zlib
from pathlib import Path


def name(path):
    """The title area holds 0x300 bytes per language (name 0x200 + publisher 0x100); take the first non-empty one (0 = American English); a missing file or no sensible name returns an empty string"""
    p = Path(path)
    if not p.is_file(): return ''
    b = p.read_bytes(); t = b[:0x3000]
    try:   # newer SDKs compress the title area: a u16 size + raw deflate, inflating to 32 languages × 0x300 (Mario 1.2.1 does)
        z = zlib.decompress(b[2:2 + struct.unpack_from('<H', b)[0]], -15)
        if len(z) == 0x6000: t = z
    except zlib.error: pass   # not compressed
    for i in range(len(t) // 0x300):
        n = t[i * 0x300:i * 0x300 + 0x200].split(b'\0', 1)[0]
        if not n: continue
        try: n = n.decode('utf-8')
        except UnicodeDecodeError: return ''
        return n if n.isprintable() else ''
    return ''


def version(path):
    """The display version (0x10 bytes at 0x3060, e.g. 1.2.1), cut to what iOS accepts as a bundle version (up to three dot-separated integers); a missing file or no leading number returns an empty string"""
    p = Path(path)
    if not p.is_file(): return ''
    m = re.match(rb'\d+(\.\d+){0,2}', p.read_bytes()[0x3060:0x3070])
    return m.group().decode() if m else ''


if __name__ == '__main__':
    a = sys.argv[1:]; f = version if a[:1] == ['--version'] else name
    if f is version: a = a[1:]
    if len(a) != 1: sys.exit('usage: nacp.py [--version] <control.nacp>')
    n = f(a[0]); print(n); sys.exit(0 if n else 1)
