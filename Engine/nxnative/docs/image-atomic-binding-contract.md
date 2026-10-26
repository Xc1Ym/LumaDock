# Packed image-atomic binding admission

MSL 2.3 represents an image atomic with two arguments: the IMG texture supplies
its dimensions, while IMGA is an atomic-word buffer pointer. Capacity and layout
must agree **before** either is used by a draw or dispatch. This host check is
separate from the shader translator's per-coordinate bounds checks: neither
replaces the other. Packed addressing assumes the translator's reviewed default
linear alignment of four bytes per 32-bit word.

`encode_args_` now resolves each IMGA's unique, same-register IMG once under the
existing registry lock, then uses that exact texture for both arguments. It does
not change argument-cache reuse, queue submission, resource residency, or deferred
resource lifetime.

## Admitted paths

- Real images must resolve to a scalar R32 integer texture of the shader's
  texture type: buffer, 2D, or 2D array, without multisampling.
- Direct guest-pool writes require an actual non-view buffer texture or base 2D
  texture, the matching guest dimensions/format size, one mip, the same Metal
  backing buffer and base offset, and enough bytes in both guest storage and the
  buffer. For 2D the actual buffer row pitch must equal width times four. A buffer
  texture's unused next row may be padded.
- The existing **discard scratch** path for non-linear images is retained, not
  made coherent with the image. Its previous source-sized request, 1 MiB rounding,
  reuse and deferred replacement policy remain for admitted images. Checked
  arithmetic and actual IMG dimensions ensure the existing request covers the
  matched image; no request is enlarged to conceal a mismatch.
- An unbound IMG may retain the existing dummy pointer only if its actual dummy
  extent fits and neither side resolves to a real image.

## Fail-closed limits

Direct padded-row textures, array images, original 1D descriptors (even when
normalized to a one-row Metal 2D texture), mip/layer/format views, private fallback
textures without the expected buffer, unsupported formats/shapes, failed scratch
allocation, and capacity/arithmetic failures stop with a diagnostic before the
argument buffer is bound and before the offending draw/dispatch. This is a
conservative trial compatibility restriction; a safe but unproved direct view is
also rejected. Real linear writes are **never redirected to discard scratch**.
The translator's existing 1D/1D-array normalization is preserved, but that alone
does not prove direct native storage. Non-linear images still follow the
separate matched-extent discard-scratch admission above. Buffer shader routes
remain scalar and are not rewritten by the 2D MSL helper; direct buffer host
admission still requires the actual backing buffer and offset checks.

The decisive diagnostic suffixes are:

- `ambiguous IMG partner` / `missing IMG partner`
- `unsupported or overflowing IMG extent`
- `real image is not a resolved R32 integer IMG`
- `unsupported direct IMG/IMGA layout or capacity`
- `scratch allocation or capacity failed; refusing short dummy`
- `unmatched unbound IMG/IMGA pair`

Each is prefixed by `image atomics:` and includes shader/stage/slot context.
These are fatal errors, not warning suppression or silent skipped draws. The
former scratch-allocation failure branch could return a short 64 KiB dummy while
IMG retained its original extent; it can no longer do so. This source-level
failure path has not been observed in the supplied validation run, which had a
real scratch buffer. This patch does not establish that failure path, direct-pool
layout mismatch, or residency caused an earlier GPU fault.

## Verification

```
make -C dm/gfx/tests GAME=0100F43008C44000 imga-layout
ASAN_OPTIONS=detect_leaks=0 make -C dm/gfx/tests GAME=0100F43008C44000 imga-layout-sanitize
python3 dm/gfx/tests/test_imga_binding_source.py
```

The portable fixture executes production checked arithmetic/admission helpers:
3 MiB versus 64 KiB capacity, valid packed layouts, overflow, zero dimensions,
short storage, wrong buffer/offset, view rejection, padding and direct arrays.
The source checks establish bounded wiring invariants, not Metal execution.
The fixture does not execute Metal binding. Native Objective-C compilation,
actual Metal texture-property behavior and game compatibility require separate
Apple validation. No allocator, texture readout,
shader algorithm, or game eligibility changes are included.

The buffer metadata comes from Apple's read-only [buffer offset](https://developer.apple.com/documentation/metal/mtltexture/bufferoffset?language=objc)
and [row pitch](https://developer.apple.com/documentation/metal/mtltexture/bufferbytesperrow)
properties; row/offset are queried only when a source buffer is present.
