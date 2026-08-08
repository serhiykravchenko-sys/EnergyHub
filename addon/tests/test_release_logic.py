from datetime import datetime
from types import ModuleType, SimpleNamespace
import json
import sys
import unittest
from unittest.mock import patch

try:
    import paho.mqtt.client  # noqa: F401
except ModuleNotFoundError:
    paho_module = ModuleType("paho")
    mqtt_module = ModuleType("paho.mqtt")
    mqtt_client_module = ModuleType("paho.mqtt.client")
    mqtt_module.client = mqtt_client_module
    paho_module.mqtt = mqtt_module
    sys.modules["paho"] = paho_module
    sys.modules["paho.mqtt"] = mqtt_module
    sys.modules["paho.mqtt.client"] = mqtt_client_module

from app.services.grid_stability import GridStabilityEngine
from app.services.hybrid_decision import HybridDecisionEngine
from app.services.inverter_controller import InverterController
from app.services.panic_decision import PanicDecisionEngine
from app.services.telemetry_freshness import TelemetryFreshnessMonitor
from app.mqtt.publisher import (
    publish_daily_summary_discovery,
    publish_hybrid_decision_discovery,
)


class FixedAvailabilityHistory:
    def __init__(self, availability):
        self.availability = availability
        self.requested_hours = []

    def availability_percent(self, hours):
        self.requested_hours.append(hours)
        return self.availability


class SplitAvailabilityHistory:
    def __init__(self, availability_24h, availability_48h):
        self.values = {
            24: availability_24h,
            48: availability_48h,
        }

    def availability_percent(self, hours):
        return self.values[hours]


class FakeInverter:
    OUTPUT_PRIORITY_VALUES = {
        "POP01": "Solar Utility Battery",
        "POP02": "Solar Battery Utility",
    }

    def __init__(self, failed_charger_commands=None):
        self.failed_charger_commands = set(
            failed_charger_commands or []
        )
        self.output_priority_raw = "Solar Battery Utility"
        self.calls = []

    def set_output_source_priority(self, command):
        self.calls.append(("menu_01", command))

        raw_value = self.OUTPUT_PRIORITY_VALUES.get(command)
        if raw_value is None:
            return False

        self.output_priority_raw = raw_value
        return True

    def set_charger_source_priority(self, command):
        self.calls.append(("menu_16", command))
        return command not in self.failed_charger_commands

    def read_settings(self):
        self.calls.append(("read_settings", None))
        return {
            "output_source_priority": self.output_priority_raw,
        }


class FakeMqttClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    def discovery_payloads(self):
        return {
            topic: json.loads(payload)
            for topic, payload, _retain in self.published
            if topic.endswith("/config") and payload
        }


class MqttDiscoveryMetadataTests(unittest.TestCase):
    def test_snapshot_energy_entities_do_not_use_measurement(self):
        client = FakeMqttClient()
        publish_daily_summary_discovery(client)
        publish_hybrid_decision_discovery(client)

        for topic, payload in client.discovery_payloads().items():
            if payload.get("device_class") != "energy":
                continue

            self.assertNotEqual(
                payload.get("state_class"),
                "measurement",
                topic,
            )


class HybridDecisionTests(unittest.TestCase):
    def setUp(self):
        self.engine = HybridDecisionEngine()

    def evaluate(self, **overrides):
        values = {
            "autopilot_enabled": True,
            "operating_mode": "solar",
            "battery_soc": 45,
            "morning_hours": 3,
            "useful_solar_start": "10:00",
            "forecast_tomorrow": 30,
            "consumption_today": 14,
            "solar_forecast_after_07": 30,
        }
        values.update(overrides)
        return self.engine.evaluate(**values)

    def test_charges_when_current_soc_is_below_adaptive_target(self):
        result = self.evaluate()

        self.assertEqual(result["status"], "hybrid_charging")
        self.assertEqual(result["request"], "hybrid")
        self.assertEqual(result["projected_soc_at_07"], 30)
        self.assertEqual(result["morning_hours"], 3)
        self.assertEqual(result["morning_reserve_soc"], 30)
        self.assertEqual(result["target_soc"], 60)
        self.assertIsNotNone(self.engine.evaluated_at)
        self.assertIn(
            "target 60.0% = 20% reserve + 10% margin + max(30.0% morning",
            self.engine.calculation,
        )

    def test_cold_season_daytime_deficit_raises_target(self):
        result = self.evaluate(
            battery_soc=45,
            morning_hours=1,
            consumption_today=40,
            forecast_tomorrow=20,
            solar_forecast_after_07=20,
        )

        self.assertAlmostEqual(
            result["expected_consumption_after_07"],
            28.33,
        )
        self.assertAlmostEqual(result["daytime_deficit_kwh"], 8.33)
        self.assertAlmostEqual(result["daytime_deficit_soc"], 57.87)
        self.assertAlmostEqual(result["target_soc"], 87.87)

    def test_extreme_cold_season_deficit_caps_target(self):
        result = self.evaluate(
            consumption_today=40,
            forecast_tomorrow=15,
            solar_forecast_after_07=15,
        )

        self.assertEqual(result["target_soc"], 95)
        self.assertTrue(result["target_capped"])

    def test_summer_surplus_keeps_morning_bridge_target(self):
        result = self.evaluate(
            consumption_today=20,
            forecast_tomorrow=35,
            solar_forecast_after_07=35,
        )

        self.assertEqual(result["daytime_deficit_kwh"], 0)
        self.assertEqual(result["target_soc"], 60)

    def test_holds_when_soc_meets_target_but_would_fall_below_it(self):
        result = self.evaluate(battery_soc=65)

        self.assertEqual(result["status"], "hybrid_grid_hold")
        self.assertEqual(result["request"], "hybrid_grid_hold")
        self.assertEqual(result["projected_soc_at_07"], 50)
        self.assertEqual(result["target_soc"], 60)

    def test_keeps_solar_when_projected_soc_meets_target(self):
        result = self.evaluate(battery_soc=80)

        self.assertEqual(result["status"], "solar")
        self.assertIsNone(result["request"])
        self.assertEqual(result["projected_soc_at_07"], 65)
        self.assertEqual(result["target_soc"], 60)

    def test_caps_target_at_95_percent(self):
        result = self.evaluate(
            battery_soc=40,
            morning_hours=8,
            useful_solar_start="15:00",
        )

        self.assertEqual(result["target_soc"], 95)
        self.assertTrue(result["target_capped"])
        self.assertEqual(result["request"], "hybrid")

    def test_uses_conservative_fallback_without_hourly_forecast(self):
        result = self.evaluate(
            morning_hours=None,
            useful_solar_start=None,
        )

        self.assertEqual(result["target_soc"], 80)
        self.assertEqual(result["morning_hours"], 5)
        self.assertTrue(result["used_fallback"])
        self.assertIn("fallback", result["reason"])

    def test_ahm_overtakes_panic_at_2350(self):
        result = self.evaluate(
            operating_mode="panic",
            battery_soc=45,
        )

        self.assertEqual(result["request"], "hybrid")

    def test_ahm_restores_solar_when_panic_reserve_is_sufficient(self):
        result = self.evaluate(
            operating_mode="panic_grid_hold",
            battery_soc=80,
        )

        self.assertEqual(result["status"], "solar")
        self.assertEqual(result["request"], "solar")

    def test_skips_when_autopilot_is_disabled(self):
        result = self.evaluate(autopilot_enabled=False)

        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["request"])

    def test_skips_when_another_strategy_is_active(self):
        result = self.evaluate(
            operating_mode="hybrid_grid_hold"
        )

        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["request"])

    def test_skips_when_battery_soc_is_missing(self):
        result = self.evaluate(battery_soc=None)

        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["request"])


class PanicDecisionTests(unittest.TestCase):
    def setUp(self):
        self.engine = PanicDecisionEngine()

    def evaluate(self, **overrides):
        values = {
            "autopilot_enabled": True,
            "operating_mode": "solar",
            "grid_confidence": "normal",
            "battery_soc": 60,
            "grid_available": True,
            "ahm_target_soc": None,
            "now": datetime(2026, 8, 1, 13, 0),
        }
        values.update(overrides)
        return self.engine.evaluate(**values)

    def test_grid_confidence_targets(self):
        cases = (
            ("normal", 20),
            ("unstable", 60),
            ("risk", 80),
            ("panic", 95),
        )

        for confidence, target in cases:
            with self.subTest(confidence=confidence):
                result = self.evaluate(
                    grid_confidence=confidence,
                    battery_soc=10,
                )

                self.assertEqual(result["status"], "trigger_charge")
                self.assertEqual(result["request"], "panic")
                self.assertEqual(result["target_soc"], target)

    def test_risk_grid_triggers_80_percent_target(self):
        result = self.evaluate(
            grid_confidence="risk",
            battery_soc=79,
        )

        self.assertEqual(result["status"], "trigger_charge")
        self.assertEqual(result["request"], "panic")
        self.assertEqual(result["target_soc"], 80)

    def test_panic_grid_uses_95_percent_policy(self):
        result = self.evaluate(
            grid_confidence="panic",
            battery_soc=40,
        )

        self.assertEqual(result["status"], "trigger_charge")
        self.assertEqual(result["target_soc"], 95)

    def test_unstable_grid_uses_60_percent_target(self):
        result = self.evaluate(
            grid_confidence="unstable",
            battery_soc=59,
        )

        self.assertEqual(result["target_soc"], 60)

    def test_sufficient_soc_prevents_panic_in_solar(self):
        result = self.evaluate(
            grid_confidence="risk",
            battery_soc=80,
        )

        self.assertEqual(result["status"], "no_action")
        self.assertIsNone(result["request"])

    def test_unmet_ahm_target_overrides_grid_target(self):
        result = self.evaluate(
            grid_confidence="normal",
            battery_soc=50,
            ahm_target_soc=70,
        )

        self.assertEqual(result["target_soc"], 70)
        self.assertIn("unmet AHM target", result["target_source"])

    def test_normal_grid_protects_20_percent(self):
        result = self.evaluate(
            grid_confidence="normal",
            battery_soc=19,
        )

        self.assertEqual(result["target_soc"], 20)
        self.assertEqual(result["request"], "panic")

    def test_offline_grid_arms_panic_and_waits(self):
        result = self.evaluate(
            grid_confidence="panic",
            battery_soc=40,
            grid_available=False,
        )

        self.assertEqual(result["phase"], "waiting_for_grid")
        self.assertEqual(result["request"], "panic")

    def test_active_panic_reports_waiting_without_retransition(self):
        result = self.evaluate(
            operating_mode="panic",
            grid_confidence="panic",
            battery_soc=40,
            grid_available=False,
        )

        self.assertEqual(result["status"], "waiting_for_grid")
        self.assertIsNone(result["request"])

    def test_panic_target_reached_requests_grid_hold(self):
        result = self.evaluate(
            operating_mode="panic",
            grid_confidence="risk",
            battery_soc=80,
        )

        self.assertEqual(result["request"], "panic_grid_hold")
        self.assertEqual(result["phase"], "grid_hold")

    def test_panic_hold_recharges_after_soc_falls(self):
        result = self.evaluate(
            operating_mode="panic_grid_hold",
            grid_confidence="risk",
            battery_soc=79,
        )

        self.assertEqual(result["request"], "panic")

    def test_evaluation_window_boundaries(self):
        with self.subTest("07:00 is included"):
            result = self.evaluate(
                grid_confidence="risk",
                battery_soc=20,
                now=datetime(2026, 8, 1, 7, 0),
            )
            self.assertEqual(result["status"], "trigger_charge")

        with self.subTest("23:50 is excluded"):
            result = self.evaluate(
                grid_confidence="risk",
                battery_soc=20,
                now=datetime(2026, 8, 1, 23, 50),
            )
            self.assertEqual(result["status"], "skipped")

    def test_active_hybrid_strategy_is_not_interrupted(self):
        result = self.evaluate(
            operating_mode="hybrid_charging",
            grid_confidence="panic",
            battery_soc=10,
        )

        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["request"])


class GridStabilityTests(unittest.TestCase):
    def test_recent_24_hours_have_three_times_the_weight(self):
        improving = GridStabilityEngine(
            SplitAvailabilityHistory(50.0, 29.2)
        )
        worsening = GridStabilityEngine(
            SplitAvailabilityHistory(8.3, 29.2)
        )

        self.assertEqual(improving.level(), "risk")
        self.assertEqual(worsening.level(), "panic")

    def test_grid_confidence_thresholds(self):
        cases = (
            (100.0, "normal"),
            (90.0, "normal"),
            (89.9, "unstable"),
            (60.0, "unstable"),
            (59.9, "risk"),
            (30.0, "risk"),
            (29.9, "panic"),
            (0.0, "panic"),
        )

        for availability, expected in cases:
            with self.subTest(
                availability=availability,
                expected=expected,
            ):
                history = FixedAvailabilityHistory(
                    availability
                )
                engine = GridStabilityEngine(history)

                self.assertEqual(engine.level(), expected)
                self.assertEqual(
                    history.requested_hours,
                    [24, 48],
                )


class TelemetryFreshnessTests(unittest.TestCase):
    def test_no_valid_telemetry_is_stale(self):
        monitor = TelemetryFreshnessMonitor()
        state = SimpleNamespace(
            valid=False,
            load_power=None,
        )

        with patch(
            "app.services.telemetry_freshness.time.monotonic",
            return_value=100.0,
        ):
            monitor.update(state)

        self.assertEqual(monitor.status, "stale")
        self.assertEqual(
            monitor.reason,
            "no_valid_telemetry",
        )

    def test_valid_telemetry_becomes_stale_after_60_seconds(self):
        monitor = TelemetryFreshnessMonitor()
        state = SimpleNamespace(
            valid=True,
            load_power=500,
        )

        with patch(
            "app.services.telemetry_freshness.time.monotonic",
            return_value=100.0,
        ):
            monitor.update(state)

        self.assertEqual(monitor.status, "fresh")

        with patch(
            "app.services.telemetry_freshness.time.monotonic",
            return_value=159.9,
        ):
            monitor.update_status()

        self.assertEqual(monitor.status, "fresh")

        with patch(
            "app.services.telemetry_freshness.time.monotonic",
            return_value=160.0,
        ):
            monitor.update_status()

        self.assertEqual(monitor.status, "stale")
        self.assertEqual(
            monitor.reason,
            "no_recent_valid_telemetry",
        )

    def test_unchanged_load_is_diagnostic_not_stale(self):
        monitor = TelemetryFreshnessMonitor()
        state = SimpleNamespace(
            valid=True,
            load_power=500,
        )

        with patch(
            "app.services.telemetry_freshness.time.monotonic",
            return_value=100.0,
        ):
            monitor.update(state)

        with patch(
            "app.services.telemetry_freshness.time.monotonic",
            return_value=400.0,
        ):
            monitor.update(state)

        with patch(
            "app.services.telemetry_freshness.time.monotonic",
            return_value=400.0,
        ):
            values = monitor.mqtt_values()

        self.assertEqual(monitor.status, "fresh")
        self.assertEqual(
            values["house_load_unchanged_minutes"],
            5,
        )


class InverterControllerTests(unittest.TestCase):
    def make_controller(self, inverter=None):
        return InverterController(
            inverter or FakeInverter(),
            state_path=None,
        )

    def test_reconstructs_solar_without_writing(self):
        inverter = FakeInverter()
        controller = self.make_controller(inverter)
        controller.confirmed_mode = "solar"
        controller.known_charger_priority = "OSO"

        result = controller.reconstruct_mode("SBU")

        self.assertTrue(result)
        self.assertEqual(controller.mode, "solar")
        self.assertEqual(inverter.calls, [])

    def test_reconstructs_hybrid_grid_hold_from_context(self):
        controller = self.make_controller()
        controller.confirmed_mode = "hybrid_charging"
        controller.known_charger_priority = "OSO"

        result = controller.reconstruct_mode("SUB")

        self.assertTrue(result)
        self.assertEqual(
            controller.mode,
            "hybrid_grid_hold",
        )

    def test_reconstructs_panic_from_persisted_target(self):
        controller = self.make_controller()
        controller.confirmed_mode = "solar"
        controller.known_charger_priority = "SNU"
        controller.panic_target_soc = 95

        result = controller.reconstruct_mode("SUB")

        self.assertTrue(result)
        self.assertEqual(controller.mode, "panic")
        self.assertEqual(controller.panic_target_soc, 95)

    def test_reconstructs_panic_grid_hold_from_context(self):
        controller = self.make_controller()
        controller.confirmed_mode = "panic_grid_hold"
        controller.known_charger_priority = "OSO"
        controller.panic_target_soc = 80

        result = controller.reconstruct_mode("SUB")

        self.assertTrue(result)
        self.assertEqual(controller.mode, "panic_grid_hold")

    def test_rejects_ambiguous_startup_state(self):
        controller = self.make_controller()
        controller.confirmed_mode = "solar"
        controller.known_charger_priority = "SNU"
        controller.panic_target_soc = None

        result = controller.reconstruct_mode("SUB")

        self.assertFalse(result)
        self.assertEqual(controller.mode, "inconsistent")
        self.assertIn(
            "Startup reconstruction is incomplete",
            controller.last_error,
        )

    @patch(
        "app.services.inverter_controller.time.sleep",
        return_value=None,
    )
    def test_enter_hybrid_executes_verified_transition(
        self,
        _sleep,
    ):
        inverter = FakeInverter()
        controller = self.make_controller(inverter)

        result = controller.enter_hybrid()

        self.assertTrue(result)
        self.assertEqual(
            controller.mode,
            "hybrid_charging",
        )
        self.assertIn(("menu_01", "POP01"), inverter.calls)
        self.assertIn(
            ("read_settings", None),
            inverter.calls,
        )
        self.assertIn(("menu_16", "PCP01"), inverter.calls)

    @patch(
        "app.services.inverter_controller.time.sleep",
        return_value=None,
    )
    def test_partial_hybrid_failure_recovers_to_solar(
        self,
        _sleep,
    ):
        inverter = FakeInverter(
            failed_charger_commands={"PCP01"}
        )
        controller = self.make_controller(inverter)

        result = controller.enter_hybrid()

        self.assertFalse(result)
        self.assertEqual(controller.mode, "solar")
        self.assertIn(("menu_16", "PCP02"), inverter.calls)
        self.assertIn(("menu_01", "POP02"), inverter.calls)

    def test_rejects_invalid_panic_target(self):
        controller = self.make_controller()

        self.assertFalse(controller.set_panic_target_soc(0))
        self.assertFalse(controller.set_panic_target_soc(101))
        self.assertFalse(
            controller.set_panic_target_soc("invalid")
        )
        self.assertIsNone(controller.panic_target_soc)

    def test_preserves_decimal_panic_target(self):
        controller = self.make_controller()

        self.assertTrue(controller.set_panic_target_soc(87.87))
        self.assertEqual(controller.panic_target_soc, 87.87)

    def test_persists_valid_hybrid_target_in_memory(self):
        controller = self.make_controller()

        self.assertTrue(controller.set_hybrid_target_soc(87.87))
        self.assertEqual(controller.hybrid_target_soc, 87.87)

    def test_tracks_and_clears_ahm_morning_debt(self):
        controller = self.make_controller()

        self.assertTrue(controller.set_ahm_debt("2026-08-08", 70))
        self.assertEqual(controller.ahm_debt_date, "2026-08-08")
        self.assertEqual(controller.ahm_debt_target_soc, 70)

        self.assertTrue(controller.set_ahm_debt("2026-08-08", None))
        self.assertIsNone(controller.ahm_debt_target_soc)

    @patch(
        "app.services.inverter_controller.time.sleep",
        return_value=None,
    )
    def test_enter_panic_grid_hold_preserves_panic_context(
        self,
        _sleep,
    ):
        controller = self.make_controller()
        controller.set_panic_target_soc(80)

        result = controller.enter_panic_grid_hold()

        self.assertTrue(result)
        self.assertEqual(controller.mode, "panic_grid_hold")
        self.assertEqual(controller.panic_target_soc, 80)


if __name__ == "__main__":
    unittest.main()
