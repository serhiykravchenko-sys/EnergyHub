from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DashboardSensorLineageTests(unittest.TestCase):
    def test_live_cards_charts_and_overload_snapshot_share_sources(self):
        dashboard = (ROOT / "homeassistant/live/storage/lovelace.dashboard_powmr1").read_text(
            encoding="utf-8"
        )
        automations = (ROOT / "homeassistant/live/config/automations.yaml").read_text(
            encoding="utf-8"
        )

        self.assertGreaterEqual(dashboard.count("sensor.powmr_10_2m_total_pv_power"), 2)
        self.assertGreaterEqual(dashboard.count("sensor.powmr_10_2m_output_power"), 2)
        for entity_id in (
            "sensor.water_pump_plug_electric_power",
            "sensor.water_boiler_plug_electric_power",
            "sensor.first_floor_heat_pump_plug_power",
            "sensor.second_floor_heat_pump_plug_power",
            "sensor.third_floor_heat_pump_plug_electric_power",
            "sensor.microwave_plug_electric_power",
        ):
            self.assertIn(entity_id, dashboard)
            self.assertIn(f"states('{entity_id}')", automations)


if __name__ == "__main__":
    unittest.main()
