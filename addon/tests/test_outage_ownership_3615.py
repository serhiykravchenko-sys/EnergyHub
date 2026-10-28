import unittest
import test_outage_preparation as fixture


class OwnershipTests(unittest.TestCase):
    setUp = fixture.OutageTests.setUp
    evaluate = fixture.OutageTests.evaluate
    def test_pv2_timeout_preserves_owned_target_without_commands(self):
        self.evaluate()
        guarded = self.evaluate(mode='panic', current_target=95, solar_w=None, soc=62)
        self.assertTrue(guarded['control_active'])
        self.assertEqual('guarded', guarded['phase'])
        self.assertEqual(95, guarded['target_soc'])
        self.assertIsNone(guarded['request'])
        recovered = self.evaluate(mode='panic', current_target=95, soc=62)
        self.assertEqual('charging', recovered['phase'])
        self.assertTrue(recovered['control_active'])

    def test_missing_telemetry_does_not_acquire_new_ownership(self):
        self.assertFalse(self.evaluate(solar_w=None)['control_active'])

    def test_malformed_saved_target_cannot_retain_ownership(self):
        self.evaluate()
        self.plan.active_context['target_soc'] = None
        self.assertFalse(self.evaluate(mode='panic', current_target=None,
                                       solar_w=None)['control_active'])

    def test_owned_target_survives_authority_gap_but_manual_override_wins(self):
        self.evaluate()
        self.assertTrue(self.evaluate(mode='panic', current_target=95, automatic=False,
                                      ownership_allowed=True)['control_active'])
        self.assertFalse(self.evaluate(mode='panic', current_target=95, automatic=False,
                                       ownership_allowed=False)['control_active'])

    def test_invalid_schedule_revokes_owned_preparation(self):
        self.evaluate()
        self.plan.update({'schema': 1, 'source_status': 'unavailable'})
        self.assertFalse(self.evaluate(mode='panic', current_target=95, solar_w=None)['control_active'])

    def test_uncertain_grid_retains_target_without_new_grid_command(self):
        self.evaluate()
        result=self.evaluate(mode='panic',current_target=95,grid_online=None,soc=62)
        self.assertTrue(result['control_active'])
        self.assertIsNone(result['request'])
        self.assertEqual(95,result['target_soc'])

    def test_grid_loss_at_eighty_one_then_return_keeps_ninety_five_target(self):
        self.evaluate()
        offline=self.evaluate(mode='panic',current_target=95,grid_online=False,soc=81)
        self.assertTrue(offline['control_active'])
        self.assertEqual(95,offline['target_soc'])
        self.assertEqual('waiting_for_grid',offline['phase'])
        self.assertIsNone(offline['request'])
        restored=self.evaluate(mode='panic',current_target=95,grid_online=True,soc=81)
        self.assertTrue(restored['control_active'])
        self.assertEqual(95,restored['target_soc'])
        self.assertEqual('charging',restored['phase'])
        self.assertIsNone(restored['request'])


if __name__ == '__main__':
    unittest.main()
