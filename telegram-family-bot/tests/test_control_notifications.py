import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase

from app.control_notifications import HELPERS, observe_controls
from app.main import deliver_pending_notifications


class ControlNotificationsTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 7, 20, tzinfo=timezone.utc)
        self.entities = {entity: {'state': 'off'} for entity in HELPERS.values()}
        self.client = SimpleNamespace(state=lambda key: self.entities.get(key))
        self.state = {}
        observe_controls(self.client, self.state, self.now)

    def change(self, key, value):
        self.entities[HELPERS[key]]['state'] = value
        observe_controls(self.client, self.state, self.now)
        self.now += timedelta(seconds=120 if key in {'quiet', 'eco'} else 10)
        observe_controls(self.client, self.state, self.now)

    def ready(self, **overrides):
        attrs = dict(mode='automatic', automatic_requested=True, armed=True,
                     control_ready=True, eligible_loads=['water_boiler'], fault=None,
                     load_snapshot_at=self.now.isoformat())
        attrs.update(overrides)
        self.entities['sensor.energyhub_peak_load_guard'] = dict(state='normal', attributes=attrs)

    def test_silent_baseline_and_restart_dedup(self):
        self.assertEqual([], self.state['pending_notifications'])
        self.change('autopilot', 'on')
        self.state = copy.deepcopy(self.state)
        observe_controls(self.client, self.state, self.now)
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('увімкнено', self.state['pending_notifications'][0]['message'])

    def test_both_profiles_ignore_flaps_and_require_two_stable_minutes(self):
        for key in ('quiet', 'eco'):
            with self.subTest(profile=key):
                self.state = {}
                self.entities[HELPERS[key]]['state'] = 'off'
                observe_controls(self.client, self.state, self.now)
                for _ in range(4):
                    self.entities[HELPERS[key]]['state'] = 'on'
                    observe_controls(self.client, self.state, self.now)
                    self.now += timedelta(seconds=30)
                    self.entities[HELPERS[key]]['state'] = 'off'
                    observe_controls(self.client, self.state, self.now)
                self.assertEqual([], self.state['pending_notifications'])
                self.entities[HELPERS[key]]['state'] = 'on'
                observe_controls(self.client, self.state, self.now)
                self.now += timedelta(seconds=119)
                observe_controls(self.client, self.state, self.now)
                self.assertEqual([], self.state['pending_notifications'])
                self.now += timedelta(seconds=1)
                self.state = copy.deepcopy(self.state)
                observe_controls(self.client, self.state, self.now)
                self.assertEqual(0, len(self.state['pending_notifications']))
                observe_controls(self.client, self.state, self.now)
                self.assertEqual(0, len(self.state['pending_notifications']))

    def test_short_toggle_and_unavailable_do_not_notify(self):
        self.entities[HELPERS['autopilot']]['state'] = 'on'
        observe_controls(self.client, self.state, self.now)
        self.change('autopilot', 'unavailable')
        self.change('autopilot', 'off')
        self.assertEqual([], self.state['pending_notifications'])

    def test_on_without_readiness_does_not_repeat_on_at_recovery(self):
        self.change('overload', 'on')
        self.ready()
        self.change('overload', 'on')
        self.assertEqual([], self.state['pending_notifications'])

    def test_empty_eligible_fault_stale_and_unarmed_are_not_ready(self):
        from app.control_notifications import control_view
        self.entities[HELPERS['overload']]['state'] = 'on'
        for override in ({'eligible_loads': []}, {'fault': 'uncertain'}, {'armed': False},
                         {'load_snapshot_at': (self.now-timedelta(seconds=91)).isoformat()},
                         {'load_snapshot_at': 'bad'}, {'automatic_requested': False}):
            self.ready(**override)
            self.assertEqual('blocked', control_view(self.client, 'overload', self.now))

    def test_unchanged_sixty_second_heartbeat_remains_ready(self):
        from app.control_notifications import control_view
        self.entities[HELPERS['overload']]['state'] = 'on'
        self.ready(load_snapshot_at=(self.now-timedelta(seconds=75)).isoformat())
        self.entities['automation.energyhub_inverter_overload_protection']={'state':'on'}
        self.entities['input_select.energyhub_overload_phase']={'state':'idle'}
        self.assertEqual('ready', control_view(self.client, 'overload', self.now))

    def test_off_does_not_claim_restoration(self):
        self.change('overload', 'on')
        self.change('overload', 'off')
        self.assertEqual([], self.state['pending_notifications'])

    def test_legacy_heating_toggles_are_silent(self):
        self.change('smart_heating', 'on')
        self.change('solar_only', 'on')
        messages = [item['message'] for item in self.state['pending_notifications']]
        self.assertEqual([], messages)

    def test_smart_policy_one_message_and_no_reserve_claim(self):
        self.entities[HELPERS['climate_policy']]['state'] = 'Off'
        observe_controls(self.client, self.state, self.now)
        self.change('climate_policy', 'Smart')
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('EH керує автоматичною роботою', self.state['pending_notifications'][0]['message'])
        self.assertNotIn('40%', self.state['pending_notifications'][0]['message'])

    def test_battery_reserve_mode_toggle_notifies(self):
        self.entities[HELPERS['reserve_mode']]['state'] = 'Manual'
        self.state = {}
        observe_controls(self.client, self.state, self.now)
        self.change('reserve_mode', 'Automatic')
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('керує EH', self.state['pending_notifications'][0]['message'])

    def test_smart_heating_runtime_transition_notifies_once(self):
        for profile in ('quiet', 'eco'):
            self.change(profile, 'on')
            self.change(profile, 'off')
        self.assertEqual([], self.state['pending_notifications'])

    def test_quiet_heating_status_is_reported(self):
        for profile in ('quiet', 'eco'):
            self.change(profile, 'on')
            self.change(profile, 'off')
        self.assertEqual([], self.state['pending_notifications'])

    def test_profile_off_is_reported_and_normal_status_is_silent(self):
        for profile in ('quiet', 'eco'):
            self.change(profile, 'on')
            self.change(profile, 'off')
        self.assertEqual([], self.state['pending_notifications'])

    def test_upgrade_retires_legacy_queued_messages(self):
        self.state['pending_notifications'] = [dict(kind='dashboard_control_smart_status', message='Normal')]
        observe_controls(self.client, self.state, self.now)
        self.assertEqual([], self.state['pending_notifications'])

    def test_upgrade_rejects_old_short_profile_notification(self):
        from app.control_notifications import queued_control_is_current
        for key in ('quiet', 'eco'):
            item = dict(control_key=key, control_value='on')
            self.entities[HELPERS[key]]['state'] = 'on'
            self.assertFalse(queued_control_is_current(self.client, item, self.now))
            item['profile_stable'] = True
            self.assertFalse(queued_control_is_current(self.client, item, self.now))

    def test_delivery_discards_obsolete_and_sends_current(self):
        self.change('autopilot', 'on')
        self.entities[HELPERS['autopilot']]['state'] = 'off'
        calls = []
        telegram = SimpleNamespace(send_message=lambda *args: calls.append(args))
        config = SimpleNamespace(timezone='Europe/Kyiv', destination_chat_id='test')
        deliver_pending_notifications(config, telegram, self.state, self.now, self.client)
        self.assertEqual([], calls)
        self.change('autopilot', 'off')
        deliver_pending_notifications(config, telegram, self.state, self.now, self.client)
        self.assertEqual(1, len(calls))
        self.assertIn('вимкнено', calls[0][1])

    def test_smart_family_message_continuous_and_scheduled(self):
        self.entities[HELPERS['climate_policy']]['state'] = 'Off'
        observe_controls(self.client, self.state, self.now)
        self.entities['input_select.energyhub_climate_operation'] = {'state': 'Continuous'}
        self.change('climate_policy', 'Smart')
        text = self.state['pending_notifications'][0]['message']
        self.assertIn('Температуру задаєте з пульта', text)
        self.assertIn('без розкладу', text)
        self.assertIn('Off або Solar-only', text)
        self.change('climate_policy', 'Off')
        self.entities['input_select.energyhub_climate_operation']['state'] = 'Scheduled'
        self.entities['input_datetime.energyhub_climate_smart_end'] = {'state': '00:00:00'}
        self.change('climate_policy', 'Smart')
        text = self.state['pending_notifications'][0]['message']
        self.assertIn('до 00:00', text)
        self.assertNotIn('без розкладу', text)

    def test_schedule_end_does_not_claim_future_starts_cancelled(self):
        self.change('climate_policy', 'Smart')
        self.state['pending_notifications'].clear()
        self.change('climate_policy', 'Off')
        self.assertEqual([], self.state['pending_notifications'])
