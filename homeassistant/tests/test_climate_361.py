"""Regression scenarios from October 8 delayed profile/temperature feedback."""
import unittest
import json
from datetime import datetime,timezone
import test_climate_3


class Climate361Tests(unittest.TestCase):
    setUp = test_climate_3.ClimateTests.setUp
    night_decision = test_climate_3.ClimateTests.night_decision

    def test_capture_21_before_profile_changes_then_apply_minus_three(self):
        first=self.night_decision(current=21,profile_ready=False)
        self.assertEqual(21,first['memory']['base'])
        self.assertNotIn('target',first)
        ready=self.night_decision(memory=first['memory'],current=20,profile_ready=True)
        self.assertEqual(18,ready['target'])
        self.assertEqual(21,ready['memory']['base'])

    def test_unconfirmed_target_retains_baseline_for_morning(self):
        failed=self.night_decision(memory={'base':21,'expected':18,'pending_until':1100},current=20,tick=1200)
        self.assertTrue(failed['memory']['failed'])
        self.assertNotIn('target',failed)
        self.assertNotIn('target',self.night_decision(memory=failed['memory'],current=20,tick=1300))
        restored=self.night_decision(memory=failed['memory'],current=20,window=False,tick=1400)
        self.assertEqual(21,restored['target'])

    def test_explicit_family_override_still_blocks_restoration(self):
        result=self.night_decision(memory={'blocked':True},current=20,window=False)
        self.assertNotIn('target',result)

    def test_17_degree_minimum_clamps_offset(self):
        self.assertEqual(17,self.night_decision(current=19,reduction=3,minimum=17)['target'])

    def test_morning_waits_for_profile_exit_then_restores_despite_mode_feedback_drift(self):
        memory={'base':21,'expected':18}
        waiting=self.night_decision(memory=memory,current=20,window=False,profile_ready=False)
        self.assertNotIn('target',waiting)
        ready=self.night_decision(memory=waiting['memory'],current=20,window=False,profile_ready=True)
        self.assertEqual(21,ready['target'])

    def test_mode_enable_requires_conflicting_mode_off(self):
        text=self.data['script']['energyhub_apply_hp_profile']['sequence'][2]['value_template']
        def permits(other):
            return self.env.from_string(text).render(profile='eco',desired='on',previous={},
                overrides={},tick=1000,entity='switch.eco',eco_episode='off:100',eco_budget={},states=lambda e:'off',
                is_state=lambda e,v:other==v)
        self.assertFalse(permits('on'))
        self.assertTrue(permits('off'))

    def test_profile_readiness_rejects_old_night_mode_after_window_end(self):
        row=next(r for r in self.data['automation'] if r['id']=='energyhub_3_night_temperature')
        template=self.env.from_string(row['actions'][0]['variables']['profile_ready'])
        def ready(quiet,in_window):
            values={'input_text.energyhub_hp1_profile_requests':'{}',
                    'input_text.energyhub_hp1_profile_expected':json.dumps({'quiet':quiet,'eco':'off'}),
                    'sensor.powmr_10_2m_grid_voltage':'230',
                    'sensor.energyhub_telemetry_freshness':'fresh',
                    'switch.first_floor_heat_pump_quiet':quiet,
                    'switch.first_floor_heat_pump_eco':'off'}
            value=template.render(states=lambda e:values.get(e,'unknown'),
                is_state=lambda e,v:values.get(e)==v,in_window=in_window,
                now=lambda:datetime.fromtimestamp(1000,timezone.utc))
            return value.strip()=='True' if isinstance(value,str) else value
        self.assertTrue(ready('on',True))
        self.assertFalse(ready('on',False))
        self.assertTrue(ready('off',False))
