# libdeflate (third party, MIT license, see COPYING)
- Upstream: https://github.com/ebiggers/libdeflate  commit 92e6a0d (2026-08-22)
- Use: zlib decoding of the BLTE blocks in TACT storage (host hle_tact.c, taken over at the main 0x1b0ee60 entry through a rewriter cut)
- Offline cross-check on the 10-01 platform line: all 4,979 files actually decompressed before character select have MD5 == the manifest CKey; 2.42× faster than the game's own zlib 1.2.11 on the same machine
- Only the decompression sources are compiled: lib/deflate_decompress.c, lib/zlib_decompress.c, lib/adler32.c, lib/utils.c, lib/arm/cpu_features.c
- Upstream code unmodified
