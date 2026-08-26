from __future__ import annotations

import unittest
from datetime import date
from zoneinfo import ZoneInfo

from app.report import (
    build_report,
    compact_number,
    inverter_duration_text,
    inverter_report_lines,
    reserve_advice_message,
    solar_peak,
    sun_moon_lines,
    useful_solar_window,
    weather_summary,
)


TZ = ZoneInfo("Europe/Kyiv")
TODAY = date(2026, 8, 11)


class NumberFormattingTests(unittest.TestCase):
    def test_compact_number_accepts_integer_input(self):
        self.assertEqual(compact_number(150), "150")


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
    def test_inverter_duration_uses_requested_units(self):
        self.assertEqual("48 с", inverter_duration_text(48.3))
        self.assertEqual("6 хв 5 с", inverter_duration_text(365))
        self.assertEqual("06:25:08", inverter_duration_text(23108.3))

    def test_expected_pv_loss_is_omitted(self):
        lines = inverter_report_lines(
            [{"attributes": {"event": {
                "started_at": "2026-08-10T20:38:00+03:00",
                "cleared_at": "2026-08-11T03:03:08+03:00",
                "duration_seconds": 23108.3,
                "messages": ["pv_loss_warning"],
            }}}],
            date(2026, 8, 10),
            TZ,
        )
        self.assertEqual([], lines)

    def test_pv_loss_is_removed_from_mixed_real_warning(self):
        lines = inverter_report_lines(
            [{"attributes": {"event": {
                "started_at": "2026-08-10T20:38:00+03:00",
                "cleared_at": "2026-08-10T20:44:05+03:00",
                "duration_seconds": 365,
                "messages": ["pv_loss_warning", "over_load"],
            }}}],
            date(2026, 8, 10),
            TZ,
        )
        self.assertNotIn("pv loss", lines[1])
        self.assertIn("перевантаження", lines[1])
        self.assertIn("6 хв 5 с", lines[1])

    def test_inverter_messages_include_yesterday_context_and_recovery(self):
        lines = inverter_report_lines(
            [{"attributes": {"event": {
                "started_at": "2026-08-10T21:43:00+03:00",
                "cleared_at": "2026-08-10T21:43:48+03:00",
                "duration_seconds": 48,
                "messages": ["over_load"],
                "latest_conditions": {
                    "load_w": 9100,
                    "load_percent": 91,
                    "grid_available": False,
                    "operating_mode": "solar",
                },
            }}}],
            date(2026, 8, 10),
            TZ,
        )
        self.assertIn("перевантаження", lines[1])
        self.assertIn("9100 W (91%)", lines[1])
        self.assertIn("мережа була відсутня", lines[1])
        self.assertIn("48 с", lines[1])

    def test_inverter_messages_omit_events_outside_report_day(self):
        lines = inverter_report_lines(
            [{"attributes": {"event": {
                "started_at": "2026-08-09T21:43:00+03:00",
                "messages": ["over_load"],
            }}}],
            date(2026, 8, 10),
            TZ,
        )
        self.assertEqual([], lines)

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

    def test_superseded_inverter_message_is_not_called_cleared(self):
        timezone = ZoneInfo("Europe/Kyiv")
        lines = inverter_report_lines(
            [{"attributes": {"event": {
                "started_at": "2026-08-10T09:00:00+03:00",
                "cleared_at": "2026-08-10T09:01:00+03:00",
                "recovery": "superseded",
                "messages": ["over_load"],
            }}}],
            date(2026, 8, 10),
            timezone,
        )

        self.assertIn("замінено іншим набором", "\n".join(lines))

    def test_current_ahm_minimum_is_not_labeled_as_recommended(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={},
            night_import=None, test_mode=False, ahm_minimum_soc=20,
            reserve_advice={"status": "learning", "sample_count": 1},
        )

        self.assertIn("Поточний мінімум AHM", message)
        self.assertNotIn("Рекомендований мінімум AHM", message)

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

    def test_tariff_import_summary_reports_yesterday_and_current_month(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            test_mode=False,
            tariff_import={
                "yesterday_night_kwh": 4.8,
                "yesterday_normal_kwh": 0.7,
                "yesterday_cost_uah": 15.5,
                "month_night_kwh": 42.3,
                "month_normal_kwh": 11.8,
                "month_total_kwh": 54.1,
                "month_cost_uah": 164.75,
                "night_price": 2.5,
                "normal_price": 5.0,
            },
        )
        self.assertIn("Оцінка імпорту з мережі за вчора", message)
        self.assertIn("Нічний: 4.8 kWh — 12.00 UAH", message)
        self.assertIn("Звичайний: 0.7 kWh — 3.50 UAH", message)
        self.assertIn("Разом: 5.5 kWh — 15.50 UAH", message)
        self.assertIn("Поточний місяць", message)
        self.assertIn("54.1 kWh — 164.75 UAH", message)
        self.assertIn("не дані розрахункового лічильника", message)

    def test_incomplete_tariff_import_summary_is_omitted(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            test_mode=False,
            tariff_import={"yesterday_night_kwh": 4.8},
        )
        self.assertNotIn("Оцінка імпорту", message)


if __name__ == "__main__":
    unittest.main()
