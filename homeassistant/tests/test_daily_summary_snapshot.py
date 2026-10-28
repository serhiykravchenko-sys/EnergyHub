import unittest
from pathlib import Path
import yaml


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
        decoded=yaml.safe_load(self.daily_summary)[0]['actions'][0]['wait_template']
        self.assertRegex(decoded,r"is_number\(\s*states\('sensor\.powmr_10_2m_daily_house_consumption'\)")
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

    def test_actual_generation_uses_verified_daily_meter_entity(self):
        self.assertIn('sensor.total_solar_generated_today',self.daily_summary)
        self.assertNotIn('sensor.energyhub_total_solar_generation_daily',self.daily_summary)

    def test_unknown_full_flag_is_not_assumed_false(self):
        self.assertIn("else none",self.daily_summary)


if __name__ == "__main__":
    unittest.main()
