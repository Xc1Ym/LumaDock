#include <assert.h>
#include <stdio.h>
#include "../nvn/nvn_imga_layout.h"

static nvn_imga_direct_layout packed(void) {
    return (nvn_imga_direct_layout){ .width=512, .height=256, .layers=1, .row_bytes=2048,
        .buffer_length=1048576, .texture_offset=4096, .pointer_offset=4096, .guest_bytes=524288,
        .word_bytes=4, .base_view=1, .same_buffer=1 };
}
int main(void) {
    uint64_t n=77, rounded=88;
    assert(nvn_imga_bytes(512,512,3,&n) && n==3u*1024*1024);
    assert(!nvn_imga_capacity(n,64u*1024,0)); // The former allocation-failure fallback is unsafe.
    assert(nvn_imga_capacity(n,n,0) && !nvn_imga_capacity(n,n-1,0));
    assert(nvn_imga_scratch_length(n,&rounded) && rounded==n);
    assert(nvn_imga_scratch_length(n+1,&rounded) && rounded==4u*1024*1024);
    assert(nvn_imga_bytes(480,270,1,&n) && n==518400);
    n=77; rounded=88;
    assert(!nvn_imga_bytes(0,1,1,&n) && n==77);
    assert(!nvn_imga_bytes(1,0,1,&n) && n==77);
    assert(!nvn_imga_bytes(1,1,0,&n) && n==77);
    assert(!nvn_imga_bytes(UINT32_MAX,UINT32_MAX,2,&n) && n==77);
    assert(!nvn_imga_bytes(UINT32_MAX,UINT32_MAX,1,&n) && n==77);
    assert(!nvn_imga_bytes(UINT64_MAX,1,1,&n) && n==77);
    assert(!nvn_imga_bytes(1,1,1,NULL));
    assert(!nvn_imga_scratch_length(UINT64_MAX,&rounded) && rounded==88);
    assert(!nvn_imga_scratch_length(0,&rounded) && rounded==88);
    assert(!nvn_imga_capacity(4,UINT64_MAX,UINT64_MAX-2));
    assert(!nvn_imga_capacity(1,0,UINT64_MAX));
    assert(!nvn_imga_capacity(0,64u*1024,0));
    nvn_imga_direct_layout d=packed(); assert(nvn_imga_direct_ok(&d));
#define REJECT(field, value) do { d=packed(); d.field=(value); assert(!nvn_imga_direct_ok(&d)); } while (0)
    REJECT(base_view,0); REJECT(same_buffer,0); REJECT(word_bytes,2); REJECT(word_bytes,8);
    REJECT(layers,2); REJECT(width,0); REJECT(height,0); REJECT(width,UINT64_MAX);
    REJECT(row_bytes,2048+256); REJECT(row_bytes,2048-4); // Padding and truncated/explicit stride.
    REJECT(pointer_offset,8192); REJECT(texture_offset,4097);
    REJECT(buffer_length,4096+524287); REJECT(guest_bytes,524287);
    REJECT(buffer_texture,1); // Multi-row direct buffer images are not a packed buffer view.
#undef REJECT
    d=packed(); d.buffer_length=d.texture_offset+d.guest_bytes; assert(nvn_imga_direct_ok(&d));
    d=packed(); d.texture_offset=d.pointer_offset=UINT64_MAX-3; assert(!nvn_imga_direct_ok(&d));
    d=packed(); d.buffer_texture=1; d.height=1; d.row_bytes=4096; d.guest_bytes=2048;
    assert(nvn_imga_direct_ok(&d)); // The unused next row of a texture buffer may be padded.
    d.guest_bytes--; assert(!nvn_imga_direct_ok(&d));
    puts("image atomic layout/capacity admission: PASS");
    return 0;
}
