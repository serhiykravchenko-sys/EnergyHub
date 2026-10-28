import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from app import hp_eco, hp_summary


class EcoNotificationsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 6, 16, tzinfo=timezone(timedelta(hours=3)))
        self.rows = {entity: {'state': value} for entity, value in {
            hp_summary.MASTER: 'Smart', hp_eco.HP: 'heat', hp_eco.ECO: 'off',
            'sensor.energyhub_telemetry_freshness': 'fresh',
            'sensor.powmr_10_2m_grid_voltage': '0',
            'binary_sensor.energyhub_hp_solar_sufficient': 'on',
        }.items()}
        self.client = SimpleNamespace(state=lambda entity: self.rows.get(entity))
        self.state = {}
        hp_eco.observe(self.state, self.client, self.now)

    def feedback(self, value):
        self.rows['input_text.energyhub_hp1_profile_requests'] = {'state': json.dumps(
            {'eco': {'t': value, 'at': self.now.timestamp(), 'n': 1}})}
        self.rows[hp_eco.ECO] = {'state': value, 'last_changed': self.now.isoformat()}

    def confirm(self):
        hp_eco.observe(self.state, self.client, self.now)
        self.now += timedelta(seconds=30)
        hp_eco.observe(self.state, self.client, self.now)

    def test_later_solar_drop_notifies_once_and_grid_return_stays_private(self):
        self.assertIn('перехід в Eco ще не підтверджено', hp_summary.outage_detail(self.client))
        self.now += timedelta(hours=1)
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on')
        self.confirm()
        queue = self.state['pending_notifications']
        self.assertEqual(1, len(queue))
        self.assertIn('ДТЕК відсутній', queue[0]['message'])
        hp_eco.observe(self.state, self.client, self.now+timedelta(seconds=30))
        self.assertEqual(1, len(queue))
        queue.clear()
        self.now += timedelta(hours=1)
        self.rows['sensor.powmr_10_2m_grid_voltage']['state'] = '220'
        self.feedback('off')
        queue.append({'kind': 'grid_recovered', 'message': 'grid restored'})
        self.confirm()
        self.assertEqual(2, len(queue))
        self.assertNotIn('hp_eco_ack', queue[0])
        self.assertEqual('hp_eco_change', queue[1]['kind'])
        self.assertIn('Eco вимкнено', hp_eco.recovery_detail(self.client, self.now))

    def test_solar_recovers_while_grid_stays_absent(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on'); self.confirm()
        self.state['pending_notifications'].clear()
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'on'
        self.feedback('off'); self.confirm()
        self.assertFalse(self.state['pending_notifications'])

    def test_request_without_feedback_and_unavailable_hp_do_not_claim_eco(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on')
        self.rows[hp_eco.ECO]['state'] = 'off'
        self.confirm()
        self.assertFalse(self.state.get('pending_notifications'))
        self.assertIn('ще не підтверджено', hp_summary.outage_detail(self.client))
        self.rows[hp_eco.HP]['state'] = 'unavailable'
        self.assertIn('недоступний', hp_summary.outage_detail(self.client))
        self.assertIn('недоступний', hp_eco.recovery_detail(self.client, self.now))

    def test_manual_state_and_stale_request_are_not_attributed_to_eh(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on')
        self.rows[hp_eco.ECO]['context'] = {'user_id': 'family'}
        self.assertIsNone(hp_eco.sample(self.client, self.now))
        self.rows[hp_eco.ECO].pop('context')
        self.assertIsNone(hp_eco.sample(self.client, self.now+timedelta(minutes=11)))

    def test_old_queued_on_is_removed_after_actual_off(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on'); self.confirm()
        item = self.state['pending_notifications'][0]
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'on'
        self.feedback('off')
        self.assertIsNone(hp_eco.refresh(item, self.client, self.now))

    def test_active_family_override_and_future_feedback_are_not_acknowledgement(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on')
        self.rows['input_text.energyhub_hp1_night_overrides'] = {'state': json.dumps({'eco_until': self.now.timestamp()+3600})}
        self.assertIsNone(hp_eco.sample(self.client, self.now))
        self.rows.pop('input_text.energyhub_hp1_night_overrides')
        self.rows[hp_eco.ECO]['last_changed'] = (self.now+timedelta(minutes=1)).isoformat()
        self.assertIsNone(hp_eco.sample(self.client, self.now))

    def test_grid_debounce_defers_standalone_eco(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.state['grid_candidate'] = False
        self.feedback('on'); self.confirm()
        self.assertFalse(self.state.get('pending_notifications'))
        self.state['grid_candidate'] = None
        self.state['pending_notifications'] = [{'kind': 'grid_lost', 'message': 'outage'}]
        hp_eco.observe(self.state, self.client, self.now)
        self.assertEqual(2, len(self.state['pending_notifications']))
        self.assertEqual('hp_eco_change', self.state['pending_notifications'][1]['kind'])

    def test_delivery_combination_survives_restart_without_replay(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on')
        hp_eco.acknowledge_grid(self.state, {'kind': 'grid_lost'}, self.client, self.now)
        restored = json.loads(json.dumps(self.state))
        hp_eco.observe(restored, self.client, self.now+timedelta(seconds=60))
        self.assertEqual(1, len(restored['pending_notifications']))
        self.assertEqual('hp_eco_change', restored['pending_notifications'][0]['kind'])

    def test_grid_delivery_routes_eco_confirmation_to_owner(self):
        from app.main import deliver_pending_notifications
        from unittest.mock import Mock
        config = SimpleNamespace(destination_chat_id='family', technical_chat_id='owner', timezone='Europe/Kyiv')
        self.feedback('on')
        self.state['pending_notifications'] = [dict(kind='grid_lost', message='ДТЕК недоступний', created_at=self.now.isoformat())]
        telegram = Mock()
        deliver_pending_notifications(config, telegram, self.state, self.now, self.client)
        self.assertEqual(['family', 'owner'], [call.args[0] for call in telegram.send_message.call_args_list])
        self.assertNotIn('Eco', telegram.send_message.call_args_list[0].args[1])
        self.assertIn('Eco', telegram.send_message.call_args_list[1].args[1])
        self.assertFalse(self.state['pending_notifications'])

    def test_first_snapshot_does_not_replay_old_native_transition(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on')
        state = {}
        hp_eco.observe(state, self.client, self.now)
        hp_eco.observe(state, self.client, self.now+timedelta(seconds=60))
        self.assertFalse(state.get('pending_notifications'))

    def test_delivery_revalidates_and_preserves_schedule_context(self):
        from app.main import deliver_pending_notifications
        from unittest.mock import Mock
        config = SimpleNamespace(destination_chat_id='family', technical_chat_id='owner', timezone='Europe/Kyiv')
        self.rows[hp_eco.HP]['state'] = 'unavailable'
        self.state['pending_notifications'] = [dict(kind='grid_lost',
            message='ДТЕК недоступний\n📅 Очікуване відновлення 20:30', created_at=self.now.isoformat())]
        tg = Mock()
        deliver_pending_notifications(config, tg, self.state, self.now, self.client)
        text = tg.send_message.call_args.args[1]
        self.assertIn('20:30', text)
        self.assertNotIn('Eco', text)  # HP diagnostics are private.

    def test_delivery_retry_and_quiet_hours_do_not_duplicate_or_send_at_night(self):
        from app.main import deliver_pending_notifications
        from unittest.mock import Mock
        config = SimpleNamespace(destination_chat_id='family', technical_chat_id='owner', timezone='Europe/Kyiv')
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'off'
        self.feedback('on'); self.confirm()
        tg = Mock()
        tg.send_message.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            deliver_pending_notifications(config, tg, self.state, self.now, self.client)
        self.assertEqual(1, len(self.state['pending_notifications']))
        tg.send_message.side_effect = None
        deliver_pending_notifications(config, tg, self.state, self.now, self.client)
        self.assertFalse(self.state['pending_notifications'])
        self.now = self.now.replace(hour=23)
        self.rows['sensor.powmr_10_2m_grid_voltage']['state'] = '220'
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']['state'] = 'on'
        self.feedback('off'); self.confirm()
        tg.reset_mock()
        deliver_pending_notifications(config, tg, self.state, self.now, self.client)
        self.assertEqual('owner', tg.send_message.call_args.args[0])
        self.assertFalse(self.state.get('overnight_family_events'))
        self.assertIn('Eco вимкнено', tg.send_message.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
