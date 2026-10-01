from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class StatisticsSensorConfigTests(unittest.TestCase):
    def test_solar_power_average_uses_statistics_entity_id_key(self):
        configuration = (
            ROOT / "homeassistant/live/config/configuration.yaml"
        ).read_text(encoding="utf-8")
        start = configuration.index("  - platform: statistics")
        block = configuration[start:].split("\n  - platform: integration", 1)[0]

        self.assertIn(
            "entity_id: sensor.powmr_10_2m_total_pv_power",
            block,
        )
        self.assertNotIn("\n    source:", block)


if __name__ == "__main__":
    unittest.main()
