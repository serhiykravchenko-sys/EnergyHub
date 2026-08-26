from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest

from app.services.soc_anomaly_journal import (
    SOC_ANOMALY_HISTORY_LIMIT,
    SocAnomalyJournal,
)


class MutableClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class SocAnomalyJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "journal.json"
        self.clock = MutableClock(
            datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        )
        self.journal = SocAnomalyJournal(self.path, self.clock)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def observe(self, soc, **overrides):
        values = {
            "valid": True,
            "soc": soc,
            "battery_voltage": 53.2,
            "charging_current": 12,
            "discharging_current": 0,
            "pv1_power": 1200,
            "pv2_power": 800,
            "total_pv_power": 2000,
            "house_load": 650,
            "grid_available": True,
            "grid_voltage": 229,
            "operating_mode": "solar",
            "telemetry_freshness": "fresh",
        }
        values.update(overrides)
        return self.journal.observe(**values)

    def test_records_five_percent_step_with_full_context(self):
        self.assertFalse(self.observe(50))
        self.clock.now += timedelta(minutes=2)

        self.assertTrue(
            self.observe(55, communication_recovered=True)
        )

        event = self.journal.events[-1]
        self.assertEqual(50, event["previous_soc"])
        self.assertEqual(55, event["current_soc"])
        self.assertEqual(5, event["delta_percent"])
        self.assertEqual(120, event["elapsed_seconds"])
        self.assertEqual(53.2, event["battery_voltage_v"])
        self.assertEqual(2000, event["total_pv_power_w"])
        self.assertTrue(event["communication_recovered"])
        self.assertFalse(event["energyhub_restarted"])
        self.assertEqual(1, self.journal.total_event_count)

    def test_normal_change_and_long_gap_are_not_events(self):
        self.observe(50)
        self.clock.now += timedelta(minutes=4)
        self.assertFalse(self.observe(54.9))
        self.clock.now += timedelta(minutes=6)
        self.assertFalse(self.observe(65))
        self.assertEqual([], self.journal.events)

    def test_invalid_sample_does_not_replace_the_valid_baseline(self):
        self.observe(50)
        self.clock.now += timedelta(minutes=1)
        self.assertFalse(self.journal.observe(valid=False, soc=None))
        self.clock.now += timedelta(minutes=1)
        self.assertTrue(self.observe(55, communication_recovered=True))
        self.assertEqual(120, self.journal.events[-1]["elapsed_seconds"])

    def test_restart_context_uses_persisted_baseline(self):
        self.observe(50)
        self.clock.now += timedelta(minutes=1)
        restarted = SocAnomalyJournal(self.path, self.clock)

        self.assertTrue(restarted.observe(valid=True, soc=55))
        self.assertTrue(restarted.events[-1]["energyhub_restarted"])

    def test_history_is_bounded_while_lifetime_count_increases(self):
        self.observe(0)
        for index in range(SOC_ANOMALY_HISTORY_LIMIT + 5):
            self.clock.now += timedelta(minutes=1)
            self.observe(5 if index % 2 == 0 else 0)

        self.assertEqual(
            SOC_ANOMALY_HISTORY_LIMIT,
            len(self.journal.events),
        )
        self.assertEqual(
            SOC_ANOMALY_HISTORY_LIMIT + 5,
            self.journal.total_event_count,
        )
        with self.path.open("r", encoding="utf-8") as file:
            persisted = json.load(file)
        self.assertEqual(
            SOC_ANOMALY_HISTORY_LIMIT,
            len(persisted["events"]),
        )

    def test_malformed_optional_fields_preserve_valid_event_history(self):
        self.path.write_text(
            json.dumps({
                "events": [{"previous_soc": 50, "current_soc": 55}],
                "total_event_count": "invalid",
                "last_sample": {"timestamp": "invalid", "soc": 55},
                "saved_at": "invalid",
            }),
            encoding="utf-8",
        )

        restored = SocAnomalyJournal(self.path, self.clock)

        self.assertEqual(1, len(restored.events))
        self.assertEqual(1, restored.total_event_count)
        self.assertIsNone(restored.last_sample)


if __name__ == "__main__":
    unittest.main()
