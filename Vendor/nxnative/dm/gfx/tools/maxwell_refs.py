# Resource references in Maxwell (Tegra X1) shader machine code: only decodes the few kinds needed for the binding mapping; not a full disassembler.
# Instruction bit patterns are taken from the yuzu shader decode table; code segment layout: graphics stage = 0x30 NVN header (0x12345678) + 0x50 SPH + instructions,
# compute stage is instructions directly; the 1st of every 4 64-bit words is the scheduling control word.
# A full measurement (10847 variants, tools/shader_map.py) gives NVN binding ↔ D3D register:
#   uniform buffer    binding r ↔ cb_r, which is c[3 + r] in machine code (14 per stage, c[3]..c[16]; the higher c[22]/c[27] are driver-internal)
#   separate texture  slot r    ↔ t_r, handle at c[2][0x168 + 8r] (two ways to read it: a c[2] operand, or the texture instruction's immediate texture index ×4)
#   separate sampler  slot r    ↔ s_r, handle at c[2][0x568 + 8r] (1 exception: cs_terrain_composite additionally uses s2, absent on PC)
#   storage buffer    slot r    ↔ u_r or read-only structured/raw buffer t_r (same numbering space), address/size at c[0][base + 0x10 r]
#                     base: vertex 0x110, compute 0x310, pixel 0x510; all 10847 match exactly in both directions
import struct

TEX_BASE, SAMP_BASE, UBO_FIRST, UBO_LAST = 0x168, 0x568, 3, 16
SSBO_BASE = {'vs': 0x110, 'cs': 0x310, 'ps': 0x510}

def instrs(code, graphics):
    off = 0x80 if graphics and code[:4] == bytes.fromhex('78563412') else 0
    out = []
    for k in range(off, len(code) - 7, 8):
        if ((k - off) // 8) % 4 == 0: continue
        out.append(struct.unpack_from('<Q', code, k)[0])
    return out

def match(w, pat):
    for i, ch in enumerate(pat):
        if ch != '-' and int(ch) != (w >> (63 - i)) & 1: return False
    return True

def cbuf_alu(ins):
    """ALU instructions whose operand class is constant buffer (top 4 bits = 0100): {(index, byte offset)}"""
    return {((w >> 34) & 0x1f, ((w >> 20) & 0x3fff) * 4) for w in ins if (w >> 60) == 0x4 and w}

def ldc(ins):
    """LDC (read constant buffer by index): {(index, byte offset)}"""
    return {((w >> 36) & 0x1f, (w >> 20) & 0xffff) for w in ins if match(w, '1110111110010---')}

def bindings(code, stage):
    ins = instrs(code, stage != 'cs')
    refs = cbuf_alu(ins) | ldc(ins)
    ubo = {i - UBO_FIRST for i, _ in refs if UBO_FIRST <= i <= UBO_LAST}
    c2 = {o for i, o in refs if i == 2}
    # Immediate texture index (bits 36..48 of TEX/TEXS/TLD/TLDS/TLD4/TLD4S) = word offset of the handle within c[2]; ×4 gives the byte offset (verified with the embedded shader's TLDS 0x6e→t10)
    for w in ins:
        for pat in ('110000----111---', '110010----111---', '11011100--11----', '1101111100------', '1101-00---------', '1101-01---------'):
            if match(w, pat): c2.add(((w >> 36) & 0x1fff) * 4); break
    tex = {(o - TEX_BASE) // 8 for o in c2 if TEX_BASE <= o < SAMP_BASE and (o - TEX_BASE) % 8 == 0}
    samp = {(o - SAMP_BASE) // 8 for o in c2 if o >= SAMP_BASE and (o - SAMP_BASE) % 8 == 0}
    base = SSBO_BASE.get(stage)
    ssbo = {(o - base) // 16 for i, o in refs if i == 0 and base and o >= base and (o - base) % 16 == 0 and (o - base) // 16 < 16} if base else set()
    drv = sorted(o for o in c2 if o < TEX_BASE)
    return {'ubo': ubo, 'tex': tex, 'samp': samp, 'ssbo': ssbo, 'c2drv': drv}

def vs_inputs(code):
    """Generic attribute slots read by the vertex shader: attribute address bits 20..29 of ALD (1110111111011---); generic attribute n is at 0x80 + 16n"""
    ins = instrs(code, True)
    return {((w >> 20) & 0x3ff) - 0x80 >> 4 for w in ins if match(w, '1110111111011---') and 0x80 <= ((w >> 20) & 0x3ff) < 0x280}

def sph_stage(code):
    """Stage field of the graphics shader SPH header (word 0, bits 10..13): 1 vertex, 5 pixel"""
    if code[:4] != bytes.fromhex('78563412'): return None
    return {1: 'vs', 5: 'ps'}.get((struct.unpack_from('<I', code, 0x30)[0] >> 10) & 0xf)
