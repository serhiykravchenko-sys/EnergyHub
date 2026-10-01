from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.report import (
    build_report,
    build_technical_report,
    compact_number,
    control_authority_message,
    grid_status_report_lines,
    inverter_duration_text,
    inverter_report_lines,
    morning_energy_lines,
    overnight_family_event_lines,
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


class ControlAuthorityTests(unittest.TestCase):
    def test_manual_heating_is_grouped_under_manual_control(self):
        message = control_authority_message(
            inverter="EH", reserve="EH", overload="EH", smart_heating="off",
        )
        self.assertEqual(
            message,
            "🧭 <b>Керування</b>\n"
            "Автоматично: режими інвертора · мін. заряд · захист від перевантаження\n"
            "Вручну: ♨️ теплові насоси",
        )

    def test_future_smart_heating_names_only_first_floor_as_automatic(self):
        message = control_authority_message(
            inverter="EH", reserve="EH", overload="EH", smart_heating="on",
        )
        self.assertIn("тепловий насос 1-го поверху", message)
        self.assertIn("теплові насоси 2-го та 3-го поверхів", message)


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
        self.assertEqual(lines[0], "🌤 Мінлива хмарність, від +15 до +30 °C")
        self.assertIn("🌧 Дощ: 16:00–18:00, близько 3.8 мм, ймовірність 70%", lines)
        self.assertIn("можлива гроза", lines[-1])
        self.assertIn("пориви вітру до 20 м/с", lines[-1])
        self.assertTrue(lines[-1].startswith("🟡"))

    def test_humidity_is_omitted_from_compact_family_weather(self):
        calm = [{
            "datetime": "2026-08-11T10:00:00+03:00",
            "condition": "sunny",
            "temperature": 20,
            "humidity": 55,
        }]
        self.assertFalse(any(
            "волог" in line
            for line in weather_summary(calm, TODAY, TZ, "km/h", 15)
        ))

        changing = [
            {**calm[0], "humidity": 35},
            {**calm[0], "datetime": "2026-08-11T18:00:00+03:00", "humidity": 70},
        ]
        lines = weather_summary(changing, TODAY, TZ, "km/h", 15)
        self.assertFalse(any("волог" in line for line in lines))

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
    def test_grid_support_and_ev_potential_use_configured_assumptions(self):
        support = morning_energy_lines(
            forecast=10, consumption_average=30, soc=25, reserve_soc=60,
            battery_capacity_kwh=16, battery_voltage_v=51.2,
            battery_charge_current_a=30, battery_efficiency=0.9,
            house_reference_current_a=16,
        )
        self.assertTrue(any("підтримки від ДТЕК" in line for line in support))
        self.assertFalse(any("електромобіля" in line for line in support))

        surplus = morning_energy_lines(
            forecast=44, consumption_average=10, soc=80, reserve_soc=20,
            battery_capacity_kwh=16, battery_voltage_v=51.2,
            battery_charge_current_a=30, battery_efficiency=0.9,
            house_reference_current_a=16,
        )
        self.assertTrue(any("Для «електрички»" in line for line in surplus))

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
        self.assertIn("ДТЕК був недоступний", lines[1])
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
            ahm_minimum_soc=20,
            heat_pump_management="heat pumps manual",
        )
        self.assertIn("sun 05:42 20:18", message)
        self.assertIn("full moon", message)
        self.assertIn("4.8 kW", message)
        self.assertIn("13:00", message)
        self.assertIn("Мін. заряд батареї: <b>20%</b>", message)
        self.assertIn("недостатньо даних", message)
        self.assertIn("heat pumps manual", message)

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
            night_import=None, ahm_minimum_soc=20,
        )

        self.assertIn("Мін. заряд батареї: <b>20%</b>", message)
        self.assertIn("рекомендація: <b>недостатньо даних</b>", message)
        self.assertNotIn("Рекомендований мінімум запасу батареї", message)

    def test_automatic_reserve_omits_recommendation(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            ahm_minimum_soc=35,
            weather_buffer={"management_mode": "automatic", "recommended_soc": 40},
        )
        self.assertNotIn("Мін. заряд батареї", message)
        self.assertNotIn("рекомендація", message)

    def test_complete_message(self):
        message = build_report(
            weather_lines=["🌤 Погода <b>сьогодні</b>: сонячно, від +15 до +30 °C"],
            solar_forecast=24.6,
            solar_window="09:20–17:30",
            threshold_w=300,
            consumption=18.6,
            snapshot={"soc": 82, "target_soc": 80, "mode": "hybrid_grid_hold"},
            night_import=7.4,
        )
        self.assertIn("🌤 Погода <b>сьогодні</b>", message)
        self.assertIn("☀️ прогноз <b>24.6 kWh</b>", message)
        self.assertNotIn("23:00–07:00", message)
        self.assertNotIn("Заряд о 07:00", message)

    def test_missing_values_are_omitted(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
        )
        self.assertEqual(message, "🌅 <b>Доброго ранку!</b>")

    def test_compact_control_status_precedes_heating(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            control_status_line=(
                "🧭 Керування: інвертор — EH · мін. заряд — EH · "
                "перевантаження — EH"
            ),
            heat_pump_management="♨️ Теплові насоси: <b>ручне керування</b>.",
        )
        self.assertIn("мін. заряд — EH", message)
        self.assertLess(message.index("🧭 Керування"), message.index("♨️"))

    def test_smart_plug_section_is_conditional(self):
        healthy = build_technical_report(smart_plug_lines=[])
        warning = build_technical_report(
            smart_plug_lines=["⚠️ Недоступна: Бойлер"],
        )

        self.assertIsNone(healthy)
        self.assertIn("🔌 <b>Розумні розетки</b>", warning)
        self.assertIn("⚠️ Недоступна: Бойлер", warning)

    def test_zero_operational_night_import_is_omitted(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={"mode": "solar"},
            night_import=0,
        )
        self.assertNotIn("Імпорт за ніч", message)

    def test_tariff_import_summary_reports_previous_week_on_monday(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            tariff_import={
                "week_night_kwh": 4.8,
                "week_normal_kwh": 0.7,
                "week_total_kwh": 5.5,
                "week_cost_uah": 15.5,
                "night_price": 2.5,
                "normal_price": 5.0,
            },
            report_date=date(2026, 9, 14),
        )
        self.assertIn("Імпорт з ДТЕК 07.09–13.09", message)
        self.assertIn("Нічний: 4.8 kWh — 12.00 грн", message)
        self.assertIn("Звичайний: 0.7 kWh — 3.50 грн", message)
        self.assertIn("Разом: <b>5.5 kWh — 15.50 грн", message)
        self.assertNotIn("не дані розрахункового лічильника", message)

    def test_zero_yesterday_tariffs_are_hidden_but_month_total_remains(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            tariff_import={
                "previous_month_night_kwh": 2.5,
                "previous_month_normal_kwh": 0,
                "previous_month_total_kwh": 2.5,
                "previous_month_cost_uah": 6.34,
                "night_price": 2.5,
                "normal_price": 5.0,
            },
            report_date=date(2026, 9, 1),
        )
        self.assertNotIn("за вчора", message)
        self.assertIn("Нічний: 2.5 kWh — 6.25 грн", message)
        self.assertNotIn("Звичайний:", message)
        self.assertIn("Разом: <b>2.5 kWh — 6.34 грн", message)

    def test_zero_tariff_line_is_hidden_when_other_tariff_has_import(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            tariff_import={
                "week_night_kwh": 2.5,
                "week_normal_kwh": 0,
                "week_total_kwh": 2.5,
                "week_cost_uah": 6.34,
                "night_price": 2.5,
                "normal_price": 5.0,
            },
            report_date=date(2026, 9, 14),
        )
        self.assertIn("Нічний: 2.5 kWh", message)
        self.assertNotIn("Звичайний:", message)

    def test_incomplete_tariff_import_summary_is_omitted(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            tariff_import={"yesterday_night_kwh": 4.8},
        )
        self.assertNotIn("Оцінка імпорту", message)

    def test_month_total_remains_when_yesterday_is_unavailable(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            tariff_import={
                "previous_month_night_kwh": 3.4,
                "previous_month_normal_kwh": 5,
                "previous_month_total_kwh": 8.4,
                "previous_month_cost_uah": 33.5,
                "night_price": 2.5,
                "normal_price": 5,
            },
            report_date=date(2026, 9, 1),
        )
        self.assertIn("Імпорт з ДТЕК за серпень", message)
        self.assertIn("Разом: <b>8.4 kWh — 33.50 грн", message)
        self.assertNotIn("за вчора", message)

    def test_overnight_grid_hold_and_return_are_in_morning(self):
        events = [{
            "kind": "grid_hold_started",
            "created_at": "2026-09-14T00:50:00+03:00",
            "message": "long live message",
            "reserve_soc": 20,
            "release_soc": 30,
        }, {
            "kind": "grid_hold_released",
            "created_at": "2026-09-14T07:15:00+03:00",
            "release_soc": 30,
        }]
        lines = overnight_family_event_lines(events)
        self.assertEqual(2, len(lines))
        self.assertIn("00:50", lines[0])
        self.assertIn("20%", lines[0])
        self.assertIn("30%", lines[1])
        self.assertIn("пріоритету сонця", lines[1])

    def test_overnight_reserve_change_preserves_reason(self):
        events = [{"kind": "battery_reserve_applied",
                   "created_at": "2026-09-25T23:52:00+03:00",
                   "message": "🔋 Мін. заряд: <b>20% → 40%</b> — прогноз генерації нижчий за споживання."}]
        self.assertIn("прогноз генерації нижчий", overnight_family_event_lines(events)[0])

    def test_overnight_inverter_fault_uses_current_mode_not_archived_instruction(self):
        events = [{"kind": "technical_inverter_strategy_fault",
                   "created_at": "2026-09-29T01:00:00+03:00",
                   "message": "Автоматичне керування резервом призупинене."}]
        observed_at = datetime.fromisoformat("2026-09-29T08:00:00+03:00")
        recovered = overnight_family_event_lines(
            events, inverter_mode="solar", mode_observed_at=observed_at)[0]
        unresolved = overnight_family_event_lines(
            events, inverter_mode="transition_failed", mode_observed_at=observed_at)[0]
        unknown = overnight_family_event_lines(
            events, mode_observed_at=observed_at)[0]
        self.assertIn("раніше", recovered)
        self.assertIn("станом на 08:00", recovered)
        self.assertNotIn("призупинене", recovered)
        self.assertIn("призупинене", unresolved)
        self.assertIn("станом на 08:00 стан потребував перевірки", unknown)
        self.assertNotIn("призупинене", unknown)

    def test_forecast_comparison_only_when_battery_not_full(self):
        base = dict(weather_lines=[], solar_forecast=10, solar_window=None,
                    threshold_w=300, consumption=None, snapshot={}, night_import=None)
        comparison = dict(forecast_kwh=10, actual_kwh=11, error_percent=10,
                          battery_full=False)
        self.assertIn("+10% до прогнозу", build_report(**base, forecast_accuracy=comparison))
        self.assertNotIn("Прогноз учора", build_report(**base,
                         forecast_accuracy=dict(comparison, battery_full=True)))
        self.assertNotIn("Учора батарея не досягла 100%", build_report(**base,
                         forecast_accuracy=dict(comparison, battery_full=None)))

    def test_zero_month_import_is_hidden(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            tariff_import={"month_total_kwh": 0, "month_cost_uah": 0},
        )
        self.assertNotIn("З мережі за місяць", message)
        self.assertNotIn("Інформаційна оцінка", message)

    def test_forecast_color_compares_with_average_consumption(self):
        deficit = build_report(
            weather_lines=[], solar_forecast=10, solar_window=None,
            threshold_w=300, consumption=18.6, snapshot={}, night_import=None,
            consumption_average=18.6, consumption_sample_count=3,
        )
        self.assertIn("🔵 прогноз <b>10 kWh</b>", deficit)
        self.assertNotIn("Прогноз генерації нижчий", deficit)
        surplus = build_report(
            weather_lines=[], solar_forecast=20, solar_window=None,
            threshold_w=300, consumption=18.6, snapshot={}, night_import=None,
            consumption_average=18.6, consumption_sample_count=3,
        )
        self.assertIn("🟠 прогноз <b>20 kWh</b>", surplus)

    def test_current_generation_uses_blue_yellow_and_orange_thresholds(self):
        def message(value):
            return build_report(
                weather_lines=[], solar_forecast=None, solar_window=None,
                threshold_w=300, consumption=None, snapshot={}, night_import=None,
                current_strategy_lines=["🔌 На 08:00: ДТЕК"], solar_average_w=value,
            )

        self.assertIn("🔵 Генерація зараз: <b>0.3 kW</b>", message(299))
        self.assertIn("🟡 Генерація зараз: <b>0.3 kW</b>", message(300))
        self.assertIn("🟠 Генерація зараз: <b>1 kW</b>", message(1000))

    def test_grid_status_is_conditional(self):
        self.assertEqual([], grid_status_report_lines("Normal", 24, 0))
        lines = grid_status_report_lines("Panic", 23.3, 0.7)
        self.assertIn("доступний 23 год 18 хв", lines[0])
        self.assertIn("недоступний 42 хв", lines[0])
        self.assertIn("Критична", lines[1])
        self.assertTrue(lines[1].startswith("🔴"))

    def test_weather_buffer_activation_is_explicitly_dry_run(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            ahm_minimum_soc=20,
            weather_buffer={
                "dry_run": True,
                "transition": "activate",
                "daily_plan_fresh": True,
                "weather_source_status": "fresh",
                "grid_confidence": "normal",
                "baseline_soc": 20,
                "recommended_soc": 40,
                "weather_modifier_percent": 20,
            },
        )
        self.assertIn("Мін. заряд батареї: <b>20%</b> · рекомендація: <b>40%</b>", message)
        self.assertIn("Керування мін. зарядом: ручне", message)
        self.assertNotIn("змінено", message)

    def test_weather_buffer_restoration_is_reported(self):
        message = build_report(
            weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=None, snapshot={}, night_import=None,
            ahm_minimum_soc=20,
            weather_buffer={
                "dry_run": True,
                "transition": "decrease",
                "daily_plan_fresh": True,
                "weather_source_status": "fresh",
                "grid_confidence": "normal",
                "baseline_soc": 20,
                "recommended_soc": 20,
                "previous_recommended_soc": 40,
            },
        )
        self.assertIn("Мін. заряд батареї: <b>20%</b> · рекомендація: <b>20%</b>", message)
        self.assertNotIn("40% → 20%", message)

    def test_three_day_average_and_overnight_weather_are_reported(self):
        message = build_report(
            weather_lines=[], solar_forecast=6, solar_window=None,
            threshold_w=300, consumption=5, snapshot={}, night_import=None,
            consumption_average=8, consumption_sample_count=3,
            weather_warning_lines=["• Рівень 2: сильний вітер."],
        )
        self.assertIn("Споживання: учора 5 kWh · середнє за 3 дні: 8 kWh", message)
        self.assertIn("• Рівень 2: сильний вітер.", message)
        self.assertNotIn("Попередження Укргідрометцентру за ніч", message)

    def test_line_fail_warning_is_omitted_from_morning_history(self):
        lines = inverter_report_lines(
            [{"attributes": {"event": {
                "started_at": "2026-08-10T11:12:00+03:00",
                "messages": ["line_fail_warning"],
            }}}],
            date(2026, 8, 10),
            TZ,
        )
        self.assertEqual([], lines)

    def test_soc_anomaly_summary_is_included_when_present(self):
        message = build_technical_report(
            soc_anomaly_lines=[
                "⚠️ <b>Стрибки SOC після попереднього звіту: 1</b>",
                "Найбільший: 70% → 100% (+30%).",
            ],
        )
        self.assertIn("Стрибки SOC після попереднього звіту: 1", message)
        self.assertIn("70% → 100%", message)
        self.assertIn("Технічний стан EnergyHub", message)


if __name__ == "__main__":
    unittest.main()
