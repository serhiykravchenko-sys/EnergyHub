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
        "⚡ <b>ДТЕК недоступний</b>",
        f"Початок відключення: {when:%H:%M}",
    ]
    soc_value = number(soc)
    if soc_value is not None:
        lines.append(f"🔋 Заряд батареї: {compact_number(soc_value)}%")
    lines.append("🏠 Будинок працює автономно від сонця або батареї.")
    return "\n".join(lines)


def recovery_message(when: datetime, outage_started_at: datetime | None, soc: Any) -> str:
    lines = [
        "🟢 <b>ДТЕК відновився</b>",
        f"Відновлення: {when:%H:%M}",
    ]
    if outage_started_at is not None:
        lines.append(f"⏱ Без ДТЕК: {format_duration((when - outage_started_at).total_seconds())}")
    soc_value = number(soc)
    if soc_value is not None:
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


def heat_pump_management_message(
    *,
    confidence: Any,
    voltage: Any,
    freshness: Any,
    minimum_soc: Any,
) -> str | None:
    reserve = number(minimum_soc)
    if reserve is None:
        return None

    if str(freshness or "").strip().lower() != "fresh":
        return (
            "♨️ Теплові насоси: <b>ЗАХИСТ ENERGYHUB — ОЧІКУВАННЯ</b>. "
            "Телеметрія не свіжа, тому EnergyHub не надсилає нових команд "
            "на основі SOC."
        )

    shed = min(100, reserve + 30)
    lockout = min(100, reserve + 20)
    recovery = min(100, reserve + 40)

    if trusted_grid(confidence, voltage, freshness):
        return (
            "♨️ Теплові насоси: <b>ручне керування</b>."
        )

    return (
        "♨️ Теплові насоси: <b>ЗАХИСТ ENERGYHUB</b>. "
        f"Вимкнення при {compact_number(shed)}%, "
        f"блокування при {compact_number(lockout)}%, "
        f"відновлення при {compact_number(recovery)}%."
    )


def reserve_warning_message(
    *,
    soc: Any,
    minimum_soc: Any,
    offset: int,
    confidence: Any,
    voltage: Any,
    freshness: Any,
    active_heat_pumps: list[tuple[str, float]],
) -> str:
    soc_value = number(soc)
    reserve = number(minimum_soc)
    if soc_value is None or reserve is None:
        raise ValueError("SOC and battery reserve are required")

    threshold = min(100, reserve + offset)
    lines = [
        f"🔋 <b>Заряд батареї знизився до {compact_number(soc_value)}%</b>",
        (
            f"Досягнуто поріг {compact_number(threshold)}%: "
            f"мінімум запасу батареї {compact_number(reserve)}% + {offset}%."
            if offset
            else f"Досягнуто мінімум запасу батареї {compact_number(reserve)}%."
        ),
    ]

    if trusted_grid(confidence, voltage, freshness):
        lines.append(
            "♨️ ДТЕК доступний і надійний: тепловими насосами керує родина; "
            "EnergyHub контролює резерв."
        )
    elif offset >= 30:
        lines.append(
            "♨️ Захист EnergyHub: працюючі теплові насоси вимикаються; "
            f"ручний запуск можливий до {compact_number(reserve + 20)}%."
        )
    elif offset >= 20:
        lines.append(
            "♨️ Захист EnergyHub: теплові насоси заблоковані до "
            f"відновлення SOC до {compact_number(reserve + 40)}%."
        )
    else:
        lines.append(
            "♨️ Захист EnergyHub залишається активним; теплові насоси "
            "залишаються вимкненими."
        )

    for floor, power_w in active_heat_pumps:
        lines.append(
            f"♨️ Тепловий насос на {escape(floor)} поверсі споживає "
            f"{compact_number(power_w)} Вт."
        )

    return "\n".join(lines)


def heat_pump_restart_restored_message(event: dict[str, Any]) -> str:
    """Describe only plug states that HA actually restored after startup."""
    restored = event.get("restored")
    if not isinstance(restored, list) or not restored:
        raise ValueError("At least one restored heat-pump plug is required")

    lines = ["\U0001f504 <b>\u041f\u0456\u0441\u043b\u044f \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a\u0443 \u0432\u0456\u0434\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u0442\u0435\u043f\u043b\u043e\u0432\u0456 \u043d\u0430\u0441\u043e\u0441\u0438</b>"]
    for item in restored:
        if not isinstance(item, dict):
            continue
        floor = escape(str(item.get("floor") or "?"))
        watts = number(item.get("power_w"))
        if watts is None:
            lines.append(f"\u267b\ufe0f {floor} \u043f\u043e\u0432\u0435\u0440\u0445: \u0440\u043e\u0437\u0435\u0442\u043a\u0443 \u0443\u0432\u0456\u043c\u043a\u043d\u0435\u043d\u043e; \u043f\u043e\u0442\u0443\u0436\u043d\u0456\u0441\u0442\u044c \u0449\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430.")
        elif watts >= 50:
            lines.append(
                f"\u2705 {floor} \u043f\u043e\u0432\u0435\u0440\u0445: {compact_number(watts)} \u0412\u0442 \u2014 "
                "\u0442\u0435\u043f\u043b\u043e\u0432\u0438\u0439 \u043d\u0430\u0441\u043e\u0441 \u043f\u0440\u0430\u0446\u044e\u0454."
            )
        else:
            lines.append(
                f"\u267b\ufe0f {floor} \u043f\u043e\u0432\u0435\u0440\u0445: {compact_number(watts)} \u0412\u0442 \u2014 "
                "\u0440\u043e\u0437\u0435\u0442\u043a\u0443 \u0443\u0432\u0456\u043c\u043a\u043d\u0435\u043d\u043e, \u0430\u043b\u0435 \u0442\u0435\u043f\u043b\u043e\u0432\u0438\u0439 \u043d\u0430\u0441\u043e\u0441 \u0449\u0435 \u043d\u0435 \u0441\u043f\u043e\u0436\u0438\u0432\u0430\u0454 \u0437\u043d\u0430\u0447\u043d\u0443 \u043f\u043e\u0442\u0443\u0436\u043d\u0456\u0441\u0442\u044c."
            )
    if len(lines) == 1:
        raise ValueError("No valid restored heat-pump records")
    return "\n".join(lines)


PEAK_LOAD_NAMES_UK = {
    "water_pump": "водяний насос",
    "water_boiler": "бойлер",
    "heat_pump_floor_2": "тепловий насос на 2-му поверсі",
    "heat_pump_floor_1": "тепловий насос на 1-му поверсі",
    "heat_pump_floor_3": "тепловий насос на 3-му поверсі",
    "microwave": "мікрохвильова піч",
}


def _peak_load_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    names = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        fallback = str(item.get("name") or key).strip()
        names.append(PEAK_LOAD_NAMES_UK.get(key, fallback))
    return names


def peak_load_guard_message(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "")
    if event_type == 'battery_reserve_warning':
        charge = number(event.get('battery_soc'))
        level = f'{compact_number(charge)}%' if charge is not None else '50%'
        if charge is not None and charge <= 40:
            return ("⚠️ <b>Увімкнено захист заряду батареї</b>\n"
                    f"ДТЕК все ще недоступний. Заряд батареї — <b>{level}</b>.\n"
                    "EnergyHub вимикає доступні некритичні пристрої. У повідомленнях "
                    "будуть зазначені лише пристрої з підтвердженим вимкненням.")
        return (f"⚠️ ДТЕК недоступний. Заряд батареї — <b>{level}</b>.\n"
                "Якщо заряд знизиться до 40%, EnergyHub почне вимикати доступні "
                "некритичні пристрої для збереження батареї.")
    if event_type in ('load_warning', 'load_warning_cleared'):
        load = number(event.get('load_percent'))
        current = f"{compact_number(load)}%" if load is not None else 'невідоме'
        if event_type == 'load_warning':
            return (f"⚠️ <b>Високе навантаження інвертора: {current}</b>\n"
                    "Автоматичне вимкнення не активне. Зменште навантаження до 75% або нижче.")
        return (f"✅ Навантаження інвертора: <b>{current}</b> — нижче 50% протягом 5 хвилин.\n"
                "Це лише повідомлення, не підтвердження ввімкнення пристроїв.")
    if event.get('mode') == 'automatic':
        names = ', '.join(_peak_load_names(event.get('affected_loads')))
        load = number(event.get('load_percent'))
        current = f"Навантаження: <b>{compact_number(load)}%</b>." if load is not None else ''
        if event_type == 'load_shed':
            if event.get('reason') == 'battery':
                charge = number(event.get('battery_soc'))
                level = f'{compact_number(charge)}%' if charge is not None else 'уточнюється'
                return (f"🔋 <b>Захист заряду батареї — {level}</b>\n"
                        f"EnergyHub підтвердив вимкнення: <b>{escape(names)}</b>.\n"
                        "Пристрій буде відновлено після повернення ДТЕК або коли "
                        "сонце зарядить батарею до <b>60%</b> (для розумного опалення "
                        "Eco може відновитися з 50%).")
            trigger = number(event.get('trigger_load_percent'))
            trigger_reason = event.get('trigger_reason')
            if trigger_reason == 'inverter_warning':
                trigger_line = ("Інвертор повідомив про перевантаження"
                    + (f" при <b>{compact_number(trigger)}%</b>." if trigger is not None else "."))
            else:
                trigger_line = (f"Навантаження зросло до <b>{compact_number(trigger)}%</b>."
                    if trigger is not None else "Спрацював поріг захисту.")
            after = (f"Після дії: <b>{compact_number(load)}%</b>."
                     if load is not None else "")
            return (f"🛡 <b>Захист інвертора</b>\n{trigger_line}\n"
                    f"Тимчасово вимкнено: <b>{escape(names)}</b>. {after}\n"
                    "Пристрій буде відновлено, коли навантаження залишатиметься нижче "
                    "<b>50% протягом 5 хвилин</b>; відновлення виконується по одному "
                    "з паузою щонайменше 1 хв.")
        if event_type == 'load_restored':
            return f"✅ <b>Відновлено роботу:</b> {escape(names)}.\n{current}"
        if event_type == 'control_complete':
            return f"✅ Відновлення пристроїв завершено. {current}"
        if event_type == 'control_attention':
            if event.get('reason') == 'battery_load_unavailable':
                return (f"⚠️ Не вдалося вимкнути для збереження заряду: {escape(names)}.\n"
                        "Перевірте пристрої вручну; EH не підтвердив їх вимкнення.")
            if event.get('reason') == 'restoration_telemetry_missing':
                return ("⚠️ Немає даних навантаження понад 5 хв. Автовідновлення призупинено.\n"
                        f"Залишаються вимкненими: {escape(names)}.\n"
                        "За потреби перевірте навантаження й увімкніть вручну; інакше EH чекатиме на дані.")
            reasons = event.get('reasons') if isinstance(event.get('reasons'), list) else [event.get('reason')]
            reason_names = {
                'command_outcome_unconfirmed': 'команду не підтверджено станом пристрою',
                'command_delivery_uncertain': 'доставку команди не підтверджено',
                'executor_rejected_command': 'Home Assistant відхилив команду',
                'executor_restarted_during_command': 'виконавець перезапустився під час команди',
                'uncertain_command_after_restart': 'результат команди до перезапуску невідомий',
                'external_control_during_command': 'під час команди втрутилося інше керування',
                'external_control_ownership_released': 'ручне або інше керування змінило стан',
                'load_unavailable': 'стан пристрою недоступний',
                'restoration_load_unavailable': 'немає підтвердженого стану для відновлення',
                'native_settings_restore_unverified': 'налаштування теплового насоса змінилися',
                'restore_rejected_requires_attention': 'відновлення відхилено',
                'no_available_loads': 'немає інших підтверджено доступних пристроїв',
            }
            details = '; '.join(dict.fromkeys(reason_names.get(reason, str(reason or 'причина невідома'))
                                                for reason in reasons))
            device = f"Пристрої: <b>{escape(names)}</b>.\n" if names else ""
            return (f"⚠️ <b>Захист інвертора: потрібна перевірка</b>\n"
                    f"{device}{escape(details)}. {current}\n"
                    "EnergyHub не вважає непідтверджену дію завершеною.")
        raise ValueError('Unsupported automatic load event')
    thresholds = event.get("thresholds") or {}
    shed = number(thresholds.get("shed_percent")) or 85
    relief = number(thresholds.get("relief_percent")) or 75
    restore = number(thresholds.get("restore_percent")) or 60
    cycle = str(event.get("cycle_id") or "")
    cycle_line = f"Цикл: {escape(cycle[-12:])}." if cycle else ""

    if event_type == "shed_recommended":
        load_percent = number(event.get("trigger_load_percent"))
        names = _peak_load_names(event.get("recommended_loads"))
        lines = [
            "🧪 <b>Peak Load Guard — Dry Run</b>",
            cycle_line,
            (
                "Навантаження інвертора досягло "
                f"{compact_number(load_percent if load_percent is not None else shed)}%."
            ),
            "EnergyHub рекомендує тимчасово вимкнути по черзі:",
            *[f"• {escape(name)}" for name in names],
            (
                "Зупиніть вимкнення, коли навантаження знизиться до "
                f"{compact_number(relief)}% або нижче."
            ),
            (
                "Початкові стани потрібно відновити в тому самому порядку, "
                f"коли навантаження знизиться до {compact_number(restore)}% або нижче."
            ),
            "EnergyHub нічого не перемикав — це лише рекомендація Dry Run.",
        ]
        return "\n".join(lines)

    if event_type == "restore_recommended":
        load_percent = number(event.get("recovery_load_percent"))
        names = _peak_load_names(event.get("restore_order"))
        lines = [
            "🟢 <b>Peak Load Guard — відновлення Dry Run</b>",
            cycle_line,
            (
                "Навантаження інвертора знизилося до "
                f"{compact_number(load_percent if load_percent is not None else restore)}%."
            ),
            "EnergyHub рекомендує відновити початкові стани в тому самому порядку:",
            *[f"• {escape(name)}" for name in names],
            (
                f"Після кожного ввімкнення перевіряйте, що навантаження не перевищує "
                f"{compact_number(relief)}%."
            ),
            "EnergyHub нічого не перемикав — цикл Dry Run завершено.",
        ]
        return "\n".join(lines)

    if event_type == "no_candidates":
        load_percent = number(event.get("trigger_load_percent"))
        return "\n".join([
            "🔴 <b>Peak Load Guard — немає доступного навантаження</b>",
            (
                "Навантаження інвертора становить "
                f"{compact_number(load_percent if load_percent is not None else shed)}%."
            ),
            "EnergyHub не знайшов увімкненої доступної розетки для рекомендації.",
            "EnergyHub нічого не перемикав — режим Dry Run.",
        ])

    raise ValueError(f"Unsupported Peak Load Guard event: {event_type}")


WEATHER_HAZARDS_UK = {
    "strong_wind": "сильний вітер або шквали",
    "thunderstorm": "гроза",
    "ice": "ожеледиця або обледеніння",
    "heavy_snow": "сильний сніг або хуртовина",
    "severe_precipitation": "сильні опади",
    "hail": "град",
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
             and reserve.get("grid_confidence") in {"normal", "unstable", "risk", "panic"}
             and not reserve.get("evidence_issues"))
    if severity >= 2:
        current = f"{compact_number(selected)}%" if selected_valid else "невідомий"
        if not ready:
            advice = "Даних для рекомендації недостатньо."
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
            validity = f" Діє до {until:%d.%m %H:%M}."
        except (TypeError, ValueError):
            pass
        lines.extend(["", f"🔋 Мінімум батареї: {current}. {advice}{validity}"])
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
