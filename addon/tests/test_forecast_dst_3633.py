"""Tomorrow's repeated local hour must not invalidate today's forecast budget."""
import unittest
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import test_outage_preparation as fixture
from app.services.solar_bridge import assess


class ForecastDSTTests(unittest.TestCase):
    def setUp(self):
        f=fixture.OutageTests();f.setUp();self.plan=f.plan
        self.now=datetime(2026,10,24,11,45,tzinfo=ZoneInfo('Europe/Kyiv'))
        self.plan.soc_for_forecast=73
        start=self.now.replace(hour=0,minute=0).astimezone(timezone.utc)
        end=(self.now+timedelta(days=2)).replace(hour=0,minute=0).astimezone(timezone.utc)
        rows=[]
        while start<end:
            rows.append(dict(start=start.astimezone(self.now.tzinfo).isoformat(),
                end=(start+timedelta(hours=1)).astimezone(self.now.tzinfo).isoformat(),pv_kw=2))
            start+=timedelta(hours=1)
        self.document=dict(forecast=rows,forecast_at=self.now.isoformat(),checked_at=self.now.isoformat(),forecast_max_age_hours=24)

    def test_today_budget_accepts_future_repeated_hour(self):
        rows=self.document['forecast']
        lexical=sorted(rows,key=lambda r:r['start'])
        self.assertNotEqual([r['start'] for r in rows],[r['start'] for r in lexical])
        result=self.plan._forecast_budget(self.document,self.now,self.now.replace(hour=14,minute=30),52,1.2,1601,0)
        self.assertIsNotNone(result)
        self.assertEqual('complete',self.plan.preparation_solar_reason)
        self.assertGreater(self.plan.preparation_gross_solar_kwh,0)

    def test_outage_coverage_accepts_future_repeated_hour(self):
        result=self.plan._outage_deficit(self.document,self.now,self.now.replace(hour=15,minute=0),
            self.now.replace(hour=19,minute=0),52,3.2,1601,0)
        self.assertIsNotNone(result)

    def test_bridge_does_not_reject_valid_future_dst_periods(self):
        result=assess(self.document,now=self.now,soc=73,reserve=40,load_w=300,solar_w=1601,
            capacity=16,heating_rate=20,telemetry_valid=True,grid_confirmed=True,authority_fresh=True,demand_kw=0.6)
        self.assertTrue(result['safe'])
