import json
import unittest
from pathlib import Path
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[2]

def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from walk(child)
    elif isinstance(value,list):
        for child in value:yield from walk(child)

class NormalBaseDashboardTests(unittest.TestCase):
    def nodes(self):
        return list(walk(json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))))

    def render(self,base,confidence='risk'):
        template=next(n['content'] for n in self.nodes() if n.get('type')=='markdown' and '## Надійність ДТЕК' in n.get('content',''))
        values={'number.energyhub_normal_reserve':base,'sensor.energyhub_grid_confidence':confidence}
        return Environment().from_string(template).render(states=lambda e:values.get(e,'unavailable'),state_attr=lambda e,a:None,now=lambda:None,as_timestamp=lambda _:0,is_state=lambda e,v:False)

    def test_editable_control_present_and_offsets_separate_from_base(self):
        rows=[n for n in self.nodes() if n.get('entity')=='number.energyhub_normal_reserve']
        self.assertEqual(1,len(rows))
        output=self.render('30')
        for value in ('+0 p.p.','+20 p.p.','+40 p.p.','+60 p.p.'):self.assertIn(value,output)
        self.assertIn('### ➜ 🟠 Risk · +40 p.p.',output)

    def test_offsets_are_fixed_and_unknown_level_is_explicit(self):
        output=self.render('80')
        self.assertIn('Risk · +40 p.p.',output)
        for value in ('unavailable','15','22','100'):
            output=self.render(value,'unknown')
            self.assertNotIn('### ➜',output)
            self.assertNotIn('· 20%',output)
            self.assertIn('Current level unavailable',output)
