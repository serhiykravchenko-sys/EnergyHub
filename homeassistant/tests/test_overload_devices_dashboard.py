"""Native overload observation table and read-only BMS view."""
import json
from pathlib import Path
import unittest
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[2]

def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from walk(child)
    elif isinstance(value,list):
        for child in value:yield from walk(child)

class OverloadDevicesTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        self.table=next(c['content'] for c in walk(self.data) if c.get('title')=='Overload devices · Restoration order')
    def test_five_devices_microwave_first(self):
        names=['Microwave','Water pump','Water boiler','Second-floor heat pump','Third-floor heat pump']
        positions=[self.table.index(name) for name in names]
        self.assertEqual(sorted(positions),positions)
        self.assertEqual(7,len(self.table.split('\n\n')[0].splitlines()))
        self.assertNotIn('climate.',self.table)
        self.assertNotIn('switch.first_floor_hp_meter',self.table)
    def test_unavailable_state_stays_visible_without_fake_zero(self):
        text=Environment().from_string(self.table).render(states=lambda _: 'unavailable')
        self.assertEqual(5,text.count('unavailable'))
        self.assertNotIn('0 W',text)
    def test_bms_view_has_separate_soc_current_axes_and_no_controls(self):
        view=next(v for v in self.data['data']['config']['views'] if v.get('path')=='bms')
        header=view['cards'][0]
        for key in ('battery','current','temperature','cycles'):
            self.assertTrue(any(r['entity'].endswith('_'+key) for r in header['entities']))
        chart=view['cards'][1]
        self.assertEqual(['soc','current'],[a['id'] for a in chart['yaxis']])
        text=json.dumps(view)
        for forbidden in ('switch.','button.','number.','lowest_cell','highest_cell','call-service'):
            self.assertNotIn(forbidden,text)
        self.assertIn('_balancer',text);self.assertIn('_problem',text)
