import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import test_outage_preparation as fixture
from app.services.outage_preparation import OutagePreparation


class CoverageTests(unittest.TestCase):
    setUp = fixture.OutageTests.setUp
    evaluate = fixture.OutageTests.evaluate

    def tick(self, minutes=0, **kwargs):
        now=fixture.NOW+timedelta(hours=2,minutes=minutes)
        self.document['checked_at']=now.isoformat()
        self.plan.update(self.document)
        return self.evaluate(now=now, mode='panic_grid_hold', current_target=95,
                             soc=kwargs.pop('soc',95), **kwargs)

    def test_capped_charge_target_never_proves_four_hour_coverage(self):
        self.evaluate()
        result=self.tick()
        self.assertEqual(95,result['target_soc'])
        self.assertEqual(125,result['coverage_required_soc'])
        self.assertFalse(result['coverage_sufficient'])
        self.assertEqual('holding',result['phase'])
        self.assertIsNone(result['request'])
        self.assertEqual('holding',self.tick(60)['phase'])
        self.assertEqual('holding',self.tick(75)['phase'])
        released=self.tick(90)
        self.assertAlmostEqual(95,released['coverage_required_soc'])
        self.assertEqual('solar',released['phase'])
        self.assertTrue(released.get('coverage_release'))

    def test_solar_resumes_ordinary_control_and_extension_rearms(self):
        self.evaluate()
        self.assertEqual('solar',self.tick(90)['phase'])
        now=fixture.NOW+timedelta(hours=3,minutes=30)
        steady=self.evaluate(now=now,soc=95,mode='solar',current_target=None)
        self.assertFalse(steady['control_active'])
        self.assertIsNone(steady['request'])
        self.document['groups']['1.1'][0]['end']=(fixture.NOW+timedelta(hours=8)).isoformat()
        self.plan.update(self.document)
        revised=self.evaluate(now=now,soc=90,mode='solar',current_target=None)
        self.assertEqual('panic',revised['request'])
        self.assertTrue(revised['control_active'])

    def test_end_revision_retains_offline_ownership_and_persists(self):
        self.evaluate()
        self.document['groups']['1.1'][0]['end']=(fixture.NOW+timedelta(hours=6,minutes=30)).isoformat()
        result=self.tick(150,grid_online=False,soc=83)
        self.assertTrue(result['control_active'])
        self.assertEqual(result['end'],self.plan.active_context['end'])
        self.assertIsNone(result['request'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'context.json'
            path.write_text(json.dumps(self.plan.active_context),encoding='utf-8')
            self.plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1'),path)
            self.assertTrue(self.tick(151,grid_online=False,soc=83)['control_active'])

    def test_end_revision_failed_save_retains_old_target_and_context(self):
        self.evaluate()
        old=dict(self.plan.active_context)
        self.document['groups']['1.1'][0]['end']=(fixture.NOW+timedelta(hours=6,minutes=30)).isoformat()
        self.document['groups']['1.1'][0]['end'] = (fixture.NOW+timedelta(hours=7)).isoformat()
        with patch.object(self.plan,'_remember',return_value=False):
            result=self.tick(150,grid_online=False,soc=83)
        self.assertTrue(result['control_active'])
        self.assertEqual('guarded',result['phase'])
        self.assertEqual(old,self.plan.active_context)
        self.assertEqual(old['target_soc'],result['target_soc'])
        self.assertIsNone(result['request'])

    def test_release_failed_save_never_requests_solar(self):
        self.evaluate()
        self.document['groups']['1.1'][0]['end'] = (fixture.NOW+timedelta(hours=7)).isoformat()
        with patch.object(self.plan,'_remember',return_value=False):
            result=self.tick(90)
        self.assertEqual('guarded',result['phase'])
        self.assertFalse(result['coverage_release'])
        self.assertIsNone(result['request'])

    def test_higher_br_and_weather_do_not_get_lost_or_double_counted(self):
        self.evaluate()
        high=self.tick(180,base_reserve=80)
        self.assertEqual(105,high['coverage_required_soc'])
        self.assertFalse(high['coverage_sufficient'])
        weather=self.tick(180,base_reserve=60,weather_modifier=20)
        self.assertEqual(85,weather['coverage_required_soc'])

    def test_unknown_grid_stale_and_manual_never_release(self):
        self.evaluate()
        for kwargs in (dict(grid_online=None),dict(grid_online=False),
                       dict(telemetry_valid=False),dict(automatic=False,ownership_allowed=False)):
            with self.subTest(kwargs=kwargs):
                self.assertIsNone(self.tick(90,**kwargs)['request'])

    def test_cancelled_window_returns_to_fallback(self):
        self.evaluate()
        self.document['groups']['1.1']=[]
        result=self.tick(90)
        self.assertFalse(result['control_active'])
        self.assertFalse(result.get('coverage_release',False))
