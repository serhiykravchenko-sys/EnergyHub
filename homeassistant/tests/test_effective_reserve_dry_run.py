from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class EffectiveReserveDryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.configuration = (
            ROOT / "homeassistant/live/config/configuration.yaml"
        ).read_text(encoding="utf-8")
        automations = (
            ROOT / "homeassistant/live/config/automations.yaml"
        ).read_text(encoding="utf-8")
        start = automations.index("- id: '1786023000017'")
        cls.reserve_automation = automations[start:]
        cls.all_automations = automations

    def test_authority_exposes_manual_and_automatic(self):
        start = self.configuration.index("  energyhub_ahm_weather_authority:")
        block = self.configuration[start:start + 300]
        self.assertIn("- Manual", block)
        self.assertIn("- Automatic", block)

    def test_daily_input_and_separate_guarded_apply_path(self):
        self.assertIn("at: '23:49:00'", self.all_automations)
        self.assertIn("at: '23:51:00'", self.all_automations)
        self.assertIn("at: '23:52:00'", self.reserve_automation)
        self.assertIn("at: '05:00:00'", self.reserve_automation)
        self.assertIn("sensor.solcast_pv_forecast_forecast_today", self.reserve_automation)
        self.assertIn("sensor.solcast_pv_forecast_forecast_tomorrow", self.reserve_automation)
        self.assertIn("'forecast_plan_stage': plan_stage", self.reserve_automation)
        self.assertIn("timedelta(days=1)", self.reserve_automation)
        self.assertIn("action: mqtt.publish", self.reserve_automation)
        self.assertNotIn("weather.get_forecasts", self.reserve_automation)
        self.assertIn("input_number.set_value", self.all_automations)
        self.assertIn("recommendation_status') == 'ready'", self.all_automations)
        self.assertNotIn("switch.turn_", self.reserve_automation)

    def test_legacy_night_and_morning_automations_are_removed(self):
        for automation_id in (
            "1786500000002",
            "1786500000003",
            "1783705009942",
        ):
            self.assertNotIn(f"- id: '{automation_id}'", self.all_automations)
        self.assertNotIn("energyhub/input/ha/early_solar_check", self.all_automations)
        self.assertNotIn("payload: evaluate_hybrid", self.all_automations)

    def test_legacy_night_notifications_are_removed(self):
        for text in (
            "Low-Tariff activated",
            "Early Solar handover",
            "energyhub_hybrid",
            "energyhub_early_solar",
            "Battery Reserve took ownership from daytime Reserve Protection at 23:50",
        ):
            self.assertNotIn(text, self.all_automations)

    def test_only_manual_setting_is_published(self):
        self.assertNotIn("energyhub_battery_reserve_baseline:", self.configuration)
        self.assertIn("'applied_minimum_soc': states('input_number.ahm_minimum_soc')", self.reserve_automation)
        self.assertNotIn("'baseline_soc':", self.reserve_automation)

    def test_auto_indicator_toggles_only_the_authority(self):
        import json
        dashboard = json.loads((ROOT / "homeassistant/live/storage/lovelace.dashboard_powmr1").read_text(encoding="utf-8"))
        def visit(value):
            if isinstance(value, dict):
                if value.get("entity") == "binary_sensor.energyhub_battery_reserve_auto":
                    self.assertEqual("perform-action", value["tap_action"]["action"])
                    self.assertEqual("input_select.select_next", value["tap_action"]["perform_action"])
                    return 1
                return sum(visit(item) for item in value.values())
            if isinstance(value, list):
                return sum(visit(item) for item in value)
            return 0
        self.assertEqual(1, visit(dashboard))

    def test_dashboard_has_only_one_editable_reserve_value(self):
        import json
        dashboard = json.loads((ROOT / "homeassistant/live/storage/lovelace.dashboard_powmr1").read_text(encoding="utf-8"))
        nodes = []
        def visit(value):
            if isinstance(value, dict):
                nodes.append(value)
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(dashboard)
        self.assertFalse(any(node.get("entity") == "input_number.energyhub_battery_reserve_baseline" for node in nodes))
        controls = [node for node in nodes if node.get("perform_action") in ("input_number.increment", "input_number.decrement")]
        self.assertEqual(2, len(controls))
        for control in controls:
            self.assertEqual("input_number.ahm_minimum_soc", control["target"]["entity_id"])

        manual_conditionals = [node for node in nodes
            if node.get("type") == "conditional"
            and {item.get("entity") for item in node.get("conditions", [])}
               == {"input_select.energyhub_ahm_weather_authority"}]
        self.assertGreaterEqual(len(manual_conditionals), 2)
        self.assertTrue(all(node["conditions"][0].get("state") == "Manual"
                            for node in manual_conditionals))

    def test_dashboard_replaces_visible_legacy_decision_panel(self):
        import json
        dashboard = json.loads((ROOT / "homeassistant/live/storage/lovelace.dashboard_powmr1").read_text(encoding="utf-8"))
        nodes = []
        def visit(value):
            if isinstance(value, dict):
                nodes.append(value)
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(dashboard)

        compact = [node for node in nodes
                   if node.get("title") == "EnergyHub Reserve Control"]
        self.assertEqual(0, len(compact))
        legacy_stacks = [node for node in nodes
                         if node.get("type") == "vertical-stack"
                         and any(card.get("title") == "EnergyHub Decision Logic"
                                 for card in node.get("cards", []))]
        self.assertEqual(0, len(legacy_stacks))

        visible_mode_cards = [node for node in nodes
                              if node.get("type") == "markdown"
                              and "Applied Battery Reserve:" in node.get("content", "")]
        self.assertGreaterEqual(len(visible_mode_cards), 1)
        self.assertTrue(all("Low-tariff window" not in node["content"]
                            for node in visible_mode_cards))


if __name__ == "__main__":
    unittest.main()
