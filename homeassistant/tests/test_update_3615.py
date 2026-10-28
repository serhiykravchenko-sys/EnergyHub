import json
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[2]


class TemplatesTests(unittest.TestCase):
    def setUp(self):
        package=yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))
        self.script=package['script']['energyhub_apply_hp_profile']['sequence']
        self.env=NativeEnvironment()
        self.env.filters['regex_match']=lambda value, pattern: bool(re.match(pattern,str(value)))
        self.env.filters['to_json']=json.dumps
        self.env.filters['from_json']=lambda value,default={}:json.loads(value) if value.startswith('{') else default
        self.now=datetime(2026,10,12,23,tzinfo=ZoneInfo('Europe/Kyiv'))
        self.values={'input_datetime.energyhub_climate_quiet_start':'23:00:00',
                     'input_datetime.energyhub_climate_quiet_end':'07:00:00',
                     'switch.first_floor_heat_pump_quiet':'off',
                     'switch.first_floor_heat_pump_eco':'off'}

    def render(self,text,**ctx):
        def today_at(value):
            hour,minute,second=map(int,value.split(':'))
            return self.now.replace(hour=hour,minute=minute,second=second,microsecond=0)
        result = self.env.from_string(text).render(now=lambda:self.now,today_at=today_at,
            timedelta=timedelta,states=lambda entity:self.values.get(entity,'unknown'),
            is_state=lambda entity,value:self.values.get(entity)==value,**ctx)
        if isinstance(result, str) and result.strip() in {'True', 'False'}:
            return result.strip() == 'True'
        return result

    def window(self):
        return str(self.render(self.script[1]['variables']['window'])).strip()

    def eligible(self, previous, overrides=None):
        return self.render(self.script[2]['value_template'],profile='quiet',desired='on',
            entity='switch.first_floor_heat_pump_quiet',tick=self.now.timestamp(),
            previous=previous,quiet_budget={},overrides=overrides or {},window=self.window())

    def test_previous_night_exhaustion_reset_same_night_persisted_midnight(self):
        window=self.window()
        old=dict(t='on',at=self.now.timestamp()-86400,n=3,w='old')
        self.assertTrue(self.eligible(old))
        current=dict(old,w=window,at=self.now.timestamp()-600)
        self.assertFalse(self.eligible(json.loads(json.dumps(current))))
        self.now+=timedelta(hours=2)
        self.assertEqual(window,self.window())
        self.assertFalse(self.eligible(current))
        self.now+=timedelta(hours=22)
        self.assertNotEqual(window,self.window())
        self.assertTrue(self.eligible(current))

    def test_manual_override_unknown_switch_and_eco_conflict(self):
        old=dict(t='on',at=0,n=3)
        self.assertFalse(self.eligible(old,{'quiet_until':self.now.timestamp()+60}))
        self.values['switch.first_floor_heat_pump_quiet']='unavailable'
        self.assertFalse(self.eligible(old))
        self.values['switch.first_floor_heat_pump_quiet']='off'
        self.values['switch.first_floor_heat_pump_eco']='on'
        self.assertFalse(self.eligible(old))

    def test_window_configuration_change_and_verified_ack(self):
        old=dict(t='on',at=0,n=3,w=self.window())
        self.values['input_datetime.energyhub_climate_quiet_start']='22:00:00'
        self.assertTrue(self.eligible(old))
        self.values['switch.first_floor_heat_pump_quiet']='on'
        self.assertFalse(self.eligible(old))

    def test_ha_notice_is_failure_only_and_marks_historical_context(self):
        rows=yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        notification=next(row for row in rows if row['alias']=='EnergyHub - Inverter Transition Failure Alert')
        condition=notification['conditions'][0]['value_template']
        for event_type,expected in [('automatic_mode_activation',False),('automatic_mode_activation_failed',True)]:
            result=self.env.from_string(condition).render(trigger={'payload_json':{'type':event_type,'mode':'panic'}})
            self.assertEqual(expected,result)
        template=notification['actions'][1]['data']['message']
        text=self.env.from_string(template).render(event={'requested_mode':'panic','current_mode':'solar','error':'No acknowledgement'})
        self.assertIn('Reported strategy at failure: solar',text)
        self.assertIn('No acknowledgement',text)
        self.assertNotIn('House on grid',text)

    def test_exhaustion_attention_is_once_per_window_and_respects_override(self):
        package=yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))
        row=next(r for r in package['automation'] if r['id']=='energyhub_quiet_acknowledgement_attention')
        template=row['conditions'][1]['value_template']
        self.values.update({'input_text.energyhub_hp1_profile_requests':json.dumps({'quiet':{'w':self.window(),'t':'on','n':3,'at':self.now.timestamp()-200}}),
            'input_text.energyhub_hp1_quiet_budget':json.dumps({'w':self.window(),'n':3,'at':self.now.timestamp()-200}),
            'input_text.energyhub_hp1_profile_expected':'{"quiet":"on"}',
            'climate.first_floor_heat_pump':'heat'})
        self.assertTrue(self.render(template))
        self.values['input_text.energyhub_hp1_quiet_failed_window']=self.window()
        self.assertFalse(self.render(template))
        self.values['input_text.energyhub_hp1_quiet_failed_window']='old'
        self.values['input_text.energyhub_hp1_night_overrides']=json.dumps({'quiet_until':self.now.timestamp()+60})
        self.assertFalse(self.render(template))
