#!/usr/bin/env python3
# Answer table for translation queries (dm/games/<id>/shader_facts.tsv in the game profile folder): one row per Switch shader key, recording the few facts the translator asks for but that cannot be read from the Switch machine code -
# dimension type of textures / images, image format, component types of vertex attributes and fragment outputs, thread group size and shared memory bytes of compute shaders.
# These facts come from the reflection of the PC shader paired one-to-one with it (NVN slot number = D3D register number, see dm/gfx/README.md). The table ships with the repo; building the shader library reads only this table
# and needs no PC game files; for keys not in the table, translation queries are answered with defaults (listed separately in the build summary).
# Usage: dmsh_facts.py --freeze   regenerate the whole table from PC reflection (for maintainers; needs the PCCACHE reflection dir, the PC DXBC dir and vkd3d-compiler)
#       dmsh_facts.py --check    recompute and compare key by key against the in-repo table; on mismatch print [RED] lines and exit 1 (as above, needs the PC-side inputs)
#       dmsh_facts.py            print the table's row count and the coverage count of each fact
# Row format: key <TAB> JSON (keys in lexicographic order, compact form; the same input gives a byte-identical table)
import json, os, re, subprocess, sys
DM_ROOT = os.environ.get('DM_ROOT') or os.path.expanduser('~/dm-work')   # Workspace root (game files, build outputs and run artifacts are all under it)
HERE = os.path.dirname(os.path.abspath(__file__)); HOME = os.path.expanduser('~')
sys.path.insert(0, os.path.join(HERE, '../../games')); import game as _game   # the tables are in the current game profile folder (DM_GAME)
TABLE = str(_game.load().table('shader_facts.tsv')); MAP = str(_game.load().table('shader_map.tsv'))
TT = {'texture1d': '1d', 'texture1darray': '1darray', 'texture2d': '2d', 'texture2darray': '2darray', 'texture2dms': '2dms',
      'texture2dmsarray': '2dmsarray', 'texture3d': '3d', 'texturecube': 'cube', 'texturecubearray': 'cubearray', 'buffer_typed': 'buffer'}
CT = {'float': 'float', 'int': 'sint', 'uint': 'uint'}

def load():
    """key → fact dict; returns an empty dict if the table does not exist"""
    if not os.path.exists(TABLE): return {}
    return {k: json.loads(v) for k, v in (l.rstrip('\n').split('\t', 1) for l in open(TABLE) if l.strip() and not l.startswith('#'))}

def row(key, facts): return key + '\t' + json.dumps(facts, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'

def from_pc(pj, stage, dxbc_asm):
    """PC reflection json (pj) + DXBC disassembly text of the compute shader (None if absent) → fact dict"""
    f = {'tex': {}, 'img': {}, 'attr': {}, 'fout': {}}
    for b in pj['bindings']:
        if b['kind'] == 't' and b['type'] in TT: f['tex'][str(b['reg'])] = TT[b['type']]
        if b['kind'] == 'u' and b['type'] in TT:
            f['img'][str(b['reg'])] = {'type': TT[b['type']], 'fmt': 'R32Uint' if 'uint' in (b.get('msl_type') or '') else 'R16G16B16A16Float'}
    for v in pj.get('vertex_inputs') or []: f['attr'][str(v.get('location', v.get('index')))] = CT.get(v.get('component_type'), 'float')
    for o in pj.get('fragment_outputs') or []: f['fout'][str(o.get('index', 0))] = CT.get(o.get('component_type'), 'float')
    if pj.get('threadgroup_size'): f['local'] = pj['threadgroup_size']
    if stage == 'cs':   # shared memory: sum of the groupshared declarations in the PC DXBC (the translator default is 48 KB, over Metal's 32 KB limit)
        asm = dxbc_asm or ''
        n = sum(int(m.group(1)) for m in re.finditer(r'dcl_tgsm_raw\s+g\d+,\s*(\d+)', asm)) + \
            sum(int(m.group(1)) * int(m.group(2)) for m in re.finditer(r'dcl_tgsm_structured\s+g\d+,\s*(\d+),\s*(\d+)', asm))
        f['shared'] = (n + 15) // 16 * 16
        if dxbc_asm is None: f['pc_missing'] = True
    return f

def pairs():
    """Mapping table (with the conflict table's overrides) → {key: (paired PC name, stage)}"""
    pc_of, stage_of = {}, {}
    for ln in open(MAP):
        c = ln.rstrip('\n').split('\t')
        if len(c) > 4 and c[0].endswith('.bin'): pc_of.setdefault(c[3], c[4]); stage_of.setdefault(c[3], c[0][:2])
        if len(c) > 4 and c[0].startswith('main.rodata@'): pc_of.setdefault(c[3], c[4]); stage_of[c[3]] = {'vertex': 'vs', 'pixel': 'ps'}[c[2]]
    for ln in open(MAP + '.conflicts.tsv'):
        c = ln.rstrip('\n').split('\t')
        if len(c) > 1 and not ln.startswith('#') and not ln.startswith('dm_') and c[0] in pc_of: pc_of[c[0]] = c[1]
    return {k: (pc_of[k], stage_of[k]) for k in pc_of}

def recompute():
    pcc = os.environ.get('PCCACHE', f'{DM_ROOT}/build/cache/metal_shader_cache')
    dxdirs = os.environ.get('PCDXBC', f'{DM_ROOT}/build/ios/dxbc_all_0930:{DM_ROOT}/data/d3d12_study/shaders').split(':')
    vk = os.environ.get('VKD3D', f'{DM_ROOT}/build/vkd3d/inst/bin/vkd3d-compiler')
    if not os.path.isdir(pcc): sys.exit(f'[RED] no PC reflection dir {pcc} (PCCACHE=)')
    out, missing = {}, 0
    for key, (pc, stage) in sorted(pairs().items()):
        pp = os.path.join(pcc, pc + '.json')
        if not os.path.exists(pp): missing += 1; continue   # no paired PC reflection: not entered in the table, queries use defaults
        asm = None
        if stage == 'cs':
            dx = next((p for d in dxdirs for p in (os.path.join(d, pc + '.dxbc'), os.path.join(d, pc[:12] + '.dxbc')) if os.path.exists(p)), None)
            if dx: asm = subprocess.run([vk, '-x', 'dxbc-tpf', '-b', 'd3d-asm', dx], capture_output=True, text=True).stdout
        out[key] = from_pc(json.load(open(pp)), stage, asm)
    return out, missing

if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['--freeze']:
        t, missing = recompute()
        open(TABLE, 'w').write('# Answer table for translation queries (generated by dmsh_facts.py --freeze, do not edit): key <TAB> fact JSON\n' + ''.join(row(k, t[k]) for k in sorted(t)))
        print(f'wrote {TABLE}: {len(t)} keys; without a paired PC reflection, left out of the table: {missing}')
    elif a == ['--check']:
        t, missing = recompute(); have = load()
        bad = sorted(k for k in set(t) | set(have) if t.get(k) != have.get(k))
        for k in bad[:10]: print(f'[RED] {k}: table {have.get(k)} / recomputed {t.get(k)}')
        print(f'compared key by key {len(set(t) | set(have))}: mismatches {len(bad)}; without a paired PC reflection {missing}'); sys.exit(1 if bad else 0)
    elif not a:
        t = load(); print(f'{len(t)} keys: ' + ', '.join(f'{n} {sum(bool(f.get(n)) for f in t.values())}' for n in ('tex', 'img', 'attr', 'fout', 'local', 'shared', 'pc_missing')))
    else: sys.exit('usage: see the file header')
