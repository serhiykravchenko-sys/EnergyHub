import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import test_outage_preparation as fixture
from app.services.outage_preparation import OutagePreparation


class ChangingTargetTests(unittest.TestCase):
    setUp = fixture.OutageTests.setUp
    evaluate = fixture.OutageTests.evaluate

    def advance(self):
        self.args['now'] = fixture.NOW + timedelta(hours=2, minutes=79)
        self.document['checked_at'] = self.args['now'].isoformat()
        self.assertTrue(self.plan.update(self.document))

    def test_changing_target_survives_offline_ticks_and_grid_return(self):
        for grid in (False, None):
            with self.subTest(grid=grid):
                self.setUp()
                self.evaluate()
                self.advance()
                first = self.evaluate(mode='panic', current_target=95, soc=91, grid_online=grid)
                self.assertEqual(95, first['target_soc'])
                self.assertTrue(first['control_active'])
                self.assertIsNone(first['request'])
                self.assertEqual(95, self.plan.active_context['target_soc'])
                second = self.evaluate(mode='panic', current_target=95, soc=91, grid_online=grid)
                self.assertTrue(second['control_active'])
                self.assertIsNone(second['request'])
                returned = self.evaluate(mode='panic', current_target=95, soc=91, grid_online=True)
                self.assertTrue(returned['control_active'])
                self.assertEqual('charging', returned['phase'])
                self.assertEqual(95, returned['target_soc'])

    def test_failed_persistence_freezes_owned_target_until_retry(self):
        for grid in (False, True):
            with self.subTest(grid=grid):
                self.setUp()
                self.evaluate()
                self.advance()
                self.document['groups']['1.1'][0]['end'] = (fixture.NOW+timedelta(hours=7)).isoformat()
                self.plan.update(self.document)
                with patch.object(self.plan, '_remember', return_value=False):
                    result = self.evaluate(mode='panic', current_target=95, soc=91, grid_online=grid)
                self.assertEqual('guarded', result['phase'])
                self.assertTrue(result['control_active'])
                self.assertEqual(95, result['target_soc'])
                self.assertEqual(95, self.plan.active_context['target_soc'])
                self.assertIsNone(result['request'])
                self.assertEqual(95, self.evaluate(mode='panic', current_target=95, soc=91,
                                                 grid_online=grid)['target_soc'])

    def test_restart_between_planner_and_controller_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preparation.json'
            options = dict(outage_preparation_enabled=True, outage_group='1.1')
            self.plan = OutagePreparation(options, path)
            self.plan.update(self.document)
            self.evaluate()
            self.advance()
            self.evaluate(mode='panic', current_target=95, soc=91, grid_online=False)
            self.plan = OutagePreparation(options, path)
            self.plan.update(self.document)
            guarded = self.evaluate(mode='panic', current_target=95, solar_w=None, grid_online=False)
            self.assertTrue(guarded['control_active'])
            self.assertEqual(95, guarded['target_soc'])
            result = self.evaluate(mode='panic', current_target=95, soc=91, grid_online=False)
            self.assertTrue(result['control_active'])
            self.assertEqual(95, result['target_soc'])
            self.assertIsNone(result['request'])

    def test_manual_override_and_other_window_do_not_inherit_ownership(self):
        self.evaluate()
        self.advance()
        manual = self.evaluate(mode='panic', current_target=95, automatic=False,
                               ownership_allowed=False, grid_online=False)
        self.assertFalse(manual['control_active'])
        self.plan.active_context['start'] = (fixture.NOW + timedelta(hours=7)).isoformat()
        self.assertFalse(self.evaluate(mode='panic', current_target=95,
                                       grid_online=False)['control_active'])

    def test_owned_hold_recharges_on_return_and_expires_at_window_end(self):
        self.evaluate()
        self.advance()
        offline = self.evaluate(mode='panic_grid_hold', current_target=95, soc=91, grid_online=False)
        self.assertTrue(offline['control_active'])
        self.assertEqual(95, offline['target_soc'])
        returned = self.evaluate(mode='panic_grid_hold', current_target=95, soc=91, grid_online=True)
        self.assertEqual('panic', returned['request'])
        self.args['now'] = fixture.NOW + timedelta(hours=6)
        self.document['checked_at'] = self.args['now'].isoformat()
        self.plan.update(self.document)
        expired = self.evaluate(mode='panic', current_target=95, grid_online=True)
        self.assertFalse(expired['control_active'])
        self.assertEqual('no_upcoming_outage', expired['phase'])
