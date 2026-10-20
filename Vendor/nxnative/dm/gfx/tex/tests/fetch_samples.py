# Fetch real-data samples for cross-checking: one copy each of the same-named .texture from the Switch package (RomFS, block-linear) and the PC package (extracted originals, linear).
# Usage: fetch_samples.py <output dir>   → <output dir>/{dm,pc}/<index>.texture + list.tsv (index, path, note)
# Sample selection: covers RGBA8 / BC1 / BC3 / BC4, sizes from 32² to 2048², including non-square; same-resolution ones are compared byte for byte, reduced-resolution ones by decoded PSNR.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../tools'))
DM_ROOT = os.environ.get('DM_ROOT') or os.path.expanduser('~/dm-work')   # Workspace root (game files, build outputs and run artifacts are all under it)
os.environ.setdefault('DMX_ROOT', os.path.join(DM_ROOT, 'data/switch/3.3.94012/Update/RomFS/data'))
import dmx
PC = os.path.join(DM_ROOT, 'data/assets-src/raw')
SAMPLES = [
    ('hd/vfx/textures/gradient/T_FX_perlin_wipe_03.texture', 'RGBA8 256² same resolution'),
    ('hd/vfx/textures/gradient/T_FX_portal_gradient.texture', 'RGBA8 256×16 non-square same resolution'),
    ('hd/env/texture/terrain/path/066_PATH.texture', 'BC4 32² same resolution'),
    ('hd/debug/wasted_mip_size_2048.texture', 'BC3 sRGB 2048² 12 levels same resolution'),
    ('hd/items/armor/armor/plate_mail/textures/armor_plate_mail_alb.texture', 'BC3 sRGB 256² (PC 1024²) reduced resolution'),
    ('hd/env/texture/global/flow/act4/lava/lava_lavaNS_FLOW.texture', 'BC1 64² (PC 256²) reduced resolution'),
    ('hd/character/enemy/fingermage1/Textures/fingermage_KTINT.texture', 'BC3 256² (PC 1024²) reduced resolution'),
]
out = sys.argv[1]
os.makedirs(f'{out}/dm', exist_ok=True); os.makedirs(f'{out}/pc', exist_ok=True)
with open(f'{out}/list.tsv', 'w') as f:
    for i, (p, why) in enumerate(SAMPLES):
        open(f'{out}/dm/{i}.texture', 'wb').write(dmx.get('data:data/' + p))
        open(f'{out}/pc/{i}.texture', 'wb').write(open(os.path.join(PC, p), 'rb').read())
        f.write(f'{i}\t{p}\t{why}\n')
print(len(SAMPLES), 'sample pairs →', out)
