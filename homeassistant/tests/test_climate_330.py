"""Exercise the deployed 3.3 templates for persistent holds and night policy."""
import json
import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path
import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT=Path(__file__).resolve().parents[2]

class Climate330Tests(unittest.TestCase):
    def setUp(self):
        self.package=yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))
        rows=yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        self.controller=next(r for r in rows if r['id']=='energyhub_smart_heating_first_floor')
        self.env=NativeEnvironment()
        self.env.filters['from_json']=lambda text,default={}:json.loads(text) if text.startswith('{') else default

    def render(self, text, values=None, **ctx):
        values=values or {}
        result = self.env.from_string(text).render(states=lambda e:values.get(e,'unknown'),
            is_state=lambda e,v:values.get(e)==v,now=lambda:datetime.fromtimestamp(1000,timezone.utc),**ctx)
        if isinstance(result,str):
            try:
                return ast.literal_eval(result.strip())
            except (ValueError,SyntaxError):
                pass
        return result

    def test_manual_hold_precedes_night_and_battery_resume(self):
        branch=self.controller['actions'][2]['choose'][0]
        self.assertTrue(self.render(branch['conditions'],{'input_boolean.energyhub_hp1_manual_hold':'on'}))
        self.assertNotIn('climate.set_hvac_mode',str(branch))
        self.assertIn('input_boolean.turn_off',str(branch))

    def test_night_off_and_current_window_manual_on_override(self):
        template=self.controller['actions'][1]['variables']['night_stop']
        values={'input_select.energyhub_climate_effective_policy':'Smart',
                'input_select.energyhub_climate_night_operation':'Off'}
        self.assertTrue(self.render(template,values,night_window=True,night_overrides={}))
        self.assertFalse(self.render(template,values,night_window=True,night_overrides={'on_until':1100}))
        self.assertTrue(self.render(template,values,night_window=True,night_overrides={'on_until':999}))
        self.assertFalse(self.render(template,values,night_window=False,night_overrides={}))

    def test_solar_sufficiency_uses_dashboard_threshold_even_with_discharge(self):
        sensors=next(r['binary_sensor'] for r in self.package['template'] if 'binary_sensor' in r)
        sensor=next(r for r in sensors if r['unique_id']=='energyhub_hp_solar_sufficient')
        values={'sensor.energyhub_telemetry_freshness':'fresh',
                'sensor.powmr_10_2m_battery_discharge_current':'0',
                'sensor.powmr_10_2m_total_pv_power':'600',
                'input_number.energyhub_solar_start_power':'600'}
        self.assertTrue(self.render(sensor['state'],values))
        for discharge in ('1', '25', 'unavailable'):
            self.assertTrue(self.render(sensor['state'],dict(values,**{'sensor.powmr_10_2m_battery_discharge_current':discharge})))
        for entity,value in [('sensor.powmr_10_2m_total_pv_power','599'),
                             ('sensor.energyhub_telemetry_freshness','stale'),
                             ('input_number.energyhub_solar_start_power','unavailable')]:
            self.assertFalse(self.render(sensor['state'],dict(values,**{entity:value})))
        self.assertEqual('00:02:00',sensor['delay_on'])
        self.assertEqual('00:02:00',sensor['delay_off'])

    def test_eco_demand_tracks_grid_and_stable_solar_exception(self):
        template=self.controller['actions'][1]['variables']['eco_needed']
        solar={'binary_sensor.energyhub_hp_solar_sufficient':'on'}
        self.assertTrue(self.render(template,solar,fresh=True,confirmed_grid='off'))
        self.assertTrue(self.render(template,{},fresh=True,confirmed_grid='off'))
        self.assertFalse(self.render(template,{},fresh=True,confirmed_grid='on'))
        self.assertFalse(self.render(template,{},fresh=False,confirmed_grid='off'))
        self.assertFalse(self.render(template,{},fresh=True,confirmed_grid='unavailable'))

    def test_profile_override_expiry_and_acknowledged_state(self):
        template=self.package['script']['energyhub_apply_hp_profile']['sequence'][2]['value_template']
        ctx=dict(entity='switch.hp',desired='on',profile='quiet',previous={},quiet_budget={},window='night',tick=1000)
        self.assertFalse(self.render(template,{'switch.hp':'off'},overrides={'quiet_until':1100},**ctx))
        self.assertTrue(self.render(template,{'switch.hp':'off','switch.first_floor_heat_pump_eco':'off'},overrides={'quiet_until':999},**ctx))
        self.assertFalse(self.render(template,{'switch.hp':'on'},overrides={},**ctx))

    def test_grid_return_clears_only_requested_eco_and_not_quiet(self):
        template=self.package['script']['energyhub_apply_hp_profile']['sequence'][2]['value_template']
        ctx=dict(entity='switch.hp',desired='off',profile='eco',tick=1000,overrides={},
                 eco_episode='on:100',eco_budget={})
        self.assertTrue(self.render(template,{'switch.hp':'on'},previous={},**ctx))
        self.assertTrue(self.render(template,{'switch.hp':'on'},previous={'t':'on','at':800,'n':1},**ctx))
        self.assertTrue(self.render(template,{'switch.hp':'on'},previous={'t':'off','at':800,'n':1},**ctx))
        self.assertTrue(self.render(template,{'switch.hp':'on'},previous={'t':'off','at':800,'n':1,'owned':True},**ctx))
        exhausted=dict(ctx,eco_budget={'e':'on:100','t':'off','at':800,'n':3})
        self.assertFalse(self.render(template,{'switch.hp':'on'},previous={'t':'off','at':800,'n':3,'owned':True},**exhausted))
        self.assertTrue(self.render(template,{'switch.hp':'on'},previous={'t':'on','at':800,'n':1,'owned':False},**ctx))

    def test_eco_off_feedback_clears_owned_metadata_only(self):
        row=next(r for r in self.package['automation'] if r['id']=='energyhub_360_eco_ownership_feedback')
        text=str(row)
        self.assertIn('owned=false',text)
        self.assertNotIn('switch.turn_',text)
        self.assertNotIn('climate.',text)

    def test_signed_cooling_and_fahrenheit_adjustment(self):
        row=next(r for r in self.package['automation'] if r['id']=='energyhub_3_night_temperature')
        decision=row['actions'][1]['variables']['decision']
        def calculate(current,offset,minimum,maximum,step):
            return self.render(decision,{'climate.hp':'cool'},memory={},current=current,unit='°C',
                offset=offset,minimum=minimum,maximum=maximum,step=step,eligible=True,
                in_window=True,profile_ready=True,hp='climate.hp',state_attr=lambda e,a:1)
        self.assertEqual(26,calculate(23,3,16,30,1)['target'])
        self.assertEqual(79,calculate(74,5.4,60,90,1)['target'])
        self.assertEqual(30,calculate(28,5,16,30,1)['target'])

    def test_holds_are_restored_and_migration_is_once(self):
        for key in ('energyhub_hp1_manual_hold','energyhub_hp1_night_paused','energyhub_330_initialized'):
            self.assertNotIn('initial',self.package['input_boolean'][key])
        self.assertNotIn('initial',self.package['input_select']['energyhub_climate_night_operation'])
        migration=next(r for r in self.package['automation'] if r['id']=='energyhub_initialize_installation')
        self.assertEqual('off',migration['actions'][1]['if'][0]['state'])
        self.assertEqual('On',migration['actions'][1]['then'][2]['data']['option'])
        manual=next(r for r in self.package['automation'] if r['id']=='energyhub_3_family_off_overrides_schedule')
        branches=manual['actions'][0]['choose']
        self.assertNotIn('input_select.select_option',str(branches[0]))
        self.assertIn("'Off'",str(branches[1]))
