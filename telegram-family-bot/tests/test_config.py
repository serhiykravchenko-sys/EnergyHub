from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.config import load_config


class ConfigTests(unittest.TestCase):
    def test_auto_weather_value_enables_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"weather_entity": "auto"}), encoding="utf-8")
            self.assertEqual(load_config(path).weather_entity, "")

    def test_explicit_weather_entity_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"weather_entity": "weather.home"}), encoding="utf-8")
            self.assertEqual(load_config(path).weather_entity, "weather.home")

    def test_default_ahm_minimum_entity_matches_home_assistant_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(
                load_config(path).ahm_minimum_soc_entity,
                "input_number.ahm_minimum_soc",
            )
            self.assertEqual(
                load_config(path).reserve_advice_entity,
                "sensor.energyhub_ahm_reserve_advice",
            )
            self.assertEqual(
                load_config(path).telemetry_freshness_entity,
                "sensor.energyhub_telemetry_freshness",
            )
            self.assertEqual(load_config(path).heat_pump_active_threshold_w, 50)
            self.assertEqual(
                load_config(path).heat_pump_floor_1_power_entity,
                "sensor.first_floor_heat_pump_plug_power",
            )
            self.assertEqual(
                load_config(path).heat_pump_floor_2_power_entity,
                "sensor.second_floor_heat_pump_plug_power",
            )
            self.assertEqual(
                load_config(path).heat_pump_floor_3_power_entity,
                "sensor.chuangmi_212a01_ea40_electric_power",
            )


if __name__ == "__main__":
    unittest.main()
