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
from app.services.inverter_controller import InverterController, atomic_write_json
from app.utils import json_store
from app.services.panic_decision import PanicDecisionEngine
from app.services.telemetry_freshness import TelemetryFreshnessMonitor
from app.mqtt.publisher import (
    publish_daily_summary_discovery,
    publish_grid_import,
    publish_grid_import,
    publish_retired_entity_cleanup,
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
    def test_missing_period_total_clears_retained_state_without_unknown_text(self):
        client = FakeMqttClient()
        service = SimpleNamespace(
            mqtt_values=lambda: {
                "grid_import_normal_previous_month_estimated": None,
            }
        )

        publish_grid_import(client, service)

        self.assertEqual(
            [("powmr/grid_import_normal_previous_month_estimated/state", "", True)],
            client.published,
        )

    def test_missing_period_total_clears_retained_state_without_unknown_text(self):
        client = FakeMqttClient()
        service = SimpleNamespace(
            mqtt_values=lambda: {
                "grid_import_normal_previous_month_estimated": None,
            }
        )

        publish_grid_import(client, service)

        self.assertEqual(
            [
                (
                    "powmr/grid_import_normal_previous_month_estimated/state",
                    "",
                    True,
                )
            ],
            client.published,
        )

    def test_snapshot_energy_entities_do_not_use_measurement(self):
        client = FakeMqttClient()
        publish_daily_summary_discovery(client)
        publish_grid_import_discovery(client)

        for topic, payload in client.discovery_payloads().items():
            if payload.get("device_class") != "energy":
                continue

            self.assertNotEqual(
                payload.get("state_class"),
                "measurement",
                topic,
            )

    def test_optional_numeric_daily_states_render_unknown_as_none(self):
        client = FakeMqttClient()
        publish_daily_summary_discovery(client)
        discovery = client.discovery_payloads()
        for key in ("daily_solar_actual", "daily_solar_forecast_error_percent"):
            config = discovery[f"homeassistant/sensor/energyhub_{key}/config"]
            self.assertEqual("{{ value | float(none) }}", config["value_template"])

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

    def test_retired_entities_and_input_topics_are_cleared_retained(self):
        client = FakeMqttClient()

        publish_retired_entity_cleanup(client)

        published = {
            topic: (payload, retained)
            for topic, payload, retained in client.published
        }
        for topic in (
            "homeassistant/sensor/energyhub_hybrid_calculation/config",
            "powmr/hybrid_calculation/state",
            "homeassistant/sensor/energyhub_ahm_reserve_advice/config",
            "energyhub/input/ha/adaptive_hybrid_plan",
            "energyhub/input/ha/peak_load_guard_plugs",
        ):
            self.assertEqual((b"", True), published[topic])

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

    def test_malformed_persisted_state_does_not_prevent_startup(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.json"
            for document in ([], {"schema_version": 3,
                                   "confirmed_mode": "solar",
                                   "known_charger_priority": "OSO",
                                   "panic_target_soc": "broken"},
                             {"schema_version": 3,
                              "confirmed_mode": {},
                              "known_charger_priority": [],
                              "panic_target_soc": "nan"}):
                with self.subTest(document=document):
                    path.write_text(json.dumps(document), encoding="utf-8")
                    controller = InverterController(FakeInverter(), state_path=path)
                    self.assertIsNone(controller.panic_target_soc)
                    self.assertEqual("unknown", controller.mode)

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

    @patch("app.services.inverter_controller.time.sleep", return_value=None)
    def test_menu_16_ack_without_durable_save_cannot_reconstruct_old_hold(self, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.json"
            inverter = FakeInverter()
            controller = InverterController(inverter, state_path=path)
            controller.confirmed_mode = controller.mode = "panic_grid_hold"
            controller.known_charger_priority = "OSO"
            controller.panic_target_soc = 50
            self.assertTrue(controller._persist_state())

            writes = 0

            def fail_after_two_writes(*args, **kwargs):
                nonlocal writes
                writes += 1
                if writes >= 3:
                    raise OSError("journal became unavailable")
                return atomic_write_json(*args, **kwargs)

            with patch("app.services.inverter_controller.atomic_write_json",
                       side_effect=fail_after_two_writes):
                self.assertFalse(controller.enter_panic())
            self.assertEqual("transition_failed", controller.mode)
            self.assertIn(("menu_16", "PCP01"), inverter.calls)
            self.assertTrue(json.loads(path.read_text())["transition_pending"])

            restarted = InverterController(inverter, state_path=path)
            self.assertFalse(restarted.reconstruct_mode("SUB"))
            self.assertEqual("inconsistent", restarted.mode)

    def test_journal_failure_before_first_write_blocks_hardware(self):
        inverter = FakeInverter()
        controller = self.make_controller(inverter)
        controller._persist_state = lambda: False
        self.assertFalse(controller.set_output_priority("SUB"))
        self.assertEqual([], inverter.calls)

    def test_directory_sync_io_failure_blocks_first_inverter_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.json"
            inverter = FakeInverter()
            controller = InverterController(inverter, state_path=path)
            with patch("app.utils.json_store._fsync_directory",
                       side_effect=OSError("directory I/O failure")):
                self.assertFalse(controller.set_output_priority("SUB"))
            self.assertEqual([], inverter.calls)
            self.assertTrue(controller.persistence_fault)
            self.assertEqual("transition_failed", controller.mode)

    def test_directory_sync_error_is_not_silenced_on_posix(self):
        with patch.object(json_store.os, "name", "posix"), \
             patch.object(json_store.os, "open", return_value=31), \
             patch.object(json_store.os, "fsync",
                          side_effect=OSError("directory I/O failure")), \
             patch.object(json_store.os, "close") as close:
            with self.assertRaises(OSError):
                json_store._fsync_directory(Path("/data"))
            close.assert_called_once_with(31)

    @patch("app.services.inverter_controller.time.sleep", return_value=None)
    def test_final_mode_save_failure_does_not_report_success(self, _sleep):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.json"
            inverter = FakeInverter()
            controller = InverterController(inverter, state_path=path)
            controller.panic_target_soc = 50
            self.assertTrue(controller._persist_state())
            writes = 0

            def fail_final_save(*args, **kwargs):
                nonlocal writes
                writes += 1
                if writes >= 4:
                    raise OSError("final mode save failed")
                return atomic_write_json(*args, **kwargs)

            with patch("app.services.inverter_controller.atomic_write_json",
                       side_effect=fail_final_save):
                self.assertFalse(controller.enter_panic())
            self.assertEqual("transition_failed", controller.mode)
            self.assertTrue(json.loads(path.read_text())["transition_pending"])
            restarted = InverterController(inverter, state_path=path)
            self.assertFalse(restarted.reconstruct_mode("SUB"))

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
        self.assertFalse(controller.set_panic_target_soc(float("nan")))
        self.assertFalse(controller.set_panic_target_soc(float("inf")))
        self.assertFalse(
            controller.set_panic_target_soc("invalid")
        )
        self.assertIsNone(controller.panic_target_soc)

    def test_preserves_decimal_panic_target(self):
        controller = self.make_controller()

        self.assertTrue(controller.set_panic_target_soc(87.87))
        self.assertEqual(controller.panic_target_soc, 87.87)

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
