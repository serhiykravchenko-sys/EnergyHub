from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.main import (
    capture_seven_snapshot,
    due_for_report,
    prepare_morning_report_outbox,
    summarized_night_mode,
    time_minutes,
)


class FakeClient:
    def __init__(self, values):
        self.values = values

    def state(self, entity_id):
        value = self.values.get(entity_id)
        return None if value is None else {"state": str(value), "attributes": {}}


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            send_time="08:00",
            soc_snapshot_time="07:00",
            battery_soc_entity="soc",
            target_soc_entity="target",
            operating_mode_entity="mode",
            yesterday_grid_import_entity="yesterday",
            daily_grid_import_entity="today",
        )
        self.now = datetime(2026, 8, 11, 7, 0, tzinfo=ZoneInfo("Europe/Kyiv"))

    def test_capture_soc_and_cross_midnight_import(self):
        state = {
            "night_baselines": {"2026-08-10": {"value": 5.0}},
            "night_observed_modes": {"2026-08-11": ["solar", "hybrid_charging", "hybrid_grid_hold"]},
        }
        client = FakeClient({"soc": 82, "target": 80, "mode": "solar", "yesterday": 7.0, "today": 5.4})
        self.assertTrue(capture_seven_snapshot(self.config, client, state, self.now))
        self.assertEqual(state["soc_snapshots"]["2026-08-11"]["soc"], 82)
        self.assertEqual(state["soc_snapshots"]["2026-08-11"]["mode"], "hybrid")
        self.assertEqual(state["night_imports"]["2026-08-11"], 7.4)

    def test_incomplete_night_omits_import(self):
        state = {"night_baselines": {}, "night_observed_modes": {}}
        client = FakeClient({"soc": 82, "target": 80, "mode": "solar", "yesterday": 7, "today": 5})
        capture_seven_snapshot(self.config, client, state, self.now)
        self.assertNotIn("2026-08-11", state["night_imports"])

    def test_report_retries_until_marked_delivered(self):
        state = {"last_report_date": None}
        at_eight = self.now.replace(hour=8)
        self.assertTrue(due_for_report(self.config, state, at_eight))
        state["last_report_date"] = "2026-08-11"
        self.assertFalse(due_for_report(self.config, state, at_eight))

    @patch("app.main.create_report", return_value="stable report")
    def test_report_outbox_reuses_the_same_logical_message_after_restart(
        self,
        create_report,
    ):
        at_eight = self.now.replace(hour=8)
        state = {}

        self.assertTrue(prepare_morning_report_outbox(
            self.config, FakeClient({}), state, at_eight
        ))
        self.assertFalse(prepare_morning_report_outbox(
            self.config, FakeClient({}), state, at_eight
        ))
        self.assertEqual("stable report", state["morning_report_outbox"]["message"])
        create_report.assert_called_once()

    def test_mode_priority(self):
        self.assertEqual(summarized_night_mode(["solar", "hybrid_charging"]), "hybrid")
        self.assertEqual(summarized_night_mode(["solar", "panic"]), "panic")

    def test_time_parser_supports_leading_zero(self):
        self.assertEqual(time_minutes("08:00"), 480)

if __name__ == "__main__":
    unittest.main()
