using System;

namespace Ryujinx.Graphics.Shader.Translation
{
    [Flags]
    public enum TranslationFlags
    {
        None = 0,

        VertexA = 1 << 0,
        Compute = 1 << 1,
        DebugMode = 1 << 2,
        // Offline MSL 2.3: SPIRV-Cross uses a raw pointer for image atomics.
        Msl23ImageAtomics = 1 << 3,
    }
}
