"""Provisional memory layouts must leave room for the game's initial heap."""
from pathlib import Path
import sys
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/games'))
import profile_guess as pg


class GlslSources(unittest.TestCase):
    def test_language_preamble_is_not_a_shader(self):
        self.assertEqual(pg.glsl_sources(b'#version 450 core\n#define float4 vec4\n\0void main() {}\0'), 0)

    def test_complete_embedded_sources(self):
        image = b'#version 450\nvoid main() {}\0#version 450\nvoid main (void) {}\0'
        self.assertEqual(pg.glsl_sources(image), 2)


class UnrealMemory(unittest.TestCase):
    def test_initial_heap_fits_beside_the_engine_region(self):
        facts = {
            'mods': {'main': {'imports': {'nvnBootstrapLoader', pg.HEAP_API}, 'bss': 0, 'far': False}},
            'romfs': {'root': set(), 'exts': {'.pak': 1}},
            'sysres': 40 * pg.MiB,
            'main_markers': {'Unreal 4'},
        }
        keys = pg.guess(facts, hooks=set())
        reserve, alias, stack = (int(keys[k][0], 0) for k in ('mem_reserve', 'mem_alias', 'mem_stack'))
        self.assertGreaterEqual(alias, 64 * 1024**3)
        # mem_init puts the modules before the alias region, then stacks and the heap.
        heap = reserve - 0x10000000 - alias - stack
        self.assertGreaterEqual(heap, 128 * pg.MiB)



class AddressRegions(unittest.TestCase):
    """region_findings: the host's region table (DM_REGIONS) of a run with a Switch-sized alias region against the profile's alias region"""
    SYMS = {'_ZN2nn3mem17StandardAllocator10InitializeEPvmb': (0x1000, 0x100), '_ZN2nn2os21AllocateAddressRegionEPmm': (0x2000, 0x40)}
    HEAD = '# alias region 0x1000000000; offset\tsize\twho\tmapped\tfirst opened\tend\tvia\n'

    def test_demangle(self):
        self.assertEqual(pg.demangle('_ZN2nn3mem17StandardAllocator10InitializeEPvmb'), 'nn::mem::StandardAllocator::Initialize')
        self.assertEqual(pg.demangle('memcpy'), 'memcpy')

    def test_fits(self):
        t = self.HEAD + '0x4000000\t0x100000000\tmain+0x10\t0x60000000\t0\t0x100000000\t0x1010\n0x104000000\t0x1000000\tmain+0x20\t0\t-\t-\t0x2010\n'
        f = pg.region_findings(t, 0x118000000, self.SYMS)
        self.assertEqual(len(f), 2, f)   # the 16 MB region is under the 256 MB listed, but counts for the reach
        self.assertIn('through nn::mem::StandardAllocator::Initialize', f[0][1])
        self.assertEqual(f[1], (False, "in its first 15 s in nnMain the game's regions reach alias +4.08 GB, within the profile's 4.38 GB alias region (what it takes later in play is not measured here)"))
        self.assertIn('returning to main+0x10', f[0][1])

    def test_standard_allocator_regions_the_host_caps(self):
        # alone: the host's cap makes it fit (not red); with 1.5 GB of regions made after it (Absolum's .NET garbage collector): red, with the stdalloc_cap value that leaves them room
        alone = self.HEAD + '0x4000000\t0x300000000\tmain+0x10\t0x60000000\t0\t0x300000000\t0x1010\n'
        f = pg.region_findings(alone, 0x110000000, self.SYMS)
        self.assertFalse(any(red for red, _ in f), f)
        self.assertIn('on the iPhone layout the host gives it 3.94 GB', f[0][1])
        self.assertIn('only by StandardAllocator regions, which the host makes fit', f[-1][1])
        later = alone + '0x304000000\t0x60000000\tmain+0x40\t0x40000000\t0\t0x60000000\t0x2010\n'
        red, text = pg.region_findings(later, 0x118000000, self.SYMS)[-1]
        self.assertTrue(red)
        self.assertIn('the regions made after the one returning to main+0x10 take 1.50 GB, more than the 0.25 GB the host leaves them: stdalloc_cap 0xb0000000 (2.75 GB)', text)
        self.assertNotIn('main+0x40 takes', text)   # it fits once the region before it is capped

    def test_a_region_too_big_by_itself(self):
        # the game's own allocator through AllocateAddressRegion (Smash's engine): red, and it does not count as room the StandardAllocator region must leave
        t = (self.HEAD + '0x4000000\t0x300000000\tmain+0x10\t0x60000000\t0\t0x300000000\t0x1010\n'
             '0x304000000\t0xf80000000\tmain+0x30\t0x70000000\t0\t0xf7f210000\t0x2010\n')
        red, text = pg.region_findings(t, 0x118000000, self.SYMS)[-1]
        self.assertTrue(red and text.startswith('in its first 15 s in nnMain'), text)
        self.assertIn('the request returning to main+0x30 takes 62.00 GB through nn::os::AllocateAddressRegion: a smaller one works only if its allocator places nothing by fixed offsets', text)
        self.assertNotIn('stdalloc_cap', text)

    def test_together_too_big(self):
        t = self.HEAD + '0x4000000\t0xc0000000\tmain+0x30\t0\t-\t-\t0x2010\n0xc4000000\t0x80000000\tmain+0x50\t0\t-\t-\t0x2010\n'
        red, text = pg.region_findings(t, 0x118000000, self.SYMS)[-1]
        self.assertTrue(red); self.assertIn('no single region is too big, but together they need more room', text)

    def test_no_table(self):
        self.assertEqual(pg.region_findings('', 0x118000000), [])


if __name__ == '__main__':
    unittest.main()
