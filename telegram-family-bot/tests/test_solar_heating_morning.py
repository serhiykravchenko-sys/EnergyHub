import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from app.solar_heating_morning import morning_lines
from app.main import fetch_solar_heating_morning_lines
from app.report import build_report
from app.home_assistant import HomeAssistantError


class SolarHeatingMorningTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 5, 8, tzinfo=ZoneInfo('Europe/Kyiv'))

    def forecast(self, values, **changes):
        result = dict(state='12', last_updated=self.now.isoformat(), attributes=dict(detailedHourly=[
            dict(period_start=self.now.replace(hour=hour).isoformat(), pv_estimate=power)
            for hour, power in values]))
        result.update(changes)
        return result

    def lines(self, forecast, **changes):
        args = dict(policy='Solar-only', operation='Continuous', family_mode='heat',
                    forecast=forecast, now=self.now)
        args.update(changes)
        return morning_lines(**args)

    def test_window_uses_start_and_stop_thresholds_in_local_24_hour_time(self):
        lines = self.lines(self.forecast([(9, .5), (10, .6), (11, .5), (12, .4), (13, .399)]))
        self.assertIn('10:00–13:00', lines[1])
        self.assertIn('орієнтовно', lines[1])
        self.assertIn('захисту', lines[2])
        self.assertNotIn('09:00', lines[1])

    def test_low_forecast_is_not_confused_with_missing_stale_or_invalid_data(self):
        self.assertIn('не очікується', self.lines(self.forecast([(10, .5), (11, .3)]))[1])
        for forecast in ({}, self.forecast([], state='unavailable'), self.forecast([]),
                         self.forecast([(10, float('inf'))]), self.forecast([(10, -1)]),
                         self.forecast([(10, 'bad')]), self.forecast([(10, .8)],
                             last_updated=(self.now-timedelta(days=2)).isoformat()),
                         self.forecast([(10, .8)], last_updated=(self.now+timedelta(hours=1)).isoformat()),
                         self.forecast([(10, .8)], attributes={'detailedHourly': 'wrong'})):
            with self.subTest(forecast=forecast):
                self.assertIn('недоступний', self.lines(forecast)[1])
                self.assertNotIn('не очікується', self.lines(forecast)[1])

    def test_gaps_cloud_breaks_and_invalid_slots_do_not_form_one_long_window(self):
        for values in ([(10, 1), (11, .2), (12, 1)], [(10, 1), (12, 1)],
                       [(10, 1), (11, 'bad'), (12, 1)]):
            with self.subTest(values=values):
                text = self.lines(self.forecast(values))[1]
                self.assertIn('10:00–11:00, 12:00–13:00', text)
                self.assertNotIn('10:00–13:00', text)

    def test_only_solar_continuous_and_cooling_label(self):
        forecast = self.forecast([(10, 1)])
        for policy, operation in [('Smart', 'Continuous'), ('Off', 'Continuous'),
                                  ('Solar-only', 'Scheduled'), ('unavailable', 'Continuous')]:
            self.assertEqual([], self.lines(forecast, policy=policy, operation=operation))
        self.assertIn('охолодження', self.lines(forecast, family_mode='cool')[0])

    def test_half_hour_intervals_utc_dates_and_remaining_today(self):
        entries = [dict(period_start='2026-10-05T07:00:00Z', pv_estimate=.8),
                   dict(period_start='2026-10-05T07:30:00Z', pv_estimate=.5),
                   dict(period_start='2026-10-05T08:00:00Z', pv_estimate=.3),
                   dict(period_start='2026-10-06T07:00:00Z', pv_estimate=1)]
        forecast = self.forecast([], attributes={'detailedHourly': entries})
        self.assertIn('10:00–11:00', self.lines(forecast)[1])
        self.assertIn('10:15–11:00', self.lines(forecast, now=self.now.replace(hour=10, minute=15))[1])
        self.assertIn('недоступний', self.lines(forecast, now=self.now.replace(hour=18))[1])

    def test_live_policy_reads_and_family_report_insertion(self):
        client = Mock()
        client.state.side_effect = lambda entity: {'state': {
            'input_select.energyhub_climate_policy': 'Solar-only',
            'input_select.energyhub_climate_operation': 'Continuous',
            'input_number.energyhub_solar_start_power': '600',
            'input_number.energyhub_solar_pause_power': '400',
            'input_select.energyhub_hp1_family_mode': 'heat'}[entity]}
        lines = fetch_solar_heating_morning_lines(client, self.forecast([(10, 1)]), self.now)
        text = build_report(weather_lines=[], solar_forecast=None, solar_window=None,
                            threshold_w=300, consumption=None, snapshot={}, night_import=None,
                            solar_heating_lines=lines)
        self.assertIn('Сонячне опалення увімкнено', text)
        self.assertIn('10:00–11:00', text)
        client.state.side_effect = HomeAssistantError('offline')
        self.assertEqual([], fetch_solar_heating_morning_lines(client, {}, self.now))
