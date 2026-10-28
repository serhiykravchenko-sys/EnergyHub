import unittest
from datetime import timedelta
import test_outage_preparation as fixture
from app.services.grid_import import GridImportService


class PlanningTests(unittest.TestCase):
    setUp = fixture.OutageTests.setUp
    evaluate = fixture.OutageTests.evaluate

    def window(self, hours=1, **settings):
        self.document.update(capacity_kwh=16, house_demand_kw=3.2, forecast_max_age_hours=24)
        self.document.update(settings)
        self.document['groups']['1.1'][0]['end'] = (fixture.NOW+timedelta(hours=2+hours)).isoformat()
        self.plan.update(self.document)

    def test_fixed_hour_and_four_hour_shortfall(self):
        self.window()
        self.assertEqual(60, self.evaluate()['target_soc'])
        self.window(4)
        result = self.evaluate()
        self.assertEqual(120, result['uncapped_target_soc'])
        self.assertEqual(95, result['target_soc'])
        self.assertTrue(result['coverage_capacity_insufficient'])

    def test_capacity_and_demand_are_shared_and_live_spikes_do_not_replace_them(self):
        for capacity, target in [(5, 95), (16, 60), (32, 50)]:
            self.window(capacity_kwh=capacity)
            self.assertEqual(target, self.evaluate(load_w=9000)['target_soc'])
        self.window(house_demand_kw=1.6)
        self.assertEqual(50, self.evaluate()['target_soc'])

    def test_missing_capacity_does_not_assume_sixteen(self):
        self.window(capacity_kwh=None)
        self.assertIsNone(self.evaluate()['request'])
        self.assertIsNone(self.evaluate()['target_soc'])

    def test_forecast_twenty_four_hour_boundary_and_complete_periods(self):
        self.window()
        self.document['forecast'] = [dict(start=(fixture.NOW+timedelta(hours=i)).isoformat(),
            end=(fixture.NOW+timedelta(hours=i+1)).isoformat(), pv_kw=1.25) for i in range(4)]
        self.document['forecast_at'] = (fixture.NOW-timedelta(hours=24)).isoformat()
        self.plan.update(self.document)
        # 20% solar reduction: 1kWh usable, demand3.2, BR40 =>53.75 rounded54.
        result = self.evaluate(solar_w=1250)
        self.assertEqual(54, result['target_soc'])
        self.document['forecast_at'] = (fixture.NOW-timedelta(hours=24,seconds=1)).isoformat()
        self.plan.update(self.document)
        self.assertEqual(60, self.evaluate()['target_soc'])

    def test_thirty_amps_advances_start(self):
        self.window(4, grid_charge_current_a=60)
        fast = self.evaluate(soc=40)['planned_grid_start']
        self.document['grid_charge_current_a'] = 30
        self.plan.update(self.document)
        slow = self.evaluate(soc=40)['planned_grid_start']
        self.assertLessEqual(slow, fast)
