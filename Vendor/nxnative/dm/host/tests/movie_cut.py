# Static check of cutscene no-op playback (the game-side protocol in the header comment of hle_movie.c): check the key instructions and vtable slot names one by one on the original image; any mismatch is a failure.
# Usage: movie_cut.py <main.orig.bin> <subsdk0.orig.bin>      (.orig.bin is generated from ExeFS by dm/tools/nso.py)
import struct, sys
from capstone import *
main, sub = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read()
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
def ins(a): i = next(md.disasm(main[a:a + 4], a)); return f'{i.mnemonic} {i.op_str}'

# (offset, expected disassembly, meaning of this instruction in the chain) -- the game-side protocol that cutscene "no-op playback for the real duration" (plays nothing but lasts the real duration) depends on (header comment of hle_movie.c)
CHAIN = [
    (0x898ed0, 'mov w1, #0x10', 'Extractor object 0x10 bytes: the cut stores its state pointer in the second word'),
    (0x899960, 'mov w1, #0x10', 'Decoder object 0x10 bytes: same as above'),
    (0x899780, 'ldr x8, [x8, #0x20]', 'Setup calls Extractor slot 4 GetTrackCount'),
    (0x89979c, 'b.lt #0x899928', 'track count < 1 skips track selection (the cut reports 0 tracks)'),
    (0x898f70, 'stp x24, x23, [x19, #0x1b8]', 'DecoderEvents[0..1] = {P+0x18, P+0x40}'),
    (0x899044, 'mov w8, #1', 'wait item kind at P+0x18 is 1 = input available'),
    (0x8990b8, 'mov w8, #2', 'wait item kind at P+0x40 is 2 = output available'),
    (0x8999e4, 'ldr x8, [x8, #0x28]', 'Setup calls Decoder slot 5 Start'),
    (0x899f54, 'cmp w21, #0', 'Open returns (Start status == 0): Start in the cut succeeds ⇒ playing'),
    (0x899f5c, 'cset w0, eq', ''),
    (0xbbfe40, 'bl #0x898230', 'the per-frame update calls the player update'),
    (0x89832c, 'ldrb w8, [x8, #0x489]', 'with the frame queue empty returns !P[+0x489] (finished flag) …'),
    (0x898334, 'cset w0, eq', '… not finished counts as playing'),
    (0x8992e0, 'cmp w21, #1', 'decoder thread: kind 1 takes the input path'),
    (0x8992e8, 'cmp w21, #2', 'decoder thread: kind 2 takes the output path'),
    (0x899508, 'ldr x8, [x8, #0x48]', 'input: Decoder slot 9 AcquireInputBufferIndex'),
    (0x899534, 'ldr x8, [x8, #0x50]', 'input: Decoder slot 10 GetInputBuffer'),
    (0x8995a8, 'ldr x8, [x8, #0x50]', 'input: Extractor slot 10 Read'),
    (0x8995b8, 'cmp w23, #2, lsl #12', 'Read returning 0x2000 = end of stream …'),
    (0x8995c0, 'ldrb w8, [x19, #0x12]', '… loop flag …'),
    (0x8995d4, 'ldr x8, [x8, #0x40]', '… if looping, Extractor slot 8 SeekTo (the cut re-arms its timer)'),
    (0x899620, 'mov w26, #4', '… otherwise sends flag 4 (end of stream)'),
    (0x899634, 'ldr x8, [x8, #0x60]', 'input: Extractor slot 12 GetSampleTime'),
    (0x899670, 'ldr x8, [x8, #0x58]', 'input: Decoder slot 11 SendInputBufferForDecode'),
    (0x89968c, 'ldr x8, [x8, #0x58]', 'input: Extractor slot 11 Advance'),
    (0x89932c, 'ldr x8, [x8, #0x60]', 'output: Decoder slot 12 AcquireOutputBufferIndex'),
    (0x899338, 'tst w0, #0xffffdfff', 'only status 0 / 0x2000 enters the frame queue (the cut returns 0x1008 with no output)'),
    (0x899cb4, 'cmp x9, #2', 'frames are dropped only with a queue ≥2 (a single end-of-stream item is never dropped)'),
    (0x89a650, 'ldr x8, [x8, #0x90]', 'frame fetch: Decoder slot 18 GetOutputBufferFormat (the cut returns non-zero)'),
    (0x89a65c, 'cmp w27, #4', 'flag 4 …'),
    (0x89a670, 'strb w8, [x25, #0x489]', '… sets finished ⇒ the game takes the normal finished path'),
    (0x899fdc, 'ldr x8, [x8, #0x30]', 'teardown calls Decoder slot 6 Stop (the cut cancels its timer)'),
    (0x899ff0, 'ldr x8, [x8, #8]', 'teardown calls Decoder slot 1 deleting destructor'),
    (0x89a004, 'ldr x8, [x8, #8]', 'teardown calls Extractor slot 1 deleting destructor'),
]
bad = 0
for a, want, why in CHAIN:
    got = ins(a); ok = got == want; bad += not ok
    print(f'{"✓" if ok else "✗"} {a:#x}  {got:28s} {"" if ok else "expected " + want}  {why}')

# Vtable slot names (subsdk0 dynamic symbols + RELATIVE relocations): the cut vtable is ordered by these slot numbers
m0 = struct.unpack_from('<I', sub, 4)[0]; dyn = m0 + struct.unpack_from('<i', sub, m0 + 4)[0]
D = {}; o = dyn
while True:
    t, v = struct.unpack_from('<qQ', sub, o); o += 16
    if t == 0: break
    D.setdefault(t, v)
rel = {}
for k in range(D[8] // 24):
    off, info, add = struct.unpack_from('<QQq', sub, D[7] + 24 * k)
    rel[off] = add if info & 0xffffffff == 1027 else ('sym', info >> 32)   # RELATIVE gives an address; ABS64 / GLOB_DAT give a symbol number
names, sym, symn = {}, {}, {}
for k in range(1, (D[5] - D[6]) // 24):
    nm, info, oth, shn, val, sz = struct.unpack_from('<IBBHQQ', sub, D[6] + 24 * k)
    s = sub[D[5] + nm:sub.index(b'\0', D[5] + nm)].decode(); symn[k] = s
    if shn and val: names.setdefault(val, s); sym[s] = val
def slot_name(r): return symn.get(r[1], '?') if isinstance(r, tuple) else names.get(r, '?')
VT = [('_ZTVN5movie9ExtractorE', 4, '_ZN5movie9Extractor13GetTrackCountEPi'),
      ('_ZTVN5movie9ExtractorE', 15, '_ZN5movie9Extractor13SetDataSourceEPNS_18ClientStreamReaderEPKc'),
      ('_ZTVN5movie7DecoderE', 2, '_ZN5movie7Decoder9ConfigureEPNS_9MediaDataE'),
      ('_ZTVN5movie7DecoderE', 3, '_ZN5movie7Decoder20RegisterClientEventsEPNS_13DecoderEventsE'),
      ('_ZTVN5movie7DecoderE', 5, '_ZN5movie7Decoder5StartEv'),
      ('_ZTVN5movie7DecoderE', 6, '_ZN5movie7Decoder4StopEv'),
      ('_ZTVN5movie9ExtractorE', 8, '_ZN5movie9Extractor6SeekToEl'),
      ('_ZTVN5movie9ExtractorE', 10, '_ZN5movie9Extractor4ReadEPNS_6BufferE'),
      ('_ZTVN5movie9ExtractorE', 11, '_ZN5movie9Extractor7AdvanceEv'),
      ('_ZTVN5movie9ExtractorE', 12, '_ZN5movie9Extractor13GetSampleTimeEPl'),
      ('_ZTVN5movie7DecoderE', 9, '_ZN5movie7Decoder23AcquireInputBufferIndexEPiS1_'),
      ('_ZTVN5movie7DecoderE', 10, '_ZN5movie7Decoder14GetInputBufferEiPNS_6BufferE'),
      ('_ZTVN5movie7DecoderE', 11, '_ZN5movie7Decoder24SendInputBufferForDecodeEiiilj'),
      ('_ZTVN5movie7DecoderE', 12, '_ZN5movie7Decoder24AcquireOutputBufferIndexEPiPlPjS1_'),
      ('_ZTVN5movie7DecoderE', 15, '_ZN5movie7Decoder24ReleaseOutputBufferIndexEi'),
      ('_ZTVN5movie7DecoderE', 18, '_ZN5movie7Decoder21GetOutputBufferFormatEiPNS_9MediaDataE')]
for vt, slot, want in VT:
    got = slot_name(rel.get(sym[vt] + 16 + 8 * slot, 0)); ok = got == want; bad += not ok
    print(f'{"✓" if ok else "✗"} {vt} slot {slot}  {got}{"" if ok else "  expected " + want}')
n = len(CHAIN) + len(VT)
print(f'{"all passed" if not bad else "[RED]"}: {n - bad}/{n}')
sys.exit(1 if bad else 0)
