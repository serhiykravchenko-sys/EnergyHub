from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
import re
from typing import Any
from zoneinfo import ZoneInfo

from .report import compact_number, number
from .presentation import CONFIDENCE_NAMES


GRID_LEVELS = {"normal", "unstable", "risk", "panic"}

CONFIDENCE_UK = CONFIDENCE_NAMES


def format_duration(seconds: float) -> str:
    total_minutes = max(0, int(round(seconds / 60)))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} год {minutes} хв"
    if hours:
        return f"{hours} год"
    return f"{minutes} хв"


def outage_message(when: datetime, soc: Any) -> str:
    lines = [
        f"⚡ <b>Дача: ДТЕК недоступний з {when:%H:%M}</b>",
    ]
    soc_value = number(soc)
    if soc_value is not None:
        lines.append(f"🔋 Заряд батареї: {compact_number(soc_value)}%")
    return "\n".join(lines)


def recovery_message(when: datetime, outage_started_at: datetime | None, soc: Any) -> str:
    lines = [
        f"🟢 <b>Дача: ДТЕК відновився о {when:%H:%M}</b>",
    ]
    if outage_started_at is not None:
        lines.append(f"⏱ Без ДТЕК: {format_duration((when - outage_started_at).total_seconds())}")
    soc_value = number(soc)
    if soc_value is not None:
        if len(lines) > 1:
            lines[-1] += f" · 🔋 {compact_number(soc_value)}%"
        else:
            lines.append(f"🔋 Заряд батареї: {compact_number(soc_value)}%")
    return "\n".join(lines)


def confidence_message(
    previous: str,
    current: str,
    reserve: dict[str, Any] | None = None,
    previous_reserve: Any = None,
) -> str:
    order = {"normal": 0, "unstable": 1, "risk": 2, "panic": 3}
    reliability = "погіршилась" if order[current] > order[previous] else "покращилась"
    marker = {"normal": "🟢", "unstable": "🟡", "risk": "🟠", "panic": "🔴"}[current]
    lines = [
        f"{marker} <b>Надійність ДТЕК {reliability}</b>: "
        f"{escape(CONFIDENCE_UK[previous])} → {escape(CONFIDENCE_UK[current])}.",
    ]
    reserve = reserve or {}
    selected = number(reserve.get("applied_minimum_soc"))
    recommended = number(reserve.get("recommended_soc"))
    old = number(previous_reserve)
    automatic = reserve.get("management_mode") == "automatic"
    confirmed = automatic and reserve.get("control_applied") is True
    if confirmed and selected is not None:
        if old is not None and selected != old:
            action = "збільшено" if selected > old else "зменшено"
            lines.append(
                f"🔋 Мінімальний заряд батареї {action}: "
                f"<b>{compact_number(old)}% → {compact_number(selected)}%</b>."
            )
        else:
            lines.append(
                "🔋 Мінімальний заряд батареї залишається "
                f"<b>{compact_number(selected)}%</b>."
            )
    elif automatic and recommended is not None:
        lines.append(
            "🔋 EH планує мінімальний заряд "
            f"<b>{compact_number(recommended)}%</b>; застосування ще не підтверджено."
        )
    elif recommended is not None:
        lines.append(
            "🔋 Ручне керування: EH рекомендує мінімальний заряд "
            f"<b>{compact_number(recommended)}%</b>."
        )
    else:
        lines.append("🔋 Реакція резерву ще уточнюється.")
    return "\n".join(lines)


def valid_confidence(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in GRID_LEVELS else None


def trusted_grid(confidence: Any, voltage: Any, freshness: Any) -> bool:
    voltage_value = number(voltage)
    return (
        valid_confidence(confidence) == "normal"
        and voltage_value is not None
        and voltage_value > 180
        and str(freshness or "").strip().lower() == "fresh"
    )






def peak_load_guard_message(event: dict[str, Any]) -> str:
    """Legacy transport name; only first-floor HP battery notices remain."""
    kind = event.get('type')
    hp1 = event.get('key') == 'heat_pump_floor_1' or any(
        row.get('key') == 'heat_pump_floor_1' for row in event.get('affected_loads') or [] if isinstance(row, dict))
    if kind == 'hp1_battery_warning':
        soc = number(event.get('battery_soc'))
        charge = f'Батарея {compact_number(soc)}%. ' if soc is not None else ''
        stop = number(event.get('battery_off_soc'))
        threshold = f'при {compact_number(stop)}%' if stop is not None else 'при досягненні порогу захисту'
        return '🔋 '+charge+'Без ДТЕК вимкнемо тепловий насос 1-го поверху '+threshold+'.'
    if not hp1:
        return ''
    if kind == 'load_shed' and event.get('reason') == 'battery':
        return ('🔋 Тепловий насос 1-го поверху вимкнено для збереження заряду батареї. '
                'Відновлення — за окремою політикою ТН, коли інші захисти дозволяють.')
    if kind == 'load_restored' and event.get('reason') == 'battery':
        return '✅ Відновлено роботу теплового насоса 1-го поверху після захисту батареї.'
    if kind == 'control_attention':
        return ('⚠️ Керування тепловим насосом 1-го поверху потребує перевірки. '
                'EnergyHub не вважає непідтверджену дію завершеною.')
    return ''


WEATHER_HAZARDS_UK = {
    "strong_wind": "сильний вітер або шквали",
    "thunderstorm": "гроза",
    "ice": "ожеледиця або обледеніння",
    "heavy_snow": "сильний сніг або хуртовина",
    "severe_precipitation": "сильні опади",
    "hail": "град",
    "frost": "заморозки",
    "fog": "туман",
    "heat": "спека",
    "other": "небезпечні погодні умови",
}


def reserve_recommendation_ready(reserve):
    selected = number(reserve.get("applied_minimum_soc"))
    target = number(reserve.get("recommended_soc"))
    return (selected is not None and 20 <= selected <= 95
            and target is not None and 20 <= target <= 95
            and reserve.get("daily_plan_fresh") is True
            and reserve.get("weather_source_status") == "fresh"
            and reserve.get("grid_confidence") in {"normal", "unstable", "risk", "panic"}
            and not reserve.get("evidence_issues"))


def reserve_reason(reserve):
    reasons = []
    for key, label in (
        ("generation_modifier_percent", "прогноз генерації нижчий за споживання"),
        ("grid_modifier_percent", "низька надійність ДТЕК"),
        ("weather_modifier_percent", "небезпечна погода"),
        ("schedule_suspension_modifier_percent", "графіки не діють — додаткові 20 п.п. резерву"),
        ("smart_heating_modifier_percent", "додатковий резерв для опалення"),
    ):
        if (number(reserve.get(key)) or 0) > 0:
            reasons.append(label)
    return ", ".join(reasons) or "додатковий запас за розрахунком не потрібен"


def reserve_change_reason(reserve: dict[str, Any], old: float, new: float) -> str:
    """Describe a confirmed change without inventing its previous cause."""
    if new < old:
        if (reserve.get("forecast_deficit") is False
                and str(reserve.get("grid_confidence") or "").lower() == "normal"
                and not (number(reserve.get("weather_modifier_percent")) or 0)
                and not (number(reserve.get("schedule_suspension_modifier_percent")) or 0)
                and not (number(reserve.get("smart_heating_modifier_percent")) or 0)):
            return "прогноз генерації покриває споживання"
        return "потреба в додатковому резерві зменшилася"
    reason = reserve_reason(reserve)
    return ("причина зміни не підтверджена"
            if reason == "додатковий запас за розрахунком не потрібен" else reason)


def manual_reserve_advice(reserve: dict[str, Any]) -> str:
    selected = number(reserve.get("applied_minimum_soc"))
    current = f"{compact_number(selected)}%" if selected is not None else "невідомий"
    target = number(reserve.get("recommended_soc"))
    recommendation = (f"{compact_number(target)}%" if reserve_recommendation_ready(reserve)
                      else "недостатньо даних")
    automatic = reserve.get("management_mode") == "automatic"
    if automatic:
        return ""
    return (f"🔋 Мін. заряд батареї: <b>{current}</b> · рекомендація: "
            f"<b>{recommendation}</b>.\nКерування мін. зарядом: ручне; EH рекомендує.")


def weather_warning_event_id(event: dict[str, Any]) -> str | None:
    value = str(event.get("event_id") or "").strip()
    return value or None


def weather_warning_message(
    event: dict[str, Any],
    reserve: dict[str, Any] | None,
) -> str:
    severity = int(number(event.get("severity")) or 0)
    marker = {1: "🟡", 2: "🟠", 3: "🔴"}.get(severity, "⚠️")
    hazards = [
        WEATHER_HAZARDS_UK.get(str(item), str(item))
        for item in event.get("hazards", [])
    ]
    roman = {1: "І", 2: "ІІ", 3: "ІІІ"}.get(severity, "?")
    color = {1: "жовтий", 2: "помаранчевий", 3: "червоний"}.get(severity, "")
    lines = [f"{marker} <b>УкрГідроМетЦентр: {roman} рівень небезпечності</b> ({color})"]

    details = []
    raw_summary = str(event.get("summary") or "")
    headings = list(re.finditer(
        r"попередження\s+про\s+небезпечні\s+метеорологічні\s+явища",
        raw_summary, re.IGNORECASE,
    ))
    if headings:
        # Mixed official posts begin with a general weather forecast. The
        # warning section starts at the final explicit warning heading.
        raw_summary = raw_summary[headings[-1].start():]
    for paragraph in re.split(r"\n\s*\n", raw_summary):
        text = re.sub(r"[*‼️]+", "", paragraph).strip()
        lowered = text.lower()
        if not text or text.startswith("http"):
            continue
        if lowered.startswith("попередження про небезпечні"):
            continue
        if "рівень небезпечності" in lowered:
            continue
        if lowered.startswith(("сайт", "instagram", "facebook", "youtube", "threads")):
            continue
        details.append(escape(text))
    if details:
        for detail in details[:2]:
            lines.extend(["", detail])
    else:
        lines.extend(["", escape(", ".join(hazards) or "Небезпечні погодні умови") + "."])

    reserve = reserve or {}
    selected = number(reserve.get("applied_minimum_soc"))
    recommended = number(reserve.get("recommended_soc"))
    selected_valid = selected is not None and 20 <= selected <= 95
    ready = (selected_valid and recommended is not None and 20 <= recommended <= 95
             and reserve.get("daily_plan_fresh") is True
             and reserve.get("weather_source_status") == "fresh"
             and (reserve.get("reserve_planning_source")=="dtek_schedule" or reserve.get("grid_confidence") in {"normal", "unstable", "risk", "panic"})
             and not reserve.get("evidence_issues"))
    if severity >= 2 and event.get('region_match', event.get('grid_relevant')) is True:
        current = f"{compact_number(selected)}%" if selected_valid else "невідомий"
        if not ready:
            advice = "Даних для рекомендації недостатньо."
        elif number(reserve.get('weather_modifier_percent')) != 20:
            advice = (f"Розрахунок EH: {compact_number(recommended)}%. Ручний вибір збережено."
                      if reserve.get('management_mode') != 'automatic' and recommended < selected
                      else "Погодна надбавка зараз не застосовується.")
        elif reserve.get("management_mode") == "automatic" and reserve.get("control_applied") is True:
            advice = f"Погодний резерв +20%; EH встановив {compact_number(selected)}%."
        elif reserve.get("management_mode") == "automatic":
            advice = f"Погодний резерв +20%; EH застосує {compact_number(recommended)}% після перевірки."
        elif recommended > selected:
            advice = f"Погодний резерв +20%; рекомендовано вручну {compact_number(recommended)}%."
        elif recommended < selected:
            advice = f"Розрахунок EH: {compact_number(recommended)}%. Ручний вибір збережено."
        else:
            advice = "Зміна не рекомендована."
        validity = ""
        try:
            until = datetime.fromisoformat(str(event.get("valid_until"))).astimezone(
                ZoneInfo("Europe/Kyiv")
            )
            validity = f" Надбавка діє протягом дня попередження, до {until:%d.%m} 23:59."
        except (TypeError, ValueError):
            pass
        lines.extend(["", f"🔋 Мінімум батареї: {current}. {advice}{validity}"])
    else:
        try:
            until = datetime.fromisoformat(str(event.get('valid_until'))).astimezone(ZoneInfo('Europe/Kyiv'))
            lines.append(f'🕒 Попередження діє до {until:%d.%m %H:%M}.')
        except (TypeError, ValueError):
            pass
    url = str(event.get("url") or "").strip()
    if url:
        lines.append(f'<a href="{escape(url)}">Джерело</a>')
    return "\n".join(lines)


def weather_warning_report_lines(events: list[dict[str, Any]], now: datetime | None = None) -> list[str]:
    lines = []
    for event in events:
        if now is not None:
            try:
                expires = datetime.fromisoformat(str(event.get("valid_until")))
                if expires.tzinfo is None or expires < now:
                    continue
            except (TypeError, ValueError):
                continue
        severity = int(number(event.get("severity")) or 0)
        hazards = [
            WEATHER_HAZARDS_UK.get(str(item), str(item))
            for item in event.get("hazards", [])
        ]
        marker = {1: "🟡", 2: "🟠", 3: "🔴"}.get(severity, "⚠️")
        label = escape(", ".join(hazards) or "небезпечні погодні умови")
        line = f"{marker} <b>УГМЦ: рівень {severity}</b> — {label}."
        url = str(event.get("url") or "").strip()
        if url.startswith("https://t.me/"):
            line += f' <a href="{escape(url, quote=True)}">Джерело</a>'
        lines.append(line)
    return lines


def weather_reserve_restoration_message(event: dict[str, Any]) -> str:
    previous = number(event.get("previous_recommended_soc"))
    current = number(event.get("recommended_soc"))
    if previous is None or current is None:
        raise ValueError("Weather reserve restoration requires both reserve values")
    return "\n".join([
        "🟢 <b>Погодний резерв більше не потрібен</b>",
        (
            "🛡 Рекомендований мінімум запасу батареї: "
            f"<b>{compact_number(previous)}% → {compact_number(current)}%</b>."
        ),
        "Офіційне погодне попередження скасовано або строк його дії завершився.",
        "🧪 Dry Run: EnergyHub не змінював мінімум запасу батареї.",
    ])


def weather_reserve_restoration_report_lines(
    events: list[dict[str, Any]],
) -> list[str]:
    if not events:
        return []
    latest = events[-1]
    previous = number(latest.get("previous_recommended_soc"))
    current = number(latest.get("recommended_soc"))
    if previous is None or current is None:
        return []
    return [
        "🟢 Погодний резерв скасовано або завершився строк його дії: "
        f"рекомендація {compact_number(previous)}% → {compact_number(current)}%.",
    ]


def _soc_anomaly_time(event: dict[str, Any], timezone) -> str | None:
    try:
        return datetime.fromisoformat(str(event["timestamp"])).astimezone(
            timezone
        ).strftime("%H:%M:%S")
    except (KeyError, TypeError, ValueError):
        return None


def soc_anomaly_event_id(event: dict[str, Any]) -> str | None:
    timestamp = str(event.get("timestamp") or "").strip()
    previous = number(event.get("previous_soc"))
    current = number(event.get("current_soc"))
    if not timestamp or previous is None or current is None:
        return None
    return f"{timestamp}|{previous:g}|{current:g}"


def soc_anomaly_message(event: dict[str, Any], timezone) -> str:
    previous = number(event.get("previous_soc"))
    current = number(event.get("current_soc"))
    if previous is None or current is None:
        raise ValueError("Battery charge observation requires both readings")
    elapsed = number(event.get("elapsed_seconds"))
    duration = f" за {compact_number(elapsed)} с" if elapsed is not None else ""
    lines = ["ℹ️ <b>Стрибок показника заряду батареї</b>",
             f"{compact_number(previous)}% → {compact_number(current)}%{duration}."]
    event_time = _soc_anomaly_time(event, timezone)
    if event_time:
        lines.append(f"🕒 {event_time}")
    lines.append("EnergyHub записав подію для спостереження.")
    return "\n".join(lines)


def soc_anomaly_report_lines(
    events: list[dict[str, Any]],
    timezone,
    history_days=None,
) -> list[str]:
    valid = [
        event
        for event in events
        if isinstance(event, dict) and soc_anomaly_event_id(event)
    ]
    if not valid:
        return []
    largest = max(
        valid,
        key=lambda event: abs(
            number(event.get("delta_percent"))
            or (
                number(event.get("current_soc"))
                - number(event.get("previous_soc"))
            )
        ),
    )
    previous = number(largest.get("previous_soc"))
    current = number(largest.get("current_soc"))
    delta = number(largest.get("delta_percent"))
    if delta is None:
        delta = current - previous
    event_time = _soc_anomaly_time(largest, timezone)
    suffix = f" о {event_time[:5]}" if event_time else ""
    recurrence = 'Лише для інформації.'
    if history_days:
        try:
            anchor = max(datetime.fromisoformat(str(e['timestamp'])).astimezone(timezone).date() for e in valid)
            streak = 0
            while (anchor-timedelta(days=streak)).isoformat() in history_days:
                streak += 1
            count = sum((anchor-timedelta(days=i)).isoformat() in history_days for i in range(10))
            if streak >= 2:
                recurrence = f'{streak} дні поспіль — варто перевірити.'
            elif count >= 2:
                recurrence = f'Зафіксовано у {count} із останніх 10 днів — варто перевірити.'
        except (ValueError,TypeError,KeyError):
            pass
    return [
        (
            f"ℹ️ Стрибок показника заряду батареї: <b>{compact_number(previous)}% → "
            f"{compact_number(current)}%</b>{suffix}. {recurrence}"
        ),
    ]
