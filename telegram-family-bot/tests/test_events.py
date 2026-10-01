from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.events import (
    confidence_message,
    format_duration,
    heat_pump_management_message,
    heat_pump_restart_restored_message,
    outage_message,
    peak_load_guard_message,
    recovery_message,
    reserve_warning_message,
    soc_anomaly_message,
    soc_anomaly_report_lines,
    weather_warning_message,
)
from app.main import (
    active_heat_pumps,
    deliver_pending_notifications,
    observe_grid,
    observe_grid_hold,
    observe_grid_confidence,
    observe_heat_pump_restart_restore,
    observe_inverter_strategy_fault,
    observe_safely,
    observe_peak_load_guard,
    observe_reserve_warnings,
    observe_soc_anomaly,
    observe_weather_warnings,
    refresh_queued_reserve_warning,
    reserve_warning_quiet_hours,
)
from app.report import overnight_family_event_lines


TZ = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 8, 12, 10, 0, tzinfo=TZ)


class FakeClient:
    def __init__(self, values):
        self.values = values

    def state(self, entity_id):
        value = self.values.get(entity_id)
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        return {"state": str(value), "attributes": {}}


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
        self.assertIn("Без ДТЕК: 1 год", recovery_message(NOW + timedelta(hours=1), NOW, 68))
        message = confidence_message(
            "normal", "panic",
            {"management_mode": "automatic", "control_applied": True,
             "applied_minimum_soc": 95, "recommended_soc": 95},
            20,
        )
        self.assertIn("Надійність ДТЕК погіршилась", message)
        self.assertIn("Нормальна → Критична", message)
        self.assertIn("20% → 95%", message)

        improved = confidence_message(
            "unstable", "normal",
            {"management_mode": "manual", "recommended_soc": 20},
            40,
        )
        self.assertIn("Надійність ДТЕК покращилась", improved)
        self.assertIn("Ручне керування", improved)
        self.assertNotIn("Цільовий запас батареї вдень", improved)

    def test_peak_load_guard_messages_are_ukrainian_and_explicitly_dry_run(self):
        shed = peak_load_guard_message({
            "type": "shed_recommended",
            "trigger_load_percent": 40,
            "thresholds": {
                "shed_percent": 40,
                "relief_percent": 30,
                "restore_percent": 20,
            },
            "recommended_loads": [
                {"key": "water_pump"},
                {"key": "water_boiler"},
            ],
        })
        self.assertIn("EnergyHub рекомендує", shed)
        self.assertIn("водяний насос", shed)
        self.assertIn("бойлер", shed)
        self.assertIn("30%", shed)
        self.assertIn("20%", shed)
        self.assertIn("нічого не перемикав", shed)

        restored = peak_load_guard_message({
            "type": "restore_recommended",
            "recovery_load_percent": 20,
            "thresholds": {"relief_percent": 30, "restore_percent": 20},
            "restore_order": [
                {"key": "water_pump"},
                {"key": "water_boiler"},
            ],
        })
        self.assertIn("відновити початкові стани", restored)
        self.assertLess(restored.index("водяний насос"), restored.index("бойлер"))
        self.assertIn("цикл Dry Run завершено", restored)

    def test_soc_anomaly_message_is_short_without_diagnostic_context(self):
        message = soc_anomaly_message({
            "timestamp": "2026-08-31T06:56:19+00:00",
            "previous_soc": 70,
            "current_soc": 100,
            "delta_percent": 30,
            "elapsed_seconds": 12,
            "battery_voltage_v": 55.4,
            "charging_current_a": 81,
            "discharging_current_a": 0,
            "total_pv_power_w": 6100,
            "house_load_w": 700,
            "operating_mode": "solar",
            "telemetry_freshness": "fresh",
        }, TZ)
        self.assertIn("Стрибок показника заряду батареї", message)
        self.assertIn("70% → 100% за 12 с", message)
        self.assertNotIn("напруга", message)
        self.assertNotIn("PV", message)
        self.assertNotIn("SOC", message)
        self.assertLessEqual(len(message.splitlines()), 4)

    def test_soc_anomaly_report_summarizes_largest_event(self):
        lines = soc_anomaly_report_lines([
            {
                "timestamp": "2026-08-31T06:00:00+00:00",
                "previous_soc": 45,
                "current_soc": 51,
                "delta_percent": 6,
            },
            {
                "timestamp": "2026-08-31T06:56:19+00:00",
                "previous_soc": 70,
                "current_soc": 100,
                "delta_percent": 30,
            },
        ], TZ)
        self.assertEqual(1, len(lines))
        self.assertIn("Стрибок показника заряду батареї: <b>70% → 100%</b> о 09:56", lines[0])
        self.assertIn("Лише для інформації", lines[0])
        self.assertNotIn("09:56:19", lines[0])

    def test_heat_pump_management_names_the_current_owner(self):
        manual = heat_pump_management_message(
            confidence="normal",
            voltage=230,
            freshness="fresh",
            minimum_soc=20,
        )
        self.assertIn("ручне керування", manual)
        self.assertEqual("♨️ Теплові насоси: <b>ручне керування</b>.", manual)

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
            weather_buffer_entity="reserve",
            battery_soc_entity="soc",
            destination_chat_id="-1",
            technical_chat_id="-2",
            ahm_minimum_soc_entity="minimum",
            operating_mode_entity="mode",
            telemetry_freshness_entity="freshness",
            peak_load_guard_event_entity="guard_event",
            heat_pump_restart_event_entity="restart_event",
            soc_anomaly_latest_entity="soc_anomaly",
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
        self.assertEqual([], state.get("pending_notifications", []))

        client.values["voltage"] = 0
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(minutes=1)))
        self.assertEqual([], state["pending_notifications"])
        self.assertFalse(observe_grid(self.config, client, state, NOW + timedelta(minutes=1, seconds=59)))
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(minutes=2)))
        self.assertEqual("grid_lost", state["pending_notifications"][0]["kind"])

        client.values.update({"voltage": 230, "soc": 72})
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(hours=1)))
        self.assertFalse(observe_grid(self.config, client, state, NOW + timedelta(hours=1, seconds=59)))
        self.assertTrue(observe_grid(self.config, client, state, NOW + timedelta(hours=1, minutes=1)))
        recovery = state["pending_notifications"][1]["message"]
        self.assertIn("Без ДТЕК: 59 хв", recovery)
        self.assertIn("Заряд батареї: 72%", recovery)

    def test_starting_offline_notifies_after_debounce(self):
        state = {}
        client = FakeClient({"voltage": 0, "soc": 50})
        observe_grid(self.config, client, state, NOW)
        self.assertIsNone(state.get("grid_online"))
        self.assertEqual([], state["pending_notifications"])
        self.assertFalse(observe_grid(
            self.config, client, state, NOW + timedelta(seconds=20)))
        self.assertFalse(observe_grid(
            self.config, client, state, NOW + timedelta(seconds=59)))
        self.assertTrue(observe_grid(
            self.config, client, state, NOW + timedelta(seconds=60)))
        self.assertFalse(state["grid_online"])
        self.assertEqual("grid_lost", state["pending_notifications"][0]["kind"])
        self.assertEqual(NOW.isoformat(), state["outage_started_at"])

    def test_grid_hold_transition_reports_dynamic_release_threshold(self):
        state = {}
        client = FakeClient({"mode": "solar", "voltage": 230, "soc": 24,
                             "minimum": 20, "freshness": "fresh"})
        self.assertTrue(observe_grid_hold(self.config, client, state, NOW))
        client.values["mode"] = "panic_grid_hold"
        self.assertTrue(observe_grid_hold(
            self.config, client, state, NOW + timedelta(seconds=1)))
        self.assertTrue(observe_grid_hold(
            self.config, client, state, NOW + timedelta(seconds=11)))
        message = state["pending_notifications"][0]
        self.assertEqual("grid_hold_started", message["kind"])
        self.assertIn("Резерв <b>20%</b>", message["message"])
        self.assertIn("режим сонце + ДТЕК", message["message"])
        self.assertIn("при <b>30%</b>", message["message"])

        state["pending_notifications"].clear()
        client.values.update({"mode": "solar", "soc": 31})
        self.assertTrue(observe_grid_hold(
            self.config, client, state, NOW + timedelta(seconds=12)))
        self.assertTrue(observe_grid_hold(
            self.config, client, state, NOW + timedelta(seconds=22)))
        released = state["pending_notifications"][0]
        self.assertEqual("grid_hold_released", released["kind"])
        self.assertIn("повернувся до пріоритету сонця", released["message"])
        self.assertIn("Поточний заряд: <b>31%</b>", released["message"])
        self.assertIn("порогу повернення <b>30%</b>", released["message"])

    def test_confirmed_below_reserve_charging_is_distinct_from_hold(self):
        state = {}
        client = FakeClient({"mode": "solar", "voltage": 230, "soc": 18,
                             "minimum": 20, "freshness": "fresh"})
        observe_grid_hold(self.config, client, state, NOW)
        client.values["mode"] = "panic"
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=1))
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=11))
        self.assertEqual("battery_reserve_charging", state["pending_notifications"][0]["kind"])
        self.assertIn("ДТЕК підключено", state["pending_notifications"][0]["message"])
        self.assertIn("до <b>20%</b>", state["pending_notifications"][0]["message"])

    def test_unavailable_dtek_never_claims_charging(self):
        state = {}
        client = FakeClient({"mode": "solar", "voltage": 0, "soc": 18,
                             "minimum": 20, "freshness": "fresh"})
        observe_grid_hold(self.config, client, state, NOW)
        client.values["mode"] = "panic"
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=1))
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=11))
        self.assertEqual([], state.get("pending_notifications", []))

    def test_grid_hold_reentry_with_same_reserve_is_not_announced_twice(self):
        state = {}
        client = FakeClient({"mode": "solar", "voltage": 230, "soc": 20,
                             "minimum": 20, "freshness": "fresh"})
        observe_grid_hold(self.config, client, state, NOW)
        client.values["mode"] = "panic_grid_hold"
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=1))
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=11))
        self.assertEqual(1, len(state["pending_notifications"]))
        state["pending_notifications"].clear()

        client.values["mode"] = "panic"
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=12))
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=22))
        client.values["mode"] = "panic_grid_hold"
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=23))
        observe_grid_hold(self.config, client, state, NOW + timedelta(seconds=33))

        self.assertEqual([], state["pending_notifications"])
        self.assertTrue(state["grid_hold_episode_active"])

    def test_existing_grid_hold_state_migrates_to_episode_latch(self):
        state = {
            "operating_mode_observed": "panic_grid_hold",
            "grid_hold_context": {"reserve_soc": 20, "release_soc": 30},
        }
        client = FakeClient({"mode": "panic_grid_hold", "voltage": 230,
                             "soc": 20, "minimum": 20, "freshness": "fresh"})

        self.assertTrue(observe_grid_hold(self.config, client, state, NOW))
        self.assertTrue(state["grid_hold_episode_active"])
        self.assertEqual(20, state["grid_hold_episode_reserve_soc"])
        self.assertEqual([], state.get("pending_notifications", []))

    def test_grid_outage_solar_transition_does_not_claim_reserve_release(self):
        state = {}
        client = FakeClient({"mode": "panic_grid_hold", "voltage": 230,
                             "soc": 20, "minimum": 20, "freshness": "fresh"})
        self.assertTrue(observe_grid_hold(self.config, client, state, NOW))
        client.values.update({"mode": "solar", "voltage": 0, "soc": 21})
        self.assertTrue(observe_grid_hold(
            self.config, client, state, NOW + timedelta(seconds=1)))
        self.assertTrue(observe_grid_hold(
            self.config, client, state, NOW + timedelta(seconds=11)))
        self.assertEqual([], state.get("pending_notifications", []))
        self.assertNotIn("grid_hold_context", state)

    def test_technical_notification_uses_private_chat(self):
        state = {"pending_notifications": [{
            "kind": "soc_anomaly", "message": "jump",
            "created_at": NOW.isoformat(),
        }]}
        telegram = FakeTelegram()
        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, NOW, FakeClient({})))
        self.assertEqual([("-2", "jump")], telegram.messages)

    def test_confidence_initialization_is_silent_then_transition_queues(self):
        state = {}
        client = FakeClient({
            "confidence": "normal",
            "reserve": {"state": "ready", "attributes": {
                "grid_confidence": "normal", "management_mode": "automatic",
                "control_applied": True, "applied_minimum_soc": 20,
                "recommended_soc": 20,
            }},
        })
        self.assertTrue(observe_grid_confidence(self.config, client, state, NOW))
        self.assertEqual([], state["pending_notifications"])
        client.values["confidence"] = "panic"
        client.values["reserve"]["attributes"].update({
            "grid_confidence": "panic", "applied_minimum_soc": 95,
            "recommended_soc": 95,
        })
        self.assertTrue(observe_grid_confidence(self.config, client, state, NOW + timedelta(minutes=1)))
        self.assertEqual("grid_confidence", state["pending_notifications"][0]["kind"])
        self.assertIn("20% → 95%", state["pending_notifications"][0]["message"])

    def test_confidence_transition_waits_for_reserve_then_has_bounded_fallback(self):
        state = {}
        client = FakeClient({
            "confidence": "normal",
            "reserve": {"state": "ready", "attributes": {
                "grid_confidence": "normal", "management_mode": "automatic",
                "control_applied": True, "applied_minimum_soc": 20,
                "recommended_soc": 20,
            }},
        })
        observe_grid_confidence(self.config, client, state, NOW)
        client.values["confidence"] = "panic"

        self.assertTrue(observe_grid_confidence(
            self.config, client, state, NOW + timedelta(minutes=1)
        ))
        self.assertEqual([], state["pending_notifications"])
        self.assertFalse(observe_grid_confidence(
            self.config, client, state, NOW + timedelta(minutes=2, seconds=59)
        ))
        self.assertTrue(observe_grid_confidence(
            self.config, client, state, NOW + timedelta(minutes=3)
        ))
        self.assertEqual(1, len(state["pending_notifications"]))
        self.assertIn("Надійність ДТЕК погіршилась", state["pending_notifications"][0]["message"])
        self.assertIn("Реакція резерву ще уточнюється", state["pending_notifications"][0]["message"])
        self.assertNotIn("залишається <b>20%</b>", state["pending_notifications"][0]["message"])

    def test_invalid_confidence_is_ignored(self):
        state = {"grid_confidence": "normal"}
        client = FakeClient({"confidence": "unavailable"})
        self.assertFalse(observe_grid_confidence(self.config, client, state, NOW))
        self.assertEqual("normal", state["grid_confidence"])

    def test_heat_pump_restart_restore_event_is_reported_once(self):
        event = {
            "id": "restart-1",
            "restored": [
                {"floor": "1-й", "power_w": 93},
                {"floor": "2-й", "power_w": 1},
            ],
        }
        client = FakeClient({"restart_event": json.dumps(event)})
        state = {}

        self.assertTrue(observe_heat_pump_restart_restore(
            self.config, client, state, NOW
        ))
        message = state["pending_notifications"][0]["message"]
        self.assertIn("1-й поверх: 93 Вт", message)
        self.assertIn("тепловий насос працює", message)
        self.assertIn("2-й поверх: 1 Вт", message)
        self.assertFalse(observe_heat_pump_restart_restore(
            self.config, client, state, NOW + timedelta(minutes=1)
        ))

    def test_malformed_restart_event_does_not_block_other_observers(self):
        for raw in ("null", "42", "[]", '"text"'):
            with self.subTest(raw=raw):
                state = {}
                client = FakeClient({"restart_event": raw})
                self.assertFalse(observe_heat_pump_restart_restore(
                    self.config, client, state, NOW
                ))
                self.assertNotIn("pending_notifications", state)

        def broken_observer():
            raise ValueError("bad entity")

        self.assertFalse(observe_safely(broken_observer))
        self.assertTrue(observe_safely(lambda: True))

    def test_failed_inverter_strategy_reports_once_until_recovered(self):
        state = {}
        client = FakeClient({"mode": "transition_failed"})
        self.assertTrue(observe_inverter_strategy_fault(
            self.config, client, state, NOW
        ))
        self.assertEqual("technical_inverter_strategy_fault",
                         state["pending_notifications"][0]["kind"])
        self.assertFalse(observe_inverter_strategy_fault(
            self.config, client, state, NOW + timedelta(minutes=1)
        ))
        client.values["mode"] = "solar"
        self.assertTrue(observe_inverter_strategy_fault(
            self.config, client, state, NOW + timedelta(minutes=2)
        ))

    def test_delayed_strategy_fault_alert_describes_recovered_state(self):
        state = {}
        client = FakeClient({"mode": "transition_failed"})
        self.assertTrue(observe_inverter_strategy_fault(
            self.config, client, state, NOW))
        with self.assertRaises(RuntimeError):
            deliver_pending_notifications(
                self.config, FakeTelegram(fail=True), state, NOW, client)
        client.values["mode"] = "solar"
        observe_inverter_strategy_fault(
            self.config, client, state, NOW + timedelta(minutes=1))
        telegram = FakeTelegram()
        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, NOW + timedelta(minutes=2), client))
        self.assertEqual("-2", telegram.messages[0][0])
        self.assertIn("раніше", telegram.messages[0][1])
        self.assertIn("solar", telegram.messages[0][1])
        self.assertNotIn("керування резервом призупинене", telegram.messages[0][1])

    def test_overnight_family_fallback_reports_recovered_fault_as_history(self):
        self.config.technical_chat_id = ""
        state = {}
        client = FakeClient({"mode": "transition_failed"})
        night = NOW.replace(hour=1)
        self.assertTrue(observe_inverter_strategy_fault(
            self.config, client, state, night))
        telegram = FakeTelegram()
        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, night, client))
        self.assertFalse(telegram.messages)
        self.assertEqual(1, len(state["overnight_family_events"]))
        client.values["mode"] = "solar"
        self.assertTrue(observe_inverter_strategy_fault(
            self.config, client, state, night + timedelta(hours=6)))
        lines = overnight_family_event_lines(
            state["overnight_family_events"], inverter_mode="solar",
            mode_observed_at=night + timedelta(hours=7))
        self.assertIn("раніше", lines[0])
        self.assertIn("станом на 08:00 підтверджено режим solar", lines[0])
        self.assertNotIn("призупинене", lines[0])

    def test_unreconstructed_strategy_is_a_technical_alert(self):
        state = {}
        client = FakeClient({"mode": "inconsistent"})
        self.assertTrue(observe_inverter_strategy_fault(
            self.config, client, state, NOW))
        self.assertFalse(observe_inverter_strategy_fault(
            self.config, client, state, NOW + timedelta(minutes=1)))
        telegram = FakeTelegram()
        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, NOW, client))
        self.assertEqual("-2", telegram.messages[0][0])
        self.assertIn("призупинене", telegram.messages[0][1])

    def test_heat_pump_restart_message_requires_confirmed_restoration(self):
        with self.assertRaises(ValueError):
            heat_pump_restart_restored_message({"id": "restart-1", "restored": []})

    def test_peak_load_guard_event_is_queued_once_by_event_id(self):
        state = {}
        event = {
            "event_id": "peak-load-1",
            "type": "load_warning",
            "load_percent": 85,
            "thresholds": {
                "shed_percent": 85,
                "relief_percent": 75,
                "restore_percent": 60,
            },
            "recommended_loads": [
                {"key": "water_pump"},
                {"key": "water_boiler"},
            ],
        }
        client = FakeClient({
            "guard_event": {
                "state": "Shed recommended",
                "attributes": {"event": event},
            }
        })

        self.assertTrue(observe_peak_load_guard(
            self.config, client, state, NOW
        ))
        self.assertEqual(
            "peak_load_guard_load_warning",
            state["pending_notifications"][0]["kind"],
        )
        self.assertFalse(observe_peak_load_guard(
            self.config, client, state, NOW + timedelta(seconds=30)
        ))
        self.assertEqual(1, len(state["pending_notifications"]))

    def test_soc_anomaly_initializes_silently_then_queues_each_new_event_once(self):
        first = {
            "timestamp": "2026-08-31T06:00:00+00:00",
            "previous_soc": 45,
            "current_soc": 51,
            "delta_percent": 6,
        }
        second = {
            "timestamp": "2026-08-31T06:56:19+00:00",
            "previous_soc": 70,
            "current_soc": 100,
            "delta_percent": 30,
        }
        state = {}
        client = FakeClient({
            "soc_anomaly": {
                "state": first["timestamp"],
                "attributes": {"event_count": 6, "latest_event": first},
            }
        })

        self.assertTrue(observe_soc_anomaly(self.config, client, state, NOW))
        self.assertEqual([], state.get("pending_notifications", []))
        client.values["soc_anomaly"]["attributes"] = {
            "event_count": 7,
            "latest_event": second,
        }
        self.assertTrue(observe_soc_anomaly(
            self.config, client, state, NOW + timedelta(minutes=1)
        ))
        self.assertEqual("soc_anomaly", state["pending_notifications"][0]["kind"])
        self.assertEqual(1, len(state["soc_anomaly_report_events"]))
        self.assertFalse(observe_soc_anomaly(
            self.config, client, state, NOW + timedelta(minutes=2)
        ))
        self.assertEqual(1, len(state["pending_notifications"]))

    def test_reserve_warnings_follow_selected_minimum_and_do_not_repeat(self):
        state = {"grid_online": False}
        client = FakeClient({
            "soc": 70,
            "minimum": 20,
            "confidence": "risk",
            "voltage": 0,
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

    def test_schema_five_drops_retired_relative_warnings(self):
        client = FakeClient({
            "sensor.energyhub_peak_load_guard": {
                "state": "normal", "attributes": {"control_schema": 5}},
            "soc": 59, "minimum": 40, "voltage": 0, "freshness": "fresh",
        })
        state = {"pending_notifications": [
            {"kind": "reserve_20", "message": "old", "created_at": NOW.isoformat()}]}
        self.assertTrue(observe_reserve_warnings(self.config, client, state, NOW))
        self.assertEqual([], state["pending_notifications"])
        self.assertEqual(("drop", None), refresh_queued_reserve_warning(
            self.config, client, "reserve_20"))

    def test_reserve_warning_is_silent_while_grid_is_confirmed_online(self):
        state = {"grid_online": True}
        client = FakeClient({
            "soc": 43,
            "minimum": 20,
            "confidence": "normal",
            "voltage": 230,
            "freshness": "fresh",
            "hp1": 93,
        })

        self.assertTrue(observe_reserve_warnings(
            self.config, client, state, NOW
        ))
        self.assertEqual([], state["pending_notifications"])
        self.assertFalse(observe_reserve_warnings(
            self.config, client, state, NOW + timedelta(minutes=1)
        ))
        self.assertEqual([], state["pending_notifications"])

    def test_reserve_warning_rearms_after_two_percent_recovery(self):
        state = {"grid_online": False}
        client = FakeClient({
            "soc": 60,
            "minimum": 20,
            "confidence": "risk",
            "voltage": 0,
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
        state = {"grid_online": False}
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
        state = {"grid_online": False}
        client = FakeClient({
            "soc": 70,
            "minimum": 20,
            "confidence": "risk",
            "voltage": 0,
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
        state = {"grid_online": False}
        client = FakeClient({
            "soc": 70,
            "minimum": 20,
            "confidence": "risk",
            "voltage": 0,
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

    def test_night_delivery_archives_family_events_for_morning(self):
        night = NOW.replace(hour=1, minute=51)
        state = {"pending_notifications": [
            {"kind": "reserve_30", "message": "reserve", "created_at": night.isoformat()},
            {"kind": "grid_lost", "message": "grid", "created_at": night.isoformat()},
        ]}
        telegram = FakeTelegram()

        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, night
        ))
        self.assertEqual([], telegram.messages)
        self.assertEqual([], state["pending_notifications"])
        self.assertEqual(
            ["reserve_30", "grid_lost"],
            [event["kind"] for event in state["overnight_family_events"]],
        )

    def test_private_technical_message_remains_immediate_at_night(self):
        night = NOW.replace(hour=1, minute=51)
        state = {"pending_notifications": [{
            "kind": "soc_anomaly", "message": "jump",
            "created_at": night.isoformat(),
        }]}
        telegram = FakeTelegram()

        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, night
        ))
        self.assertEqual([("-2", "jump")], telegram.messages)

    def test_family_delivery_waits_through_0801_then_resumes(self):
        state = {"pending_notifications": [{
            "kind": "grid_recovered", "message": "grid",
            "created_at": NOW.isoformat(),
        }]}
        telegram = FakeTelegram()

        at_0801 = NOW.replace(hour=8, minute=1)
        self.assertFalse(deliver_pending_notifications(
            self.config, telegram, state, at_0801
        ))
        self.assertEqual([], telegram.messages)
        self.assertTrue(deliver_pending_notifications(
            self.config, telegram, state, at_0801.replace(minute=2)
        ))
        self.assertEqual([("-1", "grid")], telegram.messages)

    def test_delayed_reserve_warning_refreshes_power_before_delivery(self):
        client = FakeClient({
            "soc": 49,
            "minimum": 20,
            "confidence": "risk",
            "voltage": 0,
            "freshness": "fresh",
            "hp1": 823,
        })
        action, message = refresh_queued_reserve_warning(
            self.config, client, "reserve_30"
        )
        self.assertEqual("send", action)
        self.assertIn("Заряд батареї знизився до 49%", message)
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
            "confidence": "risk",
            "voltage": 0,
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

        client.values.update({"soc": 49, "hp1": 700, "voltage": 230})
        self.assertEqual(
            ("drop", None),
            refresh_queued_reserve_warning(self.config, client, "reserve_30"),
        )

    def test_delivery_removes_only_successfully_sent_items(self):
        state = {"pending_notifications": [{"kind": "grid_lost", "message": "alert", "created_at": NOW.isoformat()}]}
        telegram = FakeTelegram()
        self.assertTrue(deliver_pending_notifications(self.config, telegram, state, now=NOW))
        self.assertEqual([], state["pending_notifications"])
        self.assertEqual("alert", telegram.messages[0][1])

        state["pending_notifications"] = [{"kind": "grid_lost", "message": "retry", "created_at": NOW.isoformat()}]
        with self.assertRaises(RuntimeError):
            deliver_pending_notifications(self.config, FakeTelegram(fail=True), state, now=NOW)
        self.assertEqual("retry", state["pending_notifications"][0]["message"])


class WeatherWarningTests(unittest.TestCase):
    def test_replaced_overnight_warning_is_not_repeated_in_morning(self):
        old = dict(self.event)
        new = dict(self.event, event_id="uhmc1921/11/hash", hazards=["strong_wind", "thunderstorm"])
        self.reserve["weather_warnings"] = [new]
        state = {"weather_warning_report_events": [old],
                 "weather_warning_seen_event_ids": [old["event_id"]],
                 "uhmc_superseded_warnings": [dict(old, superseded_by=new["event_id"])]}
        self.assertTrue(observe_weather_warnings(self.config, self.client, state, NOW.replace(hour=23)))
        self.assertEqual([new["event_id"]], [item["event_id"] for item in state["weather_warning_report_events"]])
        self.assertFalse(observe_weather_warnings(self.config, self.client, state, NOW.replace(hour=23)))

    def setUp(self):
        self.config = SimpleNamespace(weather_buffer_entity="reserve")
        self.event = {
            "event_id": "uhmc1921/10/hash",
            "severity": 1,
            "hazards": ["thunderstorm"],
            "summary": "Гроза",
            "valid_until": "2026-08-12T23:59:59+03:00",
            "url": "https://t.me/uhmc1921/10",
        }
        self.reserve = {
            "weather_warnings": [self.event],
            "applied_minimum_soc": 20,
            "daily_plan_fresh": True,
            "weather_source_status": "fresh",
            "baseline_soc": 20,
            "recommended_soc": 20,
            "weather_modifier_percent": 0,
            "grid_confidence": "normal",
            "dry_run": True,
        }
        self.client = FakeClient({
            "reserve": {
                "state": "Reserve recommendation ready",
                "attributes": self.reserve,
            }
        })

    def test_message_explains_level_two_recommendation(self):
        event = dict(self.event, severity=2, hazards=["strong_wind"])
        reserve = dict(
            self.reserve,
            recommended_soc=40,
            weather_modifier_percent=20,
        )
        message = weather_warning_message(event, reserve)
        self.assertIn("ІІ рівень небезпечності", message)
        self.assertIn("Погодний резерв +20%", message)
        self.assertIn("рекомендовано вручну 40%", message)

    def test_automatic_level_two_warning_reports_confirmed_applied_reserve(self):
        event = dict(self.event, severity=2, hazards=["strong_wind"])
        message = weather_warning_message(event, dict(
            self.reserve,
            management_mode="automatic",
            control_applied=True,
            applied_minimum_soc=45,
            recommended_soc=40,
            weather_modifier_percent=20,
        ))
        self.assertIn("EH встановив 45%", message)
        self.assertNotIn("EH встановив 40%", message)

    def test_daytime_warning_preserves_official_details_but_omits_level_one_reserve(self):
        event = dict(self.event, summary=(
            "‼️Попередження про небезпечні метеорологічні явища по території Київщини‼️\n\n"
            "До кінця доби значні дощі.\n\n"
            "І рівень небезпечності, жовтий.\n\n"
            "Погодні умови можуть ускладнити роботу підприємств."
        ))
        message = weather_warning_message(event, self.reserve)
        self.assertIn("До кінця доби значні дощі", message)
        self.assertIn("Погодні умови можуть ускладнити", message)
        self.assertIn("І рівень небезпечності", message)
        self.assertIn("Джерело", message)
        self.assertNotIn("Мінімум батареї", message)

    def test_manual_mode_preserves_higher_family_selection(self):
        event = dict(self.event, severity=2)
        message = weather_warning_message(
            event,
            dict(self.reserve, management_mode="manual", applied_minimum_soc=60),
        )
        self.assertIn("Ручний вибір збережено", message)
        self.assertIn("Мінімум батареї: 60%", message)
        self.assertNotIn("20% →", message)

    def test_daytime_warning_is_queued_once(self):
        state = {}
        self.assertTrue(observe_weather_warnings(self.config, self.client, state, NOW))
        self.assertFalse(observe_weather_warnings(self.config, self.client, state, NOW))
        self.assertEqual(1, len(state["pending_notifications"]))
        self.assertIn("І рівень небезпечності", state["pending_notifications"][0]["message"])

    def test_overnight_warning_waits_for_morning_report(self):
        state = {}
        overnight = NOW.replace(hour=23)
        self.assertTrue(observe_weather_warnings(self.config, self.client, state, overnight))
        self.assertEqual([], state.get("pending_notifications", []))
        self.assertEqual(1, len(state["weather_warning_report_events"]))

    def test_overnight_weather_reserve_restoration_is_kept_for_report(self):
        state = {}
        self.reserve.update({
            "weather_modifier_percent": 20,
            "recommended_soc": 40,
            "evaluation_signature": "warning-active",
        })
        self.assertTrue(observe_weather_warnings(self.config, self.client, state, NOW))
        state["pending_notifications"] = []
        self.reserve.update({
            "weather_source_warnings": [],
            "weather_warnings": [],
            "weather_modifier_percent": 0,
            "recommended_soc": 20,
            "evaluation_signature": "warning-expired",
        })
        self.assertTrue(
            observe_weather_warnings(
                self.config,
                self.client,
                state,
                NOW.replace(hour=23),
            )
        )
        self.assertEqual(1, len(state["weather_reserve_restoration_events"]))
        self.assertEqual([], state.get("pending_notifications", []))


if __name__ == "__main__":
    unittest.main()
