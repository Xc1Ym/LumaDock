"""Narrow production wiring checks, not a native Metal execution fixture."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "nvn/nvn_mtl.m").read_text()

class BindingWiring(unittest.TestCase):
    def test_failed_scratch_never_falls_back_to_dummy(self):
        branch = SOURCE.split('storage = atom_scratch(tt, need);', 1)[1].split('} else {', 1)[0]
        self.assertIn('!storage || !gpu || !nvn_imga_capacity', branch)
        self.assertIn('MDIE(', branch)
        self.assertIn('refusing short dummy', branch)
        self.assertNotIn('dummy_buf', branch)

    def test_actual_image_is_shared_by_pair(self):
        self.assertIn('atomic_img[r] = img_binding(tid, ib,', SOURCE)
        self.assertIn('atomic_desc[reg] ? atomic_img[reg]', SOURCE)
        self.assertIn('id<MTLTexture> image = atomic_img[reg]', SOURCE)
        self.assertIn('missing IMG partner', SOURCE)
        self.assertIn('ambiguous IMG partner', SOURCE)

    def test_direct_path_checks_actual_backing(self):
        branch = SOURCE.split('if (linear) {', 1)[1].split('} else if (tt) {', 1)[0]
        for token in ('image.buffer == storage', 'image.bufferOffset', 'image.bufferBytesPerRow',
                      '!image.parentTexture', 'nvn_imga_direct_ok(&d)', 'MDIE('):
            self.assertIn(token, branch)
        self.assertNotIn('atom_scratch', branch)
        self.assertNotIn('dummy_buf', branch)

    def test_rejection_precedes_argument_publication(self):
        body = SOURCE.split('static int encode_args_(id<MTLCommandEncoder> en, NvShader *sh, int nvn_stage, int metal_vertex) {', 1)[1]
        self.assertLess(body.index('refusing short dummy'), body.index('memcpy((uint8_t *)ab.contents'))

if __name__ == '__main__':
    unittest.main()
