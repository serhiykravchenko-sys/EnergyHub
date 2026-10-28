import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.main import observe_grid
from test_events import FakeClient


NOW = datetime(2026, 10, 16, 12, tzinfo=ZoneInfo('Europe/Kyiv'))
CONFIG = SimpleNamespace(grid_voltage_entity='voltage', battery_soc_entity='soc',
                         telemetry_freshness_entity='freshness')


class ThreeMinuteGridTests(unittest.TestCase):
    def test_instability_notice_does_not_claim_actual_charging(self):
        from app import grid_instability
        state = {}
        client = FakeClient({'binary_sensor.energyhub_grid_confirmed': dict(state='off',
            attributes=dict(checked_at=NOW.timestamp(), last_raw_transition_at=NOW.timestamp(),
                            raw_transitions_10m=4))})
        self.assertTrue(grid_instability.observe(state, client, NOW))
        message = state['pending_notifications'][0]['message']
        self.assertNotIn('Дозаряджаємо', message)
        self.assertIn('можуть переривати', message)
        self.assertFalse(grid_instability.observe(state, client, NOW+timedelta(seconds=30)))

    def test_legacy_sixty_second_confirmation_still_waits_three_minutes(self):
        state = {'grid_online': False, 'outage_started_at': (NOW-timedelta(hours=1)).isoformat()}
        client = FakeClient({'soc': 70, 'voltage': 230, 'freshness': 'fresh',
            'binary_sensor.energyhub_grid_confirmed': dict(state='on', attributes=dict(
                confirmation_seconds=60, transition_pending=False,
                checked_at=NOW.timestamp(), transition_at=(NOW-timedelta(seconds=60)).timestamp()))})
        for second in range(0, 180, 30):
            observe_grid(CONFIG, client, state, NOW+timedelta(seconds=second))
            self.assertFalse(state['grid_online'])
        observe_grid(CONFIG, client, state, NOW+timedelta(seconds=180))
        self.assertTrue(state['grid_online'])
        self.assertEqual(NOW.isoformat(), state['grid_restored_at'])
        self.assertEqual('grid_recovered', state['pending_notifications'][0]['kind'])

    def test_minute_flapping_produces_no_grid_event(self):
        state = {'grid_online': True}
        client = FakeClient({'soc': 70, 'freshness': 'fresh'})
        for second in range(0, 600, 30):
            client.values['voltage'] = 0 if (second//60)%2 == 0 else 230
            observe_grid(CONFIG, client, state, NOW+timedelta(seconds=second))
        self.assertTrue(state['grid_online'])
        self.assertEqual([], state['pending_notifications'])

    def test_confirmed_three_minutes_is_not_debounced_twice_and_keeps_start_time(self):
        state = {'grid_online': True}
        client = FakeClient({'soc': 70, 'voltage': 0, 'freshness': 'fresh'})
        for second in (180, 210):
            now = NOW+timedelta(seconds=second)
            client.values['binary_sensor.energyhub_grid_confirmed'] = dict(state='off', attributes=dict(
                confirmation_seconds=180, checked_at=now.timestamp(),
                transition_pending=False, transition_at=NOW.timestamp()))
            observe_grid(CONFIG, client, state, now)
        self.assertFalse(state['grid_online'])
        self.assertEqual(NOW.isoformat(), state['outage_started_at'])
        self.assertEqual(1, len(state['pending_notifications']))

    def test_gap_and_missing_voltage_restart_raw_confirmation(self):
        state = {'grid_online': True}
        client = FakeClient({'soc': 70, 'voltage': 0, 'freshness': 'fresh'})
        observe_grid(CONFIG, client, state, NOW)
        observe_grid(CONFIG, client, state, NOW+timedelta(seconds=120))
        self.assertEqual((NOW+timedelta(seconds=120)).isoformat(), state['grid_candidate_since'])
        client.values['voltage'] = 'unavailable'
        observe_grid(CONFIG, client, state, NOW+timedelta(seconds=150))
        self.assertIsNone(state['grid_candidate'])
        client.values['voltage'] = 0
        for second in range(180, 360, 30):
            observe_grid(CONFIG, client, state, NOW+timedelta(seconds=second))
        self.assertTrue(state['grid_online'])
        observe_grid(CONFIG, client, state, NOW+timedelta(seconds=360))
        self.assertFalse(state['grid_online'])
