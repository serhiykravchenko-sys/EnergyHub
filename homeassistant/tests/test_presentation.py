import json
from pathlib import Path
import unittest

from jinja2 import Environment
import yaml


ROOT = Path(__file__).resolve().parents[2]


def contents(value):
    if isinstance(value, dict):
        if isinstance(value.get("content"), str):
            yield value["content"]
        for child in value.values():
            yield from contents(child)
    elif isinstance(value, list):
        for child in value:
            yield from contents(child)


class PresentationTests(unittest.TestCase):
    def dashboard(self):
        return json.loads(
            (ROOT / "homeassistant/live/storage/lovelace.dashboard_powmr1").read_text(
                encoding="utf-8"
            )
        )

    def walk(self, value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from self.walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from self.walk(child)

    def test_primary_columns_have_matching_external_headings(self):
        nodes = list(self.walk(self.dashboard()))
        headings = [node.get("heading") for node in nodes if node.get("type") == "heading"]
        self.assertIn("Modes & Controls", headings)
        self.assertIn("EnergyHub Status", headings)
        self.assertFalse(any(node.get("title") == "EnergyHub Status" for node in nodes))

    def test_mission_control_buttons_are_large_and_stateful(self):
        mission_entities = {
            "input_boolean.energyhub_autopilot",
            "binary_sensor.energyhub_battery_reserve_auto",
            "input_boolean.energyhub_load_control_armed",
            "input_boolean.energyhub_smart_heating",
            "input_boolean.energyhub_solar_only_heating",
        }
        buttons = {
            node.get("entity"): node
            for node in self.walk(self.dashboard())
            if node.get("type") == "button" and node.get("entity") in mission_entities
        }
        self.assertEqual(mission_entities, set(buttons))
        for button in buttons.values():
            self.assertTrue(button.get("show_state"))
            self.assertGreaterEqual(int(button["icon_height"].removesuffix("px")), 52)

        self.assertGreaterEqual(int(buttons['input_boolean.energyhub_autopilot']['icon_height'].removesuffix('px')), 80)
        guard = buttons['input_boolean.energyhub_load_control_armed']
        self.assertEqual('Inverter Overload Guard', guard['name'])
        self.assertEqual('mdi:shield-home', guard['icon'])
        secondary = mission_entities - {'input_boolean.energyhub_autopilot'}
        self.assertEqual({56}, {int(buttons[entity]['icon_height'].removesuffix('px'))
                                for entity in secondary})
        grids = [node for node in self.walk(self.dashboard())
                 if node.get('type') == 'grid' and node.get('columns') == 2]
        self.assertTrue(any({item.get('entity') for item in grid.get('cards', [])}
                            == {'binary_sensor.energyhub_battery_reserve_auto',
                                'input_boolean.energyhub_load_control_armed'}
                            for grid in grids))
        conditions = [node.get('conditions', []) for node in self.walk(self.dashboard())
                      if node.get('type') == 'conditional' and
                      (node.get('card') or {}).get('entity') == 'input_boolean.energyhub_solar_only_heating']
        self.assertEqual([[{'entity':'input_boolean.energyhub_smart_heating','state':'on'}]], conditions)

    def test_grid_confidence_precedes_detailed_telemetry(self):
        nodes = list(self.walk(self.dashboard()))
        status = next(node for node in nodes if node.get('heading') == 'EnergyHub Status')
        # Traverse the enclosing vertical stack to verify visible card order.
        stacks = [node for node in nodes if node.get('type') == 'vertical-stack'
                  and status in node.get('cards', [])]
        self.assertEqual(1, len(stacks))
        cards = stacks[0]['cards']
        confidence = next(i for i, card in enumerate(cards) if 'Grid Confidence' in card.get('content', ''))
        telemetry = next(i for i, card in enumerate(cards) if card.get('type') == 'entities')
        self.assertLess(confidence, telemetry)

    def test_grid_confidence_card_uses_current_status_and_24_48_hour_evidence(self):
        markdown = "\n".join(
            node.get("content", "")
            for node in self.walk(self.dashboard())
            if node.get("type") == "markdown"
        )
        self.assertIn("sensor.energyhub_grid_confidence", markdown)
        self.assertIn("sensor.energyhub_grid_availability_24h", markdown)
        self.assertIn("sensor.energyhub_grid_available_48h", markdown)
        self.assertIn("Grid Confidence", markdown)

    def test_beacon_light_calls_are_cosmetic_and_non_blocking(self):
        automations = yaml.safe_load(
            (ROOT / "homeassistant/live/config/automations.yaml").read_text(
                encoding="utf-8"
            )
        )
        beacon = next(
            item for item in automations if item.get("alias") == "EnergyHub Beacon"
        )

        def actions(value):
            if isinstance(value, dict):
                if value.get("action") == "light.turn_on":
                    yield value
                for child in value.values():
                    yield from actions(child)
            elif isinstance(value, list):
                for child in value:
                    yield from actions(child)

        lamp_calls = list(actions(beacon.get("actions", [])))
        self.assertGreater(len(lamp_calls), 0)
        self.assertTrue(
            all(call.get("continue_on_error") is True for call in lamp_calls)
        )

    def test_beacon_soc_color_boundaries_match_battery_protection(self):
        automations = yaml.safe_load(
            (ROOT / "homeassistant/live/config/automations.yaml").read_text(encoding="utf-8")
        )
        beacon = next(item for item in automations if item.get("alias") == "EnergyHub Beacon")
        template = Environment().from_string(beacon["actions"][0]["variables"]["lamp_color"])
        for soc, expected in ((39, "[220, 20, 30]"), (40, "[220, 20, 30]"),
                              (41, "[255, 220, 0]"), (69, "[255, 220, 0]"),
                              (70, "[0, 255, 0]"), (94, "[0, 255, 0]"),
                              (95, "[0, 80, 255]")):
            self.assertIn(expected, template.render(soc=soc))

    def test_solar_yearly_chart_matches_working_month_spacing(self):
        dashboard = json.loads((ROOT / 'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        charts = {}
        def walk(value):
            if isinstance(value, dict):
                if value.get('header', {}).get('title'):
                    charts[value['header']['title']] = value
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(dashboard)
        solar = charts['Generation & Grid Import — 12 months']
        hp = charts['Heat-Pump Consumption — 12 months']
        self.assertEqual(hp['apex_config']['xaxis'], solar['apex_config']['xaxis'])
        self.assertEqual(hp['series'][3]['data_generator'], solar['series'][4]['data_generator'])
        self.assertEqual([0, 1, 2, 3], solar['apex_config']['tooltip']['enabledOnSeries'])
        self.assertEqual(4, len(solar['apex_config']['legend']['customLegendItems']))
        self.assertEqual(3, len([s for s in solar['series'] if s.get('show', {}).get('in_chart') is False]))
        for series in solar['series'][:4]:
            self.assertEqual({'type': 'change', 'period': 'month', 'align': 'middle'}, series['statistics'])

    def test_reserve_controls_do_not_duplicate_advisory_selector(self):
        dashboard = json.loads((ROOT / 'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        text = json.dumps(dashboard)
        self.assertIn('input_select.energyhub_ahm_weather_authority', text)
        self.assertNotIn('sensor.energyhub_hybrid_calculation', text)
        self.assertNotIn('Morning reserve observation', text)
        self.assertIn('Battery Reserve Auto', text)
        self.assertNotIn('Unavailable during testing', text)
        self.assertIn('Increase 5%', text)
        self.assertIn('Decrease 5%', text)
        self.assertNotIn('Battery Reserve · Recommendations', text)
        self.assertNotIn('Reserve Evidence', text)
        self.assertIn('generation:', text)
        self.assertIn('Smart Heating', text)
        self.assertIn('Grid Confidence:', text)
        self.assertIn('Grid and weather are monitored continuously', text)

    def test_strategy_card_gates_supply_claims_and_uses_applied_reserve(self):
        dashboard = json.loads((ROOT / "homeassistant/live/storage/lovelace.dashboard_powmr1").read_text(encoding="utf-8"))
        template = Environment().from_string(next(x for x in contents(dashboard) if "**Applied Battery Reserve:**" in x))
        states = {"sensor.energyhub_operating_mode": "hybrid_grid_hold",
                  "sensor.energyhub_telemetry_freshness": "fresh",
                  "sensor.powmr_10_2m_grid_voltage": "230",
                  "sensor.energyhub_operating_mode_reason": "restart recovery",
                  "input_number.ahm_minimum_soc": "40"}
        render = lambda: template.render(states=lambda key: states.get(key, "unavailable"))
        self.assertIn("**Strategy:** Legacy recovery · grid hold", render())
        self.assertIn("persisted legacy state", render())
        self.assertIn("**Applied Battery Reserve:** 40", render())
        states["sensor.energyhub_telemetry_freshness"] = "stale"
        self.assertNotIn("persisted legacy state", render())
        states["sensor.energyhub_telemetry_freshness"] = "fresh"
        states["sensor.powmr_10_2m_grid_voltage"] = "0"
        self.assertNotIn("persisted legacy state", render())

    def test_reserve_card_separates_automatic_and_manual_presentation(self):
        dashboard = json.loads((ROOT / "homeassistant/live/storage/lovelace.dashboard_powmr1").read_text(encoding="utf-8"))
        template = Environment().from_string(next(x for x in contents(dashboard) if "severe deficit" in x))
        attributes = {
            "recommendation_status": "ready", "recommended_soc": 40,
            "forecast_deficit": True, "generation_modifier_percent": 20,
            "severe_forecast_deficit": False,
            "grid_confidence": "normal", "grid_modifier_percent": 0,
            "qualifying_weather_warning_count": 0, "weather_modifier_percent": 0,
            "smart_heating_modifier_percent": 0,
            "solar_forecast_kwh": 5, "consumption_average_kwh": 6.03,
            "consumption_sample_count": 3, "forecast_plan_stage": "morning",
            "date": "2026-09-12", "evidence_issues": [],
        }
        values = {"input_number.ahm_minimum_soc": "40"}
        render = lambda auto: template.render(
            states=lambda key: values.get(key, "unknown"),
            state_attr=lambda entity, key: attributes.get(key),
            is_state=lambda entity, state: auto and state == "on",
        )
        automatic = render(True)
        self.assertIn("**Current reserve:** 40%", automatic)
        self.assertNotIn("EH recommendation", automatic)
        self.assertIn("generation: deficit (+20%)", automatic)
        manual = render(False)
        self.assertIn("**Selected reserve:** 40%", manual)
        self.assertIn("**EH recommendation:** 40%", manual)
