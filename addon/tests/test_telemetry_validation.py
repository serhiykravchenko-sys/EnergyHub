import math
import sys
from types import ModuleType, SimpleNamespace
import unittest

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

from app.mqtt.publisher import is_valid_value, publish_values
from app.services.battery_health import BatteryHealthMonitor
from app.services.telemetry import TelemetryService


class FakeMqttClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))


class TelemetryValidationTests(unittest.TestCase):
    def test_publisher_rejects_non_finite_numeric_values(self):
        for value in (math.nan, math.inf, -math.inf, "nan", "inf"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_value("battery_voltage", value))

        client = FakeMqttClient()
        publish_values(
            client,
            {"battery_voltage": math.nan},
            {},
        )
        self.assertFalse(any("battery_voltage/state" in item[0]
                             for item in client.published))

    def test_required_non_finite_value_invalidates_control_state(self):
        service = TelemetryService(FakeMqttClient())
        state = service.create_state({
            "battery_capacity": math.nan,
            "ac_output_active_power": 500,
            "pv1_charging_power": 700,
            "ac_input_voltage": 230,
        })

        self.assertFalse(state.valid)
        self.assertIsNone(state.battery_soc)

    def test_out_of_range_soc_invalidates_control_state(self):
        service = TelemetryService(FakeMqttClient())
        state = service.create_state({
            "battery_capacity": 101,
            "ac_output_active_power": 500,
            "pv1_charging_power": 700,
            "ac_input_voltage": 230,
        })

        self.assertFalse(state.valid)

    def test_battery_health_reports_non_finite_and_out_of_range_soc(self):
        for value in (math.nan, math.inf, -1, 101):
            with self.subTest(value=value):
                monitor = BatteryHealthMonitor()
                monitor.update(SimpleNamespace(battery_soc=value))
                self.assertEqual("warning", monitor.status)
                self.assertEqual("soc_invalid", monitor.reason)


if __name__ == "__main__":
    unittest.main()
