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
        self.now += timedelta(seconds=10)
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

    def test_short_toggle_and_unavailable_do_not_notify(self):
        self.entities[HELPERS['autopilot']]['state'] = 'on'
        observe_controls(self.client, self.state, self.now)
        self.change('autopilot', 'unavailable')
        self.change('autopilot', 'off')
        self.assertEqual([], self.state['pending_notifications'])

    def test_on_without_readiness_does_not_repeat_on_at_recovery(self):
        self.change('overload', 'on')
        self.assertIn('ще не готовий', self.state['pending_notifications'][0]['message'])
        self.ready()
        self.change('overload', 'on')
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('ще не готовий', self.state['pending_notifications'][0]['message'])

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
        self.assertEqual('ready', control_view(self.client, 'overload', self.now))

    def test_off_does_not_claim_restoration(self):
        self.change('overload', 'on')
        self.change('overload', 'off')
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('не відновлюються автоматично', self.state['pending_notifications'][0]['message'])

    def test_smart_heating_and_solar_only_toggles_notify(self):
        self.change('smart_heating', 'on')
        self.change('solar_only', 'on')
        messages = [item['message'] for item in self.state['pending_notifications']]
        self.assertTrue(any('Розумне опалення увімкнено' in message for message in messages))
        self.assertTrue(any('Опалення від сонця увімкнено' in message for message in messages))

    def test_battery_reserve_mode_toggle_notifies(self):
        self.entities[HELPERS['reserve_mode']]['state'] = 'Manual'
        self.state = {}
        observe_controls(self.client, self.state, self.now)
        self.change('reserve_mode', 'Automatic')
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('керує EH', self.state['pending_notifications'][0]['message'])

    def test_smart_heating_runtime_transition_notifies_once(self):
        self.entities[HELPERS['smart_status']]['state'] = 'Manual'
        self.state = {}
        observe_controls(self.client, self.state, self.now)
        self.change('smart_status', 'Eco')
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('Eco', self.state['pending_notifications'][0]['message'])

    def test_quiet_heating_status_is_reported(self):
        self.entities[HELPERS['smart_status']]['state'] = 'Manual'
        self.state = {}
        observe_controls(self.client, self.state, self.now)
        self.change('smart_status', 'Quiet')
        self.assertEqual(1, len(self.state['pending_notifications']))
        self.assertIn('тихий режим', self.state['pending_notifications'][0]['message'])

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
