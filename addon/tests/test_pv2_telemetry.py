import json
import math
import sys
import threading
from types import ModuleType
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

from app.adapters.powmr import (
    ModbusCrcError,
    ModbusInvalidValueError,
    ModbusMalformedResponseError,
    ModbusTimeoutError,
    ModbusUnsupportedError,
    PowMrLocalAdapter,
    build_pv2_request,
    decode_pv2_response,
    modbus_crc,
)
from app.mqtt.publisher import (
    publish_pv2_discovery,
    publish_pv2_telemetry,
)
from app.services.pv2_telemetry import PV2TelemetryService


def frame(payload):
    return payload + modbus_crc(payload).to_bytes(2, "little")


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


class FakeMqttClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    def last_payload(self, topic):
        return [
            payload
            for published_topic, payload, _retain in self.published
            if published_topic == topic
        ][-1]


class FakeSerial:
    def __init__(self, response, **settings):
        self.response = bytearray(response)
        self.settings = settings
        self.written = b""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def write(self, data):
        self.written += data
        return len(data)

    def flush(self):
        pass

    def read(self, size):
        result = self.response[:size]
        del self.response[:size]
        return bytes(result)


class FakeInverter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.pi30_reads = 0

    def read_pv2_telemetry(self):
        if self.error:
            raise self.error
        return self.result

    def read_telemetry(self):
        self.pi30_reads += 1
        return {"pv1_charging_power": 500}


class ModbusProtocolTests(unittest.TestCase):
    def test_request_matches_verified_read_only_frame(self):
        request = build_pv2_request()
        self.assertEqual(request.hex(" ").upper(), "05 03 11 D3 00 02 31 4A")

    def test_decodes_verified_byte_swapped_sample_and_scale(self):
        values = decode_pv2_response(
            bytes.fromhex("05 03 04 C6 0D 8A 0D B4 1D")
        )
        self.assertEqual(values["pv2_input_voltage"], 352.6)
        self.assertEqual(values["pv2_charging_power"], 3466)

    def test_decodes_verified_curtailed_sample(self):
        values = decode_pv2_response(
            bytes.fromhex("05 03 04 78 0F FB 00 D4 60")
        )
        self.assertEqual(values["pv2_input_voltage"], 396.0)
        self.assertEqual(values["pv2_charging_power"], 251)

    def test_rejects_crc_failure(self):
        response = bytearray.fromhex("05 03 04 C6 0D 8A 0D B4 1D")
        response[-1] ^= 0xFF
        with self.assertRaises(ModbusCrcError):
            decode_pv2_response(bytes(response))

    def test_rejects_malformed_byte_count(self):
        response = frame(bytes.fromhex("05 03 02 C6 0D"))
        with self.assertRaises(ModbusMalformedResponseError):
            decode_pv2_response(response)

    def test_rejects_wrong_slave_and_function(self):
        wrong_slave = frame(bytes.fromhex("06 03 04 C6 0D 8A 0D"))
        wrong_function = frame(bytes.fromhex("05 04 04 C6 0D 8A 0D"))
        with self.assertRaises(ModbusMalformedResponseError):
            decode_pv2_response(wrong_slave)
        with self.assertRaises(ModbusMalformedResponseError):
            decode_pv2_response(wrong_function)

    def test_rejects_out_of_range_values(self):
        # 7000 is returned as swapped bytes and scales to 700.0 V.
        response = frame(bytes.fromhex("05 03 04 58 1B 00 00"))
        with self.assertRaises(ModbusInvalidValueError):
            decode_pv2_response(response)

    def test_classifies_unsupported_register_exception(self):
        response = frame(bytes.fromhex("05 83 02"))
        with self.assertRaises(ModbusUnsupportedError):
            decode_pv2_response(response)

    def test_adapter_times_out_on_no_response(self):
        adapter = PowMrLocalAdapter({
            "serial_port": "test",
            "protocol": "PI30MAX",
            "command": "QPIGS",
            "_serial_factory": lambda **kwargs: FakeSerial(b"", **kwargs),
        })
        with self.assertRaises(ModbusTimeoutError):
            adapter.read_pv2_telemetry()

    def test_adapter_writes_only_verified_request(self):
        serial_connection = FakeSerial(
            bytes.fromhex("05 03 04 C6 0D 8A 0D B4 1D")
        )
        adapter = PowMrLocalAdapter({
            "serial_port": "test",
            "protocol": "PI30MAX",
            "command": "QPIGS",
            "_serial_factory": lambda **_kwargs: serial_connection,
        })
        values = adapter.read_pv2_telemetry()
        self.assertEqual(
            serial_connection.written,
            bytes.fromhex("05 03 11 D3 00 02 31 4A"),
        )
        self.assertEqual(values["pv2_charging_power"], 3466)

    def test_pi30_command_waits_for_the_adapter_serial_lock(self):
        adapter = PowMrLocalAdapter({
            "serial_port": "test",
            "protocol": "PI30MAX",
            "command": "QPIGS",
            "_serial_factory": lambda **kwargs: FakeSerial(b"", **kwargs),
        })
        command_started = threading.Event()

        def fake_check_output(*_args, **_kwargs):
            command_started.set()
            return "{}"

        adapter._serial_lock.acquire()
        try:
            with patch(
                "app.adapters.powmr.subprocess.check_output",
                side_effect=fake_check_output,
            ):
                worker = threading.Thread(target=adapter.read_telemetry)
                worker.start()
                self.assertFalse(command_started.wait(0.05))
                adapter._serial_lock.release()
                worker.join(1)
                self.assertTrue(command_started.is_set())
        finally:
            if adapter._serial_lock.locked():
                adapter._serial_lock.release()


class PV2TelemetryServiceTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.service = PV2TelemetryService(True, 30, self.clock)

    def test_builds_total_only_from_aligned_fresh_samples(self):
        inverter = FakeInverter({
            "pv2_input_voltage": 352.6,
            "pv2_charging_power": 3466,
        })
        self.assertTrue(self.service.poll(inverter, 700, 99.0))
        self.assertEqual(self.service.last_total_power, 4166.0)
        self.assertTrue(self.service.total_is_fresh())

    def test_rejects_total_when_samples_are_not_aligned(self):
        inverter = FakeInverter({
            "pv2_input_voltage": 352.6,
            "pv2_charging_power": 3466,
        })
        self.assertTrue(self.service.poll(inverter, 700, 80.0))
        self.assertIsNone(self.service.last_total_power)
        self.assertFalse(self.service.total_is_fresh())

    def test_rejects_non_finite_or_out_of_range_pv1_from_total(self):
        inverter = FakeInverter({
            "pv2_input_voltage": 352.6,
            "pv2_charging_power": 3466,
        })
        self.service.poll(inverter, math.nan, 99.0)
        self.assertIsNone(self.service.last_total_power)

        self.clock.value = 140.0
        self.service.poll(inverter, 13000, 139.0)
        self.assertIsNone(self.service.last_total_power)

    def test_failure_retains_value_but_marks_it_stale(self):
        good = FakeInverter({
            "pv2_input_voltage": 352.6,
            "pv2_charging_power": 3466,
        })
        self.service.poll(good, 700, 99.0)
        self.assertFalse(
            self.service.poll(
                FakeInverter(error=ModbusCrcError()),
                700,
                100.0,
            )
        )
        self.assertEqual(self.service.last_power, 3466)
        self.assertEqual(self.service.status, "crc_error")
        self.assertEqual(self.service.freshness, "stale")
        self.clock.value = 200.0
        self.service.refresh()
        self.assertEqual(self.service.status, "crc_error")

        client = FakeMqttClient()
        publish_pv2_telemetry(client, self.service)
        self.assertEqual(
            client.last_payload("powmr/pv2_charging_power/state"),
            "3466",
        )
        self.assertEqual(client.last_payload("powmr/pv2/status"), "offline")

    def test_maps_bounded_protocol_failures_to_diagnostics(self):
        cases = [
            (ModbusTimeoutError(), "timeout"),
            (ModbusMalformedResponseError(), "malformed_response"),
            (ModbusInvalidValueError(), "invalid_value"),
        ]

        for error, expected_status in cases:
            with self.subTest(expected_status):
                service = PV2TelemetryService(True, 30, self.clock)
                self.assertFalse(
                    service.poll(
                        FakeInverter(error=error),
                        700,
                        99.0,
                    )
                )
                self.assertEqual(service.status, expected_status)
                self.assertEqual(service.freshness, "stale")

    def test_sample_expires_and_total_expires_with_pv1(self):
        inverter = FakeInverter({
            "pv2_input_voltage": 352.6,
            "pv2_charging_power": 3466,
        })
        self.service.poll(inverter, 700, 99.0)
        self.clock.value = 161.0
        self.assertFalse(self.service.total_is_fresh())
        self.assertEqual(self.service.status, "fresh")
        self.clock.value = 170.0
        self.service.refresh()
        self.assertEqual(self.service.status, "stale")

    def test_long_poll_interval_keeps_aligned_pv1_fresh_until_next_poll(self):
        service = PV2TelemetryService(True, 60, self.clock)
        inverter = FakeInverter({
            "pv2_input_voltage": 352.6,
            "pv2_charging_power": 3466,
        })
        service.poll(inverter, 700, 99.0)

        self.clock.value = 160.0

        self.assertTrue(service.total_is_fresh())

    def test_unsupported_modbus_does_not_block_next_pi30_read(self):
        inverter = FakeInverter(error=ModbusUnsupportedError())
        self.assertFalse(self.service.poll(inverter, 700, 99.0))
        data = inverter.read_telemetry()
        self.assertEqual(data["pv1_charging_power"], 500)
        self.assertEqual(inverter.pi30_reads, 1)
        self.assertEqual(self.service.status, "unsupported")
        self.assertFalse(self.service.due())

    def test_restart_does_not_reconstruct_retained_value_as_fresh(self):
        restarted = PV2TelemetryService(True, 30, self.clock)
        client = FakeMqttClient()
        publish_pv2_telemetry(client, restarted)
        self.assertIsNone(restarted.last_power)
        self.assertEqual(restarted.status, "awaiting_sample")
        self.assertEqual(client.last_payload("powmr/pv2/status"), "offline")
        self.assertEqual(
            client.last_payload("powmr/total_pv/status"),
            "offline",
        )

    def test_disabled_configuration_never_polls(self):
        disabled = PV2TelemetryService(False, 30, self.clock)
        self.assertFalse(disabled.due())
        self.assertEqual(disabled.status, "disabled")


class PV2MqttTests(unittest.TestCase):
    def test_discovery_uses_dedicated_measurement_availability(self):
        client = FakeMqttClient()
        publish_pv2_discovery(client)
        configs = {
            topic: json.loads(payload)
            for topic, payload, _retain in client.published
            if topic.endswith("/config")
        }
        pv2 = configs[
            "homeassistant/sensor/powmr_10_2m_pv2_charging_power/config"
        ]
        total = configs[
            "homeassistant/sensor/powmr_10_2m_total_pv_power/config"
        ]
        self.assertEqual(pv2["availability"][1]["topic"], "powmr/pv2/status")
        self.assertEqual(
            total["availability"][1]["topic"],
            "powmr/total_pv/status",
        )
        age = configs["homeassistant/sensor/energyhub_pv2_sample_age_seconds/config"]
        self.assertEqual("{{ value | float(none) }}", age["value_template"])


if __name__ == "__main__":
    unittest.main()
