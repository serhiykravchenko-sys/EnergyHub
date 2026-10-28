"""Read-only restoration presentation and related notification coalescing."""
from datetime import datetime, timedelta
from . import source_policy, outage_schedule
from .events import recovery_message, format_duration
from .report import number, compact_number

MODE_EVENTS = {'grid_hold_started', 'grid_hold_released', 'battery_reserve_charging'}
MODE_STATES = {
    'grid_hold_started': {'panic_grid_hold', 'hybrid_grid_hold'},
    'grid_hold_released': {'solar'},
    'battery_reserve_charging': {'panic', 'hybrid_charging'},
}


def schedule_lines(config, state, now, place, group):
    """Published rows are informational; they do not restore control authority."""
    lines = []
    lines+=source_policy.status_lines(state,now,[place],only_active=True)
    if not getattr(config, 'dtek_schedule_enabled', False):
        return lines
    document = state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
    try:
        checked = datetime.fromisoformat(document['checked_at'])
        if (document.get('validated') is not True or document.get('source_status') != 'fresh'
                or not -60 <= (now-checked).total_seconds() <= outage_schedule.SOURCE_MAX_AGE_SECONDS):
            return lines + ['📅 Наступне відключення ще не підтверджено.']
        from .schedule_context import rows as confirmed_rows
        rows=confirmed_rows(state,now,group)
        if rows is None or group not in document.get('groups',{}):
            return lines + ['📅 Наступне відключення ще не підтверджено.']
        current=next(((a,b) for a,b in rows if a<=now<b),None)
        if current:
            lines.append(f'📅 Планове вікно відключень триває до <b>{current[1]:%H:%M}</b>. Можливе повторне відключення.')
            return lines
        upcoming = sorted((a, b) for a, b in rows if a > now and b > a)
        if upcoming:
            a, b = upcoming[0]
            day = ('завтра ' if a.date() == now.date()+timedelta(days=1)
                   else f'{a:%d.%m} ' if a.date() != now.date() else '')
            lines.append(f'📅 Наступне відключення: <b>{day}{a:%H:%M}–{b:%H:%M}</b>')
        elif now.date().isoformat() in document.get('dates', []):
            lines.append('📅 На сьогодні відключень більше не заплановано.')
        else:
            lines.append('📅 Наступне відключення ще не підтверджено.')
    except (KeyError, ValueError, TypeError):
        lines.append('📅 Наступне відключення ще не підтверджено.')
    return lines


def house_context(config, client, state, now):
    lines = []
    reserve = number((client.state(config.ahm_minimum_soc_entity) or {}).get('state'))
    attrs = (client.state(config.weather_buffer_entity) or {}).get('attributes') or {}
    if reserve is not None and 20 <= reserve <= 95:
        suffix = (' (за доступністю ДТЕК останні 48 год).'
                  if attrs.get('reserve_planning_source') == 'grid_confidence'
                  else '.')
        lines.append(f'🔋 Резерв батареї: <b>{compact_number(reserve)}%</b>{suffix}')
    else:
        lines.append('🔋 Резерв батареї ще не підтверджено.')
    return '\n'+'\n'.join(lines)


def house_text(config, client, state, now, item):
    event = item.get('restoration_event')
    if event:
        at = datetime.fromisoformat(event['at'])
        start = datetime.fromisoformat(event['outage_start']) if event.get('outage_start') else None
        header = recovery_message(at, start, None if event.get('rate_line') else event.get('soc'))
        if event.get('rate_line'):
            header += '\n'+event['rate_line']
        if event.get('solar_line'):
            header += '\n'+event['solar_line']
    else:
        # Keep the factual event header from legacy persisted queued messages.
        header = '\n'.join(str(item['message']).splitlines()[:2])
    return header + house_context(config, client, state, now)


def apartment_text(config, state, now, at, start):
    lines = [f'🟢 <b>Квартира: ДТЕК відновився о {at:%H:%M}</b>']
    if start is not None:
        lines.append(f'⏱ Без зв’язку з Hub: <b>{format_duration((at-start).total_seconds())}</b>')
    lines.extend(schedule_lines(config, state, now, 'квартира', getattr(config, 'dtek_apartment_group', '')))
    lines.append('📡 Xiaomi Hub онлайн.')
    return '\n'.join(lines)


def mode_action(item, config, client, state, now):
    """Restoration owns related mode messages, including persisted queued ones."""
    if (client.state(config.telemetry_freshness_entity) or {}).get('state') != 'fresh':
        return 'defer'
    voltage = number((client.state(config.grid_voltage_entity) or {}).get('state'))
    if voltage is None:
        return 'defer'
    if voltage <= 180:
        return 'drop'
    mode = (client.state(config.operating_mode_entity) or {}).get('state')
    if mode not in MODE_STATES[item['kind']]:
        return 'drop'
    if state.get('grid_candidate') is True:
        return 'defer'
    try:
        created = datetime.fromisoformat(item['created_at'])
        restored = datetime.fromisoformat(state['grid_restored_at'])
        if abs((created-restored).total_seconds()) <= 120:
            return 'drop'
    except (KeyError, ValueError, TypeError):
        pass
    return 'send'
