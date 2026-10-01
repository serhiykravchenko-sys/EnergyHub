import hashlib
import json
from unittest import TestCase

from tests.test_weather_buffer import RecordingClient
from app.mqtt import publisher
from app.utils.presentation import display_text, display_value


class PresentationTests(TestCase):
    def test_labels_are_not_control_values(self):
        self.assertEqual(display_text("Adaptive Hybrid / AHM / Panic"),
                         "Low-Tariff Plan / Battery Reserve / Reserve Protection")
        for value in ("panic", "hybrid_charging", "hybrid_grid_hold", "solar"):
            self.assertEqual(display_value("operating_mode", value), value)
        self.assertEqual(display_value("panic_decision_reason", "Panic target"),
                         "Reserve Protection target")

    def test_discovery_identity_matches_pre_naming_release(self):
        client = RecordingClient()
        for name in ("operating_mode", "panic_decision", "weather_buffer",
                     "peak_load_guard"):
            getattr(publisher, f"publish_{name}_discovery")(client)
        stable = []
        for topic, payload, retain in client.messages:
            if not payload:
                continue
            data = json.loads(payload)
            data.pop("name", None)
            stable.append([topic, data, retain])
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, "d54f2d7d51442a4625537bd5f32e7fa927b576df1739d8e735178ee6b2ea3010")
