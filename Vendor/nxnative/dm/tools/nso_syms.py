#!/usr/bin/env python3
"""Compare the SDK surface of two Switch games: dynamic symbols of NSO modules + this repo's HLE hook names.
Usage: nso_syms.py <repo dm/host dir> <gameA ExeFS | -> <gameB ExeFS>   (A = the game the host already supports, B = the new one; - = no reference game, compare with the host hooks only)"""
import collections, glob, os, re, struct, sys
import lz4.block

def load(path):
    d = open(path, 'rb').read()
    flags = struct.unpack_from('<I', d, 0xc)[0]
    segs = [struct.unpack_from('<III', d, 0x10 + i * 0x10) for i in range(3)]
    csz = struct.unpack_from('<III', d, 0x60)
    img = bytearray(segs[2][1] + segs[2][2] + struct.unpack_from('<I', d, 0x3c)[0])
    for i, (fo, mo, sz) in enumerate(segs):
        raw = d[fo:fo + csz[i]]
        if flags >> i & 1: raw = lz4.block.decompress(raw, uncompressed_size=sz)
        img[mo:mo + sz] = raw
    return bytes(img)

def dynsyms(img):
    mod0 = struct.unpack_from('<I', img, 4)[0]
    assert img[mod0:mod0 + 4] == b'MOD0', 'no MOD0'
    dyn = mod0 + struct.unpack_from('<i', img, mod0 + 4)[0]
    tags = {}
    for i in range(4096):
        t, v = struct.unpack_from('<qQ', img, dyn + i * 16)
        if t == 0: break
        tags.setdefault(t, v)
    symtab, strtab = tags[6], tags[5]
    n = struct.unpack_from('<I', img, tags[4] + 4)[0] if 4 in tags else (strtab - symtab) // 24
    out = []
    for i in range(1, n):
        name, info, other, shndx, value, size = struct.unpack_from('<IBBHQQ', img, symtab + i * 24)
        s = img[strtab + name:img.index(b'\0', strtab + name)].decode('latin1')
        if s: out.append((s, shndx != 0, info >> 4))
    return out

def imports(exefs, mod='main'): return {s for s, defined, _ in dynsyms(load(os.path.join(exefs, mod))) if not defined}
def exports(exefs, mod='sdk'): return {s for s, defined, bind in dynsyms(load(os.path.join(exefs, mod))) if defined and bind in (1, 2)}

def area(s):
    m = re.match(r'_ZN(?:K)?2nn(\d+)(\w+)', s)
    if m: n = int(m.group(1)); return 'nn::' + m.group(2)[:n]
    if s.startswith('nvn'): return 'nvn'
    if s.startswith('_Z'): return 'other C++'
    return 'C / libc'

host, A, B = sys.argv[1:4]
hooks = set()
for f in glob.glob(os.path.join(host, '*.c')):
    hooks |= set(re.findall(r'HLE(?:_FORCE)?\(\s*"([^"]+)"', open(f, encoding='utf-8', errors='replace').read()))
ia, ib, eb = (set() if A == '-' else imports(A)), imports(B), exports(B)   # A = -: no reference game, compare with the host hooks only
print('HLE hooks in host:', len(hooks), '| present in new game sdk exports:', len(hooks & eb))
print('main imports: old game %d, new game %d, shared %d, new-only %d' % (len(ia), len(ib), len(ia & ib), len(ib - ia)))
new = ib - ia
by = collections.Counter(area(s) for s in new); allb = collections.Counter(area(s) for s in ib)
print('\nnew game main imports by area (total / not imported by old game):')
for k, v in allb.most_common(40): print('  %-22s %5d / %4d' % (k, v, by.get(k, 0)))
print('\nexamples of new-only imports per area:')
for k, _ in by.most_common(14):
    ex = sorted(s for s in new if area(s) == k)[:4]; print('  ' + k + ': ' + ', '.join(ex))
