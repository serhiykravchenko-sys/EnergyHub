from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import unittest

from app.services.inverter_fault_journal import (
    INVERTER_PREFAULT_SAMPLE_LIMIT,
    InverterFaultJournal,
    active_qpiws_messages,
)


class Clock:
    def __init__(self):
        self.now = datetime.fromisoformat("2026-08-21T21:00:00+03:00")

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class InverterFaultJournalTests(unittest.TestCase):
    def test_filters_metadata_and_orders_active_messages(self):
        self.assertEqual(
            ["battery_low", "over_load"],
            active_qpiws_messages({
                "over_load": "1", "battery_low": 1,
                "reserved": "1", "fan_locked": "0",
                "_command": "QPIWS",
            }),
        )

    def test_records_one_incident_and_later_recovery(self):
        clock = Clock()
        journal = InverterFaultJournal(path=None, clock=clock)
        journal.observe_telemetry(
            valid=True, load_w=9100, load_percent=91,
            battery_soc=54, grid_available=False, operating_mode="solar",
        )
        self.assertTrue(journal.observe_qpiws({"over_load": "1"}))
        self.assertFalse(journal.observe_qpiws({"over_load": "1"}))
        clock.advance(48)
        self.assertTrue(journal.observe_qpiws({"over_load": "0"}))

        event = journal.recent_event(1)
        self.assertEqual(["over_load"], event["messages"])
        self.assertEqual("warning_cleared", event["recovery"])
        self.assertEqual(48, event["duration_seconds"])
        self.assertEqual(9100, event["latest_conditions"]["load_w"])
        self.assertFalse(event["latest_conditions"]["grid_available"])

    def test_empty_read_does_not_clear_an_active_incident(self):
        journal = InverterFaultJournal(path=None, clock=Clock())
        journal.observe_qpiws({"over_load": "1"})

        self.assertFalse(journal.observe_qpiws({}))
        self.assertEqual(["over_load"], journal.active_messages)
        self.assertIsNone(journal.recent_event(1)["cleared_at"])

    def test_direct_fault_change_marks_prior_incident_superseded(self):
        clock = Clock()
        journal = InverterFaultJournal(path=None, clock=clock)
        journal.observe_qpiws({"over_load": "1"})
        clock.advance(12)

        journal.observe_qpiws({"fan_locked": "1"})

        previous = journal.recent_event(2)
        self.assertEqual("superseded", previous["recovery"])
        self.assertEqual(12, previous["duration_seconds"])
        self.assertEqual("active", journal.recent_event(1)["recovery"])

    def test_expected_pv_loss_is_retained_but_hidden_from_dashboard(self):
        journal = InverterFaultJournal(path=None, clock=Clock())
        journal.observe_qpiws({"pv_loss_warning": "1"})

        self.assertEqual(1, len(journal.events))
        self.assertEqual(["pv_loss_warning"], journal.events[0]["messages"])
        self.assertEqual("Normal", journal.current_state())
        self.assertEqual("No incident", journal.event_state(1))
        self.assertIsNone(journal.event_attributes(1)["event"])

    def test_dashboard_skips_pv_loss_and_keeps_mixed_real_warning(self):
        clock = Clock()
        journal = InverterFaultJournal(path=None, clock=clock)
        journal.observe_qpiws({"over_load": "1"})
        clock.advance(10)
        journal.observe_qpiws({"pv_loss_warning": "1"})
        clock.advance(10)
        journal.observe_qpiws({
            "pv_loss_warning": "1",
            "fan_locked": "1",
        })

        self.assertEqual("Fan Locked", journal.event_state(1))
        self.assertEqual("Over Load", journal.event_state(2))
        self.assertEqual("No incident", journal.event_state(3))
        self.assertEqual(["fan_locked"], journal.recent_event(1)["messages"])

    def test_bounds_telemetry_and_persisted_history(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "faults.json"
            journal = InverterFaultJournal(path=path, clock=clock)
            for value in range(INVERTER_PREFAULT_SAMPLE_LIMIT + 4):
                journal.observe_telemetry(valid=True, load_w=value)
                clock.advance(10)
            journal.observe_qpiws({"fan_locked": "1"})

            stored = json.loads(path.read_text(encoding="utf-8"))
            samples = stored["events"][-1]["pre_fault_samples"]
            self.assertEqual(INVERTER_PREFAULT_SAMPLE_LIMIT, len(samples))
            self.assertEqual(4, samples[0]["load_w"])

            restored = InverterFaultJournal(path=path, clock=clock)
            self.assertEqual(["fan_locked"], restored.active_messages)
            self.assertEqual(1, restored.total_event_count)

    def test_invalid_optional_counter_does_not_discard_valid_history(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "faults.json"
            path.write_text(
                json.dumps({
                    "events": [{
                        "started_at": clock.now.isoformat(),
                        "messages": ["over_load"],
                        "recovery": "active",
                    }],
                    "total_event_count": "not-a-number",
                    "active_messages": ["over_load"],
                }),
                encoding="utf-8",
            )

            restored = InverterFaultJournal(path=path, clock=clock)

            self.assertEqual(1, len(restored.events))
            self.assertEqual(1, restored.total_event_count)
            self.assertEqual(["over_load"], restored.active_messages)


if __name__ == "__main__":
    unittest.main()
