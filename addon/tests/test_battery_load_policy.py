import unittest
from app.services.battery_load_policy import BatteryLoadPolicy, LOADS


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = BatteryLoadPolicy()

    def evaluate(self, soc, **kwargs):
        return self.policy.evaluate(soc=soc, grid_present=kwargs.pop('grid_present', False), **kwargs)

    def test_default_boundaries_and_microwave_exclusion(self):
        self.assertEqual([], self.evaluate(51)['stop'])
        warning = self.evaluate(50)
        self.assertTrue(warning['warning'])
        self.assertEqual([], warning['stop'])
        self.assertFalse(self.evaluate(49)['warning'])
        self.assertEqual(list(LOADS), self.evaluate(40)['stop'])
        self.assertNotIn('microwave', self.evaluate(20)['stop'])

    def test_manual_on_after_soft_stop_until_latched_critical(self):
        self.evaluate(50)
        self.policy.attempted_stop('water_pump')
        self.assertNotIn('water_pump', self.evaluate(45)['stop'])
        self.assertIn('water_pump', self.evaluate(40)['stop'])
        self.assertNotIn('water_pump', self.evaluate(55)['stop'])
        self.assertEqual([], self.evaluate(60)['stop'])
        self.assertFalse(self.policy.locked)

    def test_actual_grid_prevents_shedding_but_recovery_must_be_qualified(self):
        self.evaluate(39)
        self.assertEqual([], self.evaluate(39, grid_present=True)['stop'])
        self.assertFalse(self.evaluate(39, grid_present=True)['restore_allowed'])
        self.assertTrue(self.evaluate(39, grid_present=True, grid_recovered=True)['restore_allowed'])

    def test_occupied_heating_does_not_override_household_protection(self):
        self.assertNotIn('heat_pump_floor_1', self.evaluate(45, occupied_heating=True)['stop'])
        self.assertNotIn('water_boiler', self.evaluate(45, occupied_heating=True)['stop'])
        self.assertIn('heat_pump_floor_1', self.evaluate(40, occupied_heating=True)['stop'])
        self.assertTrue(self.evaluate(50, occupied_heating=True)['hp_restore_allowed'])
        self.assertFalse(self.evaluate(49, occupied_heating=True)['hp_restore_allowed'])

    def test_explicit_floor_not_charge_target(self):
        self.assertEqual((50, 40, 60), self.policy.thresholds())
        self.assertEqual((50, 40, 60), self.policy.thresholds(60))
        self.assertNotIn('heat_pump_floor_1', self.evaluate(50, occupied_heating=True, hard_floor=60)['stop'])

    def test_restart_preserves_lock_and_manual_override(self):
        self.evaluate(40)
        self.policy.attempted_stop('water_pump')
        restored = BatteryLoadPolicy.restore(self.policy.export())
        self.assertTrue(restored.locked)
        self.assertIn('water_pump', restored.attempted)
        self.assertNotIn('water_pump', restored.evaluate(soc=55, grid_present=False)['stop'])

    def test_reject_unknown_evidence(self):
        for soc in (None, -1, 101, float('nan'), True):
            with self.assertRaises(ValueError): self.evaluate(soc)
        with self.assertRaises(ValueError): self.evaluate(50, grid_present=None)
        self.assertEqual((50, 40, 60), self.policy.thresholds(None))
        with self.assertRaises(ValueError): BatteryLoadPolicy.restore({'active': True})
