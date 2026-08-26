from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.config import load_config


class ConfigTests(unittest.TestCase):
    def test_schema_options_have_both_translations(self):
        root = Path(__file__).resolve().parents[1]

        def top_level_keys_after(path, heading):
            lines = path.read_text(encoding="utf-8").splitlines()
            start = lines.index(f"{heading}:") + 1
            return {
                line.strip().split(":", 1)[0]
                for line in lines[start:]
                if line.startswith("  ")
                and not line.startswith("    ")
                and ":" in line
            }

        schema_keys = top_level_keys_after(root / "config.yaml", "schema")
        english_keys = top_level_keys_after(
            root / "translations" / "en.yaml", "configuration"
        )
        ukrainian_keys = top_level_keys_after(
            root / "translations" / "uk.yaml", "configuration"
        )
        self.assertEqual(schema_keys, english_keys)
        self.assertEqual(schema_keys, ukrainian_keys)

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
            self.assertEqual(
                load_config(path).inverter_message_entities,
                (
                    "sensor.energyhub_inverter_fault_recent_1",
                    "sensor.energyhub_inverter_fault_recent_2",
                    "sensor.energyhub_inverter_fault_recent_3",
                ),
            )
            self.assertEqual(
                load_config(path).yesterday_night_grid_import_entity,
                "sensor.energyhub_grid_import_night_yesterday_estimated",
            )
            self.assertEqual(
                load_config(path).month_grid_import_cost_entity,
                "sensor.energyhub_grid_import_cost_month_estimated",
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
                "sensor.energyhub_heat_pump_floor_3_power",
            )


if __name__ == "__main__":
    unittest.main()
