import unittest
from datetime import timedelta
from app.services.preparation_demand import PreparationDemand
import test_outage_preparation as fixtures


class PreparationDemandTests(unittest.TestCase):
    def test_night_hold_reporting_requires_observed_ack_and_survives_restart(self):
        import test_night_charge_3623 as night_fixture
        from app.services.night_charge import NightCharge
        fixture=night_fixture.NightTests();fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.evaluate(soc=91)
        self.assertFalse(fixture.plan.saved['current']['hold_confirmed'])
        fixture.evaluate(now=night_fixture.NOW+timedelta(seconds=5),soc=91,
                         mode='panic_grid_hold',current_target=90)
        self.assertTrue(fixture.plan.saved['current']['hold_confirmed'])
        fixture.plan=NightCharge(fixture.path)
        end=fixture.plan.window(night_fixture.NOW)[1]
        result=fixture.evaluate(now=end+timedelta(seconds=5),soc=91)
        self.assertTrue(result['completed']['hold_confirmed'])
        self.assertEqual(16,result['completed']['capacity_kwh'])

    def test_complete_hour_is_time_weighted_not_sample_mean(self):
        average=PreparationDemand(); now=fixtures.NOW
        result=None
        for second in range(0,3601,30):
            result=average.observe(now+timedelta(seconds=second),600 if second<1800 else 1800,True)
        self.assertAlmostEqual(1.2,result)

    def test_partial_gap_invalid_and_restart_require_fallback(self):
        average=PreparationDemand(); now=fixtures.NOW
        for second in range(0,3601,30):
            average.observe(now+timedelta(seconds=second),600,True)
        self.assertIsNotNone(average.observe(now+timedelta(seconds=3610),600,True))
        self.assertIsNone(average.observe(now+timedelta(seconds=3800),600,True))
        self.assertIsNone(average.observe(now+timedelta(seconds=3810),float('nan'),True))
        self.assertEqual(0,len(average.rows))
        self.assertIsNone(PreparationDemand().observe(now,600,True))

    def test_preparation_credits_solar_but_outage_target_stays_conservative(self):
        fixture=fixtures.OutageTests(); fixture.setUp(); plan=fixture.plan; now=fixtures.NOW
        fixture.document.update(forecast_at=now.isoformat(),forecast=[dict(
            start=(now+timedelta(hours=i)).isoformat(),end=(now+timedelta(hours=i+1)).isoformat(),pv_kw=2)
            for i in range(6)])
        plan.update(fixture.document)
        baseline=fixture.evaluate(solar_w=2000,load_w=600)
        for second in range(0,3601,30):
            plan.preparation_demand.observe(now-timedelta(hours=1)+timedelta(seconds=second),600,True)
        measured=fixture.evaluate(solar_w=2000,load_w=600)
        self.assertEqual(baseline['target_soc'],measured['target_soc'])
        self.assertEqual('rolling measured hour',measured['preparation_demand_source'])
        self.assertGreater(measured['forecast_net_solar_kwh'],baseline['forecast_net_solar_kwh'])
        self.assertLess(measured['required_grid_kwh'],baseline['required_grid_kwh'])
        self.assertAlmostEqual(4,measured['preparation_gross_solar_kwh'])
        self.assertAlmostEqual(1.2,measured['preparation_house_kwh'])
        self.assertEqual(3.2,measured['house_planning_demand_kw'])
