import unittest
from datetime import timedelta
from unittest.mock import patch
import test_outage_preparation as fixture


class RemainingReleaseTests(unittest.TestCase):
    setUp = fixture.OutageTests.setUp
    evaluate = fixture.OutageTests.evaluate

    def active(self, remaining=2.5, **overrides):
        end=fixture.NOW+timedelta(hours=6)
        now=end-timedelta(hours=remaining)
        self.document['checked_at']=now.isoformat()
        self.plan.update(self.document)
        return self.evaluate(now=now, soc=overrides.pop('soc',95),
                             mode=overrides.pop('mode','panic_grid_hold'),
                             current_target=95, **overrides)

    def test_acquired_hold_releases_at_conservative_boundary(self):
        self.evaluate()
        result=self.active()
        self.assertEqual(95,result['coverage_required_soc'])
        self.assertEqual(5,result['release_margin_percent'])
        self.assertEqual('solar',result['request'])
        self.assertTrue(self.plan.active_context['ownership_released'])
        steady=self.active(mode='solar')
        self.assertFalse(steady['control_active'])
        self.assertIsNone(steady['request'])

    def test_remaining_time_soc_and_br_each_limit_release(self):
        for changes in ({'remaining':2.6},{'soc':94},{'base_reserve':60}):
            with self.subTest(changes=changes):
                self.setUp();self.evaluate()
                result=self.active(**changes)
                self.assertNotEqual('solar',result['request'])
                self.assertFalse(result['coverage_release'])

    def test_grid_or_telemetry_gap_never_releases(self):
        for changes in ({'grid_online':False},{'grid_online':None},{'telemetry_valid':False},{'automatic':False}):
            with self.subTest(changes=changes):
                self.setUp();self.evaluate()
                result=self.active(**changes)
                self.assertNotEqual('solar',result['request'])

    def test_release_persistence_failure_retains_prior_authority(self):
        self.evaluate();old=dict(self.plan.active_context)
        with patch.object(self.plan,'_remember',return_value=False):
            result=self.active()
        self.assertEqual('guarded',result['phase'])
        self.assertIsNone(result['request'])
        self.assertEqual(old,self.plan.active_context)

    def test_extended_window_reacquires(self):
        self.evaluate();self.active()
        self.document['groups']['1.1'][0]['end']=(fixture.NOW+timedelta(hours=8)).isoformat()
        now=fixture.NOW+timedelta(hours=3.5)
        self.document['checked_at']=now.isoformat();self.plan.update(self.document)
        result=self.evaluate(now=now,soc=95,mode='solar')
        self.assertEqual('panic_grid_hold',result['request'])
        self.assertTrue(result['control_active'])
