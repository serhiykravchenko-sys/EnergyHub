from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo


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


def weather_summary(forecast: list[dict[str, Any]], today, timezone: ZoneInfo, wind_unit: str, strong_wind_ms: float, forecast_type: str = "hourly") -> list[str]:
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
    lines = [f"🌤 Погода <b>сьогодні</b>: {escape(weather_text)}"]

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
        lines.append("⚠️ " + "; ".join(warning_parts))
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
    mode = str(value or "").lower()
    if mode.startswith("hybrid"):
        return "Hybrid"
    if mode.startswith("panic"):
        return "Panic"
    if mode == "solar":
        return "Solar"
    return str(value) if value not in (None, "", "unknown", "unavailable") else None


def reserve_advice_message(advice: dict[str, Any] | None) -> str | None:
    if not advice:
        return None
    status = str(advice.get("status") or "").lower()
    current = number(advice.get("current_soc"))
    suggested = number(advice.get("suggested_soc"))
    samples = int(number(advice.get("sample_count")) or 0)
    if status == "learning":
        return f"🧭 Порада AHM навчається: <b>{samples}/3</b> завершених ранків із поточним запасом."
    if current is None or suggested is None:
        return None
    current_text = compact_number(current)
    suggested_text = compact_number(suggested)
    if status == "increase":
        return f"🧭 Захисний запас AHM: <b>{current_text}% → {suggested_text}%</b>. Рекомендація; змініть повзунок вручну."
    if status == "decrease":
        return f"🧭 Захисний запас AHM: <b>{suggested_text}% ← {current_text}%</b>. Рекомендація; змініть повзунок вручну."
    if status == "keep":
        return f"🧭 Захисний запас AHM <b>{current_text}%</b> відповідає останнім трьом ранкам."
    return None


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
            details.append("мережа була доступна")
        elif grid is False:
            details.append("мережа була відсутня")
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


def tariff_import_report_lines(values: dict[str, Any] | None) -> list[str]:
    values = values or {}
    yesterday_night = number(values.get("yesterday_night_kwh"))
    yesterday_normal = number(values.get("yesterday_normal_kwh"))
    yesterday_cost = number(values.get("yesterday_cost_uah"))
    month_night = number(values.get("month_night_kwh"))
    month_normal = number(values.get("month_normal_kwh"))
    month_total = number(values.get("month_total_kwh"))
    month_cost = number(values.get("month_cost_uah"))
    night_price = number(values.get("night_price"))
    normal_price = number(values.get("normal_price"))

    required = (
        yesterday_night,
        yesterday_normal,
        yesterday_cost,
        month_night,
        month_normal,
        month_total,
        month_cost,
        night_price,
        normal_price,
    )
    if any(value is None or value < 0 for value in required):
        return []

    yesterday_night_cost = yesterday_night * night_price
    yesterday_normal_cost = yesterday_normal * normal_price
    def money(value):
        return f"{value:.2f}"
    return [
        "⚡ <b>Оцінка імпорту з мережі за вчора</b>",
        (
            f"🌙 Нічний: {compact_number(yesterday_night)} kWh — "
            f"{money(yesterday_night_cost)} UAH"
        ),
        (
            f"☀️ Звичайний: {compact_number(yesterday_normal)} kWh — "
            f"{money(yesterday_normal_cost)} UAH"
        ),
        (
            f"Разом: {compact_number(yesterday_night + yesterday_normal)} kWh — "
            f"{money(yesterday_cost)} UAH"
        ),
        "",
        "📅 <b>Поточний місяць</b>",
        f"🌙 Нічний: {compact_number(month_night)} kWh",
        f"☀️ Звичайний: {compact_number(month_normal)} kWh",
        (
            f"Разом: {compact_number(month_total)} kWh — "
            f"{money(month_cost)} UAH"
        ),
        "ℹ️ Інформаційна оцінка, не дані розрахункового лічильника.",
    ]


def build_report(*, weather_lines: list[str], solar_forecast: float | None, solar_window: str | None, threshold_w: int, consumption: float | None, snapshot: dict[str, Any], night_import: float | None, test_mode: bool, astronomy_lines: list[str] | None = None, solar_peak_value: tuple[float, str] | None = None, reserve_advice: dict[str, Any] | None = None, ahm_minimum_soc: float | None = None, heat_pump_management: str | None = None, device_health_lines: list[str] | None = None, inverter_lines: list[str] | None = None, tariff_import: dict[str, Any] | None = None) -> str:
    lines = ["🌅 <b>Доброго ранку!</b>"]
    if test_mode:
        lines.append("🧪 Тестовий ранковий звіт")
    if weather_lines:
        lines.extend(["", *weather_lines])
    if astronomy_lines:
        lines.extend(["", *astronomy_lines])
    solar_lines = []
    if solar_forecast is not None:
        solar_lines.append(f"☀️ Прогноз генерації: {compact_number(solar_forecast)} kWh")
    if solar_window:
        solar_lines.append(f"🔆 Корисна генерація від {threshold_w} W: {solar_window}")
    elif solar_forecast is not None:
        solar_lines.append(f"🔆 Генерація від {threshold_w} W сьогодні не очікується")
    if solar_peak_value is not None:
        peak_kw, peak_time = solar_peak_value
        solar_lines.append(f"📈 Пік генерації: близько {compact_number(peak_kw)} kW о {peak_time}")
    if solar_lines:
        lines.extend(["", *solar_lines])
    if consumption is not None:
        lines.extend(["", f"🏠 Споживання вчора: {compact_number(consumption)} kWh"])

    energy_lines = []
    mode = mode_name(snapshot.get("mode"))
    if mode:
        energy_lines.append(f"🌙 Нічний режим: {escape(mode)}")
    if night_import is not None:
        energy_lines.append(f"⚡ Імпорт за ніч: {compact_number(night_import)} kWh")
    soc = number(snapshot.get("soc"))
    target = number(snapshot.get("target_soc"))
    if soc is not None:
        soc_line = f"🔋 SOC о 07:00: {compact_number(soc)}%"
        if target is not None:
            soc_line += f" / ціль {compact_number(target)}%"
        energy_lines.append(soc_line)
    if energy_lines:
        lines.extend(["", *energy_lines])
    tariff_lines = tariff_import_report_lines(tariff_import)
    if tariff_lines:
        lines.extend(["", *tariff_lines])
    if ahm_minimum_soc is not None:
        suggested = number((reserve_advice or {}).get("suggested_soc"))
        if suggested is not None:
            minimum_label = "Рекомендований мінімум AHM"
            displayed_minimum = suggested
        else:
            minimum_label = "Поточний мінімум AHM"
            displayed_minimum = ahm_minimum_soc
        lines.extend([
            "",
            f"🛡 {minimum_label}: <b>{compact_number(displayed_minimum)}%</b>",
        ])
    if heat_pump_management:
        lines.extend(["", heat_pump_management])
    recommendation = reserve_advice_message(reserve_advice)
    if recommendation:
        lines.extend(["", recommendation])
    if device_health_lines:
        lines.extend(["", "🏠 <b>Стан домашніх датчиків</b>", *device_health_lines])
    if inverter_lines:
        lines.extend(["", "⚡ <b>Повідомлення інвертора</b>", *inverter_lines])
    return "\n".join(lines)
