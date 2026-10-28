import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from app import beacon_recovery as beacon, technical_summary

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


class BeaconTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.registry = dict(entities=[dict(entity_id=beacon.LAMP, device_id='lamp', config_entry_id='tuya')],
                             devices=[dict(id='lamp', config_entries=['tuya'])])
        self.entries = [dict(entry_id='tuya', domain='tuya', state='setup_retry', reason='connection timeout')]
        self.persist, self.reload = Mock(), Mock()

    def tick(self, seconds, **kwargs):
        now = NOW+timedelta(seconds=seconds)
        beacon.observe(self.state, now, self.registry, self.entries,
                       dict(state=kwargs.pop('lamp', 'unavailable'), last_updated=now.isoformat()),
                       persist=self.persist, reload=self.reload, **kwargs)

    def test_exact_entry_bounded_attempts_persisted_before_reload(self):
        order=[]
        self.persist.side_effect=lambda state:order.append('save')
        self.reload.side_effect=lambda entry:order.append(entry)
        for second in range(0, 1501, 60): self.tick(second)
        self.assertEqual(3, self.reload.call_count)
        self.assertEqual(['save', 'tuya']*3, order)
        self.assertEqual('manual', self.state['beacon_recovery']['status'])
        self.assertIn('не допомогло', self.state['beacon_recovery']['pending'])

    def test_shared_entry_auth_and_unknown_failure_never_reload(self):
        for scenario in ('shared', 'auth', 'unknown'):
            with self.subTest(scenario=scenario):
                self.setUp()
                if scenario == 'shared':
                    self.registry['devices'].append(dict(id='other', config_entries=['tuya']))
                else:
                    self.entries[0].update(state='setup_error', reason='auth failed' if scenario == 'auth' else None)
                for second in range(0, 1201, 60): self.tick(second)
                self.reload.assert_not_called()

    def test_recovery_needs_five_minutes_loaded_and_new_feedback(self):
        for second in range(0, 181, 60): self.tick(second)
        self.assertEqual(1, self.reload.call_count)
        self.entries[0]['state']='loaded'
        for second in range(240, 541, 60): self.tick(second, lamp='off')
        self.assertIn('стабільні 5 хв', self.state['beacon_recovery']['pending'])
        self.assertEqual(1, self.reload.call_count)

    def test_failed_persistence_never_calls_service_and_old_log_no_trigger(self):
        self.persist.side_effect=OSError('disk')
        for second in range(0, 181, 60): self.tick(second)
        self.reload.assert_not_called()
        self.assertIsNone(beacon.recent_control_error([dict(name='automation.battery_lamp_color_4_levels',
                            message='network error', timestamp=NOW.timestamp()-86400)], NOW))

    def test_gap_does_not_qualify_sustained_failure(self):
        self.tick(0); self.tick(600)
        self.reload.assert_not_called()

    def test_current_entry_specific_transport_exception_allows_setup_error_recovery(self):
        self.entries[0].update(state='setup_error',reason=None,title='lamp-account')
        rows=[dict(message='Error setting up entry lamp-account for tuya',exception='TimeoutError',timestamp=NOW.timestamp())]
        self.assertTrue(beacon.recent_transport_error(rows,NOW,'lamp-account'))
        self.assertFalse(beacon.recent_transport_error(rows,NOW,'other-account'))
        for second in range(0,181,60): self.tick(second,transport_error=second==0)
        self.reload.assert_called_once_with('tuya')


class SummaryTests(unittest.TestCase):
    def test_current_fault_has_action_not_session_counts(self):
        state=dict(current_health_at=NOW.isoformat(), current_health={'ha': True},
                   data_incidents={'device:climate.heat_pump':dict(bad_since=NOW.timestamp()-3600,last_seen=NOW.timestamp())})
        text=technical_summary.build(state, NOW)
        self.assertIn('перевірте живлення',text)
        self.assertNotIn('ERROR',text)
        self.assertNotIn('459',text)

    def test_healthy_and_unknown_are_distinct(self):
        self.assertIn('не підтверджено',technical_summary.build({},NOW))
        self.assertIn('Втручання не потрібне',technical_summary.build(
            dict(current_health_at=NOW.isoformat(), current_health={'ha':True,'inverter':True}),NOW))
