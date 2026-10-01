from unittest import TestCase
from app.events import weather_warning_message


class ShortWeatherMessageTests(TestCase):
    event = dict(severity=1, hazards=["strong_wind", "thunderstorm"],
                 url="https://t.me/uhmc1921/5995", summary=(
                     "Попередження про небезпечні метеорологічні явища\n\n"
                     "До кінця доби значні дощі.\n\n"
                     "І рівень небезпечності, жовтий.\n\n"
                     "Погодні умови можуть ускладнити роботу підприємств."
                 ))

    def reserve(self, **changes):
        data = dict(applied_minimum_soc=20, recommended_soc=20,
                    daily_plan_fresh=True, weather_source_status="fresh",
                    grid_confidence="normal", evidence_issues=[], advice_only=True)
        data.update(changes)
        return data

    def test_level_one_preserves_official_details_without_battery_advice(self):
        message = weather_warning_message(self.event, self.reserve())
        self.assertIn("До кінця доби значні дощі", message)
        self.assertIn("Погодні умови можуть ускладнити", message)
        self.assertNotIn("Мінімум батареї", message)
        self.assertIn("5995", message)

    def test_mixed_forecast_post_uses_warning_section_only(self):
        mixed = dict(self.event, summary=(
            "📌 Прогноз погоди на добу.\n\nХмарно. Місцями дощі.\n\n"
            "‼️Попередження про небезпечні метеорологічні явища по Київщині‼️\n\n"
            "24 вересня значні дощі.\n\nІ рівень небезпечності, жовтий.\n\n"
            "Погодні умови можуть ускладнити рух транспорту.\n\nСайт Instagram"
        ))
        message = weather_warning_message(mixed, self.reserve())
        self.assertIn("24 вересня значні дощі", message)
        self.assertIn("ускладнити рух транспорту", message)
        self.assertNotIn("Хмарно", message)
        self.assertNotIn("Instagram", message)

    def test_incomplete_evidence_never_claims_no_change(self):
        for change in (dict(evidence_issues=["consumption_history_incomplete"]),
                       dict(daily_plan_fresh=False), dict(weather_source_status="unknown"),
                       dict(applied_minimum_soc=None), dict(recommended_soc=None),
                       dict(grid_confidence="unknown")):
            message = weather_warning_message(
                dict(self.event, severity=2), self.reserve(**change)
            )
            self.assertIn("Даних для рекомендації недостатньо", message)
            self.assertNotIn("Зміна не рекомендована", message)

    def test_level_two_missing_reserve_is_unknown_not_assumed_twenty(self):
        message = weather_warning_message(dict(self.event, severity=2), None)
        self.assertIn("невідомий", message)
        self.assertNotIn("20%", message)

    def test_recommendation_does_not_claim_action_or_stack_on_manual(self):
        message = weather_warning_message(dict(self.event, severity=2),
                                         self.reserve(recommended_soc=40))
        self.assertIn("рекомендовано вручну 40%", message)
        message = weather_warning_message(
            dict(self.event, severity=2),
            self.reserve(applied_minimum_soc=60, recommended_soc=40),
        )
        self.assertIn("Ручний вибір збережено", message)
        self.assertNotIn("рекомендовано вручну", message)
