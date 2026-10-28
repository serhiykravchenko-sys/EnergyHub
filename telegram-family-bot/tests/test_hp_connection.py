import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo
from app import hp_connection as connection


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 7, 12, tzinfo=ZoneInfo('Europe/Kyiv'))
        self.config = SimpleNamespace(house_monitor_enabled=True, destination_chat_id='family', technical_chat_id='owner',
            send_time='08:00', family_quiet_start='23:00', family_quiet_end='08:01')
        self.state = {}
        self.tg = Mock()
        self.attrs = dict(configured_ip='192.168.10.10', hp_state='unavailable',
            grid_present=True)
        self.probe = 'reachable'

    def tick(self, at, deliver=True):
        self.attrs['checked_at'] = at.isoformat()
        connection.observe(self.state, {connection.ENTITY: dict(state=self.probe, attributes=dict(self.attrs))}, at)
        return connection.deliver(self.state, self.tg, self.config, at) if deliver else False

    def hour(self):
        for n in range(61):
            self.tick(self.now+timedelta(minutes=n))

    def test_reachable_does_not_claim_address_changed_and_disabled_is_explicit(self):
        self.hour()
        text = self.tg.send_message.call_args.args[1]
        self.assertIn('Перевірте зв’язок у застосунку', text)
        self.assertNotIn('Автовідновлення', text)
        self.assertNotIn('Можливо, змінилася', text)
        self.assertEqual(1, self.tg.send_message.call_count)
        self.state = copy.deepcopy(self.state)
        self.tick(self.now+timedelta(minutes=61))
        self.assertEqual(1, self.tg.send_message.call_count)

    def test_unreachable_requires_power_and_grid_before_possible_ip_change(self):
        self.probe = 'unreachable'
        self.hour()
        self.assertIn('Поточна IP-адреса не відповідає', self.tg.send_message.call_args.args[1])
        for plug, grid in [('off', True), ('on', None), ('unavailable', True)]:
            self.attrs.update(plug_state=plug, grid_present=grid)
            text = connection.message(dict(attributes=self.attrs, reachability=self.probe))
            self.assertNotIn('Можливо, змінилася', text)

    def test_unknown_probe_never_claims_unreachable(self):
        self.probe = 'unknown'
        self.hour()
        self.assertIn('Перевірте зв’язок', self.tg.send_message.call_args.args[1])
        self.assertNotIn('не відповідає', self.tg.send_message.call_args.args[1])

    def test_stale_health_and_observation_gap_restart_timer(self):
        self.tick(self.now)
        connection.observe(self.state, {connection.ENTITY: dict(state='reachable', attributes=dict(self.attrs))},
            self.now+timedelta(hours=1))
        self.assertFalse(connection.deliver(self.state, self.tg, self.config, self.now+timedelta(hours=1)))
        self.tick(self.now+timedelta(hours=1, minutes=1))
        self.assertEqual(self.now.timestamp()+3660, self.state['hp_connection_notice']['bad_since'])

    def test_overnight_waits_until_after_successful_morning(self):
        self.now = self.now.replace(hour=7)
        self.hour()
        self.assertEqual(0, self.tg.send_message.call_count)
        self.tick(self.now.replace(hour=8, minute=2))
        self.assertEqual(0, self.tg.send_message.call_count)
        self.state['morning_delivered_date'] = self.now.date().isoformat()
        self.tick(self.now.replace(hour=8, minute=3))
        self.assertEqual(1, self.tg.send_message.call_count)

    def test_recovery_requires_five_minutes_and_preserves_failed_delivery(self):
        self.hour()
        self.attrs['hp_state'] = 'heat'
        for n in range(61, 66):
            self.tick(self.now+timedelta(minutes=n))
        self.assertEqual(1, self.tg.send_message.call_count)
        self.tg.send_message.side_effect = OSError('offline')
        with self.assertRaises(OSError): self.tick(self.now+timedelta(minutes=66))
        self.assertTrue(self.state['hp_connection_notice']['notified'])
        self.tg.send_message.side_effect = None
        self.assertTrue(self.tick(self.now+timedelta(minutes=67)))
        self.assertFalse(self.tick(self.now+timedelta(minutes=68)))

    def test_configured_quiet_hours_are_respected(self):
        self.config.family_quiet_start = '11:00'
        self.config.family_quiet_end = '14:00'
        self.hour()
        self.tg.send_message.assert_not_called()

    def test_retired_recovery_record_does_not_suppress_connection_observation(self):
        at=self.now+timedelta(hours=1)
        self.state['hp_recovery_notice']=dict(phase='awaiting_off',observed_at=at.timestamp(),
            sent_request='one',attributes={'request_id':'one'})
        self.hour()
        self.assertEqual(1,self.tg.send_message.call_count)

    def test_0801_delivery_waits_for_successful_morning(self):
        self.now=self.now.replace(hour=7)
        self.hour()
        self.state['morning_delivered_date']=self.now.date().isoformat()
        self.assertTrue(self.tick(self.now.replace(hour=8,minute=1)))


if __name__ == '__main__': unittest.main()
