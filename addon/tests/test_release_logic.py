from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
import json
import sys
import tempfile
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
from app.services.early_solar_handover import EarlySolarHandoverEngine
from app.services.hybrid_decision import HybridDecisionEngine
from app.services.hybrid_night_enforcement import (
    HybridNightEnforcement,
)
from app.services.inverter_controller import InverterController
from app.services.morning_load_profile import MorningLoadProfileService
from app.services.panic_decision import PanicDecisionEngine
from app.services.reserve_advisor import ReserveAdvisorService
from app.services.telemetry_freshness import TelemetryFreshnessMonitor
from app.mqtt.publisher import (
    publish_daily_summary_discovery,
    publish_early_solar_handover,
    publish_early_solar_handover_discovery,
    publish_hybrid_decision,
    publish_hybrid_decision_discovery,
    publish_grid_import_discovery,
    publish_inverter_fault_journal,
    publish_inverter_fault_journal_discovery,
    publish_soc_anomaly_journal,
    publish_soc_anomaly_journal_discovery,
)
from app.services.soc_anomaly_journal import SocAnomalyJournal
from app.services.inverter_fault_journal import InverterFaultJournal


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


class HybridNightEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.engine = HybridNightEnforcement()
        self.now = datetime.fromisoformat("2026-08-18T00:30:00+03:00")
        self.defaults = {
            "autopilot_enabled": True,
            "enforcement_until_date": "2026-08-18",
            "operating_mode": "solar",
            "battery_soc": 40,
            "target_soc": 20,
            "grid_available": True,
            "telemetry_freshness": "fresh",
            "now": self.now,
        }

    def evaluate(self, **overrides):
        values = dict(self.defaults)
        values.update(overrides)
        return self.engine.evaluate(**values)

    def test_night_solar_remains_while_soc_is_above_target(self):
        self.assertIsNone(self.evaluate()["request"])

    def test_exact_target_enters_grid_hold(self):
        self.assertEqual(
            "hybrid_grid_hold",
            self.evaluate(battery_soc=20)["request"],
        )

    def test_below_target_enters_charging(self):
        self.assertEqual(
            "hybrid",
            self.evaluate(battery_soc=19)["request"],
        )

    def test_grid_hold_resumes_charging_after_grid_outage_drop(self):
        self.assertEqual(
            "hybrid",
            self.evaluate(
                operating_mode="hybrid_grid_hold",
                battery_soc=18,
            )["request"],
        )

    def test_offline_grid_arms_without_request(self):
        decision = self.evaluate(
            battery_soc=19,
            grid_available=False,
        )
        self.assertEqual("waiting_for_grid", decision["status"])
        self.assertIsNone(decision["request"])

    def test_stale_telemetry_never_requests_control(self):
        decision = self.evaluate(
            battery_soc=19,
            telemetry_freshness="stale",
        )
        self.assertEqual("waiting_for_telemetry", decision["status"])
        self.assertIsNone(decision["request"])

    def test_plan_date_must_match_current_night(self):
        decision = self.evaluate(
            enforcement_until_date="2026-08-17",
            battery_soc=19,
        )
        self.assertEqual("inactive", decision["status"])
        self.assertIsNone(decision["request"])

    def test_seven_am_is_outside_window(self):
        decision = self.evaluate(
            now=datetime.fromisoformat("2026-08-18T07:00:00+03:00"),
            battery_soc=19,
        )
        self.assertEqual("outside_window", decision["status"])
        self.assertIsNone(decision["request"])

    def test_2350_plan_is_dated_for_the_following_morning(self):
        self.assertEqual(
            "2026-08-19",
            self.engine.enforcement_date(
                datetime.fromisoformat(
                    "2026-08-18T23:50:00+03:00"
                )
            ),
        )


class FakeInverter:
    OUTPUT_PRIORITY_VALUES = {
        "POP01": "Solar Utility Battery",
        "POP02": "Solar Battery Utility",
    }

    def __init__(
        self,
        failed_charger_commands=None,
        failed_output_commands=None,
    ):
        self.failed_charger_commands = set(
            failed_charger_commands or []
        )
        self.failed_output_commands = set(
            failed_output_commands or []
        )
        self.output_priority_raw = "Solar Battery Utility"
        self.calls = []

    def set_output_source_priority(self, command):
        self.calls.append(("menu_01", command))

        if command in self.failed_output_commands:
            return False

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
        publish_early_solar_handover_discovery(client)
        publish_grid_import_discovery(client)

        for topic, payload in client.discovery_payloads().items():
            if payload.get("device_class") != "energy":
                continue

            self.assertNotEqual(
                payload.get("state_class"),
                "measurement",
                topic,
            )

    def test_tariff_totals_are_long_term_statistics_sources(self):
        client = FakeMqttClient()
        publish_grid_import_discovery(client)
        discovery = client.discovery_payloads()

        for key in (
            "grid_import_night_total_estimated",
            "grid_import_normal_total_estimated",
        ):
            payload = discovery[f"homeassistant/sensor/energyhub_{key}/config"]
            self.assertEqual("energy", payload["device_class"])
            self.assertEqual("total_increasing", payload["state_class"])
            self.assertEqual("kWh", payload["unit_of_measurement"])

    def test_initial_hybrid_publish_replaces_retained_legacy_reason(self):
        client = FakeMqttClient()
        decision = HybridDecisionEngine()

        publish_hybrid_decision(client, decision)

        published = {
            topic: (payload, retain)
            for topic, payload, retain in client.published
        }
        reason, retained = published[
            "powmr/hybrid_decision_reason/state"
        ]
        status, status_retained = published[
            "powmr/hybrid_decision/state"
        ]

        self.assertEqual(
            reason,
            "No Adaptive Hybrid evaluation has been received since "
            "EnergyHub started; next scheduled evaluation is 23:50",
        )
        self.assertEqual(status, "awaiting_evaluation")
        self.assertTrue(retained)
        self.assertTrue(status_retained)
        self.assertLessEqual(len(reason), 255)

    def test_soc_anomaly_discovery_and_attributes_are_retained(self):
        client = FakeMqttClient()
        journal = SocAnomalyJournal(path=None)

        publish_soc_anomaly_journal_discovery(client)
        publish_soc_anomaly_journal(client, journal)

        discovery = client.discovery_payloads()
        latest = discovery[
            "homeassistant/sensor/energyhub_soc_anomaly_latest/config"
        ]
        self.assertEqual("timestamp", latest["device_class"])
        self.assertEqual(
            "powmr/soc_anomaly_latest/attributes",
            latest["json_attributes_topic"],
        )
        published = {
            topic: (payload, retained)
            for topic, payload, retained in client.published
        }
        attributes, retained = published[
            "powmr/soc_anomaly_latest/attributes"
        ]
        self.assertTrue(retained)
        self.assertEqual(0, json.loads(attributes)["event_count"])

    def test_inverter_fault_discovery_publishes_current_and_three_recent(self):
        client = FakeMqttClient()
        journal = InverterFaultJournal(path=None)

        publish_inverter_fault_journal_discovery(client)
        publish_inverter_fault_journal(client, journal)

        discovery = client.discovery_payloads()
        self.assertIn(
            "homeassistant/sensor/energyhub_inverter_fault_current/config",
            discovery,
        )
        for position in range(1, 4):
            key = f"inverter_fault_recent_{position}"
            payload = discovery[
                f"homeassistant/sensor/energyhub_{key}/config"
            ]
            self.assertEqual(
                f"sensor.energyhub_{key}", payload["default_entity_id"]
            )
            self.assertEqual(
                f"powmr/{key}/attributes", payload["json_attributes_topic"]
            )

    def test_inverter_fault_states_respect_home_assistant_limit(self):
        client = FakeMqttClient()
        journal = InverterFaultJournal(path=None)
        journal.current_state = lambda: "C" * 400
        journal.event_state = lambda _position: "E" * 400

        publish_inverter_fault_journal(client, journal)

        state_payloads = [
            payload
            for topic, payload, _retained in client.published
            if topic.endswith("/state")
        ]
        self.assertTrue(state_payloads)
        self.assertTrue(all(len(payload) == 255 for payload in state_payloads))

    def test_initial_hybrid_publish_explains_retained_target(self):
        client = FakeMqttClient()
        decision = HybridDecisionEngine(retained_target_soc=30)

        publish_hybrid_decision(client, decision)

        published = {
            topic: payload
            for topic, payload, _retain in client.published
        }
        self.assertEqual(
            published["powmr/hybrid_decision_reason/state"],
            "Detailed night plan is unavailable after EnergyHub restart; "
            "retained target 30.0%; next evaluation is 23:50",
        )

    def test_hybrid_reason_has_a_publisher_boundary_limit(self):
        client = FakeMqttClient()
        decision = SimpleNamespace(
            mqtt_values=lambda: {
                "hybrid_decision_reason": "x" * 355,
            }
        )

        publish_hybrid_decision(client, decision)

        _topic, payload, retained = client.published[-1]
        self.assertEqual(len(payload), 255)
        self.assertTrue(retained)


class EarlySolarHandoverTests(unittest.TestCase):
    NOW = datetime.fromisoformat("2026-08-15T06:05:00+03:00")

    def setUp(self):
        self.engine = EarlySolarHandoverEngine()

    def evaluate(self, **overrides):
        values = {
            "autopilot_enabled": True,
            "operating_mode": "hybrid_grid_hold",
            "battery_soc": 30,
            "hybrid_target_soc": 30,
            "telemetry_freshness": "fresh",
            "total_solar_fresh": True,
            "total_solar_power_w": 300,
            "forecast_energy_kwh": 1.6,
            "grid_available": True,
            "request_date": "2026-08-15",
            "now": self.NOW,
        }
        values.update(overrides)
        return self.engine.evaluate(**values)

    def test_exact_thresholds_request_early_solar(self):
        decision = self.evaluate()

        self.assertEqual(decision["status"], "release_requested")
        self.assertEqual(decision["request"], "solar")
        self.assertIn("300 W", decision["reason"])
        self.assertIn("1.60 kWh", decision["reason"])

    def test_confirmed_transition_becomes_released(self):
        self.evaluate()
        result = self.engine.confirm_transition(True)

        self.assertEqual(result["status"], "released")
        self.assertIn("transition confirmed", result["reason"])

    def test_failed_transition_remains_observable(self):
        self.evaluate()
        result = self.engine.confirm_transition(False, "Menu 01 mismatch")

        self.assertEqual(result["status"], "transition_failed")
        self.assertIn("Menu 01 mismatch", result["reason"])

    def test_non_hold_modes_are_not_applicable(self):
        for mode in ("solar", "hybrid_charging", "panic", "unknown"):
            with self.subTest(mode=mode):
                decision = self.evaluate(operating_mode=mode)
                self.assertEqual(decision["status"], "not_applicable")
                self.assertIsNone(decision["request"])

    def test_autopilot_disabled_is_not_applicable(self):
        decision = self.evaluate(autopilot_enabled=False)
        self.assertEqual(decision["status"], "not_applicable")

    def test_time_window_is_enforced_inside_energyhub(self):
        for now in (
            datetime.fromisoformat("2026-08-15T05:59:00+03:00"),
            datetime.fromisoformat("2026-08-15T07:00:00+03:00"),
        ):
            with self.subTest(now=now):
                decision = self.evaluate(now=now)
                self.assertEqual(decision["status"], "not_applicable")
                self.assertIsNone(decision["request"])

    def test_missing_or_unreached_target_holds(self):
        for target, soc in ((None, 30), (30, 29)):
            with self.subTest(target=target, soc=soc):
                decision = self.evaluate(
                    hybrid_target_soc=target,
                    battery_soc=soc,
                )
                self.assertEqual(decision["status"], "held")
                self.assertIsNone(decision["request"])

    def test_stale_inputs_or_offline_grid_hold(self):
        cases = (
            {"telemetry_freshness": "stale"},
            {"total_solar_fresh": False},
            {"grid_available": False},
            {"request_date": "2026-08-14"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                decision = self.evaluate(**overrides)
                self.assertEqual(decision["status"], "held")
                self.assertIsNone(decision["request"])

    def test_below_either_solar_threshold_holds(self):
        cases = (
            {"total_solar_power_w": 299.9},
            {"forecast_energy_kwh": 1.599},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                decision = self.evaluate(**overrides)
                self.assertEqual(decision["status"], "held")
                self.assertIsNone(decision["request"])

    def test_mqtt_values_publish_final_diagnostics(self):
        self.evaluate()
        self.engine.confirm_transition(True)
        client = FakeMqttClient()

        publish_early_solar_handover(client, self.engine)

        published = {
            topic: (payload, retained)
            for topic, payload, retained in client.published
        }
        self.assertEqual(
            published["powmr/hybrid_early_solar_check/state"],
            ("released", True),
        )
        self.assertEqual(
            published["powmr/hybrid_early_solar_live_power_w/state"],
            ("300.0", True),
        )


class MorningLoadProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.profile = MorningLoadProfileService(
            Path(self.temporary.name) / "morning.json"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def record_day(self, day, essential_values):
        house = 1.0
        heat = 10.0
        self.profile.record_snapshot({
            "captured_at": f"{day}T07:00:00+03:00",
            "date": day,
            "hour": 7,
            "house_kwh": house,
            "heat_pump_kwh": heat,
        })
        for hour, essential in zip(range(8, 13), essential_values):
            heat_delta = 0.4 if hour == 9 else 0.0
            house += essential + heat_delta
            heat += heat_delta
            self.profile.record_snapshot({
                "captured_at": f"{day}T{hour:02d}:00:00+03:00",
                "date": day,
                "hour": hour,
                "house_kwh": house,
                "heat_pump_kwh": heat,
            })

    def test_subtracts_heat_pumps_from_hourly_house_energy(self):
        self.record_day("2026-08-10", [0.5, 0.6, 0.7, 0.8, 0.9])

        profile = self.profile.profile()

        self.assertEqual(profile[7]["expected_kwh"], 0.5)
        self.assertEqual(profile[8]["expected_kwh"], 0.6)

    def test_rejects_non_finite_cumulative_energy(self):
        result = self.profile.record_snapshot({
            "captured_at": "2026-08-10T07:00:00+03:00",
            "date": "2026-08-10",
            "hour": 7,
            "house_kwh": float("nan"),
            "heat_pump_kwh": 10.0,
        })

        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "non-finite cumulative energy")
        self.assertEqual(self.profile.snapshots, {})

    def test_falls_back_until_three_complete_mornings_exist(self):
        self.record_day("2026-08-08", [0.5] * 5)
        self.record_day("2026-08-09", [0.6] * 5)

        plan = self.profile.flexible_plan([
            {"hour": hour, "power_w": 1000}
            for hour in range(7, 12)
        ])

        self.assertFalse(plan["available"])
        self.assertEqual(plan["sample_count"], 2)
        self.assertIn("learning 2/3", plan["reason"])

    def test_uses_75th_percentile_and_two_hour_solar_confirmation(self):
        self.record_day("2026-08-08", [0.4, 0.6, 0.8, 0.7, 0.5])
        self.record_day("2026-08-09", [0.5, 0.7, 0.9, 0.8, 0.6])
        self.record_day("2026-08-10", [0.6, 0.8, 1.0, 0.9, 0.7])
        solar = [
            {"hour": 7, "power_w": 100},
            {"hour": 8, "power_w": 400},
            {"hour": 9, "power_w": 1100},
            {"hour": 10, "power_w": 1000},
            {"hour": 11, "power_w": 1200},
        ]

        plan = self.profile.flexible_plan(solar)

        self.assertTrue(plan["available"])
        self.assertEqual(plan["support_time"], "09:00")
        self.assertEqual(plan["expected_load_kwh"], 3.3)
        self.assertEqual(plan["forecast_solar_kwh"], 2.6)
        self.assertEqual(plan["deficit_kwh"], 0.9)


class ReserveAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.advisor = ReserveAdvisorService(
            Path(self.temporary.name) / "advisor.json"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def observe(self, date_key, minimum, selected):
        return self.advisor.observe({
            "date": date_key,
            "minimum_soc": minimum,
            "selected_soc": selected,
        })["advisor"]

    def test_learns_until_three_comparable_mornings_exist(self):
        self.observe("2026-08-08", 25, 20)
        advice = self.observe("2026-08-09", 24, 20)

        self.assertEqual(advice["status"], "learning")
        self.assertEqual(advice["sample_count"], 2)

    def test_increases_after_two_low_mornings_out_of_three(self):
        self.observe("2026-08-08", 25, 20)
        self.observe("2026-08-09", 24, 20)
        advice = self.observe("2026-08-10", 40, 20)

        self.assertEqual(advice["status"], "increase")
        self.assertEqual(advice["suggested_soc"], 30)

    def test_decreases_only_after_three_comfortable_mornings(self):
        self.observe("2026-08-08", 55, 30)
        self.observe("2026-08-09", 54, 30)
        advice = self.observe("2026-08-10", 50, 30)

        self.assertEqual(advice["status"], "decrease")
        self.assertEqual(advice["suggested_soc"], 20)

    def test_setting_change_resets_comparable_window(self):
        self.observe("2026-08-08", 25, 20)
        self.observe("2026-08-09", 24, 20)
        self.observe("2026-08-10", 25, 20)

        advice = self.advisor.evaluate(30)

        self.assertEqual(advice["status"], "learning")
        self.assertEqual(advice["sample_count"], 0)

    def test_custom_setting_moves_to_next_safer_named_level(self):
        self.observe("2026-08-08", 29, 25)
        self.observe("2026-08-09", 30, 25)
        advice = self.observe("2026-08-10", 45, 25)

        self.assertEqual(advice["status"], "increase")
        self.assertEqual(advice["suggested_soc"], 30)


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
            "minimum_soc": 20,
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
        self.assertEqual(result["target_soc"], 50)
        self.assertIsNotNone(self.engine.evaluated_at)
        self.assertIn(
            "target 50.0% = 20% selected minimum + max(30.0% morning",
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
        self.assertAlmostEqual(result["target_soc"], 77.87)

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
        self.assertEqual(result["target_soc"], 50)

    def test_holds_when_soc_meets_target_but_would_fall_below_it(self):
        result = self.evaluate(battery_soc=55)

        self.assertEqual(result["status"], "hybrid_grid_hold")
        self.assertEqual(result["request"], "hybrid_grid_hold")
        self.assertEqual(result["projected_soc_at_07"], 40)
        self.assertEqual(result["target_soc"], 50)

    def test_stays_solar_when_projected_soc_meets_target(self):
        result = self.evaluate(battery_soc=65)

        self.assertEqual(result["status"], "solar")
        self.assertIsNone(result["request"])
        self.assertEqual(result["projected_soc_at_07"], 50)
        self.assertEqual(result["target_soc"], 50)

    def test_stays_solar_with_large_projected_surplus(self):
        result = self.evaluate(
            battery_soc=72,
            morning_hours=1,
        )

        self.assertEqual(result["status"], "solar")
        self.assertIsNone(result["request"])
        self.assertEqual(result["projected_soc_at_07"], 57)
        self.assertEqual(result["target_soc"], 30)
        self.assertIn("night-grid support is not required", result["reason"])
        self.assertLessEqual(
            len(self.engine.mqtt_values()["hybrid_decision_reason"]),
            255,
        )
        self.assertEqual(
            self.engine.mqtt_values()["hybrid_decision_reason"],
            "Projected 07:00 SOC 57.0% meets target 30.0%; remain Solar",
        )

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

        self.assertEqual(result["target_soc"], 70)
        self.assertEqual(result["morning_hours"], 5)
        self.assertTrue(result["used_fallback"])
        self.assertIn("fallback", result["reason"])

    def test_confirmed_300_to_600_w_ramp_gives_one_hour_credit(self):
        result = self.evaluate(
            battery_soc=38,
            morning_hours=1,
            raw_morning_hours=2,
            useful_solar_start="09:00",
            effective_solar_start="08:00",
            ramp_confirmed=True,
            ramp_credit_hours=1,
            ramp_start_power_w=1006.6,
            ramp_next_power_w=2396,
        )

        self.assertEqual(result["raw_morning_hours"], 2)
        self.assertEqual(result["ramp_credit_hours"], 1)
        self.assertEqual(result["morning_hours"], 1)
        self.assertEqual(result["effective_solar_start"], "08:00")
        self.assertEqual(result["target_soc"], 30)
        self.assertEqual(result["request"], "hybrid_grid_hold")

    def test_addon_rejects_unconfirmed_ramp_credit(self):
        result = self.evaluate(
            raw_morning_hours=2,
            useful_solar_start="09:00",
            effective_solar_start="08:00",
            ramp_confirmed=True,
            ramp_credit_hours=1,
            ramp_start_power_w=300,
            ramp_next_power_w=599,
        )

        self.assertFalse(result["ramp_confirmed"])
        self.assertEqual(result["ramp_credit_hours"], 0)
        self.assertEqual(result["morning_hours"], 2)
        self.assertEqual(result["effective_solar_start"], "09:00")
        self.assertEqual(result["target_soc"], 40)

    def test_selected_minimum_soc_replaces_hidden_margin(self):
        result = self.evaluate(
            morning_hours=0,
            minimum_soc=50,
        )

        self.assertEqual(result["minimum_soc"], 50)
        self.assertEqual(result["target_soc"], 50)

    def test_learned_net_energy_replaces_fixed_ten_percent_per_hour(self):
        result = self.evaluate(
            morning_hours=3,
            flexible_morning_plan={
                "available": True,
                "reason": "learned essential load",
                "sample_count": 5,
                "expected_load_kwh": 2.7,
                "forecast_solar_kwh": 1.0,
                "deficit_kwh": 1.7,
                "support_time": "10:00",
            },
        )

        self.assertEqual(result["morning_model_source"], "learned_net_energy")
        self.assertEqual(result["effective_solar_start"], "10:00")
        self.assertAlmostEqual(result["morning_reserve_soc"], 11.81)
        self.assertAlmostEqual(result["target_soc"], 31.81)

    def test_learning_model_falls_back_to_legacy_ramp(self):
        result = self.evaluate(
            morning_hours=2,
            flexible_morning_plan={
                "available": False,
                "reason": "learning 2/3 samples",
                "sample_count": 2,
            },
        )

        self.assertEqual(result["morning_model_source"], "verified_ramp_fallback")
        self.assertEqual(result["morning_reserve_soc"], 20)
        self.assertEqual(result["target_soc"], 40)
        self.assertIn("learning 2/3", self.engine.calculation)

    def test_ahm_overtakes_panic_at_2350(self):
        result = self.evaluate(
            operating_mode="panic",
            battery_soc=45,
        )

        self.assertEqual(result["request"], "hybrid")

    def test_ahm_restores_solar_from_panic_hold_when_soc_is_sufficient(self):
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
        self.assertEqual(
            self.engine.mqtt_values()["panic_ahm_target_soc"],
            "None",
        )

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

    def test_normal_grid_enters_hold_at_exactly_20_percent(self):
        result = self.evaluate(
            grid_confidence="normal",
            battery_soc=20,
        )

        self.assertEqual(result["status"], "trigger_grid_hold")
        self.assertEqual(result["request"], "panic_grid_hold")
        self.assertEqual(result["release_soc"], 30)

    def test_normal_grid_floor_requests_immediate_evaluation(self):
        self.assertTrue(
            self.engine.requires_immediate_evaluation(
                operating_mode="solar",
                grid_confidence="normal",
                battery_soc=20,
                grid_available=True,
                now=datetime(2026, 8, 1, 13, 0),
            )
        )

    def test_normal_grid_floor_waits_without_transition_while_grid_is_offline(self):
        result = self.evaluate(
            grid_confidence="normal",
            battery_soc=20,
            grid_available=False,
        )

        self.assertEqual(result["status"], "waiting_for_grid")
        self.assertIsNone(result["request"])
        self.assertEqual(result["phase"], "waiting_for_grid")

        self.assertFalse(
            self.engine.requires_immediate_evaluation(
                operating_mode="solar",
                grid_confidence="normal",
                battery_soc=20,
                grid_available=False,
                now=datetime(2026, 8, 1, 13, 0),
            )
        )

    def test_normal_grid_below_floor_stays_solar_while_grid_is_offline(self):
        result = self.evaluate(
            grid_confidence="normal",
            battery_soc=15,
            grid_available=False,
        )

        self.assertEqual(result["status"], "waiting_for_grid")
        self.assertIsNone(result["request"])
        self.assertEqual(result["phase"], "waiting_for_grid")

    def test_normal_grid_hold_releases_solar_at_30_percent(self):
        result = self.evaluate(
            operating_mode="panic_grid_hold",
            grid_confidence="normal",
            battery_soc=30,
        )

        self.assertEqual(result["status"], "release_solar")
        self.assertEqual(result["request"], "solar")

    def test_normal_grid_release_requests_immediate_evaluation(self):
        self.assertTrue(
            self.engine.requires_immediate_evaluation(
                operating_mode="panic_grid_hold",
                grid_confidence="normal",
                battery_soc=30,
                grid_available=True,
                now=datetime(2026, 8, 1, 13, 0),
            )
        )

    def test_immediate_release_requires_grid_and_daytime_window(self):
        self.assertFalse(
            self.engine.requires_immediate_evaluation(
                operating_mode="panic_grid_hold",
                grid_confidence="normal",
                battery_soc=30,
                grid_available=False,
                now=datetime(2026, 8, 1, 13, 0),
            )
        )
        self.assertFalse(
            self.engine.requires_immediate_evaluation(
                operating_mode="solar",
                grid_confidence="normal",
                battery_soc=20,
                grid_available=True,
                now=datetime(2026, 8, 1, 6, 59),
            )
        )

    def test_normal_grid_hold_waits_below_30_percent(self):
        result = self.evaluate(
            operating_mode="panic_grid_hold",
            grid_confidence="normal",
            battery_soc=29,
        )

        self.assertEqual(result["status"], "grid_hold")
        self.assertIsNone(result["request"])

    def test_0700_handoff_keeps_confirmed_hold_below_30_percent(self):
        result = self.evaluate(
            operating_mode="hybrid_grid_hold",
            grid_confidence="normal",
            battery_soc=20,
            now=datetime(2026, 8, 1, 7, 0),
        )

        self.assertEqual(result["status"], "handoff_to_grid_hold")
        self.assertEqual(result["request"], "panic_grid_hold")
        self.assertEqual(result["target_soc"], 20)

    def test_0700_handoff_releases_solar_at_30_percent(self):
        result = self.evaluate(
            operating_mode="hybrid_grid_hold",
            grid_confidence="normal",
            battery_soc=30,
            now=datetime(2026, 8, 1, 7, 0),
        )

        self.assertEqual(result["status"], "handoff_to_solar")
        self.assertEqual(result["request"], "solar")

    def test_normal_release_waits_while_grid_is_offline(self):
        result = self.evaluate(
            operating_mode="panic_grid_hold",
            grid_confidence="normal",
            battery_soc=30,
            grid_available=False,
        )

        self.assertEqual(result["status"], "grid_hold")
        self.assertIsNone(result["request"])

    def test_non_normal_hold_does_not_use_30_percent_release(self):
        result = self.evaluate(
            operating_mode="panic_grid_hold",
            grid_confidence="unstable",
            battery_soc=60,
        )

        self.assertEqual(result["status"], "grid_hold")
        self.assertIsNone(result["request"])
        self.assertIsNone(result["release_soc"])

    def test_missed_ahm_debt_disables_normal_30_percent_cycle(self):
        result = self.evaluate(
            operating_mode="panic_grid_hold",
            grid_confidence="normal",
            battery_soc=69,
            ahm_target_soc=70,
        )

        self.assertEqual(result["status"], "trigger_charge")
        self.assertEqual(result["request"], "panic")
        self.assertIsNone(result["release_soc"])

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

    def test_daytime_panic_takes_over_active_hybrid_charging(self):
        result = self.evaluate(
            operating_mode="hybrid_charging",
            grid_confidence="panic",
            battery_soc=10,
        )

        self.assertEqual(result["status"], "handoff_to_charging")
        self.assertEqual(result["request"], "panic")

    def test_nighttime_hybrid_strategy_is_not_interrupted(self):
        result = self.evaluate(
            operating_mode="hybrid_charging",
            grid_confidence="panic",
            battery_soc=10,
            now=datetime(2026, 8, 1, 6, 59),
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
    def test_enter_hybrid_clears_stale_panic_context_before_writes(
        self,
        _sleep,
    ):
        controller = self.make_controller()
        controller.set_panic_target_soc(80)

        self.assertTrue(controller.enter_hybrid())
        self.assertIsNone(controller.panic_target_soc)
        self.assertEqual(controller.mode, "hybrid_charging")

    def test_hybrid_writes_are_blocked_if_panic_context_cannot_persist_clear(self):
        inverter = FakeInverter()
        controller = self.make_controller(inverter)
        controller.panic_target_soc = 80
        controller._persist_state = lambda: False

        self.assertFalse(controller.enter_hybrid())
        self.assertEqual("transition_failed", controller.mode)
        self.assertEqual([], inverter.calls)

    @patch(
        "app.services.inverter_controller.time.sleep",
        return_value=None,
    )
    def test_hybrid_menu_01_failure_attempts_solar_recovery(
        self,
        _sleep,
    ):
        inverter = FakeInverter(failed_output_commands={"POP01"})
        controller = self.make_controller(inverter)

        self.assertFalse(controller.enter_hybrid())
        self.assertEqual(controller.mode, "solar")
        self.assertIn(("menu_16", "PCP02"), inverter.calls)
        self.assertIn(("menu_01", "POP02"), inverter.calls)

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

    def test_persists_dated_hybrid_night_enforcement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.json"
            controller = InverterController(
                FakeInverter(),
                state_path=path,
            )
            self.assertTrue(controller.set_hybrid_target_soc(35))
            self.assertTrue(
                controller.set_hybrid_enforcement_until_date(
                    "2026-08-19"
                )
            )

            restored = InverterController(
                FakeInverter(),
                state_path=path,
            )
            self.assertEqual(restored.hybrid_target_soc, 35)
            self.assertEqual(
                restored.hybrid_enforcement_until_date,
                "2026-08-19",
            )

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

    @patch(
        "app.services.inverter_controller.time.sleep",
        return_value=None,
    )
    def test_enter_panic_menu_01_failure_attempts_solar_recovery(
        self,
        _sleep,
    ):
        inverter = FakeInverter(failed_output_commands={"POP01"})
        controller = self.make_controller(inverter)

        self.assertFalse(controller.enter_panic())
        self.assertEqual(controller.mode, "solar")
        self.assertIsNone(controller.panic_target_soc)
        self.assertIn(("menu_16", "PCP02"), inverter.calls)
        self.assertIn(("menu_01", "POP02"), inverter.calls)

    def test_transfers_confirmed_hybrid_hold_without_writing(self):
        inverter = FakeInverter()
        controller = self.make_controller(inverter)
        controller.mode = "hybrid_grid_hold"
        controller.confirmed_mode = "hybrid_grid_hold"
        controller.known_charger_priority = "OSO"
        controller.set_panic_target_soc(20)

        result = controller.transfer_hybrid_hold_to_panic()

        self.assertTrue(result)
        self.assertEqual(controller.mode, "panic_grid_hold")
        self.assertEqual(controller.panic_target_soc, 20)
        self.assertEqual(inverter.calls, [])

    def test_transfers_confirmed_hybrid_charging_without_writing(self):
        inverter = FakeInverter()
        controller = self.make_controller(inverter)
        controller.mode = "hybrid_charging"
        controller.confirmed_mode = "hybrid_charging"
        controller.known_charger_priority = "SNU"
        controller.set_panic_target_soc(80)

        result = controller.transfer_hybrid_charging_to_panic()

        self.assertTrue(result)
        self.assertEqual(controller.mode, "panic")
        self.assertEqual(controller.confirmed_mode, "panic")
        self.assertEqual(controller.panic_target_soc, 80)
        self.assertEqual(inverter.calls, [])

    def test_rejects_unconfirmed_grid_hold_transfer(self):
        controller = self.make_controller()
        controller.mode = "hybrid_grid_hold"
        controller.confirmed_mode = "hybrid_grid_hold"
        controller.known_charger_priority = "SNU"
        controller.set_panic_target_soc(20)

        result = controller.transfer_hybrid_hold_to_panic()

        self.assertFalse(result)
        self.assertEqual(controller.mode, "hybrid_grid_hold")


if __name__ == "__main__":
    unittest.main()
