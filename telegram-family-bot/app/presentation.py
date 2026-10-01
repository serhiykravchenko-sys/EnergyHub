"""Ukrainian display names; internal modes and schedules are not translated."""
import math


MODE_NAMES = {
    "solar": "Пріоритет сонця",
    "hybrid": "Використання дешевого тарифу",
    "hybrid_charging": "Заряджання за тарифним планом",
    "hybrid_grid_hold": "Сонце + ДТЕК — очікування заряду",
    "panic": "Захист резерву батареї",
    "panic_grid_hold": "Збереження резерву батареї",
    "transitioning": "Зміна стратегії",
    "transition_failed": "Зміну стратегії не підтверджено",
}
CONFIDENCE_NAMES = {
    "normal": "Нормальна", "unstable": "Нестабільна",
    "risk": "Ризик", "panic": "Критична",
}


def mode_label(value):
    key = str(value or "").lower()
    return MODE_NAMES.get(key, "Невідома стратегія") if key not in ("", "unknown", "unavailable") else None


def tariff_label(now, start="23:00", end="07:00"):
    """Installed EH tariff window; labels follow time, never the mode name.

    Defaults match the current GridImportService boundaries. This formatter
    supports other windows for display but does not configure EH scheduling.
    """
    def minutes(value):
        hour, minute = map(int, value.split(":"))
        if not 0 <= hour < 24 or not 0 <= minute < 60:
            raise ValueError("Invalid tariff window")
        return hour * 60 + minute
    first, last = minutes(start), minutes(end)
    current = now.hour * 60 + now.minute
    if first == last:
        return "за тарифом ДТЕК"
    low = first <= current < last if first < last else current >= first or current < last
    # Ukrainian household wording is used only for the installed night window.
    if (start, end) == ("23:00", "07:00"):
        return "за нічним тарифом" if low else "за денним тарифом"
    return "за дешевим тарифом" if low else "за звичайним тарифом"


def strategy_lines(mode, target, *, now, fresh, grid_online):
    label = mode_label(mode)
    if not label:
        return []
    lines = [f"🧭 О {now:%H:%M}: режим <b>{label}</b>."]
    if not fresh:
        return [f"⚠️ О {now:%H:%M}: дані про живлення застарілі."]
    if mode == 'solar':
        return [f"☀️ О {now:%H:%M} будинок у <b>пріоритеті сонця</b>"]
    if mode not in {"hybrid_charging", "hybrid_grid_hold", "panic", "panic_grid_hold"}:
        return lines
    if not grid_online:
        return lines + ["⚠️ Живлення від ДТЕК зараз не підтверджено."]
    try:
        value = float(target)
        valid = math.isfinite(value) and 0 <= value <= 100
    except (TypeError, ValueError):
        valid = False
    if mode == "hybrid_grid_hold":
        return [f"🔌 О {now:%H:%M} режим <b>сонце + ДТЕК</b> · батарею заряджає лише сонце"]
    if mode == "panic_grid_hold":
        if valid and value < 95:
            release = min(100, value + 10)
            return [
                f"🔌 О {now:%H:%M} режим <b>сонце + ДТЕК</b> · "
                f"резерв <b>{value:g}%</b> · пріоритет сонця при <b>{release:g}%</b>",
            ]
        if valid:
            return [
                f"🔌 О {now:%H:%M} будинок живиться від <b>ДТЕК</b>",
                "EnergyHub зберігає резерв <b>95%</b>; повернення до пріоритету сонця "
                "очікує зниження вибраного резерву.",
            ]
        return [f"🔌 О {now:%H:%M} будинок живиться від <b>ДТЕК</b> · резерв невідомий"]
    goal = f" до <b>{value:g}%</b>" if valid else " (ціль недоступна)"
    return [
        f"⚡ О {now:%H:%M} будинок живиться від <b>ДТЕК</b> · "
        f"заряджання батареї{goal} · {tariff_label(now)}"
    ]
