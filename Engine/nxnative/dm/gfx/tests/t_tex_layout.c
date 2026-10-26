// Texture storage against shapes the original NVN driver gives (digitalhivehub ran Tears of the Kingdom's driver under emulation, nxnative PR #11; MacNativeGames 3c482a7):
// cube array depth counts layer-faces, packaged byte 0 = block height (low nibble) and block depth (high nibble), linear storage (LINEAR or LINEAR_RENDER_TARGET alone)
// counts pixel rows, also for BC. pkg is byte 0 + 1 (0 = automatic), as nvn_texdesc stores it. The driver's MINIMAL_LAYOUT shapes (flag 0x200) are not here: nvn_tex.c
// does not implement that flag
#include <stdio.h>
#include "../nvn/nvn_tex.h"

typedef struct { const char *what; int target, format, flags; unsigned w, h, depth, levels, stride; int pkg; uint64_t size, layer, off1; unsigned align, th, td; } shape_t;
static const shape_t driver[] = {
    {"cube array RGBA8 4x4 depth 6",                9, 0x25, 0,    4, 4, 6, 1, 0, 0,         3072, 512, 0, 512, 0, 0},
    {"cube array RGBA8 64x64 depth 12, 7 levels",   9, 0x25, 0,    64, 64, 12, 7, 0, 0,      294912, 24576, 16384, 512, 3, 0},
    {"packaged 3D BC4 64^3, 7 levels, byte 0x40",   2, 0x49, 0,    64, 64, 64, 7, 0, 0x41,   163328, 163328, 131072, 512, 0, 4},
    {"packaged 3D RGBA8 32^3, byte 0x00",           2, 0x25, 0,    32, 32, 32, 1, 0, 0x01,   131072, 131072, 0, 512, 0, 0},
    {"packaged 3D RGBA8 32^3, byte 0x12",           2, 0x25, 0,    32, 32, 32, 1, 0, 0x13,   131072, 131072, 0, 512, 2, 1},
    {"packaged 2D RGBA8 64x64, byte 0x13",          1, 0x25, 0,    64, 64, 1, 1, 0, 0x14,    16384, 16384, 0, 512, 3, 0},
    {"linear RT RGBA8 260x260 stride 1152",         1, 0x25, 0x40, 260, 260, 1, 1, 1152, 0,  299520, 299520, 0, 128, 0, 0},
    {"linear RT RGBA8 1x1 stride 128",              1, 0x25, 0x40, 1, 1, 1, 1, 128, 0,       128, 128, 0, 128, 0, 0},
    {"linear BC1 64x64 stride 128",                 1, 0x42, 0x10, 64, 64, 1, 1, 128, 0,     8192, 8192, 0, 32, 0, 0},
};

int main(void) {
    int fail = 0, n = (int)(sizeof driver / sizeof *driver);
    for (int i = 0; i < n; i++) {
        const shape_t *c = &driver[i];
        nvn_texdesc d = {.target = c->target, .format = c->format, .flags = c->flags, .width = c->w, .height = c->h, .depth = c->depth, .levels = c->levels, .stride = c->stride, .pkg_block_h = c->pkg};
        nvn_texlayout l; nvn_tex_layout(&d, &l);
        uint64_t off1 = c->levels > 1 ? nvn_tex_level_offset(&d, 1) : 0;
        if (l.size != c->size || l.layer_size != c->layer || off1 != c->off1 || l.align != c->align || l.tileH != c->th || l.tileD != c->td) {
            fail++;
            printf("FAIL %s: size %llu layer %llu level 1 at %llu align %u block %u/%u; driver %llu %llu %llu %u %u/%u\n", c->what, (unsigned long long)l.size, (unsigned long long)l.layer_size,
                   (unsigned long long)off1, l.align, l.tileH, l.tileD, (unsigned long long)c->size, (unsigned long long)c->layer, (unsigned long long)c->off1, c->align, c->th, c->td);
        }
    }
    printf("t_tex_layout: %d of %d driver shapes match\n", n - fail, n);
    return fail != 0;
}
