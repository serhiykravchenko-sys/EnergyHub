import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from app import recovery_advice


class RecoveryAdviceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 4, 9, tzinfo=timezone.utc)
        self.state = {}
        self.rows = {key: {'state': value} for key, value in {
            'sensor.energyhub_telemetry_freshness': 'stale',
            'binary_sensor.zigbee2mqtt_bridge_connection_state': 'off'}.items()}

    def observe(self, count):
        for _ in range(count):
            recovery_advice.observe(self.state, self.rows, self.now)
            self.now += timedelta(seconds=30)

    def test_ten_minutes_ack_retry_and_budget(self):
        self.observe(20)
        self.assertIsNone(self.state['host_recovery_advice'].get('pending'))
        self.observe(1)
        tg = Mock()
        tg.send_message.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            recovery_advice.deliver(self.state, tg, 'technical', self.now)
        self.assertTrue(self.state['host_recovery_advice']['pending'])
        tg.send_message.side_effect = None
        self.assertTrue(recovery_advice.deliver(self.state, tg, 'technical', self.now))
        self.observe(2)
        self.assertFalse(recovery_advice.deliver(self.state, tg, 'technical', self.now))
        self.assertIn('Автоматичного перезавантаження немає', tg.send_message.call_args.args[1])

    def test_recovery_cancels_pending_and_gap_resets_continuity(self):
        self.observe(21)
        self.rows['binary_sensor.zigbee2mqtt_bridge_connection_state']['state'] = 'on'
        self.observe(1)
        self.assertFalse(self.state['host_recovery_advice']['pending'])
        self.rows['binary_sensor.zigbee2mqtt_bridge_connection_state']['state'] = 'off'
        self.observe(19)
        self.now += timedelta(seconds=100)
        self.observe(1)
        self.assertIsNone(self.state['host_recovery_advice']['bad_since'])

    def test_single_outage_and_restart_grace_do_not_qualify(self):
        self.rows['binary_sensor.zigbee2mqtt_bridge_connection_state']['state'] = 'on'
        self.observe(30)
        self.assertFalse(self.state['host_recovery_advice']['pending'])
        self.rows['binary_sensor.zigbee2mqtt_bridge_connection_state']['state'] = 'off'
        self.rows['input_text.energyhub_load_bridge_session'] = {'state': 'new-session'}
        self.observe(10)
        self.assertIsNone(self.state['host_recovery_advice']['bad_since'])
