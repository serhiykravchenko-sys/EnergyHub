import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import patch

from app.co2_monitor import morning_lines
from app.home_assistant import HomeAssistantError
from app.main import fetch_co2_morning_lines
from app.report import build_report


class MorningCo2Tests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 4, 8, tzinfo=ZoneInfo('Europe/Kyiv'))
        self.target = SimpleNamespace(entity='sensor.co2', label='Room <1>', parent='binary_sensor.bridge')
        self.entities = {
            'sensor.co2': dict(entity_id='sensor.co2', state='1100', last_updated=self.now.isoformat()),
            'binary_sensor.bridge': dict(entity_id='binary_sensor.bridge', state='on'),
        }

    def test_current_reading_and_unchanged_urgent_threshold_in_family_report(self):
        lines = morning_lines([self.target], self.entities, self.now)
        self.assertEqual(['🌿 CO₂ — вуглекислий газ: 1100 ppm · макс. за 24 год: дані недоступні'], lines)
        text = build_report(weather_lines=[], solar_forecast=None, solar_window=None,
                            threshold_w=300, consumption=None, snapshot={}, night_import=None,
                            co2_lines=lines)
        self.assertIn(lines[0], text)

    def test_stale_invalid_future_or_parent_off_never_show_cached_ppm(self):
        for value, age, bridge in [('1100', 181, 'on'), ('1100', -6, 'on'),
                                   ('unknown', 0, 'on'), ('nan', 0, 'on'),
                                   ('399', 0, 'on'), ('5001', 0, 'on'), ('1100', 0, 'off')]:
            with self.subTest(value=value, age=age, bridge=bridge):
                self.entities['sensor.co2'].update(state=value, last_updated=(self.now-timedelta(seconds=age)).isoformat())
                self.entities['binary_sensor.bridge']['state'] = bridge
                text = morning_lines([self.target], self.entities, self.now)[0]
                self.assertIn('дані недоступні', text)
                self.assertNotIn('1100 ppm', text)

    def test_multiple_sensors_escape_labels_and_keep_missing_sensor_visible(self):
        second = SimpleNamespace(entity='sensor.second', label='Room &2', parent='')
        text = morning_lines([self.target, second], self.entities, self.now)[0]
        self.assertIn('Room &lt;1&gt; — 1100 ppm', text)
        self.assertIn('Room &amp;2 — дані недоступні', text)
        self.assertNotIn('рекомендоване провітрювання', text)

    def test_report_timestamp_is_actual_capture_time(self):
        when = self.now+timedelta(minutes=1)
        self.assertIn('1100 ppm', morning_lines([self.target], self.entities, when)[0])
        self.assertNotIn('на 08:01', morning_lines([self.target], self.entities, when)[0])

    def test_delivery_reads_one_live_snapshot_without_mutating_alert_episode(self):
        calls = []
        config = SimpleNamespace(co2_sensors=[self.target])
        client = SimpleNamespace(states=lambda: calls.append('read') or list(self.entities.values()))
        self.assertIn('1100 ppm', fetch_co2_morning_lines(config, client, self.now)[0])
        self.entities['sensor.co2']['state'] = '900'
        self.assertIn('900 ppm', fetch_co2_morning_lines(config, client, self.now)[0])
        self.assertEqual(calls, ['read', 'read'])

    def test_ha_failure_reports_unavailable_and_unconfigured_does_not_poll(self):
        def fail():
            raise HomeAssistantError('offline')
        client = SimpleNamespace(states=fail)
        self.assertEqual([], fetch_co2_morning_lines(SimpleNamespace(co2_sensors=[]), client, self.now))
        self.assertIn('дані недоступні', fetch_co2_morning_lines(
            SimpleNamespace(co2_sensors=[self.target]), client, self.now)[0])

    def test_capture_clock_is_read_after_live_snapshot(self):
        order = []
        client = SimpleNamespace(states=lambda: order.append('snapshot') or list(self.entities.values()))
        clock = SimpleNamespace(now=lambda zone: order.append('clock') or self.now)
        config = SimpleNamespace(co2_sensors=[self.target], timezone='Europe/Kyiv')
        with patch('app.main.datetime', clock):
            self.assertIn('1100 ppm', fetch_co2_morning_lines(config, client)[0])
        self.assertEqual(order, ['snapshot', 'clock'])
