#!/usr/bin/env python3
"""Registration gate for controller / touch modes (run in the host unit tests, takes seconds). Reads source only, does not run the game.
Three rules:
1. Every pump on the long per-frame line in dm_cursor.c either carries "if (tm) " (touch-only: not run in controller mode or while a switch is in progress) or is on the list in the comment above it headed "Runs in both modes:";
   every *_pump defined in the file must also appear on this line or on that list -- a newly added pump registered in neither fails.
2. The number of places that check the mode ad hoc (dm_padmode_current()) and that press keys / send messages on the player's behalf (fe_key / ui_auto_key / fe_send / dm_ui_key_pulse) is recorded per file in the two tables below, and may only decrease, never increase.
   To add one: first think through whether in the other mode it should stop, carry on as usual, or work differently, register it in dm_mode_items.h (for things to be cleaned up on a switch) or on the list above, then change the number here and state the reason in the commit message.
3. Every enter / leave function registered in dm_mode_items.h must have a definition.
Usage: mode_scan.py <dm directory>
"""
import re, sys, os, glob
root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', '..')
red = []
def src(rel): return open(os.path.join(root, rel), encoding='utf-8').read()
def strip_comments(s): return re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', s, flags=re.S))

# ---- 1 ----
cur = src('host/dm_cursor.c')
m = re.search(r'^.*int tm = ui_touch_mode\(\);.*$', cur, re.M)
if not m: red.append('cannot find the per-frame line in dm_cursor.c (int tm = ui_touch_mode();)')
else:
    line = m.group(0)
    both_txt = re.search(r'Runs in both modes:(.*?)\nstatic int ui_touch_mode', cur, re.S)
    both = set(re.findall(r'\b(\w+_pump|ui_map_center|ui_panel_heal)\b', both_txt.group(1))) if both_txt else set()
    if not both: red.append('cannot find the "Runs in both modes:" list in dm_cursor.c')
    on_line = {}
    for mm in re.finditer(r'(if \(tm\) )?\b(\w+_pump|ui_map_center)\(', line): on_line[mm.group(2)] = bool(mm.group(1))
    for name, gated in sorted(on_line.items()):
        if not gated and name not in both: red.append('%s on the per-frame line neither carries if (tm) nor is on the "Runs in both modes" list' % name)
        if gated and name in both: red.append('%s carries if (tm) and is also on the "Runs in both modes" list; pick one' % name)
    for name in sorted(set(re.findall(r'^static void (\w+_pump)\(', cur, re.M))):
        if name not in on_line and name not in both: red.append('dm_cursor.c defines %s, but it is neither on the per-frame line nor on the "Runs in both modes" list' % name)

# ---- 2 ----
PADMODE = {'host/dm_cursor.c': 8, 'host/dm_custom.c': 2, 'host/dm_kills.c': 2, 'host/dm_rift_ui.c': 4, 'host/dm_runeword.c': 3, 'host/dm_vault_ui.c': 1, 'host/dm_update.c': 2, 'host/hle_tact.c': 1}
AUTOKEY = {'host/dm_cursor.c': 38, 'host/dm_rift_ui.c': 6, 'host/hle_hid.c': 2, 'ios/Sources/front_ios.m': 4}
def count(pat, skip_defs):
    out = {}
    for f in sorted(glob.glob(os.path.join(root, 'host', '*.c')) + glob.glob(os.path.join(root, 'ios', 'Sources', '*.m')) + glob.glob(os.path.join(root, 'ios', 'Sources', '*.c'))):
        rel = os.path.relpath(f, root); s = strip_comments(open(f, encoding='utf-8').read()); n = 0
        for mm in re.finditer(pat, s):
            ls = s.rfind('\n', 0, mm.start()) + 1; head = s[ls:mm.start()]
            if skip_defs and re.search(r'(^|\s)(static\s+)?(void|int|uint64_t)\s+$', head): continue   # A function definition / declaration itself does not count as a call
            n += 1
        if n: out[rel] = n
    return out
for label, table, got in (('ad-hoc mode check dm_padmode_current()', PADMODE, count(r'\bdm_padmode_current\(\)', True)),
                          ('key presses / messages for the player', AUTOKEY, count(r'\b(fe_key|ui_auto_key|fe_send|dm_ui_key_pulse|dm_ui_key_pulse_alone|dm_ui_send|dm_ui_send_queue)\(', True))):
    if label.startswith('ad-hoc') and 'host/dm_padmode.c' in got: got.pop('host/dm_padmode.c')
    for rel in sorted(set(got) | set(table)):
        g, t = got.get(rel, 0), table.get(rel, 0)
        if g > t: red.append('%s: %s has %d now, the table records %d -- register the new ones first (see the top of this file), then change the table' % (label, rel, g, t))
        elif g < t: red.append('%s: %s has %d now, fewer than the %d in the table -- lower the number in the table (it may only go down)' % (label, rel, g, t))

# ---- 3 ----
items = src('host/dm_mode_items.h'); allsrc = ''.join(open(f, encoding='utf-8').read() for f in glob.glob(os.path.join(root, 'host', '*.c')))
for name, side, enter, leave in re.findall(r'X\("([^"]+)",\s*(\d),\s*(\w+),\s*(\w+)\)', items):
    for fn in (enter, leave):
        if not re.search(r'\bvoid %s\(void\)\s*\{' % fn, allsrc): red.append('dm_mode_items.h entry "%s": function %s is not defined' % (name, fn))

if red:
    print('mode registration gate [RED]: %d' % len(red)); [print('  ' + r) for r in red]; sys.exit(1)
print('✓ mode registration gate: all %d per-frame pumps are classified, ad-hoc mode checks and key presses for the player are within the registered counts, all entry functions are defined' % (len(on_line) if m else 0))
