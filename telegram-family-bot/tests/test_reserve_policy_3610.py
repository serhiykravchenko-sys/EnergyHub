import unittest
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo
from app import reserve_policy_text as policy
from app import outage_schedule
from unittest.mock import patch

NOW=datetime(2026,10,9,14,tzinfo=ZoneInfo('Europe/Kyiv'))

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_dacha_district='Obukhiv')
        self.rows={'sensor.energyhub_telemetry_freshness':{'state':'fresh'},'sensor.energyhub_operating_mode':{'state':'solar'},'input_number.ahm_minimum_soc':{'state':'40'}}
        self.client=SimpleNamespace(state=lambda entity:self.rows.get(entity))

    def test_schedule_hides_protective_base_reserve(self):
        with patch.object(outage_schedule,'recovery_plan',return_value='\n📅 EH керує зарядом за графіком відключень.\n🔋 Потрібний заряд до 18:00: <b>95%</b>.'):
            text=policy.context(self.cfg,self.client,{},NOW)
        self.assertIn('95%',text)
        self.assertNotIn('Мінімальний резерв',text)

    def test_grid_confidence_and_unknown_reserve_are_explicit(self):
        text=policy.context(self.cfg,self.client,{},NOW)
        self.assertIn('48 годин',text)
        self.assertIn('<b>40%</b>',text)
        self.rows['input_number.ahm_minimum_soc']['state']='unavailable'
        self.assertIn('ще не підтверджено',policy.context(self.cfg,self.client,{},NOW))

    def test_panic_is_distinct_from_automatic_preparation(self):
        self.rows['sensor.energyhub_operating_mode']['state']='panic'
        self.rows['sensor.energyhub_panic_target_source']={'state':'Manual Panic: dashboard'}
        self.assertIn('павербанк',policy.context(self.cfg,self.client,{},NOW))
        self.rows['sensor.energyhub_panic_target_source']['state']='Scheduled outage'
        self.assertNotIn('павербанк',policy.context(self.cfg,self.client,{},NOW))

    def test_fault_notice_overrides_schedule_without_forcing_95(self):
        with patch('app.source_policy.suspended',return_value=True):
            text=policy.context(self.cfg,self.client,{'regional_notices':{'дача':{'kind':'fault'}}},NOW)
        self.assertIn('аварійні',text)
        self.assertIn('48 годин',text)
        self.assertIn('40%',text)
        self.assertNotIn('95%',text)

    def test_suspension_allowance_is_explicit_without_claiming_target_applied(self):
        self.rows['sensor.energyhub_ahm_weather_buffer']={'attributes':{
            'schedule_suspension_modifier_percent':20,'recommended_soc':60}}
        with patch('app.source_policy.suspended',return_value=True):
            text=policy.context(self.cfg,self.client,{},NOW)
        self.assertIn('+20 п.п.',text)
        self.assertIn('95%',text)
        self.assertIn('Мінімальний резерв: <b>40%</b>',text)
        self.assertNotIn('Мінімальний резерв: <b>60%</b>',text)

    def test_schedule_metadata_with_missing_bot_plan_does_not_claim_grid_confidence(self):
        self.rows['sensor.energyhub_ahm_weather_buffer']={'attributes':{'reserve_planning_source':'dtek_schedule'}}
        self.assertIn('ще уточнюються',policy.context(self.cfg,self.client,{},NOW))
        self.assertNotIn('48 годин',policy.context(self.cfg,self.client,{},NOW))

    def test_disconnected_grid_is_never_reported_as_supply_from_strategy_alone(self):
        self.rows['sensor.energyhub_operating_mode']['state']='panic_grid_hold'
        self.rows['sensor.powmr_10_2m_grid_voltage']={'state':'0'}
        self.assertIn('без допомоги',policy.supply_line(self.cfg,self.client,NOW))
        from grid_fixture_3623 import rows
        self.rows.update(rows(NOW))
        self.assertIn('з допомогою',policy.supply_line(self.cfg,self.client,NOW))
        self.rows['sensor.energyhub_telemetry_freshness']['state']='stale'
        self.assertEqual('',policy.supply_line(self.cfg,self.client,NOW))
