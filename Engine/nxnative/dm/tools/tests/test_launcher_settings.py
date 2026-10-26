"""The launcher's settings (dm/games/settings.tsv through dm/games/settings.py): rows by graphics API and profile, single-screen sections, toggle values and the strict format."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('launcher_settings', ROOT / 'dm/games/settings.py')
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)

BOTW, WONDER = '01007EF00011E000', '010015100B514000'
PERFORMANCE_NVN = ['DM_PRESENT_SNAP', 'DM_PSO_MTL4', 'DM_PSO_PREBUILD', 'DM_NVN_ENC_THREAD', 'DM_FPS_HOLD', 'DM_METAL_HUD']


def build(gid, api):
    with tempfile.TemporaryDirectory() as tmp, patch.object(settings.nacp, 'languages', return_value=['en-US']), patch.dict(os.environ, {'GFXAPI': api}):
        return {s['env']: s for s in settings.build(gid, tmp, Path(tmp) / 'control.nacp')['settings']}


class LauncherSettingsTests(unittest.TestCase):
    def test_upscaling_is_opt_in_for_every_graphics_api(self):
        for api, gid in [('nvn', BOTW), ('vulkan', '0100535012974000'), ('gl', '010014E00DB56000')]:
            with self.subTest(api=api):
                s = build(gid, api)['DM_PRESENT_UPSCALE']
                self.assertEqual((s['kind'], s['section'], s['default']), ('choice', 'Game', 'off'))
                self.assertEqual(s['options'], [['off', 'Standard'], ['metalfx', 'MetalFX']])

    def test_frame_buffering_by_graphics_api(self):
        for api, gid in [('nvn', BOTW), ('vulkan', '0100535012974000'), ('gl', '010014E00DB56000'), ('', BOTW)]:
            with self.subTest(api=api):
                rows = build(gid, api)
                self.assertEqual('DM_PRESENT_SNAP' in rows, api == 'nvn')
                if api == 'nvn':
                    s = rows['DM_PRESENT_SNAP']
                    self.assertEqual((s['kind'], s['section'], s['default']), ('toggle', 'Performance', '1'))   # Breath of the Wild's profile: present_snap on
                    self.assertIn('latency', s['note'])

    def test_sections_keep_the_profile_defaults(self):
        botw, wonder = build(BOTW, 'nvn'), build(WONDER, 'nvn')
        self.assertEqual([e for e, s in botw.items() if s['section'] == 'Performance'], PERFORMANCE_NVN)
        self.assertEqual(botw['DM_PSO_MTL4']['default'], '1')   # pso_mtl4 on
        self.assertEqual((wonder['DM_PRESENT_SNAP']['default'], wonder['DM_PSO_MTL4']['default']), ('0', '0'))
        self.assertEqual((botw['DM_PSO_PREBUILD']['default'], botw['DM_NVN_ENC_THREAD']['default'], botw['DM_METAL_HUD']['default']), ('1', '1', '0'))   # the host's iOS defaults
        self.assertEqual(list(dict.fromkeys(s['section'] for s in botw.values())), ['Game', 'Controls', 'Performance'])
        self.assertNotIn('DM_FPS_HOLD', wonder)   # no frame step, as the Frame rate row
        self.assertIn('first start', botw['DM_PSO_PREBUILD']['note'])   # it runs once in the prepare step, before the first frame

    def test_hold_frames_takes_on_and_off(self):   # the host reads DM_FPS_HOLD as on / off (hle_nvn.c), not 1 / 0
        s = build(BOTW, 'nvn')['DM_FPS_HOLD']
        self.assertEqual((s['on'], s['off'], s['default']), ('on', 'off', 'on'))
        s = build(BOTW, 'nvn')['DM_SHOW_FPS']
        self.assertEqual((s['on'], s['off']), ('1', '0'))

    def test_table_format_is_strict(self):
        good = 'DM_X\ttoggle\t-\t0\talways\tGame\tX\n'
        for bad, why in [('DM_X\ttoggle\t-\t0\talways\tX\n', 'columns'), ('DM_X\ttoggle\t-\t0\talways\tsecret\tX\n', 'section'),
                         ('DM_X\ttoggle\ton\t0\talways\tGame\tX\n', 'toggle values'), ('DM_X\ttoggle\t-\t2\talways\tGame\tX\n', 'defaults to 0 or 1')]:
            with self.subTest(why=why), tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / 'settings.tsv').write_text('# header\n' + good + bad, encoding='utf-8')
                with patch.object(settings, 'HERE', Path(tmp)), \
                        patch.object(settings.nacp, 'languages', return_value=['en-US']), self.assertRaises(SystemExit) as e:
                    settings.build(BOTW, tmp, Path(tmp) / 'control.nacp')
                self.assertIn(why, str(e.exception))


if __name__ == '__main__':
    unittest.main()
