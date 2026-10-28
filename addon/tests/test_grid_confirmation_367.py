import unittest
from unittest.mock import patch
from types import SimpleNamespace
from app.services.grid_monitor import GridMonitor
import test_outage_preparation as baseline


class GridTests(unittest.TestCase):
    def tick(self, monitor, at, online, valid=True):
        with patch('app.services.grid_monitor.time.monotonic',return_value=at), patch('app.services.grid_monitor.time.time',return_value=1000+at):
            monitor.handle_inverter_state(SimpleNamespace(valid=valid,grid_available=online))

    def initialized(self):
        monitor=GridMonitor()
        for at in range(0,181,10): self.tick(monitor,at,True)
        self.assertTrue(monitor.confirmed)
        return monitor

    def test_brief_loss_does_not_change_confirmed_state(self):
        monitor=self.initialized()
        for at,online in [(190,False),(210,False),(240,False),(250,True)]:
            self.tick(monitor,at,online)
        self.assertTrue(monitor.confirmed)

    def test_sustained_loss_and_return(self):
        monitor=self.initialized()
        for at in range(190,370,10): self.tick(monitor,at,False)
        self.assertTrue(monitor.confirmed)
        self.tick(monitor,370,False)
        self.assertFalse(monitor.confirmed)
        self.assertEqual(1190,monitor.confirmed_at)
        for at in range(380,560,10): self.tick(monitor,at,True)
        self.assertFalse(monitor.confirmed)
        self.tick(monitor,560,True)
        self.assertTrue(monitor.confirmed)
        self.assertEqual(1380,monitor.confirmed_at)

    def test_invalid_read_resets_confirmation_candidate(self):
        monitor=self.initialized()
        self.tick(monitor,190,False)
        self.tick(monitor,210,False,valid=False)
        self.tick(monitor,230,False)
        self.assertTrue(monitor.confirmed)
        self.assertEqual(230,monitor.since)

    def test_cold_start_and_gap_require_new_full_window(self):
        monitor=GridMonitor()
        for at in range(0,180,10): self.tick(monitor,at,True)
        self.assertIsNone(monitor.confirmed)
        self.tick(monitor,220,True)
        self.assertIsNone(monitor.confirmed)
        self.assertEqual(220,monitor.since)
        for at in range(230,401,10): self.tick(monitor,at,True)
        self.assertTrue(monitor.confirmed)

    def test_minute_flapping_never_changes_confirmed_grid(self):
        monitor=self.initialized()
        for at in range(190,790,10):
            self.tick(monitor,at,((at-190)//60)%2 == 1)
            self.assertTrue(monitor.confirmed)


class OwnershipTests(unittest.TestCase):
    setUp=baseline.OutageTests.setUp
    evaluate=baseline.OutageTests.evaluate
    def test_supply_loss_keeps_target_without_charging_command(self):
        first=self.evaluate()
        self.assertEqual('panic',first['request'])
        lost=self.evaluate(grid_online=False,mode='panic',current_target=95)
        self.assertEqual('waiting_for_grid',lost['phase'])
        self.assertTrue(lost['control_active'])
        self.assertEqual(95,lost['target_soc'])
        self.assertIsNone(lost['request'])
        returned=self.evaluate(mode='panic',current_target=95)
        self.assertTrue(returned['control_active'])
        self.assertIsNone(returned['request'])

    def test_initial_offline_never_requests_grid_charge(self):
        result=self.evaluate(grid_online=False)
        self.assertFalse(result['control_active'])
        self.assertIsNone(result['request'])
