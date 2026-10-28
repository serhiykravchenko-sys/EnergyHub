import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from app.services.grid_monitor import GridMonitor
import test_grid_confirmation_367 as grid_fixture


class EpisodeTests(unittest.TestCase):
    def tick(self,monitor,at,online):
        grid_fixture.GridTests.tick(self,monitor,at,online)

    def qualify(self,monitor,start,online):
        for at in range(start,start+181,10):self.tick(monitor,at,online)

    def test_restart_requires_requalification_but_preserves_same_episode(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'grid.json'
            first=GridMonitor(path)
            self.qualify(first,0,False)
            stamp=first.confirmed_at
            self.assertTrue(first.episode_persisted)
            restored=GridMonitor(path)
            self.assertIsNone(restored.confirmed)
            self.tick(restored,200,False)
            self.assertIsNone(restored.confirmed)
            self.qualify(restored,210,False)
            self.assertEqual(stamp,restored.confirmed_at)
            self.assertTrue(restored.episode_persisted)

    def test_real_confirmed_return_then_loss_gets_new_episode_flaps_do_not(self):
        with TemporaryDirectory() as directory:
            monitor=GridMonitor(Path(directory)/'grid.json')
            self.qualify(monitor,0,False)
            first=monitor.confirmed_at
            for at,online in [(190,True),(200,False),(210,True),(220,False)]:self.tick(monitor,at,online)
            self.assertEqual(first,monitor.confirmed_at)
            self.qualify(monitor,230,True)
            returned=monitor.confirmed_at
            self.qualify(monitor,420,False)
            self.assertGreater(monitor.confirmed_at,returned)
            self.assertGreater(returned,first)

    def test_persistence_failure_does_not_advertise_durable_episode(self):
        monitor=GridMonitor('/nonexistent/grid.json')
        with patch('app.utils.json_store.atomic_write_json',side_effect=OSError('disk unavailable')):
            self.qualify(monitor,0,False)
        self.assertFalse(monitor.episode_persisted)
        self.assertFalse(monitor.confirmed)

    def test_legacy_journal_and_corrupt_episode_requalify_safely(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'grid.json'
            for content in [dict(transitions=[]),dict(transitions=[],episode=dict(online='off',at=1))]:
                path.write_text(json.dumps(content),encoding='utf-8')
                monitor=GridMonitor(path)
                self.assertIsNone(monitor.saved_episode)
                self.qualify(monitor,0,True)
                self.assertTrue(monitor.confirmed)
                self.assertTrue(monitor.episode_persisted)
