from datetime import datetime
from unittest import TestCase

from app.presentation import mode_label, strategy_lines, tariff_label


class PresentationTests(TestCase):
    def lines(self, mode, target=40, hour=5, fresh=True, grid_online=True):
        return "\n".join(strategy_lines(mode, target, now=datetime(2026, 9, 7, hour),
                                      fresh=fresh, grid_online=grid_online))

    def test_tariff_boundaries(self):
        for hour, minute, expected in ((22, 59, "денним"), (23, 0, "нічним"),
                                       (6, 59, "нічним"), (7, 0, "денним")):
            self.assertIn(expected, tariff_label(datetime(2026, 9, 7, hour, minute)))
        self.assertIn("дешевим", tariff_label(datetime(2026, 9, 7, 12), "11:00", "15:00"))
        self.assertIn("звичайним", tariff_label(datetime(2026, 9, 7, 15), "11:00", "15:00"))

    def test_hold_is_not_charging(self):
        self.assertIn("батарею заряджає лише сонце", self.lines("hybrid_grid_hold"))
        self.assertNotIn("ДТЕК</b> · заряджання", self.lines("hybrid_grid_hold"))
        self.assertIn("при <b>50%</b>", self.lines("panic_grid_hold"))
        self.assertEqual(
            "🔌 О 05:00 режим <b>сонце + ДТЕК</b> · резерв <b>40%</b> "
            "· пріоритет сонця при <b>50%</b>",
            self.lines("panic_grid_hold"),
        )

    def test_charging_uses_current_tariff_not_mode(self):
        self.assertIn("до <b>40%</b> · за денним тарифом", self.lines("hybrid_charging", hour=8))
        self.assertIn("за нічним тарифом", self.lines("panic"))
        self.assertNotIn("Після досягнення цілі", self.lines("panic"))

    def test_incomplete_evidence_does_not_claim_grid_supply(self):
        for kwargs in ({"fresh": False}, {"grid_online": False}):
            self.assertNotIn("Будинок живиться", self.lines("hybrid_charging", **kwargs))
        for target in (None, "unavailable", float("nan"), 101):
            text = self.lines("hybrid_charging", target)
            self.assertIn("ціль недоступна", text)
            self.assertNotIn("Після досягнення цілі", text)

    def test_historical_aggregate_does_not_claim_charging(self):
        self.assertEqual(mode_label("hybrid"), "Використання дешевого тарифу")
        self.assertEqual(mode_label("<unknown>"), "Невідома стратегія")
        self.assertIsNone(mode_label("unavailable"))
