"""Two family messages: bounded overnight observations and a daily outlook."""
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo
from .report import compact_number, overnight_family_event_lines


def night_window(config, now):
    local = now.astimezone(ZoneInfo(config.timezone))
    hour, minute = map(int, getattr(config, 'send_time', '08:00').split(':'))
    end = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    hour, minute = map(int, getattr(config, 'family_quiet_start', '23:00').split(':'))
    start = end.replace(hour=hour, minute=minute)
    if start >= end:
        start -= timedelta(days=1)
    return start, end


def _time(value):
    try:
        at = datetime.fromisoformat(str(value))
        return at if at.tzinfo else None
    except (ValueError, TypeError):
        return None


def overnight(config, state, now, *, current_strategy, soc, solar_w, grid_voltage,
              telemetry_fresh, inverter_mode, night_summary=''):
    start, end = night_window(config, now)
    events = []
    allowed = {'grid_lost', 'grid_recovered',
               'grid_unstable', 'grid_stable', 'technical_inverter_strategy_fault',
               'peak_load_guard_load_shed',
               'peak_load_guard_load_restored'}
    for event in state.get('overnight_family_events', []):
        if not isinstance(event, dict) or event.get('kind') not in allowed:
            continue
        at = _time(event.get('created_at'))
        if at and start <= at <= min(end, now):
            events.append(dict(event, created_at=at.astimezone(start.tzinfo).isoformat()))
    events.sort(key=lambda e: e['created_at'])
    house = []
    transitions = [e for e in events if e['kind'] in {'grid_lost', 'grid_recovered'}]
    # A busy night is one bounded summary; snapshot below shows current supply.
    condensed = len(transitions) > 6 or any(
        len([e for e in transitions if 0 <= (_time(e['created_at'])-_time(first['created_at'])).total_seconds() <= 600]) >= 4
        for first in transitions)
    if condensed:
        house.append(f'⚠️ ДТЕК неодноразово зникав і повертався: {len(transitions)} змін за ніч.')
    for event in events:
        if condensed and event['kind'] in {'grid_lost', 'grid_recovered', 'grid_unstable', 'grid_stable'}:
            continue
        for line in overnight_family_event_lines([event], inverter_mode=inverter_mode, mode_observed_at=now):
            if line not in house:
                house.append(line)
    if len(house) > 8:
        house = house[:7] + [f'ℹ️ Інших подій за ніч: {len(house)-7}.']
    apartment = []
    for event in state.get('apartment_grid', {}).get('events', []):
        at = _time(event.get('at'))
        if at and start <= at <= min(end, now) and isinstance(event.get('online'), bool):
            local_at = at.astimezone(start.tzinfo)
            if event['online']:
                text = f'🟢 <b>Квартира: ДТЕК відновився о {local_at:%H:%M}</b>'
            elif event.get('onset_unknown'):
                text = '⚡ <b>Квартира: ДТЕК імовірно недоступний; початок невідомий</b>'
            else:
                text = f'⚡ <b>Квартира: ДТЕК недоступний з {local_at:%H:%M}</b>'
            apartment.append((at, text))
    apartment.sort(key=lambda e: e[0])
    apartment_lines = list(dict.fromkeys(text for _, text in apartment))
    if len(apartment_lines) > 6:
        apartment_lines = [f'⚠️ За ніч зафіксовано {len(apartment_lines)} змін доступності ДТЕК.', apartment_lines[-1]]
    lines = [f'🌙 <b>За ніч · {start:%H:%M}–{end:%H:%M}</b>']
    if house:
        lines += ['', '🏠 <b>Дача</b>', *house]
    if apartment_lines:
        lines += ['', '🏢 <b>Квартира</b>', *apartment_lines]
    if night_summary:
        lines += ['', night_summary]
    local = now.astimezone(start.tzinfo)
    lines += ['', f'🏠 <b>Стан на {local:%H:%M}</b>']
    if telemetry_fresh:
        values = []
        if soc is not None and 0 <= soc <= 100:
            values.append(f'🔋 Батарея: <b>{compact_number(soc)}%</b>')
        if values:
            lines.append(' · '.join(values)+'.')
        if grid_voltage is not None and 0 <= grid_voltage <= 300:
            lines.append('⚡ ДТЕК на дачі <b>'+('доступний' if grid_voltage > 180 else 'недоступний')+'</b>.')
    else:
        lines.append('⚠️ Актуальні дані інвертора не підтверджені.')
    lines.extend(current_strategy)
    return '\n'.join(lines)


def schedule(config, state, now):
    if not getattr(config, 'dtek_schedule_enabled', False):
        return []
    from . import source_policy, published_schedule
    lines = []
    blocked = [p for p in ('дача', 'квартира') if source_policy.suspended(state, p)]
    if blocked:
        records = state.get('regional_notices', {})
        for place in blocked:
            notice = records.get(place) or state.get('pro_notice', {})
            label = 'аварійні' if notice.get('kind') == 'fault' else 'екстрені'
            checked = _time(notice.get('checked_at'))
            stale = not checked or not -60 <= (now-checked).total_seconds() <= 2100
            prefix = 'Останній підтверджений статус: ' if stale else ''
            lines.append(f'⚠️ <b>{escape(place.capitalize())}: {prefix}{label} відключення.</b>')
        lines.append('Можливі відключення поза графіком; час відновлення не гарантовано.')
    document = state.get('dtek_raw_snapshot') or {}
    # Retain only unfinished intervals today, without inventing today's authority.
    document = dict(document)
    if isinstance(document.get('groups'), dict):
        document['groups'] = {g: [r for r in rows if isinstance(r, dict) and (_time(r.get('end')) or now) > now]
                              for g, rows in document['groups'].items() if isinstance(rows, list)}
    published = published_schedule.lines(config, state, now, document)
    if published and published[0].startswith('📅 <b>'):
        published[0] = '📅 <b>Опублікований графік · до кінця дня:</b>'
        published = [line.replace('відключень немає', 'відключень більше немає') for line in published]
    lines.extend(published)
    source = document.get('source')
    links = {'pro_kyiv': ('Pro Kyiv · дані ДТЕК', 'https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/'),
             'alerts_energy': ('Alerts.energy · дані ДТЕК', 'https://alerts.energy/kyivska-oblast')}
    if source in links:
        label, url = links[source]
        lines.append(f'<a href="{url}">Джерело — {label}</a>.')
    return lines
