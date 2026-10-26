"""Function patch recognition through real AArch64 code and synthetic unwind tables.
No game files. Relocation is accepted; changed logic, callees, ambiguity and wrong
profile/module selection are refused through the rewriter's actual registry code.
"""
import ast
import copy
import glob
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from nso_asm import ADRP, ADDI, B, NOP
from nso_match import Image, MatchError, resolve, validate

MOV = 0xaa1703e0  # mov x0, x23
ADD = 0x914012e0  # add x0, x23, #0x4000
RET = 0xd65f03c0


def image(functions):
    """A MOD0 and .eh_frame_hdr describing the supplied functions."""
    out = bytearray(0x4000)
    struct.pack_into('<I', out, 4, 0x20)
    out[0x20:0x24] = b'MOD0'
    struct.pack_into('<ii', out, 0x30, 0x3000 - 0x20, 0x300c + len(functions) * 8 - 0x20)
    out[0x3000:0x3004] = bytes((1, 0x1b, 3, 0x3b))
    struct.pack_into('<iI', out, 0x3004, 0x3200 - 0x3004, len(functions))
    # A zR CIE with pcrel/sdata4 PCs and four-byte lengths.
    struct.pack_into('<II', out, 0x3200, 16, 0)
    out[0x3208:0x3211] = b'\x01zR\0\x04\x78\x1e\x01\x1b'
    for i, (start, words) in enumerate(sorted(functions.items())):
        struct.pack_into('<' + 'I' * len(words), out, start, *words)
        fde = 0x3240 + i * 24
        struct.pack_into('<ii', out, 0x300c + i * 8, start - 0x3000, fde - 0x3000)
        struct.pack_into('<IIiI', out, fde, 16, fde + 4 - 0x3200, start - (fde + 8), len(words) * 4)
    return out


def caller(start, target, data=0x2200):
    return [ADRP(8, start, data), ADDI(8, 8, data & 0xfff), MOV,
            B(start + 12, target) | 0x80000000, 0x54000040, NOP, RET]  # bl; b.eq +8


def imported(name, plt=0x1800, slot=0x2500):
    out = image({0x100: caller(0x100, plt)})
    struct.pack_into('<i', out, 0x24, 0x2100 - 0x20)
    for i, (tag, value) in enumerate(((20, 7), (23, 0x2200), (2, 24), (6, 0x2300), (5, 0x2400), (0, 0))):
        struct.pack_into('<qQ', out, 0x2100 + i * 16, tag, value)
    struct.pack_into('<QQq', out, 0x2200, slot, (1 << 32) | 1026, 0)
    struct.pack_into('<I', out, 0x2318, 1)
    data = b'\0' + name.encode() + b'\0'; out[0x2400:0x2400 + len(data)] = data
    lo = slot & 0xfff
    struct.pack_into('<4I', out, plt, ADRP(16, plt, slot), 0xf9400211 | (lo // 8) << 10, ADDI(16, 16, lo), 0xd61f0220)
    return out


class Matching(unittest.TestCase):
    def setUp(self):
        self.original = image({0x100: caller(0x100, 0x500), 0x500: [0xd2800020, RET]})
        self.rule = Image(self.original, 0x2000).recipe(0x108, 'e00317aa', 'e0124091', 'heap')

    def test_relocated_function_callee_and_data_addresses(self):
        new = image({0x800: caller(0x800, 0x1200, 0x2980), 0x1200: [0xd2800020, RET]})
        before = bytes(new)
        cuts = resolve(new, 0x2000, [self.rule], lambda _: None)
        self.assertEqual(cuts[0][:3], (0x808, 'e00317aa', 'e0124091'))
        self.assertEqual(bytes(new), before)  # selection never writes partially verified patches

    def test_changed_logic_and_callee_are_not_matches(self):
        for off, word in ((0x108, 0xaa1603e0), (0x110, 0x54000020), (0x500, 0xd2800040)):
            with self.subTest(off=hex(off)):
                changed = bytearray(self.original); struct.pack_into('<I', changed, off, word)
                with self.assertRaisesRegex(MatchError, '0 matching'):
                    Image(changed, 0x2000).match(self.rule)

    def test_call_redirected_to_different_function(self):
        changed = image({0x100: caller(0x100, 0x600), 0x500: [0xd2800020, RET], 0x600: [0xd2800040, RET]})
        with self.assertRaisesRegex(MatchError, '0 matching'): Image(changed, 0x2000).match(self.rule)

    def test_import_identity_survives_relocation_but_not_redirection(self):
        old = Image(imported('allocate'), 0x2000)
        rule = old.recipe(0x108, 'e00317aa', 'e0124091', 'heap')
        moved = Image(imported('allocate', plt=0x1900, slot=0x2800), 0x2000)
        self.assertEqual(moved.match(rule)[0][0], 0x108)
        with self.assertRaisesRegex(MatchError, '0 matching'):
            Image(imported('free'), 0x2000).match(rule)

    def test_address_register_clobbers_preserve_member_offsets(self):
        for reg, move in ((8, 0x2a0003e8), (29, 0xaa0003fd)):
            words = [ADRP(reg, 0x100, 0x2000), move, 0xf9400000 | (reg << 5) | (8 << 10), MOV, RET]
            old = image({0x100: words})
            rule = Image(old, 0x2000).recipe(0x10c, 'e00317aa', 'e0124091', 'heap')
            words[2] += 1 << 10  # changed field offset after the address was overwritten
            with self.assertRaisesRegex(MatchError, '0 matching'):
                Image(image({0x100: words}), 0x2000).match(rule)

    def test_internal_adr_target_is_not_normalized(self):
        old = image({0x100: [MOV, 0x10000040, NOP, RET]})  # adr x0, function+12
        rule = Image(old, 0x2000).recipe(0x100, 'e00317aa', 'e0124091', 'heap')
        new = image({0x100: [MOV, 0x10000020, NOP, RET]})  # adr x0, function+8
        with self.assertRaisesRegex(MatchError, '0 matching'): Image(new, 0x2000).match(rule)

    def test_ambiguous_function_and_missing_callee_boundary(self):
        duplicate = image({0x100: caller(0x100, 0x500), 0x800: caller(0x800, 0x500), 0x500: [0xd2800020, RET]})
        with self.assertRaisesRegex(MatchError, '2 matching'): Image(duplicate, 0x2000).match(self.rule)
        missing = image({0x100: caller(0x100, 0x500)})
        with self.assertRaisesRegex(MatchError, '0 matching'): Image(missing, 0x2000).match(self.rule)

    def test_original_bytes_still_required(self):
        rule = copy.deepcopy(self.rule); rule['cuts'][0] = (8, '00000000', 'e0124091', 'heap')
        with self.assertRaisesRegex(MatchError, 'original bytes differ'): Image(self.original, 0x2000).match(rule)

    def test_relocations_in_replacement_are_rejected(self):
        for w in (B(0, 4), ADRP(0, 0, 0x1000), 0x58000020):
            rule = copy.deepcopy(self.rule); rule['cuts'][0] = (8, 'e00317aa', struct.pack('<I', w).hex(), 'heap')
            with self.assertRaisesRegex(ValueError, 'PC-relative'): validate(rule)

    def test_no_boundaries_and_ambiguous_match_are_reported(self):
        for img in (bytearray(0x40), image({0x100: [RET]})):
            messages = []
            self.assertEqual(resolve(img, len(img), [self.rule], messages.append), [])
            self.assertTrue(messages[0].startswith('[RED] '))

    def test_overlapping_rules_are_rejected(self):
        other = dict(self.rule, name='another patch')
        with self.assertRaisesRegex(MatchError, 'overlap'):
            resolve(self.original, 0x2000, [self.rule, other], lambda _: None)

    def test_same_name_rules_are_alternative_implementations(self):
        # A later build changed the function (another size, the cut elsewhere in it): one rule per reviewed implementation, under one name
        def changed(start):  # caller() with one more instruction before the cut
            return [ADRP(8, start, 0x2200), ADDI(8, 8, 0x200), NOP, MOV, B(start + 16, 0x500) | 0x80000000, 0x54000040, NOP, RET]
        later = image({0x100: changed(0x100), 0x500: [0xd2800020, RET]})
        alt = Image(later, 0x2000).recipe(0x10c, 'e00317aa', 'e0124091', 'heap')
        self.assertNotEqual(alt['size'], self.rule['size'])
        for img, off in ((self.original, 0x108), (later, 0x10c)):
            with self.subTest(off=hex(off)):
                messages = []
                cuts = resolve(img, 0x2000, [self.rule, alt], messages.append)
                self.assertEqual([c[0] for c in cuts], [off])
                self.assertFalse([m for m in messages if m.startswith('[RED]')], messages)
        messages = []
        self.assertEqual(resolve(image({0x100: [RET]}), 0x2000, [self.rule, alt], messages.append), [])
        self.assertEqual(len(messages), 1); self.assertTrue(messages[0].startswith('[RED] '))
        both = image({0x100: caller(0x100, 0x500), 0x800: changed(0x800), 0x500: [0xd2800020, RET]})
        messages = []
        self.assertEqual(resolve(both, 0x2000, [self.rule, alt], messages.append), [])
        self.assertIn('2 implementations match', messages[0])

    def test_registry_scopes_rules_and_preserves_known_builds(self):
        source = TOOLS / 'patch_nso.py'; tree = ast.parse(source.read_text())
        start = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'PATCH_FILES')
        end = next(i for i, n in enumerate(tree.body[start:], start) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'KEYS')
        code = compile(ast.Module(body=tree.body[start:end], type_ignores=[]), str(source), 'exec')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'tools').mkdir(); (root / 'tools/sdk_patches.py').write_text('')
            for gid in ('0100000000000001', '0100000000000002'):
                p = root / 'games' / gid / 'patches.py'; p.parent.mkdir(parents=True)
                rule = copy.deepcopy(self.rule)
                replacement = 'e0124091' if gid.endswith('1') else '1f2003d5'  # different game, different fix
                rule['cuts'][0] = (8, 'e00317aa', replacement, 'heap')
                p.write_text(f'MATCH_CUTS = {{"main": [{rule!r}]}}\n' +
                             ("CUTS = {'" + 'ab' * 16 + "': [(0x108, 'e00317aa', '1f2003d5', 'known')]}\n" if gid.endswith('1') else ''))
            for gid, name, bid, expected in (
                    ('0100000000000001', 'main', '00' * 16, ADD),
                    ('0100000000000002', 'main', '00' * 16, NOP),
                    ('0100000000000003', 'main', '00' * 16, MOV),
                    ('0100000000000001', 'sdk', '00' * 16, MOV),
                    ('0100000000000001', 'main', 'ab' * 16, NOP)):
                with self.subTest(game=gid, module=name, build=bid):
                    img = bytearray(self.original)
                    ns = dict(__file__=str(root / 'tools/patch_nso.py'), os=os, glob=glob, importlib=importlib,
                              d=bytes(0x40) + bytes.fromhex(bid), IMG=img, TEXT_END=0x2000, NAME=name)
                    with patch.dict(os.environ, DM_GAME=gid, DM_GAMES_DIR='/derived/profile', DM_GAMES_FIRST='1'):
                        exec(code, ns)
                    self.assertEqual(struct.unpack_from('<I', img, 0x108)[0], expected)


if __name__ == '__main__': unittest.main()
