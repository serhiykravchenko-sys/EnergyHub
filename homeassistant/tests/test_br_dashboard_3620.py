import json
import unittest
from jinja2 import Environment
from test_presentation import ROOT, contents


class ReserveDashboardTests(unittest.TestCase):
    def setUp(self):
        path=ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1'
        self.dashboard=json.loads(path.read_text(encoding='utf-8'))
        env=Environment()
        env.filters['timestamp_custom']=lambda value,fmt:str(value)
        self.template=env.from_string(next(x for x in contents(self.dashboard)
            if '**Base reserve calculation:**' in x))
        self.reserve=dict(policy_base_soc=20,schedule_modifier_percent=20,
            grid_modifier_percent=0,generation_modifier_percent=0,
            weather_modifier_percent=20,schedule_suspension_modifier_percent=20,
            reserve_planning_source='dtek_schedule',control_applied=True,
            recommendation_status='ready',recommended_soc=80)
        self.preparation={}
        self.values={'input_number.ahm_minimum_soc':'80'}

    def render(self,auto=True):
        return self.template.render(states=lambda entity:self.values.get(entity,'unknown'),
            is_state=lambda entity,value:(auto and value=='on') if entity=='binary_sensor.energyhub_battery_reserve_auto'
                else self.values.get(entity)==value,
            state_attr=lambda entity,key:(self.reserve if entity=='sensor.energyhub_ahm_weather_buffer'
                                          else self.preparation).get(key))

    def test_schedule_emergency_breakdown_keeps_schedule_and_excludes_fallback(self):
        self.preparation['source_status']='suspended'
        result=self.render()
        self.assertIn('Minimum +20 scheduled + weather + emergency',result)
        self.assertIn('| Schedule | +20 p.p. |',result)
        self.assertIn('| Grid Confidence | +0 p.p. |',result)
        self.assertIn('| Emergency / unscheduled outages | +20 p.p. |',result)
        self.assertIn('after 95% cap: 80%',result)
        self.assertNotIn('Emergency reserve — schedule unavailable',result)

    def test_fallback_breakdown_and_cap(self):
        self.reserve.update(reserve_planning_source='grid_confidence',
            schedule_modifier_percent=0,grid_modifier_percent=60,generation_modifier_percent=20)
        result=self.render()
        self.assertIn('Minimum + Grid Confidence + weather + emergency',result)
        self.assertIn('= 120%',result)
        self.assertIn('after 95% cap: 95%',result)

    def test_missing_component_is_not_zero_and_unapplied_result_is_distinct(self):
        self.reserve.pop('schedule_modifier_percent')
        result=self.render()
        self.assertIn('| Schedule | Unconfirmed |',result)
        self.assertIn('missing allowances are not zero',result)
        self.assertNotIn('after 95% cap:',result)
        self.reserve.update(schedule_modifier_percent=20,control_applied=False)
        self.values['input_number.ahm_minimum_soc']='60'
        result=self.render()
        self.assertIn('**Current reserve:** 60%',result)
        self.assertIn('after 95% cap: 80%',result)
        self.assertIn('not confirmed applied by HA',result)

    def test_manual_setting_is_not_replaced_by_calculated_recommendation(self):
        self.values['input_number.ahm_minimum_soc']='50'
        result=self.render(auto=False)
        self.assertIn('**Selected reserve:** 50%',result)
        self.assertIn('**EH recommendation:** 80%',result)
        self.assertIn('selected reserve remains in control',result)

    def test_rolling_hour_and_restart_fallback_are_explained(self):
        result=self.render()
        self.assertIn('Full valid hour unavailable; using configured planning',result)
        self.assertNotIn('includes 20% allowance',result)
        self.preparation.update(observed_net_discharge_kw=1.58,
            discharge_check_advanced_start=True,predicted_waiting_discharge_kwh=2.1)
        self.values.update({'sensor.energyhub_outage_preparation':'waiting',
            'sensor.energyhub_telemetry_freshness':'fresh'})
        result=self.render()
        self.assertIn('1.58 kW (net discharge)',result)
        self.assertIn('advanced the planned grid start',result)
        self.assertIn('2.1 kWh',result)
        self.assertIn('reserve recovery starts immediately',result)
        self.values['sensor.energyhub_telemetry_freshness']='stale'
        self.assertNotIn('1.58 kW',self.render())
