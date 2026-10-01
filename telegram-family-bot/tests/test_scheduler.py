from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import mock_open, patch
from zoneinfo import ZoneInfo

from app.main import (
    acknowledge_overnight_family_events,
    acknowledge_soc_anomaly_report,
    clean_old_state,
    due_for_report,
    prepare_morning_report_outbox,
    time_minutes,
)
from app.config import load_config


class FakeClient:
    def __init__(self, values):
        self.values = values

    def state(self, entity_id):
        value = self.values.get(entity_id)
        return None if value is None else {"state": str(value), "attributes": {}}

    def error_log(self):
        return ""


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            send_time="08:00",
            destination_chat_id="family",
            technical_chat_id="technical",
            battery_soc_entity="soc",
            operating_mode_entity="mode",
            yesterday_grid_import_entity="yesterday",
            daily_grid_import_entity="today",
        )
        self.now = datetime(2026, 8, 11, 7, 0, tzinfo=ZoneInfo("Europe/Kyiv"))

    def test_legacy_seven_oclock_state_is_removed(self):
        state = {
            "soc_snapshots": {"2026-08-11": {"soc": 82}},
            "night_baselines": {"2026-08-10": {"value": 5.0}},
            "night_imports": {"2026-08-11": 7.4},
            "night_observed_modes": {"2026-08-11": ["solar"]},
        }
        clean_old_state(state, self.now)
        for key in (
            "soc_snapshots",
            "night_baselines",
            "night_imports",
            "night_observed_modes",
        ):
            self.assertNotIn(key, state)

    def test_report_retries_until_marked_delivered(self):
        state = {"last_report_date": None}
        at_eight = self.now.replace(hour=8)
        self.assertTrue(due_for_report(self.config, state, at_eight))
        state["last_report_date"] = "2026-08-11"
        self.assertFalse(due_for_report(self.config, state, at_eight))

    @patch("app.main.create_reports", return_value=("technical report", "stable report"))
    def test_report_outbox_reuses_the_same_logical_message_after_restart(
        self,
        create_report,
    ):
        at_eight = self.now.replace(hour=8)
        state = {
            "soc_anomaly_report_events": [
                {
                    "timestamp": "2026-08-31T06:56:19+00:00",
                    "previous_soc": 70,
                    "current_soc": 100,
                }
            ],
            "overnight_family_events": [{
                "kind": "grid_hold_started",
                "created_at": "2026-08-11T00:50:00+03:00",
                "message": "hold",
            }],
        }

        self.assertTrue(prepare_morning_report_outbox(
            self.config, FakeClient({}), state, at_eight
        ))
        self.assertFalse(prepare_morning_report_outbox(
            self.config, FakeClient({}), state, at_eight
        ))
        self.assertEqual("stable report", state["morning_report_outbox"]["message"])
        self.assertEqual(
            ["technical report", "stable report"],
            state["morning_report_outbox"]["messages"],
        )
        self.assertEqual(
            ["technical", "family"],
            state["morning_report_outbox"]["destinations"],
        )
        self.assertEqual(0, state["morning_report_outbox"]["next_message_index"])
        self.assertEqual(
            ["2026-08-31T06:56:19+00:00|70|100"],
            state["morning_report_outbox"]["soc_anomaly_event_ids"],
        )
        self.assertEqual(
            ["grid_hold_started|2026-08-11T00:50:00+03:00|hold"],
            state["morning_report_outbox"]["overnight_family_event_ids"],
        )
        create_report.assert_called_once()

    def test_delayed_report_dates_the_fault_status_observed_before_recovery(self):
        with patch.object(Path, "open", mock_open(read_data="{}")):
            config = load_config(Path("unused-options.json"))
        client = FakeClient({config.operating_mode_entity: "transition_failed",
                             config.telemetry_freshness_entity: "fresh"})
        at_eight = self.now.replace(hour=8)
        state = {"overnight_family_events": [{
            "kind": "technical_inverter_strategy_fault",
            "created_at": self.now.replace(hour=1).isoformat(),
            "message": "The fault was observed overnight",
        }]}
        with patch("app.main.fetch_weather", return_value=[]):
            self.assertTrue(prepare_morning_report_outbox(
                config, client, state, at_eight))
            state = deepcopy(state)  # Restore the saved outbox after a restart.
            client.values[config.operating_mode_entity] = "solar"
            self.assertFalse(prepare_morning_report_outbox(
                config, client, state, at_eight.replace(hour=9)))
        saved = state["morning_report_outbox"]["message"]
        self.assertIn("станом на 08:00 автоматичне керування резервом було призупинене", saved)
        self.assertNotIn("зараз автоматичне керування резервом призупинене", saved)

    def test_report_acknowledgement_preserves_events_arriving_during_delivery(self):
        first = {
            "timestamp": "2026-08-31T06:00:00+00:00",
            "previous_soc": 45,
            "current_soc": 51,
        }
        second = {
            "timestamp": "2026-08-31T06:56:19+00:00",
            "previous_soc": 70,
            "current_soc": 100,
        }
        state = {"soc_anomaly_report_events": [first, second]}
        acknowledge_soc_anomaly_report(
            state,
            ["2026-08-31T06:00:00+00:00|45|51"],
        )
        self.assertEqual([second], state["soc_anomaly_report_events"])

    def test_overnight_acknowledgement_preserves_later_events(self):
        first = {"kind": "grid_hold_started", "created_at": "a", "message": "one"}
        second = {"kind": "grid_hold_released", "created_at": "b", "message": "two"}
        state = {"overnight_family_events": [first, second]}
        acknowledge_overnight_family_events(
            state,
            ["grid_hold_started|a|one"],
        )
        self.assertEqual([second], state["overnight_family_events"])

    def test_time_parser_supports_leading_zero(self):
        self.assertEqual(time_minutes("08:00"), 480)

if __name__ == "__main__":
    unittest.main()
