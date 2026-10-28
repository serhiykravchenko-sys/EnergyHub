"""Informational solar heating windows; never used for hardware control."""
from datetime import timedelta
from math import isfinite

from .report import local_datetime, number


def morning_lines(policy, operation, family_mode, forecast, now, limits=(600, 400)):
    if policy != 'Solar-only' or operation != 'Continuous':
        return []
    name = {'heat': 'опалення', 'cool': 'охолодження'}.get(family_mode, 'опалення/охолодження')
    title = f'☀️ Сонячне {name} увімкнено (без розкладу).'
    unavailable = [title, '🕒 Прогноз часу роботи недоступний. EH керує за фактичними умовами.']
    if limits is None:
        return [title, '🕒 Прогноз роботи недоступний: перевірте пороги сонячної генерації на панелі EH.']
    start_w, pause_w = limits
    updated = local_datetime(forecast.get('last_updated'), now.tzinfo)
    if (forecast.get('state') in {'unknown', 'unavailable', None}
            or updated is None or not -300 <= (now-updated).total_seconds() <= 86400):
        return unavailable
    raw = forecast.get('attributes', {}).get('detailedHourly')
    if not isinstance(raw, list):
        return unavailable
    periods = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        start = local_datetime(item.get('period_start'), now.tzinfo)
        if start and start.date() == now.date():
            power = number(item.get('pv_estimate'))
            periods[start] = power * 1000 if power is not None and isfinite(power) and power >= 0 else None
    stamps = sorted(periods)
    steps = [(b-a).total_seconds() for a, b in zip(stamps, stamps[1:]) if 0 < (b-a).total_seconds() <= 3600]
    duration = timedelta(seconds=min(steps) if steps else 3600)
    windows, active, previous_end, valid = [], None, None, 0
    for start in stamps:
        end, power = start+duration, periods[start]
        if end <= now:
            continue
        if power is not None:
            valid += 1
        if active and (start != previous_end or power is None or power < pause_w):
            windows.append((active, previous_end))
            active = None
        if active is None and power is not None and power >= start_w:
            active = max(start, now)
        previous_end = end
    if active:
        windows.append((active, previous_end))
    if not valid:
        return unavailable
    if not windows:
        return [title, '🕒 За доступним прогнозом, достатньої генерації для запуску сьогодні не очікується.']
    times = ', '.join(f'{start:%H:%M}–{end:%H:%M}' for start, end in windows[:3])
    if len(windows) > 3:
        times += ' та пізніше'
    return [title, f'🕒 За прогнозом, робота очікується орієнтовно {times}.',
            'EH запускатиме й призупинятиме насос за фактичними сонячними умовами та дозволом захисту.']
