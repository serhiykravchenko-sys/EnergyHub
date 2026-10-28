"""Presentation reorganization retains household control and safety boundaries."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
def walk(n):
    if isinstance(n,dict):
        yield n
        for child in n.values():yield from walk(child)
    elif isinstance(n,list):
        for child in n:yield from walk(child)

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.views=json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))['data']['config']['views']

    def test_native_toggles_unique_and_real_settings_separate(self):
        nodes=list(walk(self.views));mission=next(v for v in self.views if v['path']=='mission-control')
        for entity in ['automation.energyhub_battery_discharge_protection',
                       'automation.energyhub_fridge_battery_protection_20_30',
                       'input_boolean.energyhub_load_control_armed']:
            buttons=[n for n in nodes if n.get('type')=='button' and n.get('entity')==entity]
            self.assertEqual(1,len(buttons));self.assertEqual('toggle',buttons[0]['tap_action']['action'])
            self.assertIn(buttons[0],list(walk(mission)))
        settings=next(v for v in self.views if v['path']=='settings')
        for entity in ['number.energyhub_normal_reserve','input_number.energyhub_load_off_soc',
                       'input_number.energyhub_load_restore_soc','input_number.energyhub_battery_capacity_kwh']:
            self.assertTrue(any(n.get('entity')==entity for n in walk(settings)))
            self.assertFalse(any(n.get('entity')==entity for n in walk(mission)))

    def test_diagnostics_not_mission_and_navigation_resolves(self):
        mission=next(v for v in self.views if v['path']=='mission-control')
        self.assertFalse(any(n.get('title')=='Overload devices · Restoration order' for n in walk(mission)))
        diag=next(v for v in self.views if v['path']=='diagnostics')
        self.assertTrue(any(n.get('title')=='Overload devices · Restoration order' for n in walk(diag)))
        paths={v['path'] for v in self.views}
        for n in walk(self.views):
            if n.get('tap_action',{}).get('action')=='navigate':
                self.assertIn(n['tap_action']['navigation_path'].rsplit('/',1)[-1],paths)

    def test_bms_direction_colors_and_integer_zero_axis_keep_widths(self):
        bms=next(v for v in self.views if v['path']=='bms');chart=bms['cards'][1]
        self.assertEqual([3,2],[s['stroke_width'] for s in chart['series']])
        self.assertEqual('#2ecc71',chart['series'][0]['color'])
        self.assertEqual(['#3498db','#e74c3c'],[r['color'] for r in chart['series'][1]['color_threshold']])
        self.assertEqual(['#2ecc71','#3498db'],[a['apex_config']['labels']['style']['colors'] for a in chart['yaxis']])
        self.assertEqual([0,0],[a['decimals'] for a in chart['yaxis']])
        self.assertEqual(20,chart['yaxis'][1]['align_to'])
        self.assertEqual(0,chart['apex_config']['annotations']['yaxis'][0]['y'])
