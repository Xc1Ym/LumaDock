"""Source-owned MSL 2.3 atomic coordinate helper, after exact ABI validation.

IR guards each original coordinate before ImageTexelPointer and remains valid
SPIR-V. Only the known standalone compiler helper is replaced: shader calls,
control flow and expressions are never matched or rewritten. Unknown backends
fail closed rather than receiving a heuristic source transformation.
"""
import re

# The recognized upstream macro is the SPIRV-Cross emulation ABI (KhronosGroup,
# Apache-2.0); the typed, layer-aware implementation below is source-owned.

_XY_HELPER = '''#define spvImage2DAtomicCoord(tc, tex) (((((tex).get_width() + spvLinearTextureAlignment / 4 - 1) & ~(spvLinearTextureAlignment / 4 - 1)) * (tc).y) + (tc).x)'''
_DEFAULT_ALIGNMENT = '''constant uint spvLinearTextureAlignment = is_function_constant_defined(spvLinearTextureAlignmentOverride) ? spvLinearTextureAlignmentOverride : 4;'''
# Explicit overloads preserve the original image-coordinate domain. uint casts
# are safe only because the IR guard dominates the atomic; use ulong for the
# address arithmetic so separate array layers cannot wrap at 32-bit offsets.
HELPERS = '''template<typename T, access A>
inline ulong spvImage2DAtomicCoord(int2 tc, texture2d<T, A> tex)
{
    ulong alignment = ulong(spvLinearTextureAlignment) / 4;
    ulong stride = (ulong(tex.get_width()) + alignment - 1) & ~(alignment - 1);
    return stride * ulong(uint(tc.y)) + ulong(uint(tc.x));
}
template<typename T, access A>
inline ulong spvImage2DAtomicCoord(int3 tc, texture2d_array<T, A> tex)
{
    ulong alignment = ulong(spvLinearTextureAlignment) / 4;
    ulong stride = (ulong(tex.get_width()) + alignment - 1) & ~(alignment - 1);
    ulong row = ulong(uint(tc.z)) * ulong(tex.get_height()) + ulong(uint(tc.y));
    return stride * row + ulong(uint(tc.x));
}'''


def _helper_line(line):
    return re.match(r'^\s*#\s*define\s+spvImage2DAtomicCoord\b', line) is not None


def validate_msl(source):
    """Validate upstream emulation ABI without modifying it."""
    if 'spvImage2DAtomicCoord' not in source:
        return source  # buffer-image atomics have no 2D helper
    compact = lambda s: re.sub(r'\s+', '', s)
    helpers = [line for line in source.splitlines() if _helper_line(line)]
    if len(helpers) != 1 or compact(helpers[0]) != compact(_XY_HELPER):
        raise ValueError('image atomic emulation: unsupported SPIRV-Cross coordinate helper; rebuild with the reviewed MSL 2.3 compiler')
    if compact(_DEFAULT_ALIGNMENT) not in compact(source):
        raise ValueError('image atomic emulation: expected four-byte default linear-texture alignment')
    return source


def lower_msl(source):
    validate_msl(source)
    # The exact definition was checked above. No shader-specific source enters
    # this module and no expression/call-site rewrite is permitted here.
    return '\n'.join(HELPERS if _helper_line(line) else line
                     for line in source.split('\n'))
