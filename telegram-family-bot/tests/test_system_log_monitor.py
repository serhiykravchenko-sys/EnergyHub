import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from app import system_log_monitor, log_digest
from app.home_assistant import HomeAssistantClient, HomeAssistantError


class LogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 3, 8, tzinfo=timezone.utc)
        self.state = {}
        self.tg = Mock()

    def row(self, level='ERROR', count=1, text='connection failed', now=None):
        return dict(level=level, count=count, message=[text], name='integration',
                    source=['integration.py', 12], timestamp=(now or self.now).timestamp())

    def test_restart_grace_recurrence_dedup_and_ack(self):
        system_log_monitor.observe(self.state, [self.row()], self.now, boot='a')
        self.assertFalse(system_log_monitor.deliver(self.state, self.tg, 'chat', self.now))
        later = self.now+timedelta(seconds=10)
        row = self.row(count=3, now=later)
        system_log_monitor.observe(self.state, [row], later, boot='a')
        self.tg.send_message.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            system_log_monitor.deliver(self.state, self.tg, 'chat', later)
        self.assertEqual(1, len(self.state['system_log_monitor']['pending']))
        self.tg.send_message.side_effect = None
        self.assertTrue(system_log_monitor.deliver(self.state, self.tg, 'chat', later))
        # Simulated persistent-state reconstruction.
        self.state = json.loads(json.dumps(self.state))
        for minute in (10, 20, 30):
            tick = self.now+timedelta(minutes=minute)
            system_log_monitor.observe(self.state, [self.row(count=minute, now=tick)], tick, boot='a')
            self.assertFalse(system_log_monitor.deliver(self.state, self.tg, 'chat', tick))
        tick = self.now+timedelta(hours=2)
        system_log_monitor.observe(self.state, [self.row(count=50, now=tick)], tick, boot='a')
        self.assertFalse(system_log_monitor.deliver(self.state, self.tg, 'chat', tick))

    def test_critical_bypasses_grace_and_redacts_credentials(self):
        row = self.row('CRITICAL', text='Bearer private-token password=secret https://user:pass@host/x {"token":"jsonsecret"}')
        system_log_monitor.observe(self.state, [row], self.now, boot='a')
        self.assertTrue(system_log_monitor.deliver(self.state, self.tg, 'chat', self.now))
        text = self.tg.send_message.call_args.args[1]
        for secret in ('private-token', 'secret', 'user:pass', 'jsonsecret'):
            self.assertNotIn(secret, text)

    def test_old_single_warnings_and_bounds(self):
        system_log_monitor.observe(self.state, [self.row('WARNING'),
            self.row(now=self.now-timedelta(days=2)), None], self.now)
        self.assertFalse(system_log_monitor.deliver(self.state, self.tg, 'chat', self.now))
        rows = [self.row(text=str(i)) for i in range(300)]
        system_log_monitor.observe(self.state, rows, self.now)
        self.assertEqual(8, len(self.state['system_log_monitor']['pending']))
        self.assertLessEqual(len(self.state['system_log_monitor']['seen']), 200)

    def test_known_churn_goes_to_digest_even_with_large_counts(self):
        rows = []
        for name, text in (
            ('custom_components.hisense_aircon.aircon', 'Ignoring unrecognized t_fan_speed value packed in t_control_value=808059459'),
            ('custom_components.hisense_aircon.notifier', 'Device connection failed (TimeoutError)'),
            ('custom_components.xiaomi_miot.core.xiaomi_cloud', 'miotspec/prop/get timeout'),
            ('pychromecast.socket_client', 'Failed to connect to service')):
            row = self.row(count=3031, text=text)
            row['name'] = name
            rows.append(row)
        system_log_monitor.observe(self.state, rows, self.now)
        self.assertFalse(system_log_monitor.deliver(self.state, self.tg, 'owner', self.now))
        self.assertTrue(log_digest.digest_lines(json.dumps(rows), self.now))

    def test_beacon_wrappers_are_one_cause_and_not_delivered_at_night(self):
        rows = [self.row(count=4, text=text) for text in ('Unexpected error while executing automation',
                'Error executing script: network error')]
        for row in rows: row['name'] = 'homeassistant.components.automation.battery_lamp_color_4_levels'
        system_log_monitor.observe(self.state, rows, self.now)
        self.assertEqual(1, len(self.state['system_log_monitor']['pending']))
        self.assertFalse(system_log_monitor.deliver(self.state, self.tg, '', self.now))
        self.assertFalse(system_log_monitor.deliver(self.state, self.tg, 'owner', self.now.replace(hour=23)))
        self.assertTrue(system_log_monitor.deliver(self.state, self.tg, 'owner', self.now))

    def test_empty_buffer_and_aggregate_count_are_qualified(self):
        self.assertIn('не повний', log_digest.digest_lines('[]', self.now)[0])
        lines = log_digest.digest_lines(json.dumps([self.row(count=10)]), self.now)
        self.assertIn('весь сеанс', lines[0])
        self.assertIn('Помилки: 10', lines[1])

    def test_authenticated_websocket_and_404_fallback(self):
        ws = Mock()
        ws.recv.side_effect = [json.dumps({'type': 'auth_required'}),
            json.dumps({'type': 'auth_ok'}), json.dumps({'id': 1, 'success': True, 'result': [self.row()]})]
        client = HomeAssistantClient(base_url='http://supervisor/core/api', token='test-secret')
        with patch('websocket.create_connection', return_value=ws) as connect:
            with patch.object(client, '_request_text', side_effect=HomeAssistantError('HTTP 404')):
                result = json.loads(client.error_log())
        self.assertEqual(1, len(result))
        self.assertEqual('ws://supervisor/core/websocket', connect.call_args.args[0])
        self.assertEqual({'type': 'auth', 'access_token': 'test-secret'}, json.loads(ws.send.call_args_list[0].args[0]))
        self.assertEqual({'id': 1, 'type': 'system_log/list'}, json.loads(ws.send.call_args_list[1].args[0]))
        ws.close.assert_called_once()

    def test_authentication_failure_closes_socket(self):
        ws = Mock()
        ws.recv.side_effect = ['{"type":"auth_required"}', '{"type":"auth_invalid"}']
        with patch('websocket.create_connection', return_value=ws):
            with self.assertRaisesRegex(HomeAssistantError, 'authentication rejected'):
                HomeAssistantClient(token='secret').system_log_entries()
        ws.close.assert_called_once()
