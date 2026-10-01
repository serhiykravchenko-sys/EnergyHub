from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from .presentation import mode_label, CONFIDENCE_NAMES


CONDITIONS_UK = {
    "clear-night": "ясно",
    "cloudy": "хмарно",
    "fog": "туман",
    "hail": "град",
    "lightning": "гроза",
    "lightning-rainy": "гроза з дощем",
    "partlycloudy": "мінлива хмарність",
    "pouring": "сильна злива",
    "rainy": "дощ",
    "snowy": "сніг",
    "snowy-rainy": "дощ зі снігом",
    "sunny": "сонячно",
    "windy": "вітряно",
    "windy-variant": "хмарно та вітряно",
    "exceptional": "небезпечні погодні умови",
}
PRECIPITATION_CONDITIONS = {"hail", "lightning-rainy", "pouring", "rainy", "snowy", "snowy-rainy"}


def control_authority_message(
    *,
    inverter: str,
    reserve: str,
    overload: str,
    smart_heating: str,
) -> str:
    automatic: list[str] = []
    manual: list[str] = []
    uncertain: list[str] = []

    for label, owner in (
        ("режими інвертора", inverter),
        ("мін. заряд", reserve),
        ("захист від перевантаження", overload),
    ):
        if owner == "EH":
            automatic.append(label)
        elif owner == "вручну":
            manual.append(label)
        else:
            uncertain.append(label)

    if smart_heating == "on":
        automatic.append("тепловий насос 1-го поверху")
        manual.append("♨️ теплові насоси 2-го та 3-го поверхів")
    elif smart_heating == "off":
        manual.append("♨️ теплові насоси")
    else:
        uncertain.append("♨️ опалення")

    lines = ["🧭 <b>Керування</b>"]
    if automatic:
        lines.append("Автоматично: " + " · ".join(automatic))
    if manual:
        lines.append("Вручну: " + " · ".join(manual))
    if uncertain:
        lines.append("Уточнюється: " + " · ".join(uncertain))
    return "\n".join(lines)


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def compact_number(value: float, digits: int = 1) -> str:
    rounded = round(value, digits)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def temperature(value: float) -> str:
    rounded = int(value + 0.5) if value >= 0 else int(value - 0.5)
    return f"{rounded:+d}"


def local_datetime(value: Any, timezone: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def weather_summary(
    forecast: list[dict[str, Any]],
    today,
    timezone: ZoneInfo,
    wind_unit: str,
    strong_wind_ms: float,
    forecast_type: str = "hourly",
    humidity_low_percent: float = 30,
    humidity_high_percent: float = 80,
    humidity_change_percent: float = 25,
) -> list[str]:
    periods = []
    for item in forecast:
        stamp = local_datetime(item.get("datetime"), timezone)
        if stamp and stamp.date() == today:
            periods.append((stamp, item))
    if not periods:
        return []

    temperatures = [value for _, item in periods for key in ("templow", "temperature") if (value := number(item.get(key))) is not None]
    conditions = [str(item.get("condition")) for _, item in periods if item.get("condition")]
    daytime_conditions = [str(item.get("condition")) for stamp, item in periods if 6 <= stamp.hour < 21 and item.get("condition")]
    dominant_pool = daytime_conditions or conditions
    dominant = Counter(dominant_pool).most_common(1)[0][0] if dominant_pool else ""
    weather_text = CONDITIONS_UK.get(dominant, dominant or "прогноз доступний")
    if temperatures:
        weather_text += f", від {temperature(min(temperatures))} до {temperature(max(temperatures))} °C"
    sentence_weather = weather_text[:1].upper() + weather_text[1:]
    lines = [f"🌤 {escape(sentence_weather)}"]

    wet = []
    for stamp, item in periods:
        amount = number(item.get("precipitation")) or 0.0
        probability = number(item.get("precipitation_probability")) or 0.0
        condition = str(item.get("condition") or "")
        if amount > 0 or condition in PRECIPITATION_CONDITIONS:
            wet.append((stamp, item, amount, probability, condition))
    if wet:
        conditions_wet = {item[4] for item in wet}
        if "snowy-rainy" in conditions_wet:
            kind = "Дощ зі снігом"
        elif "snowy" in conditions_wet:
            kind = "Сніг"
        elif "hail" in conditions_wet:
            kind = "Град"
        else:
            kind = "Дощ"
        if forecast_type == "hourly":
            start, end = wet[0][0], wet[-1][0] + timedelta(hours=1)
            detail = f"{start:%H:%M}–{end:%H:%M}"
        else:
            detail = "протягом дня"
        total = sum(item[2] for item in wet)
        probability = max(item[3] for item in wet)
        if total > 0:
            suffix = " мм водного еквівалента" if kind in {"Сніг", "Дощ зі снігом"} else " мм"
            detail += f", близько {compact_number(total)}{suffix}"
        if probability > 0:
            detail += f", ймовірність {compact_number(probability, 0)}%"
        lines.append(f"🌧 {kind}: {detail}")

    warning_parts = []
    condition_set = set(conditions)
    if condition_set & {"lightning", "lightning-rainy"}:
        warning_parts.append("можлива гроза")
    if "pouring" in condition_set:
        warning_parts.append("можлива сильна злива")
    if "hail" in condition_set:
        warning_parts.append("можливий град")
    if "fog" in condition_set:
        warning_parts.append("можливий туман")
    wind_values = [number(item.get("wind_gust_speed")) or number(item.get("wind_speed")) for _, item in periods]
    wind_values = [value for value in wind_values if value is not None]
    if wind_values:
        maximum = max(wind_values)
        unit = (wind_unit or "km/h").lower()
        if unit in {"km/h", "kmh", "kph"}:
            maximum_ms = maximum / 3.6
        elif unit in {"mph"}:
            maximum_ms = maximum * 0.44704
        elif unit in {"kn", "kt", "kts"}:
            maximum_ms = maximum * 0.514444
        else:
            maximum_ms = maximum
        if maximum_ms >= strong_wind_ms:
            warning_parts.append(f"пориви вітру до {compact_number(maximum_ms)} м/с")
    if warning_parts:
        lines.append("🟡 " + "; ".join(warning_parts))
    return lines


def useful_solar_window(hourly: list[dict[str, Any]], today, timezone: ZoneInfo, threshold_w: int) -> str | None:
    qualifying = []
    all_periods = []
    for item in hourly:
        stamp = local_datetime(item.get("period_start"), timezone)
        estimate_kw = number(item.get("pv_estimate"))
        if stamp and stamp.date() == today:
            all_periods.append(stamp)
            if estimate_kw is not None and estimate_kw * 1000 >= threshold_w:
                qualifying.append(stamp)
    if not qualifying:
        return None
    qualifying.sort()
    period_minutes = 60
    all_periods.sort()
    if len(all_periods) > 1:
        differences = [int((right - left).total_seconds() / 60) for left, right in zip(all_periods, all_periods[1:]) if right > left]
        if differences:
            period_minutes = min(60, min(differences))
    end = qualifying[-1].timestamp() + period_minutes * 60
    end_time = datetime.fromtimestamp(end, timezone)
    return f"{qualifying[0]:%H:%M}–{end_time:%H:%M}"


def solar_peak(hourly: list[dict[str, Any]], today, timezone: ZoneInfo) -> tuple[float, str] | None:
    candidates = []
    for item in hourly:
        stamp = local_datetime(item.get("period_start"), timezone)
        estimate_kw = number(item.get("pv_estimate"))
        if stamp and stamp.date() == today and estimate_kw is not None:
            candidates.append((estimate_kw, stamp))
    if not candidates:
        return None
    power, stamp = max(candidates, key=lambda item: item[0])
    return power, f"{stamp:%H:%M}"


def sun_moon_lines(sun_state: dict[str, Any] | None, moon_state: dict[str, Any] | None, today, timezone: ZoneInfo) -> list[str]:
    lines = []
    sun_attributes = (sun_state or {}).get("attributes", {})
    rising = local_datetime(sun_attributes.get("next_rising"), timezone)
    setting = local_datetime(sun_attributes.get("next_setting"), timezone)
    if rising and rising.date() > today:
        rising -= timedelta(days=1)
    if setting and setting.date() < today:
        setting += timedelta(days=1)
    if rising and setting and rising.date() == today and setting.date() == today:
        lines.append(f"🌄 Сонце: схід {rising:%H:%M}, захід {setting:%H:%M}")

    moon = str((moon_state or {}).get("state") or "").lower()
    if moon == "full_moon":
        lines.append("🌕 Місяць: повня")
    elif moon == "new_moon":
        lines.append("🌑 Місяць: молодик")
    return lines


def mode_name(value: Any) -> str | None:
    return mode_label(value)


INVERTER_MESSAGE_NAMES = {
    "over_load": "перевантаження",
    "overload": "перевантаження",
    "battery_low": "низький заряд батареї",
    "battery_under_shutdown": "аварійно низька напруга батареї",
    "over_temperature": "перегрів інвертора",
    "fan_locked": "блокування вентилятора",
    "output_short_circuited": "коротке замикання виходу",
    "battery_voltage_high": "висока напруга батареї",
}

IGNORED_INVERTER_REPORT_MESSAGES = {
    "pv_loss_warning",
    "line_fail",
    "line_fail_warning",
}


def _inverter_message_name(value: Any) -> str:
    key = str(value or "unknown").strip().lower()
    return INVERTER_MESSAGE_NAMES.get(key, key.replace("_", " "))


def inverter_duration_text(value: Any) -> str | None:
    seconds_value = number(value)
    if seconds_value is None or seconds_value < 0:
        return None
    total_seconds = int(round(seconds_value))
    if total_seconds < 60:
        return f"{total_seconds} с"
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes} хв {seconds} с"
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def inverter_report_lines(
    entities: list[dict[str, Any]],
    report_day,
    timezone: ZoneInfo,
) -> list[str]:
    events = []
    seen = set()
    for entity in entities:
        event = (entity.get("attributes") or {}).get("event")
        if not isinstance(event, dict):
            continue
        started_raw = event.get("started_at")
        try:
            started = datetime.fromisoformat(str(started_raw))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone)
            started = started.astimezone(timezone)
        except (TypeError, ValueError):
            continue
        if started.date() != report_day or started.isoformat() in seen:
            continue
        messages = [
            str(item)
            for item in event.get("messages", [])
            if str(item).strip().lower()
            not in IGNORED_INVERTER_REPORT_MESSAGES
        ]
        if not messages:
            continue
        seen.add(started.isoformat())
        report_event = dict(event)
        report_event["messages"] = messages
        events.append((started, report_event))
    if not events:
        return []

    events.sort(key=lambda item: item[0])
    lines = [
        f"⚠️ У доступній історії за вчора повідомлень інвертора: "
        f"<b>{len(events)}</b>."
    ]
    for started, event in events:
        names = ", ".join(
            _inverter_message_name(item)
            for item in event.get("messages", [])
        ) or "невідоме повідомлення"
        conditions = event.get("latest_conditions") or {}
        details = []
        load_w = number(conditions.get("load_w"))
        load_percent = number(conditions.get("load_percent"))
        if load_w is not None:
            load = f"навантаження {compact_number(load_w)} W"
            if load_percent is not None:
                load += f" ({compact_number(load_percent)}%)"
            details.append(load)
        mode = mode_name(conditions.get("operating_mode"))
        if mode:
            details.append(f"режим {mode}")
        grid = conditions.get("grid_available")
        if grid is True:
            details.append("ДТЕК був доступний")
        elif grid is False:
            details.append("ДТЕК був недоступний")
        recovered = event.get("cleared_at") is not None
        if event.get("recovery") == "superseded":
            recovery = "замінено іншим набором повідомлень"
        else:
            recovery = "повідомлення зникло" if recovered else "не закрите"
        duration = inverter_duration_text(event.get("duration_seconds"))
        if recovered and duration is not None:
            recovery += f" через {duration}"
        suffix = f"; {', '.join(details)}" if details else ""
        lines.append(
            f"• {started:%H:%M} — <b>{escape(names)}</b>{suffix}; {recovery}."
        )
    return lines


MONTHS_UK = {
    1: "січень", 2: "лютий", 3: "березень", 4: "квітень",
    5: "травень", 6: "червень", 7: "липень", 8: "серпень",
    9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень",
}


def tariff_import_report_lines(values: dict[str, Any] | None, report_date=None) -> list[str]:
    values = values or {}
    if report_date is None:
        return []
    night_price = number(values.get("night_price"))
    normal_price = number(values.get("normal_price"))
    if night_price is None or normal_price is None:
        return []

    def section(prefix, title):
        night = number(values.get(f"{prefix}_night_kwh"))
        normal = number(values.get(f"{prefix}_normal_kwh"))
        total = number(values.get(f"{prefix}_total_kwh"))
        cost = number(values.get(f"{prefix}_cost_uah"))
        if any(value is None or value < 0 for value in (night, normal, total, cost)):
            return []
        result = [f"⚡ <b>{title}</b>"]
        if night > 0:
            result.append(f"🌙 Нічний: {compact_number(night)} kWh — {night * night_price:.2f} грн")
        if normal > 0:
            result.append(f"☀️ Звичайний: {compact_number(normal)} kWh — {normal * normal_price:.2f} грн")
        result.append(f"Разом: <b>{compact_number(total)} kWh — {cost:.2f} грн</b>")
        return result

    sections = []
    if report_date.weekday() == 0:
        week_end = report_date - timedelta(days=1)
        week_start = week_end - timedelta(days=6)
        sections.append(section("week", f"Імпорт з ДТЕК {week_start:%d.%m}–{week_end:%d.%m}"))
    if report_date.day == 1:
        previous_month = (report_date.replace(day=1) - timedelta(days=1))
        sections.append(section("previous_month", f"Імпорт з ДТЕК за {MONTHS_UK[previous_month.month]}"))
    lines = []
    for item in sections:
        if not item:
            continue
        if lines:
            lines.append("")
        lines.extend(item)
    return lines


def morning_energy_lines(*, forecast, consumption_average, soc, reserve_soc,
                         battery_capacity_kwh, battery_voltage_v,
                         battery_charge_current_a, battery_efficiency,
                         house_reference_current_a):
    values = (forecast, consumption_average, soc, reserve_soc)
    if any(number(value) is None for value in values):
        return []
    forecast, consumption_average, soc, reserve_soc = map(float, values)
    efficiency = max(0.5, min(1.0, float(battery_efficiency)))
    house_deficit = max(0.0, consumption_average - forecast)
    reserve_energy = max(0.0, reserve_soc - soc) / 100 * battery_capacity_kwh / efficiency
    battery_power = battery_voltage_v * battery_charge_current_a / 1000
    house_power = 230 * house_reference_current_a / 1000
    hours = max(
        reserve_energy / battery_power if battery_power > 0 else 0,
        house_deficit / house_power if house_power > 0 else 0,
    )
    lines = []
    if hours > 0.05:
        lines.append(f"⚡ <b>Сьогодні потрібно близько {compact_number(round(hours, 1))} год підтримки від ДТЕК.</b>")
    battery_full_energy = max(0.0, 100 - soc) / 100 * battery_capacity_kwh / efficiency
    ev_kwh = max(0.0, forecast - consumption_average - battery_full_energy)
    if ev_kwh >= 0.5:
        distance = ev_kwh / 15 * 100
        lines.append(f"🚗 Для «електрички»: <b>{compact_number(round(ev_kwh, 1))} kWh ≈ {round(distance):d} км</b>")
    return lines


def overnight_family_event_lines(
    events: list[dict[str, Any]] | None,
    *,
    inverter_mode: str | None = None,
    mode_observed_at: datetime | None = None,
) -> list[str]:
    """Condense family notifications collected during quiet hours."""
    if not events:
        return []
    lines = []
    seen: set[str] = set()
    for event in sorted(events, key=lambda item: str(item.get("created_at") or "")):
        try:
            occurred = datetime.fromisoformat(str(event.get("created_at")))
            clock = occurred.strftime("%H:%M")
        except (TypeError, ValueError):
            clock = "--:--"
        kind = str(event.get("kind") or "")
        if kind == "technical_inverter_strategy_fault":
            observed_when = (f"станом на {mode_observed_at:%H:%M}"
                             if mode_observed_at else "на час підготовки звіту")
            if inverter_mode in {"solar", "panic", "panic_grid_hold",
                                 "hybrid_charging", "hybrid_grid_hold"}:
                summary = (f"• {clock} — EnergyHub раніше не підтвердив режим інвертора; "
                           f"{observed_when} підтверджено режим {escape(inverter_mode)}.")
            elif inverter_mode in {"transition_failed", "inconsistent"}:
                summary = (f"• {clock} — EnergyHub не підтвердив режим інвертора; "
                           f"{observed_when} автоматичне керування резервом було призупинене.")
            else:
                summary = (f"• {clock} — EnergyHub не підтвердив режим інвертора; "
                           f"{observed_when} стан потребував перевірки.")
        elif kind == "grid_hold_started":
            reserve = number(event.get("reserve_soc"))
            release = number(event.get("release_soc"))
            summary = (f"• {clock} — резерв {compact_number(reserve)}% досягнуто; "
                       f"режим сонце + ДТЕК, повернення до пріоритету сонця при {compact_number(release)}%"
                       if reserve is not None and release is not None
                       else f"• {clock} — режим сонце + ДТЕК для збереження резерву")
        elif kind == "grid_hold_released":
            release = number(event.get("release_soc"))
            summary = (f"• {clock} — заряд досяг {compact_number(release)}%, будинок повернувся до пріоритету сонця"
                       if release is not None else f"• {clock} — будинок повернувся до пріоритету сонця")
        elif kind == "battery_reserve_charging":
            reserve = number(event.get("reserve_soc"))
            summary = (f"• {clock} — ДТЕК підключено для заряджання батареї до {compact_number(reserve)}%"
                       if reserve is not None else f"• {clock} — ДТЕК підключено для заряджання батареї")
        elif kind == "battery_reserve_applied":
            message = str(event.get("message") or "")
            summary = f"• {clock} — {message}" if message else f"• {clock} — мін. заряд змінено"
        else:
            message = str(event.get("message") or "Подія EnergyHub")
            headline = next((line.strip() for line in message.splitlines() if line.strip()), "Подія EnergyHub")
            summary = f"• {clock} — {headline}"
        if summary in seen:
            continue
        seen.add(summary)
        lines.append(summary)
    return lines


CONFIDENCE_UK = CONFIDENCE_NAMES


def grid_status_report_lines(
    confidence: Any,
    available_hours: Any,
    outage_hours: Any,
) -> list[str]:
    confidence_key = str(confidence or "").strip().lower()
    available = number(available_hours)
    outage = number(outage_hours)
    lines = []
    if available is not None and available < 23.999:
        if outage is None:
            outage = max(0.0, 24 - available)

        def duration(value: float) -> str:
            minutes = max(0, round(value * 60))
            hours, remainder = divmod(minutes, 60)
            if hours and remainder:
                return f"{hours} год {remainder} хв"
            if hours:
                return f"{hours} год"
            return f"{remainder} хв"

        lines.append(
            "ℹ️ ДТЕК за 24 год: доступний "
            f"{duration(available)}; недоступний {duration(outage)}."
        )
    if confidence_key and confidence_key != "normal":
        marker = "🔴" if confidence_key in {"risk", "panic"} else "🟡"
        lines.append(
            f"{marker} Надійність ДТЕК: "
            f"<b>{escape(CONFIDENCE_UK.get(confidence_key, str(confidence)))}</b>."
        )
    return lines


def build_report(*, weather_lines: list[str], solar_forecast: float | None, solar_window: str | None, threshold_w: int, consumption: float | None, snapshot: dict[str, Any], night_import: float | None, astronomy_lines: list[str] | None = None, solar_peak_value: tuple[float, str] | None = None, ahm_minimum_soc: float | None = None, weather_buffer: dict[str, Any] | None = None, control_status_line: str | None = None, heat_pump_management: str | None = None, device_health_lines: list[str] | None = None, smart_plug_lines: list[str] | None = None, inverter_lines: list[str] | None = None, tariff_import: dict[str, Any] | None = None, grid_status_lines: list[str] | None = None, calendar_lines: list[str] | None = None, soc_anomaly_lines: list[str] | None = None, consumption_average: float | None = None, consumption_sample_count: int = 0, weather_warning_lines: list[str] | None = None, weather_restoration_lines: list[str] | None = None, current_strategy_lines: list[str] | None = None, overnight_event_lines: list[str] | None = None, report_date=None, current_soc: float | None = None, solar_average_w: float | None = None, energy_outlook_lines: list[str] | None = None, forecast_accuracy: dict[str, Any] | None = None) -> str:
    lines = ["🌅 <b>Доброго ранку!</b>"]
    if calendar_lines:
        lines.extend(["", *calendar_lines])
    if weather_lines:
        lines.extend(["", *weather_lines])
    if weather_warning_lines:
        distinct_warnings = [line for line in weather_warning_lines if line not in (weather_lines or [])]
        if distinct_warnings:
            lines.extend(["", *distinct_warnings])
    if weather_restoration_lines:
        lines.extend(["", *weather_restoration_lines])
    if astronomy_lines:
        lines.extend(["", *astronomy_lines])
    solar_parts = []
    if solar_forecast is not None:
        if consumption_average is None:
            forecast_marker = "☀️"
        elif solar_forecast > consumption_average:
            forecast_marker = "🟠"
        else:
            forecast_marker = "🔵"
        solar_parts.append(
            f"{forecast_marker} прогноз <b>{compact_number(solar_forecast)} kWh</b>"
        )
    if solar_window:
        solar_parts.append(f">{threshold_w} W: {solar_window}")
    elif solar_forecast is not None:
        solar_parts.append(f">{threshold_w} W не очікується")
    if solar_peak_value is not None:
        peak_kw, peak_time = solar_peak_value
        solar_parts.append(f"пік {compact_number(peak_kw)} kW о {peak_time}")
    if solar_parts:
        lines.extend(["", " · ".join(solar_parts)])
    if consumption is not None:
        consumption_line = f"🏠 Споживання: учора {compact_number(consumption)} kWh"
        if consumption_average is not None and consumption_sample_count:
            consumption_line += (
                f" · середнє за {consumption_sample_count} дні: "
                f"{compact_number(consumption_average)} kWh"
            )
        lines.extend(["", consumption_line])
    elif consumption_average is not None and consumption_sample_count:
        day_word = "день" if consumption_sample_count == 1 else "дні"
        lines.append(
            f"📊 Середнє за останні {consumption_sample_count} {day_word}: "
            f"{compact_number(consumption_average)} kWh"
        )
    if overnight_event_lines:
        lines.extend(["", *overnight_event_lines])
    if current_strategy_lines:
        status = list(current_strategy_lines)
        if current_soc is not None:
            status.append(f"🔋 Заряд <b>{compact_number(current_soc)}%</b>")
        if solar_average_w is not None:
            solar_kw = solar_average_w / 1000
            marker = "🔵" if solar_kw < 0.3 else "🟡" if solar_kw < 1 else "🟠"
            status.append(
                f"{marker} Генерація зараз: <b>{compact_number(solar_kw)} kW</b>"
            )
        lines.extend(["", *status])
    if forecast_accuracy:
        actual = number(forecast_accuracy.get("actual_kwh"))
        forecast_value = number(forecast_accuracy.get("forecast_kwh"))
        error = number(forecast_accuracy.get("error_percent"))
        if forecast_accuracy.get("battery_full") is False and actual is not None and forecast_value is not None and error is not None:
            sign = "+" if error >= 0 else ""
            lines.extend(["", f"🎯 Учора батарея не досягла 100%: прогноз {compact_number(forecast_value)} kWh · генерація {compact_number(actual)} kWh ({sign}{compact_number(error)}% до прогнозу)."])
    if energy_outlook_lines:
        lines.extend(["", *energy_outlook_lines])
    tariff_lines = tariff_import_report_lines(tariff_import, report_date)
    if tariff_lines:
        lines.extend(["", *tariff_lines])
    if grid_status_lines:
        lines.extend(["", *grid_status_lines])
    from .events import manual_reserve_advice
    if ahm_minimum_soc is not None or weather_buffer:
        advice = manual_reserve_advice(dict(weather_buffer or {},
                    applied_minimum_soc=ahm_minimum_soc))
        if advice:
            lines.extend(["", advice])
    if control_status_line:
        lines.extend(["", control_status_line])
    if heat_pump_management:
        lines.append(heat_pump_management)
    return "\n".join(lines)


def build_technical_report(*, log_digest_lines: list[str] | None = None,
                           soc_anomaly_lines: list[str] | None = None,
                           device_health_lines: list[str] | None = None,
                           smart_plug_lines: list[str] | None = None,
                           inverter_lines: list[str] | None = None) -> str | None:
    """Return a separate morning diagnostic message only when evidence exists."""
    other_evidence = any((soc_anomaly_lines, device_health_lines,
                          smart_plug_lines, inverter_lines))
    if (log_digest_lines and log_digest_lines[0].startswith("✅")
            and all(line.startswith("ℹ️ Supervisor не перевіряється")
                    for line in log_digest_lines[1:]) and not other_evidence):
        return None
    sections: list[str] = []
    if log_digest_lines:
        sections.extend(["🧾 <b>HA Core · поточний сеанс, до 24 годин</b>", *log_digest_lines])
    if soc_anomaly_lines:
        if sections:
            sections.append("")
        sections.extend(soc_anomaly_lines)
    if device_health_lines:
        if sections:
            sections.append("")
        sections.extend(["🏠 <b>Стан домашніх датчиків</b>", *device_health_lines])
    if smart_plug_lines:
        if sections:
            sections.append("")
        sections.extend(["🔌 <b>Розумні розетки</b>", *smart_plug_lines])
    if inverter_lines:
        if sections:
            sections.append("")
        sections.extend(["🔴 <b>Повідомлення інвертора</b>", *inverter_lines])
    if not sections:
        return None
    return "\n".join(["⚙️ <b>Технічний стан EnergyHub</b>", "", *sections])
