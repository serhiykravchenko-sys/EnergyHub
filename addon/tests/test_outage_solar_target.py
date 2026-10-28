import unittest
from datetime import timedelta
import test_outage_preparation as fixtures

NOW=fixtures.NOW


class SolarTargetTests(unittest.TestCase):
    setUp=fixtures.OutageTests.setUp
    evaluate=fixtures.OutageTests.evaluate

    def forecast(self,powers):
        self.document.update(forecast_at=NOW.isoformat(),forecast=[dict(
            start=(NOW+timedelta(hours=2+i)).isoformat(),
            end=(NOW+timedelta(hours=3+i)).isoformat(),pv_kw=p) for i,p in enumerate(powers)])
        self.plan.update(self.document)

    def test_net_solar_reduces_target_to_eighty(self):
        self.forecast([2]*4)
        result=self.evaluate()
        self.assertEqual(80,result['target_soc'])
        self.assertAlmostEqual(6.4,result['outage_required_battery_kwh'])
        self.assertAlmostEqual(6.4,result['outage_credited_solar_kwh'])
        self.assertTrue(result['outage_forecast_complete'])

    def test_late_sun_cannot_erase_earlier_deficit(self):
        self.forecast([0,0,8,8])
        result=self.evaluate()
        self.assertEqual(80,result['target_soc'])
        self.assertAlmostEqual(6.4,result['outage_required_battery_kwh'])

    def test_strong_sun_keeps_minimum_and_weather_allowance(self):
        self.forecast([8]*4)
        self.assertEqual(40,self.evaluate()['target_soc'])
        self.assertEqual(60,self.evaluate(weather_modifier=20,base_reserve=60)['target_soc'])
        self.assertEqual(70,self.evaluate(base_reserve=70)['target_soc'])

    def test_early_surplus_is_not_banked_optimistically(self):
        self.forecast([8,8,0,0])
        self.assertEqual(80,self.evaluate()['target_soc'])

    def test_missing_stale_gap_and_overlap_use_conservative_target(self):
        for damage in ('missing','stale','gap','overlap','unknown'):
            with self.subTest(damage=damage):
                self.forecast([2]*4)
                if damage=='missing':self.document.pop('forecast')
                elif damage=='stale':self.document['forecast_at']=(NOW-timedelta(hours=25)).isoformat()
                elif damage=='gap':self.document['forecast'].pop(1)
                elif damage=='overlap':self.document['forecast'].append(dict(self.document['forecast'][0]))
                else:self.document['forecast'][0]['pv_kw']='unknown'
                self.plan.update(self.document)
                result=self.evaluate()
                self.assertEqual(95,result['target_soc'])
                self.assertFalse(result['outage_forecast_complete'])

    def test_observed_high_load_and_telemetry_guard(self):
        self.forecast([2]*4)
        self.assertEqual(80,self.evaluate(load_w=5000)['target_soc'])  # Explicit configured demand, not instantaneous spikes
        result=self.evaluate(telemetry_valid=False)
        self.assertFalse(result['control_active'])
        self.assertFalse(result['outage_forecast_complete'])

    def test_fractional_outage_and_non_smart_rate(self):
        self.document['groups']['1.1'][0]['end']=(NOW+timedelta(hours=5,minutes=30)).isoformat()
        self.forecast([12/7]*4)  # 6 kWh gross during 3.5 hours.
        self.assertEqual(80,self.evaluate()['target_soc'])
        self.document.update(heating_policy='Off',heating_checked_at=NOW.isoformat())
        self.forecast([0]*4)
        self.assertEqual(95,self.evaluate()['target_soc'])  # Total configured demand includes heating policy

    def test_observed_underperformance_scales_outage_forecast_down(self):
        self.forecast([8]*4)
        self.document['forecast'].insert(0,dict(start=NOW.isoformat(),end=(NOW+timedelta(hours=1)).isoformat(),pv_kw=8))
        self.plan.update(self.document)
        result=self.evaluate(solar_w=500,charge_a=0)
        self.assertEqual(95,result['target_soc'])

    def test_grid_charges_only_remaining_lower_target_deficit(self):
        self.forecast([2]*4)
        result=self.evaluate(soc=70)
        self.assertAlmostEqual(1.6,result['required_grid_kwh'])
        self.assertEqual('waiting',result['phase'])
        self.assertFalse(result['control_active'])

    def test_restart_at_new_target_and_manual_authority_guard(self):
        self.forecast([2]*4)
        result=self.evaluate(soc=80,mode='panic_grid_hold',current_target=80)
        self.assertEqual('waiting',result['phase'])
        self.assertTrue(result['battery_ready'])
        self.assertFalse(result['control_active'])
        self.assertFalse(self.evaluate(automatic=False)['control_active'])
