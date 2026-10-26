"""Conservative function matching for opt-in patches across game updates.

Fingerprints cover an entire unwind function, its internal branches, constants and
registers, and the bodies (or imported names) of its direct callees. Only relocation
addresses are normalized. This is code identity evidence, not proof that an updated
game still needs a workaround; enrolling a patch requires checking that assumption.
No fuzzy matching, raw byte scanning or guessed function boundaries.
"""
import hashlib
import json
import struct

from nso_code import fde_ranges


class MatchError(ValueError):
    pass


def _signed(n, bits):
    return n - (1 << bits) if n & (1 << (bits - 1)) else n


def _relative(w):
    """(immediate-bit mask, signed byte displacement) for direct branches."""
    if w & 0x7c000000 == 0x14000000: return 0x03ffffff, _signed(w & 0x3ffffff, 26) * 4
    if w & 0xff000010 == 0x54000000 or w & 0x7e000000 == 0x34000000:
        return 0x00ffffe0, _signed((w >> 5) & 0x7ffff, 19) * 4
    if w & 0x7e000000 == 0x36000000: return 0x0007ffe0, _signed((w >> 5) & 0x3fff, 14) * 4
    return None


def _pc_relative(w):
    return _relative(w) or w & 0x1f000000 == 0x10000000 or w & 0x3b000000 == 0x18000000


class Image:
    def __init__(self, image, text_end):
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        self.image, self.text_end = image, text_end
        self.md = Cs(CS_ARCH_ARM64, CS_MODE_ARM); self.md.detail = True
        self.bodies, self.fingerprints = {}, {}
        try:
            ranges = fde_ranges(image)
        except (AssertionError, ValueError, IndexError, struct.error) as e:
            raise MatchError(f'cannot read function boundaries: {e}') from e
        self.functions = {}
        for start, end in ranges:
            if not 0 <= start < end <= min(text_end, len(image)) or start % 4 or end % 4: continue
            if start in self.functions and self.functions[start] != end:
                raise MatchError(f'conflicting function boundaries at {start:#x}')
            self.functions[start] = end
        self.imports = None

    def _body(self, start):
        if start in self.bodies: return self.bodies[start]
        end = self.functions[start]
        code = self.image[start:end]
        ins = list(self.md.disasm(code, start))
        if len(ins) * 4 != len(code): raise MatchError(f'undecodable function at {start:#x}')
        words = list(struct.unpack('<' + 'I' * len(ins), code))
        normalized, branches = words.copy(), []
        for i, (w, op) in enumerate(zip(words, ins)):
            branch = _relative(w)
            if branch:
                mask, delta = branch; target = op.address + delta
                if not start <= target < end:
                    normalized[i] &= ~mask
                    branches.append((i * 4, target))
            elif w & 0x1f000000 == 0x10000000:  # ADR / ADRP
                delta = _signed(((w >> 29) & 3) | ((w >> 5) & 0x7ffff) << 2, 21)
                if w & 0x80000000 or not start <= op.address + delta < end:
                    normalized[i] &= 0x9f00001f
            elif w & 0x3b000000 == 0x18000000:  # literal load
                target = op.address + _signed((w >> 5) & 0x7ffff, 19) * 4
                if not start <= target < end: normalized[i] &= 0xff00001f
            if w & 0x9f000000 != 0x90000000: continue
            rd = w & 31
            for j in range(i + 1, min(i + 9, len(words))):
                u = words[j]
                # The low part of an ADRP address, not an ordinary member offset.
                if ((u & 0xffc00000 == 0x91000000 or u & 0x3b000000 == 0x39000000)
                        and (u >> 5) & 31 == rd):
                    normalized[j] &= ~0x3ffc00
                    break
                if _relative(u) or ins[j].mnemonic in ('br', 'blr', 'ret'): break
                _, writes = ins[j].regs_access()
                if any(ins[j].reg_name(r) in (f'x{rd}', f'w{rd}', {29: 'fp', 30: 'lr'}.get(rd, '')) for r in writes): break
        digest = hashlib.sha256(struct.pack('<' + 'I' * len(normalized), *normalized)).hexdigest()
        self.bodies[start] = digest, branches
        return digest, branches

    def _import_slots(self):
        """GOT slot -> symbol name from DT_JMPREL; unknown formats cannot match."""
        if self.imports is not None: return self.imports
        self.imports = {}
        img = self.image
        try:
            mod = struct.unpack_from('<I', img, 4)[0]
            dyn = mod + struct.unpack_from('<i', img, mod + 4)[0]
            tags = {}
            for pos in range(dyn, min(len(img) - 15, dyn + 4096 * 16), 16):
                tag, value = struct.unpack_from('<qQ', img, pos)
                if tag == 0: break
                tags[tag] = value
            if tags.get(20) != 7: return self.imports  # DT_PLTREL must be DT_RELA
            for pos in range(tags[23], tags[23] + tags[2], 24):
                slot, info, _ = struct.unpack_from('<QQq', img, pos)
                if info & 0xffffffff != 1026: continue  # R_AARCH64_JUMP_SLOT
                name = struct.unpack_from('<I', img, tags[6] + (info >> 32) * 24)[0] + tags[5]
                self.imports[slot] = bytes(img[name:img.index(0, name)]).decode('utf-8')
        except (KeyError, ValueError, IndexError, struct.error):
            self.imports = {}
        return self.imports

    def _callee(self, target):
        # AArch64 PLT: adrp x16, page; ldr x17,[x16,#lo]; add x16,x16,#lo; br x17.
        if 0 <= target <= min(self.text_end, len(self.image)) - 16:
            a, b, c, d = struct.unpack_from('<4I', self.image, target)
            if (a & 0x9f00001f == 0x90000010 and b & 0xffc003ff == 0xf9400211
                    and c & 0xffc003ff == 0x91000210 and d == 0xd61f0220):
                page = (target & ~0xfff) + (_signed(((a >> 29) & 3) | ((a >> 5) & 0x7ffff) << 2, 21) << 12)
                lo = ((b >> 10) & 0xfff) * 8
                if (c >> 10) & 0xfff == lo:
                    name = self._import_slots().get(page + lo)
                    if name: return ('import', name)
        if target not in self.functions: raise MatchError(f'callee has no verified boundary or import at {target:#x}')
        return ('function', self.functions[target] - target, self._body(target)[0])

    def fingerprint(self, start):
        if start not in self.fingerprints:
            body, branches = self._body(start)
            refs = [(off, self._callee(target)) for off, target in branches]
            self.fingerprints[start] = hashlib.sha256(json.dumps([body, refs], separators=(',', ':')).encode()).hexdigest()
        return self.fingerprints[start]

    def recipe(self, offset, old, new, name):
        """Prepare a rule from a reviewed cut; the caller must validate another build."""
        starts = [s for s, e in self.functions.items() if s <= offset and offset + len(bytes.fromhex(old)) <= e]
        if len(starts) != 1: raise MatchError('cut must belong to exactly one complete unwind function')
        start, = starts
        rule = dict(name=name, size=self.functions[start] - start, fingerprints=[self.fingerprint(start)],
                    cuts=[(offset - start, old, new, name)])
        validate(rule)
        if self.image[offset:offset + len(bytes.fromhex(old))] != bytes.fromhex(old): raise MatchError('original bytes do not match')
        self.match(rule)  # an authoring tool must reject an ambiguous reference too
        return rule

    def match(self, rule):
        validate(rule)
        matches = []
        for start, end in self.functions.items():
            if end - start != rule['size']: continue
            try: digest = self.fingerprint(start)
            except MatchError: continue
            if digest in rule['fingerprints']: matches.append(start)
        if len(matches) != 1: raise MatchError(f'{len(matches)} matching functions (need exactly one)')
        start, = matches
        cuts = []
        for delta, old, new, reason in rule['cuts']:
            off = start + delta
            if self.image[off:off + len(bytes.fromhex(old))] != bytes.fromhex(old): raise MatchError(f'original bytes differ at {off:#x}')
            cuts.append((off, old, new, reason + ' [function match]'))
        return cuts


def validate(rule):
    """Reject malformed rules and replacements whose meaning depends on an address."""
    if set(rule) != {'name', 'size', 'fingerprints', 'cuts'}: raise ValueError('function patch needs name, size, fingerprints and cuts')
    if not rule['name'] or not isinstance(rule['size'], int) or rule['size'] <= 0 or rule['size'] % 4: raise ValueError('invalid function size/name')
    if not isinstance(rule['fingerprints'], (list, tuple)) or not rule['fingerprints']: raise ValueError('missing function fingerprints')
    for digest in rule['fingerprints']:
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest): raise ValueError('invalid function fingerprint')
    if not rule['cuts']: raise ValueError('function patch has no cuts')
    used = set()
    for delta, old, new, reason in rule['cuts']:
        ob, nb = bytes.fromhex(old), bytes.fromhex(new)
        if (not reason or len(ob) != len(nb) or not ob or len(ob) % 4 or delta % 4
                or not 0 <= delta <= rule['size'] - len(ob)): raise ValueError('invalid function-relative cut')
        span = set(range(delta, delta + len(ob)))
        if used & span: raise ValueError('overlapping cuts')
        used |= span
        if any(_pc_relative(w) for w, in struct.iter_unpack('<I', nb)): raise ValueError('replacement must not contain PC-relative instructions')


def resolve(image, text_end, rules, report=print):
    """Return verified cuts without mutating the image; refuse missing/ambiguous rules."""
    if not rules: return []
    try: module = Image(image, text_end)
    except MatchError as e:
        report(f'[RED] function patches skipped: {e}')
        return []
    cuts, groups = [], {}
    # Rules with the same name are one patch's reviewed implementations (a function another build changed, with its own size or cut offsets): exactly one of them must match
    for rule in rules: groups.setdefault(rule['name'], []).append(rule)
    for name, alternatives in groups.items():
        found, misses = [], []
        for i, rule in enumerate(alternatives, 1):
            try: found.append((i, module.match(rule)))
            except MatchError as e: misses.append(str(e))
        if len(found) != 1:
            report(f'[RED] function patch {name!r} skipped: ' + (f'{len(found)} implementations match (need exactly one)' if found else '; '.join(misses)))
            continue
        (i, got), = found
        cuts.extend(got)
        report(f'function patch {name!r}: matched at {got[0][0]:#x}' + (f' (implementation {i} of {len(alternatives)})' if len(alternatives) > 1 else ''))
    occupied = set()
    for off, old, _, _ in cuts:
        span = set(range(off, off + len(bytes.fromhex(old))))
        if span & occupied: raise MatchError('function patches overlap')
        occupied |= span
    return cuts


if __name__ == '__main__':
    import argparse
    from nso_syms import load
    ap = argparse.ArgumentParser(description='Prepare an opt-in function patch from a reviewed NSO cut; verify its match on another build before registering it.')
    ap.add_argument('nso'); ap.add_argument('offset', type=lambda s: int(s, 0)); ap.add_argument('old'); ap.add_argument('new'); ap.add_argument('name')
    args = ap.parse_args()
    with open(args.nso, 'rb') as f: header = f.read(0x30)
    print(json.dumps(Image(load(args.nso), struct.unpack_from('<I', header, 0x18)[0]).recipe(args.offset, args.old, args.new, args.name), indent=2))
