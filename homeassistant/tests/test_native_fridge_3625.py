"""Validate preservation of homeowner rules and retirement of custom dispatch."""
import json
import unittest
from pathlib import Path
import yaml
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[2]


class NativeFridgeTests(unittest.TestCase):
    def test_no_custom_component_and_one_combined_native_rule(self):
        self.assertFalse((ROOT/'homeassistant/live/config/custom_components/energyhub_fridge/__init__.py').exists())
        self.assertFalse((ROOT/'homeassistant/live/config/packages/energyhub_fridge.yaml').exists())
        rows=yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        rule=next(a for a in rows if str(a['id'])=='energyhub_fridge_battery_protection')
        self.assertEqual('EnergyHub Fridge Battery Protection (20-30%)',rule['alias'])
        for ident in ('1792600567774','1792601761980'):
            self.assertNotIn(ident,{str(a['id']) for a in rows})
        self.assertEqual(4,len(rule['triggers']))
        self.assertEqual(20,rule['triggers'][0]['below'])
        self.assertEqual(30,rule['triggers'][1]['above'])
        self.assertNotIn('value_template',rule['triggers'][0])
        def walk(value):
            if isinstance(value,dict):
                yield value
                for child in value.values():yield from walk(child)
            elif isinstance(value,list):
                for child in value:yield from walk(child)
        for branch,service in zip(rule['actions'][-1]['choose'],('switch.turn_off','switch.turn_on')):
            switch=next(x for x in walk(branch['sequence']) if x.get('action')==service)
            self.assertEqual('switch.first_floor_hp_meter',switch['target']['entity_id'])
            notify=next(x for x in walk(branch['sequence']) if x.get('action')=='notify.send_message')
            self.assertEqual('notify.energyhub_family_telegram',notify['target']['entity_id'])
        on=rule['actions'][-1]['choose'][1]
        self.assertEqual('input_boolean.energyhub_fridge_owned_off',on['conditions'][1]['entity_id'])

    def test_retained_automation_aliases_do_not_embed_release_numbers(self):
        import re
        for file in ['automations.yaml','packages/energyhub_3.yaml']:
            text=(ROOT/'homeassistant/live/config'/file).read_text(encoding='utf-8')
            self.assertNotRegex(text,r'alias: EnergyHub 3\.\d')

    def test_grid_indicator_rejects_stale_pending_and_contradictory_inputs(self):
        data=json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        def walk(n):
            if isinstance(n,dict):
                yield n
                for v in n.values():yield from walk(v)
            elif isinstance(n,list):
                for v in n:yield from walk(v)
        template=next(n['content'] for n in walk(data) if n.get('type')=='markdown' and 'Надійність ДТЕК' in n.get('content',''))
        states={'sensor.energyhub_telemetry_freshness':'fresh','sensor.powmr_10_2m_grid_voltage':'230','binary_sensor.energyhub_grid_confirmed':'on'}
        attrs={'checked_at':990,'confirmation_seconds':180,'transition_pending':False}
        def render():
            return Environment().from_string(template).render(
                states=lambda e:states.get(e,'unknown'),is_state=lambda e,s:states.get(e)==s,
                state_attr=lambda e,a:attrs.get(a),now=lambda:None,as_timestamp=lambda _:1000)
        self.assertIn('🟢 ДТЕК доступний',render())
        attrs['checked_at']=900
        self.assertIn('⚪ Стан ДТЕК не підтверджено',render())
        attrs['checked_at']=990;attrs['transition_pending']=True
        self.assertIn('⚪ Стан ДТЕК не підтверджено',render())
        attrs['transition_pending']=False;states['sensor.powmr_10_2m_grid_voltage']='0'
        self.assertIn('⚪ Стан ДТЕК не підтверджено',render())
        states['binary_sensor.energyhub_grid_confirmed']='off'
        self.assertIn('🔴 ДТЕК недоступний',render())
