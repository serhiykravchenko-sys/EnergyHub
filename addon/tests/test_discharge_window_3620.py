import unittest
from datetime import timedelta
from app.services.battery_discharge_window import BatteryDischargeWindow, checked_start
import test_outage_preparation as fixture

NOW = fixture.NOW


class DischargeWindowTests(unittest.TestCase):
    def sample(self, window, now, **kwargs):
        window.observe(now, **dict(dict(voltage=50, discharge_a=30,
            charge_a=10, valid=True, mode='solar'), **kwargs))

    def test_requires_hour_and_uses_net_battery_flow(self):
        window=BatteryDischargeWindow()
        for seconds in range(0,3600,30):
            self.sample(window,NOW+timedelta(seconds=seconds))
        self.assertIsNone(window.average_kw(NOW+timedelta(seconds=3570)))
        self.sample(window,NOW+timedelta(hours=1))
        self.assertAlmostEqual(1,window.average_kw(NOW+timedelta(hours=1)))

    def test_rolling_window_drops_old_load_and_weights_time(self):
        window=BatteryDischargeWindow()
        for seconds in range(0,7201,30):
            self.sample(window,NOW+timedelta(seconds=seconds),
                        discharge_a=30 if seconds<3600 else 50)
        self.assertAlmostEqual(2,window.average_kw(NOW+timedelta(hours=2)))
        # Dense sampling of a short spike cannot outweigh its duration.
        window=BatteryDischargeWindow()
        for seconds in range(0,3601,30):
            self.sample(window,NOW+timedelta(seconds=seconds),discharge_a=30)
            if seconds==1800:
                for offset in range(1,11):
                    self.sample(window,NOW+timedelta(seconds=seconds+offset),discharge_a=100)
        self.assertLess(window.average_kw(NOW+timedelta(hours=1)),1.05)

    def test_gaps_bad_values_and_grid_support_reset_history(self):
        for change in [dict(valid=False),dict(mode='panic'),dict(mode='panic_grid_hold'),
                       dict(mode='transitioning'),dict(charge_a=None),
                       dict(discharge_a=float('nan')),dict(voltage=0)]:
            window=BatteryDischargeWindow()
            self.sample(window,NOW)
            self.sample(window,NOW+timedelta(seconds=30),**change)
            self.assertEqual(0,len(window.samples))
        window=BatteryDischargeWindow()
        self.sample(window,NOW)
        self.sample(window,NOW+timedelta(seconds=91))
        self.assertEqual(1,len(window.samples))
        self.assertIsNone(window.average_kw(NOW+timedelta(hours=1)))

    def test_solar_charging_is_not_misreported_as_discharge(self):
        window=BatteryDischargeWindow()
        for seconds in range(0,3601,30):
            self.sample(window,NOW+timedelta(seconds=seconds),discharge_a=0,charge_a=20)
        self.assertAlmostEqual(-1,window.average_kw(NOW+timedelta(hours=1)))
        self.assertIsNone(BatteryDischargeWindow().average_kw(NOW))

    def start(self, **kwargs):
        completion=NOW+timedelta(hours=4)
        return checked_start(**dict(dict(now=NOW,completion=completion,
            planned_start=NOW+timedelta(hours=3),gap_kwh=1,solar_kwh=0,
            rows=[(NOW,completion,0,1)],discharge_kw=1,soc=70,reserve=40,capacity=16),**kwargs))

    def test_trend_advances_deadline_and_counts_waiting_discharge(self):
        start,loss=self.start()
        self.assertAlmostEqual(1.5,(start-NOW).total_seconds()/3600,places=5)
        self.assertAlmostEqual(1.5,loss,places=5)

    def test_no_trend_or_net_gain_never_postpones_configured_start(self):
        for rate in (None,0,-1):
            start,loss=self.start(discharge_kw=rate)
            self.assertEqual(NOW+timedelta(hours=3),start)
            self.assertEqual(0,loss)

    def test_reserve_caps_waiting_loss_and_infeasible_deadline_still_starts_now(self):
        start,loss=self.start(soc=41)
        self.assertAlmostEqual(.16,loss)
        self.assertAlmostEqual(2.84,(start-NOW).total_seconds()/3600,places=5)
        start,_=self.start(gap_kwh=8)
        self.assertEqual(NOW,start)

    def test_planner_uses_window_without_replacing_outage_demand(self):
        setup=fixture.OutageTests();setup.setUp()
        plan=setup.plan
        for seconds in range(-3600,1,30):
            self.sample(plan.discharge_window,NOW+timedelta(seconds=seconds))
        result=plan.evaluate(**dict(setup.args,soc=85))
        self.assertEqual(1,result['observed_net_discharge_kw'])
        self.assertEqual(3.2,result['outage_planning_load_kw'])
        self.assertEqual('rolling battery flow',result['discharge_check_source'])
        self.assertTrue(result['discharge_check_advanced_start'])
        self.assertLessEqual(result['planned_grid_start'],result['configured_grid_start'])
        plan.discharge_window=BatteryDischargeWindow()
        self.assertIsNone(plan.evaluate(**setup.args)['observed_net_discharge_kw'])
