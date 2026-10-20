# Ryujinx shader translator (vendored subset)

Three projects from Ryujinx 1.3.2: `Ryujinx.Graphics.Shader`, `Ryujinx.Common` and `Spv.Generator`, with these local changes:

- `Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs`, `GenerateTextureSample`:
  - Texel offsets that are not constants (Maxwell AOFFI / TLD4.PTP offsets read from a register) are built with `OpCompositeConstruct` and passed as `Offset`. A four-offset gather becomes four one-offset gathers, each giving component w. Upstream wrote them as an `OpConstantComposite` with `ConstOffset(s)`, which is invalid SPIR-V; SPIRV-Cross threw `nullptr` and the shader never built (2026-10-18: 8 shaders in Wonder, Link's Awakening, Tears of the Kingdom and Age of Calamity). Marked `nxnative:` in the code.
  - Texture coordinates that are NaN are replaced by 0 (the `nfZero` select). This came with the first import.
- `Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs`, `TryGetOperation` / `IsSameOperand`: a bindless handle that reaches the texture instruction through a phi is followed through the phis that feed it (a handle kept in a loop variable comes back through the loop's own phi), and two `constant buffer | constant` handles count as the same value. Upstream compared only the phi's direct inputs, so such handles fell to the texture-pool array of 32 (`*_t2d_cb0_40000000`), which cannot be bound; 218 pixel shaders in Monster Hunter Rise (2026-10-20). Marked `nxnative:` in the code.

The shader translation tool in `dm/gfx/tools/dmsh_xlate` references them to translate the original Switch shaders to SPIR-V.
License: MIT, see `LICENSE.txt`. Upstream: <https://github.com/Ryubing>.
