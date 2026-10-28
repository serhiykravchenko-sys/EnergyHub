from datetime import datetime, timezone
from unittest import TestCase

from app.bms_freshness import latest_primary_report, stamp


class FreshnessTests(TestCase):
    def test_timestamp_boundaries_and_missing_fields(self):
        tick = datetime(2026, 10, 4, tzinfo=timezone.utc).timestamp()
        def readings(age):
            at = datetime.fromtimestamp(tick-age, timezone.utc).isoformat()
            return {key: dict(value=value, reported_at=at)
                    for key, value in dict(soc=50, current=0, voltage=52).items()}
        self.assertIsNotNone(latest_primary_report(readings(90), tick))
        self.assertIsNone(latest_primary_report(readings(90.01), tick))
        self.assertIsNotNone(latest_primary_report(readings(-5), tick))
        self.assertIsNone(latest_primary_report(readings(-5.01), tick))
        rows = readings(0)
        del rows['voltage']
        self.assertIsNone(latest_primary_report(rows, tick))

    def test_invalid_or_naive_timestamps_do_not_prove_freshness(self):
        for value in (None, '', 'bad', '2026-10-04T00:00:00'):
            self.assertIsNone(stamp(value))
        self.assertIsNotNone(stamp('2026-10-04T00:00:00Z'))
