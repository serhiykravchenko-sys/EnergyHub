from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from .report import compact_number, number


GRID_TARGETS = {
    "normal": 20,
    "unstable": 60,
    "risk": 80,
    "panic": 95,
}

CONFIDENCE_UK = {
    "normal": "Normal",
    "unstable": "Unstable",
    "risk": "Risk",
    "panic": "Panic",
}


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
        "🔴 <b>Зовнішня мережа зникла</b>",
        f"Початок відключення: {when:%H:%M}",
    ]
    soc_value = number(soc)
    if soc_value is not None:
        lines.append(f"🔋 SOC: {compact_number(soc_value)}%")
    lines.append("🏠 Будинок працює від сонця та батареї.")
    return "\n".join(lines)


def recovery_message(when: datetime, outage_started_at: datetime | None, soc: Any) -> str:
    lines = [
        "🟢 <b>Зовнішня мережа відновилась</b>",
        f"Відновлення: {when:%H:%M}",
    ]
    if outage_started_at is not None:
        lines.append(f"⏱ Без мережі: {format_duration((when - outage_started_at).total_seconds())}")
    soc_value = number(soc)
    if soc_value is not None:
        lines.append(f"🔋 SOC: {compact_number(soc_value)}%")
    return "\n".join(lines)


def confidence_message(previous: str, current: str) -> str:
    old_target = GRID_TARGETS[previous]
    new_target = GRID_TARGETS[current]
    reliability = "погіршилась" if new_target > old_target else "покращилась"
    lines = [
        f"🛡 <b>Надійність мережі {reliability}</b>",
        f"Grid Confidence: {escape(CONFIDENCE_UK[previous])} → {escape(CONFIDENCE_UK[current])}",
        f"🔋 Цільовий запас батареї вдень: {old_target}% → {new_target}%",
    ]
    if new_target > old_target:
        lines.append("EnergyHub зберігатиме більший резерв.")
    elif new_target < old_target:
        lines.append("EnergyHub може використовувати більшу частину батареї.")
    return "\n".join(lines)


def valid_confidence(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in GRID_TARGETS else None


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
            "♨️ Теплові насоси: <b>РУЧНЕ КЕРУВАННЯ</b>. "
            "Родина керує ними; EnergyHub стежить за резервом батареї."
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
        raise ValueError("SOC and AHM minimum are required")

    threshold = min(100, reserve + offset)
    lines = [
        f"🔋 <b>SOC знизився до {compact_number(soc_value)}%</b>",
        (
            f"Досягнуто поріг {compact_number(threshold)}%: "
            f"мінімум AHM {compact_number(reserve)}% + {offset}%."
            if offset
            else f"Досягнуто мінімум AHM {compact_number(reserve)}%."
        ),
    ]

    if trusted_grid(confidence, voltage, freshness):
        lines.append(
            "♨️ Мережа надійна: тепловими насосами керує родина; "
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
