from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.events import (
    confidence_message,
    format_duration,
    heat_pump_management_message,
    outage_message,
    recovery_message,
    reserve_warning_message,
)
from app.main import (
    active_heat_pumps,
    deliver_pending_notifications,
    observe_grid,
    observe_grid_confidence,
    observe_reserve_warnings,
    refresh_queued_reserve_warning,
    reserve_warning_quiet_hours,
)


TZ = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 8, 12, 10, 0, tzinfo=TZ)


class FakeClient:
    def __init__(self, values):
        self.values = values

    def state(self, entity_id):
        value = self.values.get(entity_id)
        return None if value is None else {"state": str(value), "attributes": {}}


class FakeTelegram:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def send_message(self, chat_id, message):
        if self.fail:
            raise RuntimeError("offline")
        self.messages.append((chat_id, message))


class EventFormattingTests(unittest.TestCase):
    def test_duration_wording(self):
        self.assertEqual("1 год", format_duration(3600))
        self.assertEqual("1 год 15 хв", format_duration(4500))
        self.assertEqual("5 хв", format_duration(300))

    def test_messages_use_correct_reserve_term(self):
        self.assertIn("Початок відключення: 10:00", outage_message(NOW, 76))
        self.assertIn("Без мережі: 1 год", recovery_message(NOW + timedelta(hours=1), NOW, 68))
        message = confidence_message("normal", "panic")
        self.assertIn("Надійність мережі погіршилась", message)
        self.assertIn("Grid Confidence: Normal → Panic", message)
        self.assertIn("Цільовий запас батареї вдень: 20% → 95%", message)

        improved = confidence_message("unstable", "normal")
        self.assertIn("Надійність мережі покращилась", improved)
        self.assertIn("Цільовий запас батареї вдень: 60% → 20%", improved)
        self.assertIn("може використовувати більшу частину батареї", improved)

    def test_heat_pump_management_names_the_current_owner(self):
        manual = heat_pump_management_message(
            confidence="normal",
            voltage=230,
            freshness="fresh",
            minimum_soc=20,
        )
        self.assertIn("РУЧНЕ КЕРУВАННЯ", manual)
        self.assertIn("Родина", manual)

        protected = heat_pump_management_message(
            confidence="risk",
            voltage=230,
            freshness="fresh",
            minimum_soc=30,
        )
        self.assertIn("ЗАХИСТ ENERGYHUB", protected)
        self.assertIn("60%", protected)
        self.assertIn("50%", protected)
        self.assertIn("70%", protected)

        waiting = heat_pump_management_message(
            confidence="normal",
            voltage=230,
            freshness="stale",
            minimum_soc=20,
        )
        self.assertIn("ОЧІКУВАННЯ", waiting)
        self.assertIn("не надсилає нових команд", waiting)

    def test_grid_voltage_must_exceed_inverter_presence_threshold(self):
        message = heat_pump_management_message(
            confidence="normal",
            voltage=120,
            freshness="fresh",
            minimum_soc=20,
        )

        self.assertIn("ЗАХИСТ ENERGYHUB", message)

    def test_reserve_warning_explains_manual_or_protected_policy(self):
        manual = reserve_warning_message(
            soc=50,
            minimum_soc=20,
            offset=30,
            confidence="normal",
            voltage=230,
            freshness="fresh",
            active_heat_pumps=[("1-му", 742)],
        )
        self.assertIn("керує родина", manual)
        self.assertIn("1-му поверсі", manual)
        self.assertIn("742 Вт", manual)

        protected = reserve_warning_message(
            soc=40,
            minimum_soc=20,
            offset=20,
            confidence="unstable",
            voltage=230,
            freshness="fresh",
            active_heat_pumps=[("2-му", 815), ("3-му", 603)],
        )
        self.assertIn("заблоковані", protected)
        self.assertIn("60%", protected)
        self.assertIn("2-му поверсі", protected)
        self.assertIn("3-му поверсі", protected)


class EventObservationTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            grid_voltage_entity="voltage",
            grid_confidence_entity="confidence",
            battery_soc_entity="soc",
            destination_chat_id="-1",
            ahm_minimum_soc_entity="minimum",
            telemetry_freshness_entity="freshness",
            heat_pump_active_threshold_w=50,
            heat_pump_floor_1_power_entity="hp1",
            heat_pump_floor_2_power_entity="hp2",
            heat_pump_floor_3_power_entity="hp3",
            timezone="Europe/Kyiv",
        )

    def test_grid_loss_and_recovery_are_debounced_and_duration_persists(self):
        state = {}
        client = FakeClient({"voltage": 230, "soc": 80})
        self.assertTrue(observe_grid(self.config, client, state, NOW))
        self.assertEqual([], state["pending_notifications"])

        client.values["voltage"] = 0
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(minutes=1)))
        self.assertEqual([], state["pending_notifications"])
        self.assertFalse(observe_grid(self.config, client, state, NOW + timedelta(minutes=1, seconds=20)))
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(minutes=1, seconds=30)))
        self.assertEqual("grid_lost", state["pending_notifications"][0]["kind"])

        client.values.update({"voltage": 230, "soc": 72})
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(hours=1)))
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(hours=1, seconds=30)))
        recovery = state["pending_notifications"][1]["message"]
        self.assertIn("Без мережі: 59 хв", recovery)
        self.assertIn("SOC: 72%", recovery)

    def test_starting_offline_initializes_without_false_alert(self):
        state = {}
        client = FakeClient({"voltage": 0, "soc": 50})
        observe_grid(self.config, client, state, NOW)
        self.assertFalse(state["grid_online"])
        self.assertEqual([], state["pending_notifications"])
        self.assertEqual(NOW.isoformat(), state["outage_started_at"])

    def test_confidence_initialization_is_silent_then_transition_queues(self):
        state = {}
        client = FakeClient({"confidence": "normal"})
        self.assertTrue(observe_grid_confidence(self.config, client, state, NOW))
        self.assertEqual([], state["pending_notifications"])
        client.values["confidence"] = "panic"
        self.assertTrue(observe_grid_confidence(self.config, client, state, NOW + timedelta(minutes=1)))
        self.assertEqual("grid_confidence", state["pending_notifications"][0]["kind"])

    def test_invalid_confidence_is_ignored(self):
        state = {"grid_confidence": "normal"}
        client = FakeClient({"confidence": "unavailable"})
        self.assertFalse(observe_grid_confidence(self.config, client, state, NOW))
        self.assertEqual("normal", state["grid_confidence"])

    def test_reserve_warnings_follow_selected_minimum_and_do_not_repeat(self):
        state = {}
        client = FakeClient({
            "soc": 70,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "fresh",
            "hp1": 700,
        })
        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, NOW
        ))
        self.assertEqual([], state["pending_notifications"])

        client.values["soc"] = 50
        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=1)
        ))
        self.assertEqual("reserve_30", state["pending_notifications"][-1]["kind"])

        client.values["soc"] = 49
        self.assertFalse(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=2)
        ))

        client.values["soc"] = 40
        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=3)
        ))
        self.assertEqual("reserve_20", state["pending_notifications"][-1]["kind"])

    def test_reserve_warning_rearms_after_two_percent_recovery(self):
        state = {}
        client = FakeClient({
            "soc": 60,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "fresh",
            "hp1": 700,
        })
        observe_reserve_warnings(self.config, client, state, NOW)
        client.values["soc"] = 50
        observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=1)
        )
        client.values["soc"] = 52
        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=2)
        ))
        client.values["soc"] = 50
        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=3)
        ))
        self.assertEqual(2, len(state["pending_notifications"]))

    def test_stale_telemetry_does_not_create_reserve_warning(self):
        state = {}
        client = FakeClient({
            "soc": 20,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "stale",
            "hp1": 700,
        })
        self.assertFalse(observe_reserve_warnings(
            self.config, client, state, NOW
        ))
        self.assertEqual([], state["pending_notifications"])

    def test_reserve_warning_requires_heat_pump_above_50_watts(self):
        state = {}
        client = FakeClient({
            "soc": 70,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "fresh",
            "hp1": 50,
            "hp2": 12,
            "hp3": 0,
        })
        observe_reserve_warnings(self.config, client, state, NOW)

        client.values["soc"] = 50
        self.assertFalse(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=1)
        ))
        self.assertEqual([], state["pending_notifications"])

        client.values["hp2"] = 650
        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=2)
        ))
        message = state["pending_notifications"][0]["message"]
        self.assertIn("2-му поверсі", message)
        self.assertIn("650 Вт", message)

    def test_reserve_warning_is_suppressed_through_0801(self):
        state = {}
        client = FakeClient({
            "soc": 70,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "fresh",
            "hp1": 700,
        })
        before_midnight = NOW.replace(hour=23, minute=59)
        observe_reserve_warnings(self.config, client, state, before_midnight)
        client.values["soc"] = 50

        at_0801 = (NOW + timedelta(days=1)).replace(hour=8, minute=1)
        self.assertTrue(reserve_warning_quiet_hours(at_0801))
        self.assertFalse(observe_reserve_warnings(
            self.config, client, state, at_0801
        ))
        self.assertEqual([], state["pending_notifications"])

        at_0802 = at_0801.replace(minute=2)
        self.assertFalse(reserve_warning_quiet_hours(at_0802))
        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, at_0802
        ))
        self.assertEqual("reserve_30", state["pending_notifications"][0]["kind"])

    def test_active_heat_pumps_reports_every_floor_above_threshold(self):
        client = FakeClient({"hp1": 51, "hp2": 50, "hp3": 824.4})
        self.assertEqual(
            [("1-му", 51.0), ("3-му", 824.4)],
            active_heat_pumps(self.config, client),
        )

    def test_night_delivery_defers_reserve_but_sends_grid_event(self):
        night = NOW.replace(hour=1, minute=51)
        state = {"pending_notifications": [
            {"kind": "reserve_30", "message": "reserve", "created_at": night.isoformat()},
            {"kind": "grid_lost", "message": "grid", "created_at": night.isoformat()},
        ]}
        telegram = FakeTelegram()

        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, night
        ))
        self.assertEqual([("-1", "grid")], telegram.messages)
        self.assertEqual("reserve_30", state["pending_notifications"][0]["kind"])

    def test_delayed_reserve_warning_refreshes_power_before_delivery(self):
        client = FakeClient({
            "soc": 49,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "fresh",
            "hp1": 823,
        })
        action, message = refresh_queued_reserve_warning(
            self.config, client, "reserve_30"
        )
        self.assertEqual("send", action)
        self.assertIn("SOC знизився до 49%", message)
        self.assertIn("823 Вт", message)

        state = {"pending_notifications": [{
            "kind": "reserve_30",
            "message": "stale message",
            "created_at": NOW.isoformat(),
        }]}
        telegram = FakeTelegram()
        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, NOW, client
        ))
        self.assertIn("823 Вт", telegram.messages[0][1])

    def test_delayed_reserve_warning_waits_for_pump_and_drops_after_recovery(self):
        client = FakeClient({
            "soc": 49,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "fresh",
            "hp1": 0,
        })
        self.assertEqual(
            ("defer", None),
            refresh_queued_reserve_warning(self.config, client, "reserve_30"),
        )

        client.values["soc"] = 53
        self.assertEqual(
            ("drop", None),
            refresh_queued_reserve_warning(self.config, client, "reserve_30"),
        )

    def test_delivery_removes_only_successfully_sent_items(self):
        state = {"pending_notifications": [{"kind": "grid_lost", "message": "alert", "created_at": NOW.isoformat()}]}
        telegram = FakeTelegram()
        self.assertTrue(deliver_pending_notifications(self.config, telegram, state))
        self.assertEqual([], state["pending_notifications"])
        self.assertEqual("alert", telegram.messages[0][1])

        state["pending_notifications"] = [{"kind": "grid_lost", "message": "retry", "created_at": NOW.isoformat()}]
        with self.assertRaises(RuntimeError):
            deliver_pending_notifications(self.config, FakeTelegram(fail=True), state)
        self.assertEqual("retry", state["pending_notifications"][0]["message"])


if __name__ == "__main__":
    unittest.main()
