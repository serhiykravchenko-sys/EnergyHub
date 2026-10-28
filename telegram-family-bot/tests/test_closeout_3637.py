import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

from app import solar_observation as solar, system_log_monitor as logs, technical_summary
from app.main import (observe_grid, observe_reserve_warnings,
                      deliver_pending_notifications, retired_protection_notice,
                      retire_zigbee_diagnostics)
from app import data_incidents
from app.state import StateStore, DEFAULT_STATE
from app.automation_notifications import NotificationDeliveryWorker

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


class SolarClockTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(telemetry_freshness_entity='fresh')

    def client(self, report_at, value='800', pv2='fresh'):
        def read(entity):
            if entity == solar.ENTITY:
                return dict(state=value, last_reported=report_at.isoformat())
            return dict(state=pv2 if entity.endswith('pv2_telemetry_freshness') else 'fresh')
        return SimpleNamespace(state=read)

    def test_reports_arriving_after_loop_time_qualify_and_survive_restart(self):
        state = {}
        for step in range(11):
            tick = NOW+timedelta(seconds=step*30)
            reported = tick+timedelta(seconds=7)
            complete = tick+timedelta(seconds=8)
            observed = solar.observe(self.client(reported), self.config, state, tick,
                                     clock=lambda: complete)
            state = json.loads(json.dumps(state))
        self.assertEqual(complete, observed)
        self.assertEqual(800, solar.average(state['solar_event_samples'], complete))
        self.assertEqual('ready', state['solar_event_diagnostic']['reason'])
        self.assertIn('0.8 kW', solar.line(state, complete))

    def test_source_time_checks_use_completion_time(self):
        complete = NOW+timedelta(seconds=10)
        for offset, reason in [(2, 'insufficient_coverage'), (3, 'future_report'),
                               (-90, 'insufficient_coverage'), (-91, 'stale_report')]:
            with self.subTest(offset=offset):
                state = {}
                solar.observe(self.client(complete+timedelta(seconds=offset)),
                              self.config, state, NOW, clock=lambda: complete)
                self.assertEqual(reason, state['solar_event_diagnostic']['reason'])
                self.assertTrue(all(solar.stamp(r['last_updated']) <= complete
                                    for r in state['solar_event_samples']))

    def test_clock_reversal_invalid_power_and_pv2_remain_unknown(self):
        for client, clock, reason in [
            (self.client(NOW), lambda: NOW-timedelta(seconds=1), 'clock_reversed'),
            (self.client(NOW, True), lambda: NOW, 'invalid_power'),
            (self.client(NOW, 'nan'), lambda: NOW, 'invalid_power'),
            (self.client(NOW, pv2='stale'), lambda: NOW, 'pv2_not_fresh')]:
            state = {}
            solar.observe(client, self.config, state, NOW, clock=clock)
            self.assertEqual([], state['solar_event_samples'])
            self.assertEqual(reason, state['solar_event_diagnostic']['reason'])

    def test_long_poll_and_restart_gap_do_not_invent_coverage(self):
        state = {}
        for seconds in (0, 30, 60, 180):
            tick = NOW+timedelta(seconds=seconds)
            solar.observe(self.client(tick), self.config, state, tick)
        self.assertIsNone(solar.average(state['solar_event_samples'], tick))
        self.assertEqual(1, len(state['solar_event_samples']))

    def test_diagnostics_do_not_spam_flapping_inputs(self):
        state = {}
        with patch.object(solar.LOGGER, 'info') as log:
            for second in range(300):
                solar.diagnose(state, 'ready' if second % 2 else 'stale_report',
                               NOW+timedelta(seconds=second))
            self.assertEqual(1, log.call_count)
            solar.diagnose(state, 'read_failed', NOW+timedelta(seconds=300))
            self.assertEqual(2, log.call_count)
        self.assertEqual('read_failed', state['solar_event_diagnostic']['reason'])

    def test_grid_notice_uses_completed_observation_not_earlier_loop_clock(self):
        complete = NOW+timedelta(seconds=8)
        config = SimpleNamespace(telemetry_freshness_entity='fresh',
                                 battery_soc_entity='soc', grid_voltage_entity='voltage')
        values = {'fresh': dict(state='fresh'), 'soc': dict(state='60'),
                  'voltage': dict(state='0'),
                  'sensor.energyhub_pv2_telemetry_freshness': dict(state='fresh'),
                  solar.ENTITY: dict(state='800', last_reported=(complete-timedelta(seconds=1)).isoformat()),
                  'binary_sensor.energyhub_grid_confirmed': dict(state='off')}
        state = dict(grid_online=True, grid_candidate=False,
                     grid_candidate_since=(NOW-timedelta(minutes=4)).isoformat(),
                     grid_last_observed_at=(NOW-timedelta(seconds=30)).isoformat(),
                     solar_event_samples=[dict(state=800, last_updated=(complete-timedelta(seconds=300-i*30)).isoformat())
                                          for i in range(10)])
        observe_grid(config, SimpleNamespace(state=values.get), state, NOW, solar_clock=lambda: complete)
        notice = state['pending_notifications'][0]
        self.assertIn('0.8 kW', notice['message'])
        self.assertEqual((NOW-timedelta(minutes=4)).isoformat(), notice['created_at'])


class TechnicalLogTests(unittest.TestCase):
    def row(self, level='ERROR', count=1):
        return dict(name='test.integration', message=['failure'], level=level,
                    timestamp=NOW.timestamp(), count=count)

    def test_severity_escalation_same_timestamp_count_is_delivered(self):
        state = {}; telegram = Mock()
        logs.observe(state, [self.row('WARNING', 3)], NOW)
        logs.deliver(state, telegram, 'technical', NOW)
        logs.observe(state, [self.row('CRITICAL', 3)], NOW)
        self.assertTrue(logs.deliver(state, telegram, 'technical', NOW))
        self.assertIn('CRITICAL', telegram.send_message.call_args.args[1])
        logs.observe(state, [self.row('CRITICAL', 3)], NOW)
        self.assertFalse(logs.deliver(state, telegram, 'technical', NOW))

    def test_grace_does_not_permanently_acknowledge_an_undelivered_error(self):
        state = {}; telegram = Mock()
        logs.observe(state, [self.row()], NOW, boot='a')
        self.assertFalse(logs.deliver(state, telegram, 'technical', NOW))
        later = NOW+timedelta(minutes=5)
        logs.observe(state, [self.row()], later, boot='a')
        self.assertTrue(logs.deliver(state, telegram, 'technical', later))

    def test_boot_rechecks_unacknowledged_critical_after_warning(self):
        state = {}; telegram = Mock()
        logs.observe(state, [self.row('WARNING', 3)], NOW, boot='a')
        logs.deliver(state, telegram, 'technical', NOW)
        logs.observe(state, [self.row('CRITICAL', 3)], NOW, boot='a')
        state = json.loads(json.dumps(state))
        logs.observe(state, [self.row('CRITICAL', 3)], NOW, boot='b')
        self.assertTrue(logs.deliver(state, telegram, 'technical', NOW))

    def test_delivery_expires_queue_without_a_successful_log_poll(self):
        for destination, later in [('technical', NOW+timedelta(days=2)),
                                   ('', NOW+timedelta(days=2)),
                                   ('technical', NOW+timedelta(days=2, hours=11))]:
            state = {}; telegram = Mock()
            logs.observe(state, [self.row()], NOW)
            self.assertTrue(logs.deliver(state, telegram, destination, later))
            self.assertEqual([], state['system_log_monitor']['pending'])
            telegram.send_message.assert_not_called()

    def test_summary_does_not_claim_system_recovered_from_available_data(self):
        state = dict(current_health_at=NOW.isoformat(), current_health={'ha': True},
                     core_log_status={'available': False})
        text = technical_summary.build(state, NOW)
        self.assertIn('Журнал HA недоступний', text)
        self.assertNotIn('Втручання не потрібне', text)
        logs.observe(state, [self.row()], NOW)
        self.assertIn('очікують доставки — 1', technical_summary.build(state, NOW))


class LegacyNoticeTests(unittest.TestCase):
    def test_hp_only_bridge_does_not_make_plugs_missing_or_block_native_status(self):
        config = SimpleNamespace(telemetry_freshness_entity='fresh',
            battery_soc_entity='soc', grid_voltage_entity='voltage',
            solar_forecast_entity='forecast', weather_buffer_entity='reserve',
            house_monitor_enabled=False)
        values = {key: dict(state=value) for key, value in {
            'fresh': 'fresh', 'soc': '80', 'voltage': '230', 'forecast': '9',
            'reserve': 'ready', 'input_boolean.energyhub_load_control_armed': 'on',
            'automation.energyhub_inverter_overload_protection': 'on',
            'input_select.energyhub_overload_phase': 'idle'}.items()}
        health = data_incidents.collect(SimpleNamespace(state=values.get), config, {}, NOW)
        self.assertFalse(health['bridge'])
        self.assertTrue(health['control'])
        self.assertFalse(any(key.startswith('load_') for key in health))

    def test_retired_participant_incidents_do_not_emit_recovery(self):
        state = dict(data_incidents={'load_water_pump': {}, 'bridge': {}},
                     current_health={'load_water_pump': False, 'bridge': True},
                     data_incident_history=[{'key': 'load_water_pump'}, {'key': 'inverter'}])
        retire_zigbee_diagnostics(state)
        self.assertEqual({'bridge'}, set(state['data_incidents']))
        self.assertEqual([{'key': 'inverter'}], state['data_incident_history'])
        self.assertFalse(state.get('pending_notifications'))

    def test_hp_bridge_recovery_never_claims_overload_recovery(self):
        state = dict(data_incidents={'bridge': dict(warned=True, bad_since=None,
            recovered_since=NOW.timestamp()-301, last_seen=NOW.timestamp(), intervals=[])})
        telegram = Mock()
        client = Mock()
        self.assertTrue(data_incidents.deliver(state, telegram,
            SimpleNamespace(technical_chat_id='technical', destination_chat_id='family'), NOW, client))
        client.state.assert_not_called()
        text = telegram.send_message.call_args.args[1]
        self.assertIn('не підтвердження роботи насоса', text)
        self.assertNotIn('перевантаження', text)

    def test_startup_cleanup_preserves_hp_and_charging(self):
        hp = dict(kind='peak_load_guard_load_shed', producer='hp1_battery', message='HP')
        charge = dict(kind='battery_reserve_charging', message='charge')
        state = dict(pending_notifications=[dict(kind='reserve_10'), hp, charge],
                     reserve_warning_offsets=[10],
                     peak_load_attention_pending={'old': {}, 'hp': {'producer': 'hp1_battery'}})
        self.assertTrue(observe_reserve_warnings(None, None, state, NOW))
        self.assertEqual([hp, charge], state['pending_notifications'])
        self.assertEqual({'hp'}, set(state['peak_load_attention_pending']))
        self.assertFalse(observe_reserve_warnings(None, None, state, NOW))

    def test_delivery_rejects_retired_queue_without_client_or_startup(self):
        config = SimpleNamespace(timezone='UTC', destination_chat_id='family')
        state = dict(pending_notifications=[dict(kind=kind, message='obsolete') for kind in
                     ('reserve_10', 'dashboard_control_overload', 'peak_load_guard_load_shed')])
        telegram = Mock()
        self.assertTrue(deliver_pending_notifications(config, telegram, state, NOW))
        self.assertEqual([], state['pending_notifications'])
        telegram.send_message.assert_not_called()
        self.assertFalse(retired_protection_notice(dict(kind='battery_reserve_charging')))


class RestartAndWorkerTests(unittest.TestCase):
    def test_empty_and_corrupt_store_never_share_default_notification_queues(self):
        before = json.dumps(DEFAULT_STATE, sort_keys=True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            store = StateStore(path)
            for content in (None, '{broken', '[]'):
                if content is not None:
                    path.write_text(content, encoding='utf-8')
                first = store.load()
                first['pending_notifications'].append({'message': 'not saved'})
                self.assertEqual([], store.load()['pending_notifications'])
        self.assertEqual(before, json.dumps(DEFAULT_STATE, sort_keys=True))

    def test_saved_queue_and_installed_cursors_survive_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder)/'state.json')
            state = store.load()
            state.update(peak_load_guard_cursors={'stream': 42},
                         pending_notifications=[{'producer': 'hp1_battery', 'message': 'saved'}])
            store.save(state)
            self.assertEqual(state, store.load())

    def test_worker_failure_logs_once_and_recovers_without_claiming_message_delivery(self):
        from app import automation_notifications as notices
        queue, bridge = Mock(), Mock()
        bridge.publish_status.side_effect = [OSError('down'), OSError('down'), None, None]
        worker = NotificationDeliveryWorker(queue, bridge, Mock(), lambda: False)
        worker.stopping = Mock()
        worker.stopping.is_set.side_effect = [False]*4+[True]
        with patch.object(notices.LOGGER, 'warning') as warning, patch.object(notices.LOGGER, 'info') as info:
            worker.run()
        self.assertEqual(1, warning.call_count)
        self.assertEqual(1, info.call_count)
        self.assertEqual(4, queue.deliver_one.call_count)


if __name__ == '__main__':
    unittest.main()
