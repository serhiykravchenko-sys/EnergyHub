from datetime import datetime
from pathlib import Path
from unittest import TestCase

from app.services.panic_decision import PanicDecisionEngine


class DaytimeManualReserveTests(TestCase):
    def evaluate(self, **changes):
        arguments = dict(autopilot_enabled=True, operating_mode="solar",
                         grid_confidence="normal", battery_soc=60,
                         grid_available=True, manual_reserve_soc=60,
                         now=datetime(2026, 9, 6, 12))
        arguments.update(changes)
        return PanicDecisionEngine().evaluate(**arguments)

    def test_manual_floor_and_solar_release(self):
        for floor in (20, 40, 60, 90, 95):
            with self.subTest(floor=floor):
                result = self.evaluate(manual_reserve_soc=floor, battery_soc=floor)
                self.assertEqual("panic_grid_hold", result["request"])
                self.assertEqual(floor, result["target_soc"])
                expected_release = None if floor == 95 else floor + 10
                self.assertEqual(expected_release, result["release_soc"])
                expected_request = None if floor == 95 else "solar"
                self.assertEqual(expected_request, self.evaluate(manual_reserve_soc=floor,
                    battery_soc=min(100, floor + 10), operating_mode="panic_grid_hold")["request"])

    def test_high_floor_has_hysteresis_not_hold_release_oscillation(self):
        self.assertIsNone(self.evaluate(manual_reserve_soc=95, battery_soc=95,
                                       operating_mode="panic_grid_hold")["request"])
        self.assertIsNone(self.evaluate(manual_reserve_soc=95, battery_soc=100,
                                       operating_mode="panic_grid_hold")["request"])

    def test_charge_only_to_manual_floor_then_wait_for_solar(self):
        self.assertEqual("panic", self.evaluate(battery_soc=59)["request"])
        self.assertEqual("panic_grid_hold", self.evaluate(operating_mode="panic")["request"])
        self.assertIsNone(self.evaluate(battery_soc=69, operating_mode="panic_grid_hold")["request"])

    def test_family_lowering_is_not_advisory_lowering(self):
        self.assertEqual("solar", self.evaluate(manual_reserve_soc=20,
                         battery_soc=50, operating_mode="panic_grid_hold")["request"])

    def test_grid_confidence_is_not_applied_twice(self):
        self.assertEqual(60, self.evaluate(grid_confidence="risk")["target_soc"])
        self.assertEqual(60, self.evaluate(grid_confidence="panic")["target_soc"])

    def test_invalid_or_missing_manual_setting_never_defaults_to_twenty(self):
        for value in (None, "unavailable", float("nan"), float("inf"), 19, 62, 100):
            with self.subTest(value=value):
                self.assertEqual("skipped", self.evaluate(manual_reserve_soc=value)["status"])

    def test_no_ownership_with_autopilot_off_or_transition(self):
        self.assertIsNone(self.evaluate(autopilot_enabled=False, battery_soc=10)["request"])
        self.assertIsNone(self.evaluate(operating_mode="transitioning", battery_soc=10)["request"])
        self.assertIsNone(self.evaluate(grid_confidence="unknown", battery_soc=10)["request"])
        self.assertIsNone(self.evaluate(battery_soc=float("nan"))["request"])

    def test_outage_waits_without_switching_solar(self):
        self.assertIsNone(self.evaluate(grid_available=False, battery_soc=50)["request"])

    def test_restart_reconstructs_same_floor_from_received_manual_input(self):
        first = self.evaluate()
        self.assertEqual(first, self.evaluate())

    def test_immediate_wakeup_uses_manual_boundaries(self):
        for mode, soc, expected in (("solar", 60, True), ("solar", 61, False),
                                     ("panic_grid_hold", 59, True),
                                     ("panic_grid_hold", 69, False),
                                     ("panic_grid_hold", 70, True)):
            self.assertEqual(expected, PanicDecisionEngine().requires_immediate_evaluation(
                operating_mode=mode, battery_soc=soc, grid_confidence="normal",
                grid_available=True, manual_reserve_soc=60, now=datetime(2026, 9, 6, 12)))

    def test_main_wires_family_input_not_observer_recommendation(self):
        source = (Path(__file__).parents[1] / "app/main.py").read_text(encoding="utf-8")
        self.assertEqual(2, source.count('manual_reserve_soc=decision_inputs.get("ahm_minimum_soc")'))

    def test_main_retires_competing_night_control_paths(self):
        source = (Path(__file__).parents[1] / "app/main.py").read_text(encoding="utf-8")
        self.assertNotIn("                enforce_hybrid_night_target(state)", source)
        self.assertNotIn("                    evaluate_early_solar(state, request)", source)
        self.assertIn("Legacy Hybrid evaluation request redirected", source)
        self.assertNotIn("early_solar", source)
