import unittest
from datetime import datetime, timedelta, timezone
from app.services.solar_bridge import assess
from app.services.panic_decision import PanicDecisionEngine
from app.services.outage_preparation import OutagePreparation

NOW=datetime(2026,10,11,7,tzinfo=timezone(timedelta(hours=3)))


class SolarBridgeTests(unittest.TestCase):
    def document(self):
        return dict(forecast_max_age_hours=24,checked_at=NOW.isoformat(),forecast_at=NOW.isoformat(),forecast=[
            dict(start=(NOW+timedelta(hours=i)).isoformat(),end=(NOW+timedelta(hours=i+1)).isoformat(),pv_kw=0 if i<1 else 6)
            for i in range(-1,5)])

    def run_assessment(self,document=None,**kw):
        args=dict(now=NOW,soc=80,reserve=40,load_w=1000,solar_w=0,capacity=16,
                  heating_rate=20,telemetry_valid=True,grid_confirmed=True,authority_fresh=True)
        args.update(kw)
        return assess(document or self.document(),**args)

    def test_delay_peak_and_active_reserve(self):
        value=self.run_assessment()
        self.assertTrue(value['safe'])
        self.assertEqual(46.67,value['minimum_soc']) # Includes conservative discharge conversion loss
        self.assertFalse(self.run_assessment(soc=60)['safe'])
        self.assertFalse(self.run_assessment(reserve=60)['safe'])
        self.assertFalse(self.run_assessment(soc=75)['safe']) # exact margin is insufficient

    def test_stale_gaps_and_invalid_evidence_fail_closed(self):
        for field in ('forecast_at','checked_at'):
            doc=self.document();doc[field]=(NOW-timedelta(hours=25 if field=='forecast_at' else 2)).isoformat()
            self.assertFalse(self.run_assessment(doc)['safe'])
        doc=self.document();doc['forecast'].pop(1)
        self.assertFalse(self.run_assessment(doc)['safe'])
        doc=self.document();doc['forecast'][2]['pv_kw']='nan'
        self.assertFalse(self.run_assessment(doc)['safe'])
        for kw in (dict(authority_fresh=False),dict(grid_confirmed=None),dict(telemetry_valid=False),dict(solar_w=None)):
            self.assertFalse(self.run_assessment(**kw)['safe'])

    def test_live_solar_underperformance_blocks_release(self):
        doc=self.document();doc['forecast'][1]['pv_kw']=1
        self.assertFalse(self.run_assessment(doc,solar_w=0)['safe'])

    def test_suspended_schedule_keeps_independent_forecast(self):
        service=OutagePreparation({})
        doc=dict(self.document(),schema=1,region='kyiv_region',source='pro_kyiv',source_status='suspended',validated=False)
        self.assertFalse(service.update(doc))
        self.assertTrue(self.run_assessment(service.forecast_document)['safe'])
        self.assertFalse(service.update({}))
        self.assertEqual({},service.forecast_document)

    def test_engine_priority_and_existing_floor_protection(self):
        engine=PanicDecisionEngine()
        args=dict(autopilot_enabled=True,operating_mode='panic_grid_hold',grid_confidence='normal',
                  battery_soc=65,grid_available=True,manual_reserve_soc=60,solar_bridge=dict(safe=True,reason='verified bridge'))
        self.assertEqual('solar',engine.evaluate(**args)['request'])
        self.assertNotEqual('solar',engine.evaluate(**dict(args,manual_panic_active=True))['request'])
        self.assertEqual('panic',engine.evaluate(**dict(args,battery_soc=59))['request'])
        self.assertIsNone(engine.evaluate(**dict(args,autopilot_enabled=False))['request'])
        self.assertIsNone(engine.evaluate(**dict(args,solar_bridge=None))['request'])
