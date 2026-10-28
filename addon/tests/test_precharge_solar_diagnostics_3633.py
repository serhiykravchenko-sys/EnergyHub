import unittest
from datetime import timedelta
import test_outage_preparation as fixture


class SolarDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        f=fixture.OutageTests();f.setUp();self.plan=f.plan;self.now=fixture.NOW
        self.plan.soc_for_forecast=73
        self.rows=[dict(start=(self.now+timedelta(hours=i)).isoformat(),
            end=(self.now+timedelta(hours=i+1)).isoformat(),pv_kw=2) for i in range(2)]

    def budget(self,document,pv=2000):
        return self.plan._forecast_budget(document,self.now,self.now+timedelta(hours=2),52,0.6,pv,20)

    def test_complete_hourly_forecast_keeps_existing_solar_credit(self):
        result=self.budget(dict(forecast_at=self.now.isoformat(),forecast=self.rows))
        self.assertEqual('complete',self.plan.preparation_solar_reason)
        self.assertEqual(2,len(result))
        self.assertAlmostEqual(4,self.plan.preparation_gross_solar_kwh)

    def test_rejection_reasons_do_not_invent_zero_solar(self):
        base=dict(forecast_at=self.now.isoformat(),forecast=self.rows)
        cases=[('missing_refresh_time',dict(base,forecast_at=None),2000),
            ('stale_forecast',dict(base,forecast_at=(self.now-timedelta(hours=25)).isoformat()),2000),
            ('missing_hourly_forecast',dict(base,forecast=[]),2000),
            ('coverage_gap',dict(base,forecast=self.rows[1:]),2000),
            ('incomplete_coverage',dict(base,forecast=self.rows[:1]),2000),
            ('overlapping_periods',dict(base,forecast=self.rows+[self.rows[0]]),2000),
            ('missing_current_pv',base,None)]
        for reason,data,pv in cases:
            with self.subTest(reason=reason):
                self.assertIsNone(self.budget(data,pv))
                self.assertEqual(reason,self.plan.preparation_solar_reason)
