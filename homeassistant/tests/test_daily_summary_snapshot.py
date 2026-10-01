import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTOMATIONS = ROOT / "homeassistant/live/config/automations.yaml"


class DailySummarySnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        automations = AUTOMATIONS.read_text(encoding="utf-8")
        start = automations.index("- id: '1783245343717'")
        end = automations.index("- id: '1784300000001'")
        cls.daily_summary = automations[start:end]

    def test_waits_for_numeric_consumption_before_publishing(self):
        wait_position = self.daily_summary.index("- wait_template:")
        variables_position = self.daily_summary.index("- variables:")

        self.assertLess(wait_position, variables_position)
        self.assertIn(
            "is_number(\n        states('sensor.powmr_10_2m_daily_house_consumption')",
            self.daily_summary,
        )
        self.assertIn("timeout: 00:01:30", self.daily_summary)
        self.assertIn("continue_on_timeout: false", self.daily_summary)

    def test_does_not_manufacture_zero_for_missing_consumption(self):
        self.assertNotIn(
            "sensor.powmr_10_2m_daily_house_consumption'')\n        | float(0)",
            self.daily_summary,
        )
        self.assertIn(
            "sensor.powmr_10_2m_daily_house_consumption'')\n        | float(none)",
            self.daily_summary,
        )


if __name__ == "__main__":
    unittest.main()
