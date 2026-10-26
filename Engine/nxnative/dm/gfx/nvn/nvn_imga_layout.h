// Admission for the packed 32-bit IMG/IMGA contract, independent of Metal.
#pragma once
#include <stdint.h>

static inline int nvn_imga_bytes(uint64_t w, uint64_t h, uint64_t layers, uint64_t *out) {
    if (!out || !w || !h || !layers || w > UINT32_MAX || h > UINT32_MAX || layers > UINT32_MAX ||
        w > UINT64_MAX / h || w * h > UINT64_MAX / layers || w * h * layers > UINT64_MAX / 4) return 0;
    *out = w * h * layers * 4;
    return 1;
}
static inline int nvn_imga_capacity(uint64_t need, uint64_t length, uint64_t offset) {
    return need && offset <= length && need <= length - offset;
}
static inline int nvn_imga_scratch_length(uint64_t need, uint64_t *out) {
    const uint64_t mask = (1u << 20) - 1;
    if (!out || !need || need > UINT64_MAX - mask) return 0;
    *out = (need + mask) & ~mask;
    return 1;
}
typedef struct {
    uint64_t width, height, layers, row_bytes;
    uint64_t buffer_length, texture_offset, pointer_offset, guest_bytes;
    unsigned word_bytes;
    int buffer_texture, base_view, same_buffer;
} nvn_imga_direct_layout;
static inline int nvn_imga_direct_ok(const nvn_imga_direct_layout *d) {
    uint64_t need;
    if (!d || !d->base_view || !d->same_buffer || d->word_bytes != 4 || d->layers != 1 ||
        !nvn_imga_bytes(d->width, d->height, d->layers, &need) || d->texture_offset != d->pointer_offset ||
        d->texture_offset % 4 || !nvn_imga_capacity(need, d->buffer_length, d->texture_offset) || need > d->guest_bytes) return 0;
    // Buffer textures have no next row: Metal may pad their unused row length.
    return d->buffer_texture ? d->height == 1 : d->row_bytes == d->width * 4;
}
