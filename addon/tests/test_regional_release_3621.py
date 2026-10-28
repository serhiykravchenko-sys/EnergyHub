"""A cleared regional allowance must reach an already owned outage window."""
import unittest
from datetime import timedelta
import test_outage_preparation as fixture


class RegionalReleaseTests(unittest.TestCase):
    def test_lower_applied_reserve_allows_remaining_window_release(self):
        f=fixture.OutageTests();f.setUp()
        initial=f.evaluate(base_reserve=60)
        self.assertTrue(initial['control_active'])
        self.assertEqual(95,initial['target_soc'])
        later=fixture.NOW+timedelta(hours=4)
        f.document['checked_at']=later.isoformat()
        f.plan.update(f.document)
        before=f.evaluate(now=later,soc=89,base_reserve=60,mode='panic')
        self.assertEqual(95,before['target_soc'])
        after=f.evaluate(now=later,soc=89,base_reserve=40,mode='panic')
        self.assertEqual(95,after['target_soc'])
        self.assertEqual('solar',after['request'])
        self.assertTrue(after.get('coverage_release'))
