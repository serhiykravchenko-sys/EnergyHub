import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from jinja2.nativetypes import NativeEnvironment
import yaml

ROOT=Path(__file__).resolve().parents[2]


class EcoBeaconTests(unittest.TestCase):
    def setUp(self):
        package=yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))
        self.script=package['script']['energyhub_apply_hp_profile']['sequence']
        self.budget={}
        self.now=datetime(2026,10,17,15,10,tzinfo=timezone.utc)
        self.tick=self.now.timestamp()
        self.values={'climate.first_floor_heat_pump':'heat','switch.first_floor_heat_pump_eco':'off',
            'switch.first_floor_heat_pump_quiet':'off','sensor.energyhub_telemetry_freshness':'fresh',
            'binary_sensor.energyhub_grid_confirmed':'off'}
        self.attrs=dict(transition_at=1000,checked_at=self.tick,confirmation_seconds=180,
                        transition_pending=False,episode_persisted=True)
        self.env=NativeEnvironment()
        self.env.filters['to_json']=json.dumps
        self.automations=yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))

    def render(self,text,**ctx):
        return self.env.from_string(text).render(states=lambda e:self.values.get(e,'unknown'),
            is_state=lambda e,v:self.values.get(e)==v,state_attr=lambda e,k:self.attrs.get(k),now=lambda:self.now,**ctx)

    def episode(self,desired='on'):
        return self.render(self.script[1]['variables']['eco_episode'],desired=desired)

    def permits(self,**ctx):
        args=dict(profile='eco',desired='on',entity='switch.first_floor_heat_pump_eco',
            tick=self.tick,eco_episode=self.episode(),eco_budget=self.budget,overrides={},
            previous=dict(t='on',n=3,at=self.tick-86400),window='night',quiet_budget={})
        args.update(ctx)
        return self.render(self.script[2]['value_template'],**args)

    def test_new_episode_ignores_exhausted_legacy_request_but_same_budget_is_bounded(self):
        self.assertTrue(self.permits())
        self.budget=dict(e='off:1000',t='on',n=3,at=self.tick-600)
        self.assertFalse(self.permits())
        self.budget=json.loads(json.dumps(self.budget))
        self.assertFalse(self.permits())
        self.attrs['transition_at']=2000
        self.assertTrue(self.permits())

    def test_cooldown_manual_override_and_profile_conflict(self):
        self.budget=dict(e='off:1000',t='on',n=1,at=self.tick-179)
        self.assertFalse(self.permits())
        self.budget['at']-=1
        self.assertTrue(self.permits())
        self.assertFalse(self.permits(overrides=dict(eco_until=self.tick+60)))
        self.values['switch.first_floor_heat_pump_quiet']='on'
        self.assertFalse(self.permits())

    def test_pending_stale_unknown_or_non_durable_grid_does_not_create_budget(self):
        for key,value in [('transition_pending',True),('checked_at',self.tick-31),
                          ('confirmation_seconds',60),('episode_persisted',False),('transition_at',None)]:
            original=dict(self.attrs);self.attrs[key]=value
            self.assertEqual('',str(self.episode()).strip())
            self.assertFalse(self.permits())
            self.attrs=original
        self.values['binary_sensor.energyhub_grid_confirmed']='unknown'
        self.assertFalse(self.permits())

    def test_confirmed_return_allows_off_with_independent_new_episode(self):
        self.values.update({'binary_sensor.energyhub_grid_confirmed':'on','switch.first_floor_heat_pump_eco':'on'})
        self.budget=dict(e='off:1000',t='on',n=3,at=self.tick-60)
        self.assertTrue(self.permits(desired='off',eco_episode=self.episode('off')))
        self.assertEqual('',str(self.episode('on')).strip())

    def test_new_budget_persists_before_command_and_is_small(self):
        step=next(row for row in self.script if row.get('if')=="{{ profile == 'eco' }}")
        template=step['then'][0]['data']['value']
        result=self.render(template,eco_episode='off:2000',eco_budget=dict(e='off:1000',t='on',n=3),
                           tick=self.tick,desired='on')
        data=json.loads(result) if isinstance(result,str) else result
        self.assertEqual(1,data['n'])
        self.assertEqual('off:2000',data['e'])
        self.assertLessEqual(len(json.dumps(data)),160)
        self.assertLess(self.script.index(step),len(self.script)-1)

    def test_heating_status_uses_actual_feedback_after_profile_request(self):
        policy=next(a for a in self.automations if a.get('id')=='energyhub_smart_heating_first_floor')
        # Find the default branch directly; no fabricated actuator feedback.
        branch=next(a['default'] for a in policy['actions'] if 'default' in a)
        template=branch[-1]['data']['option']
        self.assertEqual('Waiting',self.render(template,eco_needed=True,quiet_hours=False).strip())
        self.values['switch.first_floor_heat_pump_eco']='on'
        self.assertEqual('Eco',self.render(template,eco_needed=True,quiet_hours=False).strip())
        self.values['switch.first_floor_heat_pump_quiet']='on'
        self.assertEqual('Waiting',self.render(template,eco_needed=True,quiet_hours=False).strip())
        self.assertTrue(any(step.get('wait_template') and 'heat_pump_eco' in step['wait_template'] for step in branch))

    def test_unknown_soc_uses_unavailable_branch_in_all_modes(self):
        beacon=next(a for a in self.automations if a.get('alias')=='EnergyHub Beacon')
        variables=beacon['actions'][0]['variables']
        for soc in [-1,101,float('nan')]:
            self.assertFalse(self.render(variables['telemetry_ok'],soc=soc,
                freshness_state='fresh',output_power_age_seconds=0))
        self.assertTrue(self.render(variables['telemetry_ok'],soc=94,
            freshness_state='fresh',output_power_age_seconds=0))
        self.assertEqual([0,80,255],json.loads(str(self.render(variables['lamp_color'],soc=95))))
        self.assertEqual([0,255,0],json.loads(str(self.render(variables['lamp_color'],soc=94))))

    def test_dashboard_profile_uses_feedback_and_waiting(self):
        from test_presentation import contents
        document=json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        template=next(c for c in contents(document) if 'Battery Reserve Auto:' in c)
        self.values['input_select.energyhub_smart_heating_status']='Waiting'
        self.assertIn('Очікуємо підтвердження режиму ТН',str(self.render(template)))
        self.values['input_select.energyhub_smart_heating_status']='Eco'
        self.assertNotIn('Eco підтверджено в HA',str(self.render(template)))
        self.values['switch.first_floor_heat_pump_eco']='on'
        self.assertIn('Eco підтверджено в HA',str(self.render(template)))
