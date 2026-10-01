from datetime import datetime, timedelta, timezone
import unittest
from app.uhmc_morning import morning_status, CLEAR, UNKNOWN


class MorningStatusTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 8, 8, tzinfo=timezone(timedelta(hours=3)))
        self.snapshot = dict(source_status='fresh', observed_at=self.now.isoformat(), warnings=[])

    def test_fresh_empty(self):
        self.assertEqual(CLEAR, morning_status(self.snapshot, self.now))

    def test_clear_status_is_omitted_from_family_report(self):
        from app.report import build_report
        result = build_report(weather_lines=['WEATHER', CLEAR], solar_forecast=None,
            solar_window=None, threshold_w=300, consumption=None, snapshot={},
            night_import=None, astronomy_lines=['ASTRONOMY'])
        self.assertNotIn('УГМЦ', result)
        self.assertLess(result.index('WEATHER'), result.index('ASTRONOMY'))

    def test_stale_unknown_and_missing(self):
        for data in (None, {}, dict(self.snapshot, source_status='unknown'),
                     dict(self.snapshot, observed_at=(self.now-timedelta(minutes=76)).isoformat()),
                     dict(self.snapshot, observed_at=(self.now+timedelta(seconds=1)).isoformat())):
            self.assertEqual(UNKNOWN, morning_status(data, self.now))

    def test_today_level_one_counts(self):
        warning = dict(severity=1, hazards=['severe_precipitation', 'thunderstorm'],
                       valid_from=self.now.isoformat(),
                       valid_until=(self.now+timedelta(hours=10)).isoformat())
        self.assertIn('сильні опади, гроза', morning_status(dict(self.snapshot, warnings=[warning]), self.now))

    def test_tomorrow_does_not_count(self):
        warning = dict(valid_from=(self.now+timedelta(days=1)).isoformat(),
                       valid_until=(self.now+timedelta(days=2)).isoformat())
        self.assertEqual(CLEAR, morning_status(dict(self.snapshot, warnings=[warning]), self.now))

    def test_malformed_never_clear(self):
        for warnings in (None, 'bad', [{}], [None]):
            self.assertEqual(UNKNOWN, morning_status(dict(self.snapshot, warnings=warnings), self.now))

    def test_expired_or_cancelled_does_not_count(self):
        warning = dict(valid_from=(self.now-timedelta(hours=2)).isoformat(),
                       valid_until=(self.now-timedelta(hours=1)).isoformat())
        self.assertEqual(CLEAR, morning_status(dict(self.snapshot, warnings=[warning]), self.now))
        warning.update(active=False, valid_until=(self.now+timedelta(hours=1)).isoformat())
        self.assertEqual(CLEAR, morning_status(dict(self.snapshot, warnings=[warning]), self.now))
