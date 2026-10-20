#!/usr/bin/env python3
# Runs the shader build chain on a machine without Apple's Metal compiler (Windows / Linux / a Mac without Xcode; for use by tools/d2rm_pack.py).
# Usage: nometal_run.py <script.py> [args...]   Example: nometal_run.py dmsh_build.py <package dir> <cache dir>
# How: not a single file of the build chain is modified (their contents feed into the translation chain version, and any change would force a whole new generation of the beta shader libraries); only, within this process, the one entry through which they call external commands
# (subprocess.run) is taken over: the commands below are recognized and answered here, and everything else is passed through unchanged:
#   xcrun -sdk <x> metal --version              → answers "none" (the compiler is recorded as unused in the tool fingerprint → the chain version forms its own branch, and its cache never mixes with normal mode's)
#   xcrun -sdk <x> metal -c <source> -o <intermediate file>    → copies the source as the intermediate file (line endings normalized to LF)
#   xcrun -sdk <x> metallib <intermediate file> -o <library>      → copies the intermediate file verbatim as the library
#   which <name>                                 → looked up by Python itself
#   cp -c <a> <b>                              → ordinary copy
# Result: the "library files" (*_b.metallib / *_bf.metallib) contain shader source. When the graphics layer of the shell (DM_SHELL build) finds that a library is not a compiled one, it compiles it on the device
# (gfx/nvn/nvn_mtl.m); the system caches the compiled result, and from the second launch on nothing is compiled again.
# The one check that is lost: in normal mode Apple's compiler also verifies along the way that every source compiles; here that is not verified, and one that fails to compile only reports a failure when it is used on the device.
import os, runpy, shutil, subprocess, sys

_real = subprocess.run


def _done(args, out=''):
    return subprocess.CompletedProcess(args, 0, stdout=out, stderr='')


def run(args, *a, **k):
    text = k.get('text') or k.get('universal_newlines')
    enc = (lambda s: s) if text else (lambda s: s.encode())
    if isinstance(args, (list, tuple)) and args:
        c = [str(x) for x in args]
        if c[0] == 'xcrun' and 'metal' in c and '--version' in c: return _done(args, enc('none\n'))
        if c[0] == 'xcrun' and 'metal' in c and '-c' in c and '-o' in c:   # source = the first argument after metal that is neither an option nor the value of -o (the iOS command also carries a version option after -c)
            o = c.index('-o'); src = [x for i, x in enumerate(c[c.index('metal') + 1:], c.index('metal') + 1) if not x.startswith('-') and i != o + 1]
            if len(src) != 1: raise RuntimeError('nometal_run: cannot tell the source argument in %r' % c)
            with open(src[0], 'rb') as f: b = f.read()
            with open(c[o + 1], 'wb') as f: f.write(b.replace(b'\r\n', b'\n'))   # On Windows spirv-cross writes sources with CRLF line endings: normalize before they go into the install package, so the same input gives the same package on every system
            return _done(args, enc(''))
        if c[0] == 'xcrun' and 'metallib' in c and '-o' in c: shutil.copyfile(c[c.index('metallib') + 1], c[c.index('-o') + 1]); return _done(args, enc(''))
        if c[0] == 'xcrun': raise RuntimeError('nometal_run: unrecognized xcrun command %r' % c)
        if c[0] == 'which' and len(c) == 2: return _done(args, enc((shutil.which(c[1]) or '') + '\n'))
        if c[0] == 'cp' and len(c) == 4 and c[1] == '-c': shutil.copyfile(c[2], c[3]); return _done(args, enc(''))
    return _real(args, *a, **k)


if __name__ == '__main__':
    if len(sys.argv) < 2: sys.exit(__doc__ or 'usage: nometal_run.py <script.py> [args...]')
    subprocess.run = run
    script = os.path.abspath(sys.argv[1]); sys.argv = sys.argv[1:]; sys.path.insert(0, os.path.dirname(script))
    runpy.run_path(script, run_name='__main__')
