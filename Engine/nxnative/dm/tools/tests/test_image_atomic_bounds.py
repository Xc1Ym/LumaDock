"""MSL-2.3 image atomic contract, using synthetic shaders only.

Portable tests require Python. To exercise the actual rebuilt offline compiler:
  DMSH_TEST_XLATE=/absolute/path/to/dmsh_xlate python3 -m unittest discover \
    -s dm/tools/tests -p test_image_atomic_bounds.py -v
Requires spirv-cross and spirv-val on PATH; optionally DMSH_TEST_METAL=1 on Mac
also compiles and links each generated MSL file. DMSH_TEST_METAL_SDKS defaults
to macosx; set macosx,iphoneos to check both SDKs with the production flags.
No shader is submitted to a GPU and no game inputs are used.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
RYU = ROOT / 'dm/third_party/ryujinx/src/Ryujinx.Graphics.Shader'
spec = importlib.util.spec_from_file_location('dmsh_atomic', ROOT / 'dm/gfx/tools/dmsh_atomic.py')
atomic = importlib.util.module_from_spec(spec); spec.loader.exec_module(atomic)


def offset(coord, extent):
    """Reference algebra, not a substitute for executing the compiler fixture."""
    if not all((x & 0xffffffff) < n for x, n in zip(coord, extent)):
        return None
    return coord[0] + extent[0] * (coord[1] + extent[1] * coord[2])


def synthetic_shader(x, y, layer=0, *, array=True, mode=0, discard=True, reduction=False, size=0, dim=None, bindless=None):
    table = (RYU / 'Decoders/InstTable.cs').read_text()
    def base(name):
        pattern = re.search(r'Add\("([01x]{64})", InstName\.' + name + r'\s*,', table)[1]
        return int(pattern.replace('x', '0'), 2)
    def mov(reg, value):
        return base('Mov32i') | ((value & 0xffffffff) << 20) | (7 << 16) | (15 << 12) | reg
    instructions = [mov(0, x), mov(1, y), mov(2, layer), mov(3, 1)]
    dim = (4 if array else 3) if dim is None else dim
    if reduction:
        op = base('Sured') | (mode << 49) | (0x48 << 36) | (dim << 33) | (2 << 24) | (7 << 16) | 3
    else:
        op = base('Suatom') | (mode << 49) | (0x48 << 36) | (dim << 33) | (2 << 29) | (3 << 20) | (7 << 16) | (255 if discard else 4)
    op |= size << (20 if reduction else 51)
    if bindless is not None:
        assert reduction  # This fixture uses SURED.B's non-returning form.
        if bindless == 'cbuf':
            # LDC.32 R4, c[2][0x120], RZ: the descriptor for image slot zero.
            instructions.append(base('Ldc') | (4 << 48) | (2 << 36) | (0x120 << 20) | (7 << 16) | (255 << 8) | 4)
            handle = 4
        else:
            assert bindless == 'unresolved'
            handle = 3  # The constant in R3 cannot resolve to a descriptor.
        op = base('SuredB') | (handle << 39) | (mode << 49) | (dim << 33) | (2 << 24) | (size << 20) | (7 << 16) | 3
    assert ((op >> 49) & 3) == mode
    instructions += [op, base('Exit') | (7 << 16) | 15]
    words = []
    for i, instruction in enumerate(instructions):
        if i % 3 == 0: words.append(0)  # Maxwell scheduling word
        words.append(instruction)
    return struct.pack('<%dQ' % len(words), *words)


def instructions(path):
    data = path.read_bytes(); words = struct.unpack('<%dI' % (len(data) // 4), data)
    assert words[0] == 0x07230203
    result = []; i = 5
    while i < len(words):
        n, op = words[i] >> 16, words[i] & 0xffff
        assert n > 0 and i + n <= len(words)
        result.append((op, list(words[i + 1:i + n]))); i += n
    return result


def check_coordinate_guard(ops, expected):
    """Verify actual emitted dataflow, not merely a guard-opcode census."""
    defs, blocks, predecessors, branches, pointers = {}, {}, {}, [], []
    current = None
    for op, args in ops:
        if op in (43, 80, 124, 61, 104, 176, 155, 60): defs[args[1]] = (op, args)
        if op == 248:
            current = args[0]; blocks[current] = []; predecessors.setdefault(current, set())
        if current is not None: blocks[current].append((op, args))
        if op == 60: pointers.append((current, args))
        if op == 249: predecessors.setdefault(args[0], set()).add(current)
        if op == 250:
            branches.append((current, args))
            for target in args[1:3]: predecessors.setdefault(target, set()).add(current)
    assert len(pointers) == 1
    pointer_block, pointer = pointers[0]
    coord_id = pointer[3]
    op, coord = defs[coord_id]
    if len(expected) == 1:  # Native texture-buffer indexing keeps a scalar coordinate.
        assert op == 43 and coord[2] == (expected[0] & 0xffffffff)
    else:
        assert op == 80
        assert tuple(defs[c][1][2] for c in coord[2:]) == tuple(v & 0xffffffff for v in expected)
        assert all(defs[c][0] == 43 for c in coord[2:])
    guard_block, branch = next((b, a) for b, a in branches if a[1] == pointer_block and a[2] != pointer_block)
    assert predecessors[pointer_block] == {guard_block}
    op, comparison = defs[branch[0]]
    if len(expected) != 1:
        assert op == 155  # OpAll
        op, comparison = defs[comparison[2]]
    assert op == 176
    op, cast = defs[comparison[2]]; assert op == 124 and cast[2] == coord_id
    op, query = defs[comparison[3]]; assert op == 104
    op, load = defs[query[2]]; assert op == 61 and load[2] == pointer[2]
    entry = next(iter(blocks))
    dominators = {b: ({b} if b == entry else set(blocks)) for b in blocks}
    while True:
        updated = {b: ({b} if b == entry else {b} | set.intersection(*(dominators[p] for p in predecessors[b]))) for b in blocks}
        if updated == dominators: break
        dominators = updated
    assert guard_block in dominators[pointer_block]
    assert [b for b, body in blocks.items() if any(op == 239 for op, _ in body)] == [pointer_block]


class Portable(unittest.TestCase):
    def test_axis_bounds_not_flattened_bounds(self):
        for coord in [(-1, 1, 0), (8, 0, 0), (0, -1, 0), (0, 4, 0), (0, 0, -1), (0, 0, 3), (-2**31, 0, 0)]:
            self.assertIsNone(offset(coord, (8, 4, 3)), coord)
        self.assertEqual(offset((0, 0, 0), (8, 4, 3)), 0)
        self.assertEqual(offset((7, 3, 2), (8, 4, 3)), 95)
        self.assertEqual([offset((0, 0, z), (8, 4, 3)) for z in range(3)], [0, 32, 64])

    def test_compiler_helper_contract(self):
        source = atomic._XY_HELPER + '\n' + atomic._DEFAULT_ALIGNMENT
        self.assertEqual(atomic.validate_msl(source), source)
        self.assertIn(atomic.HELPERS, atomic.lower_msl(source))
        self.assertNotIn('#define spvImage2DAtomicCoord', atomic.lower_msl(source))
        self.assertIn(atomic.HELPERS, atomic.lower_msl(source.replace(' ', '  ')))
        self.assertEqual(atomic.validate_msl('fragment void main0() {}'), 'fragment void main0() {}')
        for changed in [source.replace('(tc).x)', '(tc).z)'), source.replace(': 4;', ': 256;'), source.replace('#define', 'inline'), source + '\n' + atomic._XY_HELPER]:
            with self.assertRaises(ValueError): atomic.validate_msl(changed)

    @unittest.skipUnless(shutil.which('c++'), 'portable C++ compiler unavailable')
    def test_exact_helper_body(self):
        # Compile and execute the exact source-owned helper, with only the
        # texture/type API mocked. This is not a Metal compiler/GPU test.
        source = '''#include <cassert>
#include <cstdint>
using uint = uint32_t; using ulong = uint64_t;
enum access { sample }; struct int2 { int x,y; }; struct int3 { int x,y,z; };
uint spvLinearTextureAlignment = 4;
template<typename T, access A> struct texture2d { uint w,h; uint get_width() const {return w;} uint get_height() const {return h;} };
template<typename T, access A> struct texture2d_array { uint w,h; uint get_width() const {return w;} uint get_height() const {return h;} };
''' + atomic.HELPERS + '''
int main() {
    texture2d<uint, sample> two{8,4}; texture2d_array<uint,sample> array{8,4};
    assert(spvImage2DAtomicCoord(int2{7,3},two)==31);
    assert(spvImage2DAtomicCoord(int3{7,3,0},array)==31);
    assert(spvImage2DAtomicCoord(int3{0,0,1},array)==32);
    assert(spvImage2DAtomicCoord(int3{7,3,2},array)==95);
    texture2d_array<uint,sample> large{16384,16384};
    assert(spvImage2DAtomicCoord(int3{7,3,65},large)==ulong(65)*16384*16384+3*16384+7);
    spvLinearTextureAlignment=256;
    texture2d_array<uint,sample> padded{17,3};
    assert(spvImage2DAtomicCoord(int3{16,2,1},padded)==64*(3+2)+16);
}'''
        with tempfile.TemporaryDirectory(prefix='dm-atomic-helper-') as temp:
            path=Path(temp); (path/'test.cpp').write_text(source)
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)

    def test_mode_and_result_are_retained(self):
        src = (RYU / 'Instructions/InstEmitSurface.cs').read_text()
        self.assertEqual(src.count('                op.Clamp,'), 5)
        self.assertEqual(src.count('EmitSured(context, op.Dim, op.Clamp,'), 2)
        self.assertIn('dest == RegisterConsts.RegisterZeroIndex && !compareAndSwap', src)
        self.assertEqual(src.count('(TextureFlags)((int)clamp << 20)'), 2)
        instructions_source = (RYU / 'CodeGen/Spirv/Instructions.cs').read_text()
        part = instructions_source.split('private static OperationResult GenerateImageAtomic', 1)[1].split('private static OperationResult GenerateImageLoad', 1)[0]
        self.assertLess(part.index('context.BranchConditional(inside'), part.index('context.ImageTexelPointer'))
        self.assertIn('context.ULessThan(compareType, coords, extent)', part)
        self.assertNotIn('context.IMul(uintType, height, layer)', part)
        self.assertEqual(part.count('pCoords ='), 2)  # scalar/vector construction only; never folded
        self.assertIn('context.HostCapabilities.Msl23ImageAtomics', part)
        self.assertIn('texOp.Format != TextureFormat.R32Uint', part)
        self.assertIn('texOp.Format != TextureFormat.R32Sint', part)
        self.assertEqual(src.count('size is not (SuatomSize.U32 or SuatomSize.S32 or SuatomSize.Sd32)'), 2)

    def test_helper_participates_in_cache_digest(self):
        source = (ROOT / 'dm/gfx/tools/dmsh_build.py').read_text()
        assignment = next(n for n in ast.parse(source).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CODE_FP' for t in n.targets))
        self.assertIn('dmsh_atomic', {n.id for n in ast.walk(assignment) if isinstance(n, ast.Name)})
        self.assertIn("'tools/dmsh_atomic.py'", (ROOT / 'dm/gfx/tools/dmsh_chain.py').read_text())

    def test_synthetic_inputs(self):
        for mode in range(4):
            data = synthetic_shader(0, -1, mode=mode)
            self.assertEqual(len(data), 64)
            op = struct.unpack_from('<Q', data, 48)[0]
            self.assertEqual((op >> 49) & 3, mode)
            self.assertEqual(op & 255, 255)


@unittest.skipUnless(os.environ.get('DMSH_TEST_XLATE'), 'rebuilt .NET translator not configured; portable tests only')
class Compiler(unittest.TestCase):
    def test_descriptor_sized_formats(self):
        # Sd32 takes its format from the descriptor. Validate that original
        # format before the legacy translator can default it to R32Sint.
        with tempfile.TemporaryDirectory(prefix='dm-image-atomic-format-') as temp:
            work = Path(temp)
            for reduction, bindless in ((False, None), (True, None), (True, 'cbuf')):
                for fmt in ('R32Uint', 'R32Sint', 'R16Float', 'R32Float', 'R8G8B8A8Unorm', 'Unknown'):
                    key = ('sured' if reduction else 'suatom') + '_' + str(bindless) + '_' + fmt
                    code = work / (key + '.bin')
                    code.write_bytes(synthetic_shader(0, 0, reduction=reduction, size=6, bindless=bindless))
                    jobs = work / 'jobs.json'
                    jobs.write_text(json.dumps([dict(key=key, stage='cs', code=str(code),
                        img={'0': dict(type='2darray', fmt=fmt)}, local=[1, 1, 1], debug=True)]))
                    result = subprocess.run([os.environ['DMSH_TEST_XLATE'], str(jobs), str(work)], capture_output=True, text=True)
                    spv = work / (key + '.spv')
                    if fmt in ('R32Uint', 'R32Sint'):
                        self.assertEqual(result.returncode, 0, result.stderr)
                        subprocess.run(['spirv-val', '--target-env', 'vulkan1.1', str(spv)], check=True)
                    else:
                        self.assertNotEqual(result.returncode, 0, fmt)
                        self.assertIn('require an R32 integer descriptor format', result.stderr)
                        self.assertFalse(spv.exists())

    def test_unresolved_bindless_atomic_rejected(self):
        with tempfile.TemporaryDirectory(prefix='dm-image-atomic-bindless-') as temp:
            work = Path(temp)
            code = work / 'unresolved.bin'
            code.write_bytes(synthetic_shader(0, 0, reduction=True, bindless='unresolved'))
            jobs = work / 'jobs.json'
            jobs.write_text(json.dumps([dict(key='unresolved', stage='cs', code=str(code),
                img={'0': dict(type='2darray', fmt='R32Uint')}, local=[1, 1, 1], debug=True)]))
            result = subprocess.run([os.environ['DMSH_TEST_XLATE'], str(jobs), str(work)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('require a statically resolved image handle', result.stderr)
            self.assertFalse((work / 'unresolved.spv').exists())

    def compile_metal(self, msl, work, key):
        if os.environ.get('DMSH_TEST_METAL') != '1':
            return
        metal_sdks = os.environ.get('DMSH_TEST_METAL_SDKS', 'macosx').split(',')
        self.assertTrue(metal_sdks and all(sdk in ('macosx', 'iphoneos') for sdk in metal_sdks),
                        'DMSH_TEST_METAL_SDKS must be macosx, iphoneos or macosx,iphoneos')
        for sdk in metal_sdks:
            # Match dmsh_build.MAC_METAL and ios_metal.METAL;
            # the latter needs relaxed NaN-aware arithmetic.
            flags = ['-fpreserve-invariance'] if sdk == 'macosx' else [
                '-mios-version-min=18.0', '-fmetal-math-mode=relaxed', '-fpreserve-invariance']
            air = work / (key + '.' + sdk + '.air')
            library = work / (key + '.' + sdk + '.metallib')
            subprocess.run(['xcrun','-sdk',sdk,'metal','-c',*flags,str(msl),'-o',str(air)],check=True)
            subprocess.run(['xcrun','-sdk',sdk,'metallib',str(air),'-o',str(library)],check=True)
            self.assertGreater(air.stat().st_size, 0)
            self.assertGreater(library.stat().st_size, 0)
            print('synthetic Metal compile/link passed:', key, sdk, library.stat().st_size, 'bytes')

    def test_dimension_routes(self):
        # 1D routes retain the existing y=0 normalization; buffer images stay
        # scalar and must not acquire the source-owned 2D helper.
        shapes = [('1d', (1, 0)), ('buffer', (1,)), ('1darray', (1, 0, 2)),
                  ('2d', (1, 2)), ('2darray', (1, 2, 3)), ('3d', None)]
        with tempfile.TemporaryDirectory(prefix='dm-image-atomic-dim-') as temp:
            work = Path(temp)
            for reduction in (False, True):
                for dim, (shape, expected) in enumerate(shapes):
                    key = ('sured' if reduction else 'suatom') + '_dim_' + shape
                    code = work / (key + '.bin')
                    code.write_bytes(synthetic_shader(1, 2, 3, reduction=reduction, dim=dim))
                    jp = work / 'jobs.json'
                    jp.write_text(json.dumps([dict(key=key, stage='cs', code=str(code),
                        img={'0': dict(type=shape, fmt='R32Uint')}, local=[1, 1, 1], debug=True)]))
                    result = subprocess.run([os.environ['DMSH_TEST_XLATE'], str(jp), str(work)], capture_output=True, text=True)
                    spv = work / (key + '.spv')
                    if expected is None:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('support non-indexed 32-bit buffer/2D/2D-array images only', result.stderr)
                        self.assertFalse(spv.exists())
                        continue
                    self.assertEqual(result.returncode, 0, result.stderr)
                    subprocess.run(['spirv-val', '--target-env', 'vulkan1.1', str(spv)], check=True)
                    check_coordinate_guard(instructions(spv), expected)
                    msl = work / (key + '.metal')
                    subprocess.run(['spirv-cross', '--msl', '--msl-version', '20300', '--msl-argument-buffers',
                        '--msl-texture-buffer-native', str(spv), '--output', str(msl)], check=True)
                    original = msl.read_text(); source = atomic.lower_msl(original)
                    if shape == 'buffer':
                        self.assertEqual(source, original)
                        self.assertNotIn('spvImage2DAtomicCoord', source)
                    else:
                        self.assertIn(atomic.HELPERS, source)
                    msl.write_text(source)
                    self.compile_metal(msl, work, key)

    def test_source_size_gate(self):
        with tempfile.TemporaryDirectory(prefix='dm-image-atomic-width-') as temp:
            work = Path(temp)
            for reduction in (False, True):
                for size in range(8):
                    key = ('sured' if reduction else 'suatom') + '_size_' + str(size)
                    code = work / (key + '.bin')
                    code.write_bytes(synthetic_shader(0, 0, reduction=reduction, size=size))
                    jp = work / 'jobs.json'
                    jp.write_text(json.dumps([dict(key=key, stage='cs', code=str(code),
                        img={'0': dict(type='2darray', fmt='R32Uint')}, local=[1, 1, 1], debug=True)]))
                    result = subprocess.run([os.environ['DMSH_TEST_XLATE'], str(jp), str(work)], capture_output=True, text=True)
                    spv = work / (key + '.spv')
                    if size in (0, 1, 6):  # U32, S32, descriptor-sized32.
                        self.assertEqual(result.returncode, 0, result.stderr)
                        subprocess.run(['spirv-val', '--target-env', 'vulkan1.1', str(spv)], check=True)
                        msl = work / (key + '.metal')
                        subprocess.run(['spirv-cross', '--msl', '--msl-version', '20300', '--msl-argument-buffers',
                            '--msl-texture-buffer-native', str(spv), '--output', str(msl)], check=True)
                        msl.write_text(atomic.lower_msl(msl.read_text()))
                        self.compile_metal(msl, work, key)
                    else:  # U64, S64, descriptor-sized64, float and half2.
                        self.assertNotEqual(result.returncode, 0, key)
                        self.assertIn('require a 32-bit integer source size', result.stderr)
                        self.assertFalse(spv.exists())

    def test_real_translation_and_cross(self):
        for tool in ('spirv-cross', 'spirv-val'):
            self.assertIsNotNone(shutil.which(tool), tool + ' required for compiler acceptance')
        with tempfile.TemporaryDirectory(prefix='dm-image-atomic-') as temp:
            work = Path(temp)
            cases = [('negative_x', -1, 1, 0), ('negative_y', 0, -1, 0), ('int_min', -2**31, 0, 0),
                     ('width_edge', 8, 0, 0), ('height_edge', 0, 4, 0), ('layer_edge', 0, 0, 3),
                     ('valid_origin', 0, 0, 0), ('valid_last', 7, 3, 2)]
            for array in (False, True):
                for reduction in (False, True):
                    jobs = []; expected = {}
                    for name, x, y, z in cases:
                        key = name + ('_array' if array else '_2d') + ('_sured' if reduction else '_suatom')
                        code = work / (key + '.bin'); code.write_bytes(synthetic_shader(x, y, z, array=array, reduction=reduction))
                        expected[key] = (x, y, z) if array else (x, y)
                        jobs.append(dict(key=key, stage='cs', code=str(code), img={'0':dict(type='2darray' if array else '2d',fmt='R32Uint')},local=[1,1,1],debug=True))
                    jp = work / 'jobs.json'; jp.write_text(json.dumps(jobs))
                    subprocess.run([os.environ['DMSH_TEST_XLATE'], str(jp), str(work)], check=True)
                    for job in jobs:
                        spv = work / (job['key'] + '.spv')
                        subprocess.run(['spirv-val', '--target-env', 'vulkan1.1', str(spv)], check=True)
                        ops = instructions(spv)
                        check_coordinate_guard(ops, expected[job['key']])
                        current = None; pointer_blocks = []; branches = []
                        for op, args in ops:
                            if op == 248: current = args[0]
                            if op == 60: pointer_blocks.append(current)
                            if op == 250: branches.append(args)
                        self.assertEqual(len(pointer_blocks), 1)
                        self.assertTrue(any(b[1] == pointer_blocks[0] and b[2] != pointer_blocks[0] for b in branches))
                        self.assertTrue(any(op == 104 for op, _ in ops))  # OpImageQuerySize
                        self.assertTrue(any(op == 176 for op, _ in ops))  # OpULessThan
                        self.assertTrue(any(op == 239 for op, _ in ops))  # OpAtomicUMax
                        msl = work / (job['key'] + '.metal')
                        subprocess.run(['spirv-cross','--msl','--msl-version','20300','--msl-argument-buffers','--msl-texture-buffer-native',str(spv),'--output',str(msl)], check=True)
                        original = msl.read_text(); source = atomic.lower_msl(original)
                        helper_line = next(line for line in original.splitlines() if atomic._helper_line(line))
                        self.assertEqual(source, original.replace(helper_line, atomic.HELPERS, 1))
                        msl.write_text(source)
                        self.assertIn('.get_height()', source)
                        if array: self.assertIn('.get_array_size()', source)
                        self.compile_metal(msl, work, job['key'])
            for mode, discard in [(1, True), (2, True), (3, True), (0, False)]:
                key = 'reject_%d_%d' % (mode, discard)
                code=work/(key+'.bin'); code.write_bytes(synthetic_shader(0,0,mode=mode,discard=discard))
                jp.write_text(json.dumps([dict(key=key,stage='cs',code=str(code),img={'0':dict(type='2darray',fmt='R32Uint')},local=[1,1,1],debug=True)]))
                result=subprocess.run([os.environ['DMSH_TEST_XLATE'],str(jp),str(work)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('require IGN with a discarded result',result.stderr)
                self.assertFalse((work/(key+'.spv')).exists())


if __name__ == '__main__': unittest.main()
