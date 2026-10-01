from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.config import load_config


class ConfigTests(unittest.TestCase):
    def test_technical_chat_manifest_option_is_truly_optional(self):
        manifest = (Path(__file__).resolve().parents[1] / "config.yaml").read_text(
            encoding="utf-8"
        )
        options = manifest.split("options:", 1)[1].split("schema:", 1)[0]
        schema = manifest.split("schema:", 1)[1]
        self.assertNotIn("technical_chat_id:", options)
        self.assertIn('technical_chat_id: "str?"', schema)

    def test_retired_schedule_options_remain_schema_compatible_only(self):
        manifest = (Path(__file__).resolve().parents[1] / "config.yaml").read_text(
            encoding="utf-8"
        )
        options, schema = manifest.split("\nschema:\n", 1)
        for key in ("soc_snapshot_time", "night_start_time"):
            self.assertNotIn(f"  {key}:", options)
            self.assertIn(f'  {key}: "str?"', schema)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(
                json.dumps(
                    {
                        "soc_snapshot_time": "07:00",
                        "night_start_time": "23:00",
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertFalse(hasattr(config, "soc_snapshot_time"))
            self.assertFalse(hasattr(config, "night_start_time"))

    def test_retired_hybrid_and_reserve_advisor_options_are_fully_absent(self):
        root = Path(__file__).resolve().parents[1]
        retired = (
            "target_soc_entity",
            "reserve_advice_entity",
            "reserve_advice_current_soc_entity",
            "reserve_advice_suggested_soc_entity",
            "reserve_advice_sample_count_entity",
        )
        searched = [
            root / "config.yaml",
            root / "app" / "config.py",
            root / "translations" / "en.yaml",
            root / "translations" / "uk.yaml",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in searched)
        for key in retired:
            self.assertNotIn(key, combined)

    def test_current_option_translations_do_not_call_control_a_dry_run(self):
        root = Path(__file__).resolve().parents[1]
        for language in ("en", "uk"):
            translations = (root / "translations" / f"{language}.yaml").read_text(
                encoding="utf-8"
            )
            block = translations.split("  peak_load_guard_event_entity:", 1)[1]
            block = block.split("  inverter_message_entities:", 1)[0]
            self.assertNotIn("Dry Run", block)
            self.assertNotIn("2.1", block)

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

    def test_private_ical_option_is_visible_and_password_masked(self):
        manifest = (
            Path(__file__).resolve().parents[1] / "config.yaml"
        ).read_text(encoding="utf-8")
        options, schema = manifest.split("\nschema:\n", 1)
        self.assertIn('  family_calendar_ical_url: ""', options)
        self.assertIn('  family_calendar_ical_url: "password?"', schema)

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

    def test_family_calendar_ical_url_is_optional_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(
                json.dumps({"family_calendar_ical_url": "https://example.test/private.ics"}),
                encoding="utf-8",
            )
            self.assertEqual(
                load_config(path).family_calendar_ical_url,
                "https://example.test/private.ics",
            )

    def test_smart_plug_registry_is_parsed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(
                json.dumps({
                    "smart_plug_entities": (
                        "Heat pump|switch.heat_pump;Boiler|switch.boiler"
                    )
                }),
                encoding="utf-8",
            )
            plugs = load_config(path).smart_plugs
            self.assertEqual(
                [("Heat pump", "switch.heat_pump"), ("Boiler", "switch.boiler")],
                [(plug.label, plug.switch_entity) for plug in plugs],
            )

    def test_default_ahm_minimum_entity_matches_home_assistant_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(
                load_config(path).ahm_minimum_soc_entity,
                "input_number.ahm_minimum_soc",
            )
            self.assertEqual(
                load_config(path).weather_buffer_entity,
                "sensor.energyhub_ahm_weather_buffer",
            )
            self.assertEqual(
                load_config(path).soc_anomaly_latest_entity,
                "sensor.energyhub_soc_anomaly_latest",
            )
            self.assertEqual(
                load_config(path).telemetry_freshness_entity,
                "sensor.energyhub_telemetry_freshness",
            )
            self.assertEqual(
                load_config(path).grid_available_24h_entity,
                "sensor.energyhub_grid_available_24h",
            )
            self.assertEqual(
                load_config(path).grid_outage_24h_entity,
                "sensor.energyhub_grid_outage_24h",
            )
            self.assertEqual(load_config(path).weather_humidity_low_percent, 30)
            self.assertEqual(load_config(path).weather_humidity_high_percent, 80)
            self.assertEqual(load_config(path).weather_humidity_change_percent, 25)
            self.assertEqual(load_config(path).family_calendar_ical_url, "")
            self.assertEqual(load_config(path).technical_chat_id, "")
            self.assertEqual(load_config(path).uhmc_weather_source, "uhmc1921")
            self.assertEqual(
                load_config(path).uhmc_weather_mqtt_topic,
                "energyhub/input/weather/uhmc",
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
                "sensor.third_floor_heat_pump_plug_electric_power",
            )


if __name__ == "__main__":
    unittest.main()
