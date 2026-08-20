from __future__ import annotations

import unittest
from datetime import date
from zoneinfo import ZoneInfo

from app.report import (
    build_report,
    reserve_advice_message,
    solar_peak,
    sun_moon_lines,
    useful_solar_window,
    weather_summary,
)


TZ = ZoneInfo("Europe/Kyiv")
TODAY = date(2026, 8, 11)


class WeatherSummaryTests(unittest.TestCase):
    def test_formats_condition_temperature_rain_and_warning(self):
        forecast = [
            {
                "datetime": "2026-08-11T09:00:00+03:00",
                "condition": "partlycloudy",
                "temperature": 15,
                "precipitation": 0,
                "wind_speed": 10,
            },
            {
                "datetime": "2026-08-11T16:00:00+03:00",
                "condition": "lightning-rainy",
                "temperature": 30,
                "precipitation": 2.3,
                "precipitation_probability": 70,
                "wind_gust_speed": 72,
            },
            {
                "datetime": "2026-08-11T17:00:00+03:00",
                "condition": "partlycloudy",
                "temperature": 25,
                "precipitation": 1.5,
                "precipitation_probability": 55,
                "wind_speed": 10,
            },
        ]
        lines = weather_summary(forecast, TODAY, TZ, "km/h", 15)
        self.assertEqual(lines[0], "🌤 Погода <b>сьогодні</b>: мінлива хмарність, від +15 до +30 °C")
        self.assertIn("🌧 Дощ: 16:00–18:00, близько 3.8 мм, ймовірність 70%", lines)
        self.assertIn("можлива гроза", lines[-1])
        self.assertIn("пориви вітру до 20 м/с", lines[-1])

    def test_snow_amount_is_named_water_equivalent(self):
        lines = weather_summary(
            [{
                "datetime": "2026-08-11T10:00:00+03:00",
                "condition": "snowy",
                "temperature": -2,
                "precipitation": 4.2,
                "precipitation_probability": 80,
            }],
            TODAY,
            TZ,
            "m/s",
            15,
        )
        self.assertIn("4.2 мм водного еквівалента", lines[1])

    def test_daily_forecast_uses_day_wording_and_templow(self):
        lines = weather_summary(
            [{
                "datetime": "2026-08-11T00:00:00+03:00",
                "condition": "rainy",
                "templow": 12,
                "temperature": 22,
                "precipitation": 3,
                "precipitation_probability": 60,
            }],
            TODAY,
            TZ,
            "km/h",
            15,
            "daily",
        )
        self.assertIn("від +12 до +22 °C", lines[0])
        self.assertIn("Дощ: протягом дня", lines[1])

    def test_ignores_other_days(self):
        lines = weather_summary(
            [{"datetime": "2026-08-12T10:00:00+03:00", "condition": "sunny", "temperature": 20}],
            TODAY,
            TZ,
            "km/h",
            15,
        )
        self.assertEqual(lines, [])


class SolarSummaryTests(unittest.TestCase):
    def test_finds_first_and_end_of_last_qualifying_period(self):
        hourly = [
            {"period_start": "2026-08-11T08:00:00+03:00", "pv_estimate": 0.2},
            {"period_start": "2026-08-11T09:00:00+03:00", "pv_estimate": 0.3},
            {"period_start": "2026-08-11T17:00:00+03:00", "pv_estimate": 0.4},
            {"period_start": "2026-08-11T18:00:00+03:00", "pv_estimate": 0.1},
        ]
        self.assertEqual(useful_solar_window(hourly, TODAY, TZ, 300), "09:00–18:00")


class AddedMorningDetailsTests(unittest.TestCase):
    def test_finds_expected_peak_power_and_time(self):
        hourly = [
            {"period_start": "2026-08-11T12:00:00+03:00", "pv_estimate": 3.2},
            {"period_start": "2026-08-11T13:00:00+03:00", "pv_estimate": 4.8},
            {"period_start": "2026-08-11T14:00:00+03:00", "pv_estimate": 4.1},
        ]
        self.assertEqual(solar_peak(hourly, TODAY, TZ), (4.8, "13:00"))

    def test_shows_today_sun_and_full_moon(self):
        lines = sun_moon_lines(
            {"attributes": {
                "next_rising": "2026-08-12T05:42:00+03:00",
                "next_setting": "2026-08-11T20:18:00+03:00",
            }},
            {"state": "full_moon"},
            TODAY,
            TZ,
        )
        self.assertEqual(2, len(lines))
        self.assertIn("05:42", lines[0])
        self.assertIn("20:18", lines[0])

    def test_omits_intermediate_moon_phase(self):
        self.assertEqual([], sun_moon_lines(None, {"state": "waxing_gibbous"}, TODAY, TZ))

    def test_shows_new_moon(self):
        self.assertEqual(1, len(sun_moon_lines(None, {"state": "new_moon"}, TODAY, TZ)))


class ReportTests(unittest.TestCase):
    def test_complete_new_morning_details(self):
        message = build_report(
            weather_lines=[],
            astronomy_lines=["sun 05:42 20:18", "full moon"],
            solar_forecast=24.6,
            solar_window="08:20-19:10",
            solar_peak_value=(4.8, "13:00"),
            threshold_w=300,
            consumption=18.6,
            snapshot={},
            night_import=None,
            test_mode=False,
            reserve_advice={
                "status": "learning",
                "current_soc": 20,
                "suggested_soc": 20,
                "sample_count": 0,
            },
            ahm_minimum_soc=20,
            heat_pump_management="heat pumps manual",
        )
        self.assertIn("sun 05:42 20:18", message)
        self.assertIn("full moon", message)
        self.assertIn("4.8 kW", message)
        self.assertIn("13:00", message)
        self.assertIn("<b>20%</b>", message)
        self.assertIn("0/3", message)
        self.assertIn("heat pumps manual", message)

    def test_formats_three_morning_increase_advice(self):
        recommendation = reserve_advice_message({
            "status": "increase", "current_soc": 20,
            "suggested_soc": 30, "sample_count": 3,
        })
        self.assertIn("20% → 30%", recommendation)

    def test_formats_decrease_as_left_arrow(self):
        recommendation = reserve_advice_message({
            "status": "decrease", "current_soc": 40,
            "suggested_soc": 30, "sample_count": 3,
        })
        self.assertIn("30% ← 40%", recommendation)

    def test_formats_learning_progress(self):
        recommendation = reserve_advice_message({
            "status": "learning", "sample_count": 2,
        })
        self.assertIn("2/3", recommendation)

    def test_complete_message(self):
        message = build_report(
            weather_lines=["🌤 Погода <b>сьогодні</b>: сонячно, від +15 до +30 °C"],
            solar_forecast=24.6,
            solar_window="09:20–17:30",
            threshold_w=300,
            consumption=18.6,
            snapshot={"soc": 82, "target_soc": 80, "mode": "hybrid_grid_hold"},
            night_import=7.4,
            test_mode=False,
        )
        self.assertIn("🌤 Погода <b>сьогодні</b>", message)
        self.assertIn("Прогноз генерації: 24.6 kWh", message)
        self.assertIn("Нічний режим: Hybrid", message)
        self.assertIn("SOC о 07:00: 82% / ціль 80%", message)

    def test_missing_values_are_omitted(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            test_mode=False,
        )
        self.assertEqual(message, "🌅 <b>Доброго ранку!</b>")


if __name__ == "__main__":
    unittest.main()
