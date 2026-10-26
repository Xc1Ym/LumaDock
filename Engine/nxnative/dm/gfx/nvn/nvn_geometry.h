// Primitive assembly for geometry compute. Values are capture-record indices;
// restart separates runs before strips/fans are assembled. No game-specific state.
#pragma once
#include <stdint.h>
#include <stddef.h>

static int nvn_geo_topology(int prim) {
    switch (prim) {
        case 0: return 0;
        case 1: case 2: case 3: return 1;
        case 10: case 11: return 2;
        case 4: case 5: case 6: case 7: return 3;
        case 12: return 4;
        default: return -1;
    }
}
static int nvn_geo_width(int topology) { static const int width[] = {1, 2, 4, 3, 6}; return topology >= 0 && topology < 5 ? width[topology] : 0; }

// Returns words required/written. SIZE_MAX means unsupported topology or overflow.
// dst == NULL counts only. A short destination is never partially written.
static size_t nvn_geo_assemble(int prim, const uint32_t *src, size_t count, int restart, uint32_t restart_index, uint32_t *dst, size_t capacity) {
    int width = nvn_geo_width(nvn_geo_topology(prim));
    if (!width) return SIZE_MAX;
    if (dst) {
        size_t needed = nvn_geo_assemble(prim, src, count, restart, restart_index, NULL, 0);
        if (needed == SIZE_MAX || needed > capacity) return SIZE_MAX;
    }
    size_t words = 0;
    for (size_t begin = 0; begin < count;) {
        size_t end = begin;
        while (end < count && !(restart && src[end] == restart_index)) end++;
        size_t n = end - begin, np = 0;
        switch (prim) {
            case 0: np = n; break;
            case 1: np = n / 2; break;
            case 2: np = n > 1 ? n : 0; break;
            case 3: np = n > 1 ? n - 1 : 0; break;
            case 4: np = n / 3; break;
            case 5: case 6: np = n > 2 ? n - 2 : 0; break;
            case 7: np = n / 4 * 2; break;
            case 10: np = n / 4; break;
            case 11: np = n > 3 ? n - 3 : 0; break;
            case 12: np = n / 6; break;
        }
        if (np > (SIZE_MAX - words) / (size_t)width) return SIZE_MAX;
        if (dst && words + np * width > capacity) return SIZE_MAX;
        for (size_t i = 0; dst && i < np; i++) {
            size_t k[6] = {0};
            switch (prim) {
                case 0: k[0] = i; break;
                case 1: k[0] = 2*i; k[1] = 2*i+1; break;
                case 2: k[0] = i; k[1] = (i+1)%n; break;
                case 3: k[0] = i; k[1] = i+1; break;
                case 4: for (int c=0;c<3;c++) k[c]=3*i+c; break;
                case 5: k[0]=i+(i&1); k[1]=i+1-(i&1); k[2]=i+2; break;
                case 6: k[0]=0; k[1]=i+1; k[2]=i+2; break;
                case 7: k[0]=4*(i/2); k[1]=k[0]+1+(i&1); k[2]=k[1]+1; break;
                case 10: for (int c=0;c<4;c++) k[c]=4*i+c; break;
                case 11: for (int c=0;c<4;c++) k[c]=i+c; break;
                case 12: for (int c=0;c<6;c++) k[c]=6*i+c; break;
            }
            for (int c=0;c<width;c++) dst[words+i*width+c]=src[begin+k[c]];
        }
        words += np * width;
        begin = end < count ? end + 1 : end;
    }
    return words;
}

// One ordered compaction per draw. Output is a point/line/triangle list, so it
// does not depend on Metal primitive-restart behaviour. Preserve triangle-strip
// winding and the last vertex. Unwritten GS index slots are UINT_MAX.
// Three dispatches, in order: geo_pack_count (a thread per invocation group counts the indices it
// emits), geo_pack_scan (one workgroup scans contiguous chunks into ordered offsets and writes the indirect arguments)
// and geo_pack_write (a thread per group writes its indices at its offset). A single thread used to
// walk every group: with it, each frame that drew OCTOPATH TRAVELER II's 129,032-triangle cube shadow mesh
// (drawn in runs, nvn_geometry.inc geo_split) took about 300 ms; now only the first one is long.
static const char k_nvn_geo_pack_msl[] =
"#include <metal_stdlib>\nusing namespace metal;\n"
"struct geo_pack { device const uint *src; device uint *dst; device uint *args; uint groups, stride, topology, capacity; device uint *cnt; };\n"
"static bool geo_room(constant geo_pack&j,uint o,uint k,uint n){return o<=j.capacity&&k<=j.capacity-o&&n<=j.capacity-o-k;}\n"
"static uint geo_group(constant geo_pack& j, uint g, bool w, uint o) {\n"
" uint a=0,b=0,n=0,k=0;\n"
" for(uint i=0;i<j.stride;i++) { uint v=j.src[g*j.stride+i];\n"
"  if(v==0xffffffffu) {n=0;continue;}\n"
"  if(j.topology==1) {if(w && geo_room(j,o,k,1)) j.dst[o+k]=v; k+=1;}\n"
"  else if(j.topology==6) {if(n) {if(w && geo_room(j,o,k,2)) {j.dst[o+k]=b;j.dst[o+k+1]=v;} k+=2;}}\n"
"  else if(n>=2) {if(w && geo_room(j,o,k,3)) {j.dst[o+k]=(n&1)?b:a;j.dst[o+k+1]=(n&1)?a:b;j.dst[o+k+2]=v;} k+=3;}\n"
"  a=b;b=v;n++;\n"
" }\n"
" return k;\n"
"}\n"
"kernel void geo_pack_count(constant geo_pack& j [[buffer(0)]], uint g [[thread_position_in_grid]]) { if(g<j.groups) j.cnt[g]=geo_group(j,g,false,0); }\n"
"kernel void geo_pack_scan(constant geo_pack& j [[buffer(0)]],uint t[[thread_index_in_threadgroup]],uint3 tg[[threads_per_threadgroup]]) {\n"
" threadgroup ulong sums[256]; uint nt=tg.x, chunk=j.groups/nt+uint(j.groups%nt!=0);\n"
" uint begin=uint(min(ulong(t)*chunk,ulong(j.groups))),end=begin+min(chunk,j.groups-begin);\n"
" ulong s=0;for(uint g=begin;g<end;g++)s+=j.cnt[g];sums[t]=s;threadgroup_barrier(mem_flags::mem_threadgroup);\n"
" for(uint d=1;d<nt;d<<=1){ulong a=t>=d?sums[t-d]:0;threadgroup_barrier(mem_flags::mem_threadgroup);sums[t]+=a;threadgroup_barrier(mem_flags::mem_threadgroup);}\n"
" s=t?sums[t-1]:0;for(uint g=begin;g<end;g++){uint c=j.cnt[g];j.cnt[g]=uint(min(s,ulong(0xffffffffu)));s+=c;}\n"
" if(t==0){ulong total=sums[nt-1];uint w=j.topology==1?1u:j.topology==6?2u:3u,n=total<=j.capacity?uint(total):j.capacity-j.capacity%w;\n"
" j.args[0]=n;j.args[1]=1;j.args[2]=0;j.args[3]=0;j.args[4]=0;}\n"
"}\n"
"kernel void geo_pack_write(constant geo_pack& j [[buffer(0)]], uint g [[thread_position_in_grid]]) { if(g<j.groups) geo_group(j,g,true,j.cnt[g]); }\n";
// The job record geo_pack reads (host side): the counts / offsets buffer holds a word per group
typedef struct { uint64_t src, dst, args; uint32_t groups, stride, topology, capacity; uint64_t cnt; } nvn_geo_pack_job;
