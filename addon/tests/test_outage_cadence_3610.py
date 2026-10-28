import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
import test_outage_preparation as fixtures
NOW=fixtures.NOW
from app.services.outage_preparation import OutagePreparation


class CadenceTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.OutageTests();fixture.setUp()
        self.plan,self.document,self.args=fixture.plan,fixture.document,fixture.args

    def evaluate(self,**kwargs):
        return self.plan.evaluate(**dict(self.args,**kwargs))

    def test_sufficient_soc_keeps_normal_operation_and_half_hour_slots(self):
        first=self.evaluate(soc=96)
        self.assertTrue(first['battery_ready'])
        self.assertFalse(first['control_active'])
        self.assertIsNone(first['request'])
        self.assertEqual((NOW+timedelta(minutes=15)).isoformat(),first['next_assessment_at'])
        self.assertFalse(self.evaluate(now=NOW+timedelta(minutes=1),soc=96)['assessment_due'])
        self.assertTrue(self.evaluate(now=NOW+timedelta(minutes=15),soc=96)['assessment_due'])

    def test_grid_return_and_revised_interval_assess_immediately(self):
        self.evaluate(grid_online=False,soc=96)
        self.assertTrue(self.evaluate(now=NOW+timedelta(minutes=1),soc=96)['assessment_due'])
        self.document['groups']['1.1'][0]['start']=(NOW+timedelta(hours=3)).isoformat()
        self.plan.update(self.document)
        self.assertTrue(self.evaluate(now=NOW+timedelta(minutes=2),soc=96)['assessment_due'])

    def test_durable_intent_survives_end_revision_with_controller_confirmation(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'intent.json'
            self.plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1'),path)
            self.plan.update(self.document)
            self.assertEqual('panic',self.evaluate()['request'])
            self.plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1'),path)
            self.plan.update(self.document)
            self.assertEqual('holding',self.evaluate(soc=96,mode='panic_grid_hold',current_target=95)['phase'])
            self.assertFalse(self.evaluate(soc=96,mode='solar',current_target=95)['control_active'])
            self.document['groups']['1.1'][0]['end']=(NOW+timedelta(hours=7)).isoformat()
            self.plan.update(self.document)
            self.assertTrue(self.evaluate(soc=96,mode='panic_grid_hold',current_target=95)['control_active'])

    def test_failed_persistence_never_acquires_control(self):
        self.plan.path=Path('unused.json')
        with patch('app.services.outage_preparation.atomic_write_json',side_effect=OSError('disk')):
            result=self.evaluate()
        self.assertEqual('guarded',result['phase'])
        self.assertFalse(result['control_active'])
        self.assertIsNone(result['request'])
