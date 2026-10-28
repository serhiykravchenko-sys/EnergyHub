"""Read yesterday's HA daily energy statistics, matching the HP chart."""
import logging
from datetime import datetime, timedelta, timezone
from .report import number, compact_number
from .home_assistant import HomeAssistantError

LOGGER = logging.getLogger(__name__)


def timestamp(value):
    numeric = number(value)
    if numeric is not None:
        return numeric / 1000 if numeric >= 100_000_000_000 else numeric
    try:
        at = datetime.fromisoformat(value.replace('Z','+00:00'))
        return at.timestamp() if at.tzinfo else None
    except (ValueError,TypeError,AttributeError):
        return None


def daily_value(rows, start, end):
    """Select the exact completed calendar-day bucket; never use a nearby day."""
    selected = []
    for row in rows or []:
        a,b = timestamp(row.get('start')),timestamp(row.get('end'))
        if a is not None and b is not None and abs(a-start.timestamp())<1 and abs(b-end.timestamp())<1:
            selected.append(row)
    if len(selected) != 1:
        return None
    value = number(selected[0].get('change'))
    return value if value is not None and value >= 0 else None


def lines(config, client, now, *, compact=False):
    end = now.replace(hour=0,minute=0,second=0,microsecond=0)
    start = (end-timedelta(days=1)).astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    targets = [(floor,getattr(config,f'heat_pump_floor_{floor}_energy_entity','')) for floor in (1,2,3)]
    targets = [(floor,entity) for floor,entity in targets if entity]
    if not targets:
        return []
    try:
        statistics = client.daily_energy_statistics(start,end,[entity for _,entity in targets])
        if not isinstance(statistics,dict):
            raise ValueError('Invalid recorder statistics')
    except (ValueError,TypeError,AttributeError,HomeAssistantError,OSError) as exc:
        LOGGER.warning('HP daily statistics unavailable: %s',type(exc).__name__)
        statistics = {}
    result = []
    short = []
    for floor,entity in targets:
        try:
            value = daily_value(statistics.get(entity,[]),start,end)
        except (ValueError,TypeError,AttributeError):
            value = None
        if value is None:
            short.append(f'{floor}-й поверх — не підтверджено')
            result.append(f'♨️ Тепловий насос {floor}-го поверху: учора — даних недостатньо.')
        elif value >= 0.2:
            short.append(f'{floor}-й поверх — <b>{compact_number(value,1)} kWh</b>')
        if value is not None and value > 0.1 + 1e-9:
            qualifier = ' (за виміряною потужністю)' if entity.endswith('_energy_calculated') else ''
            result.append(f'♨️ Тепловий насос {floor}-го поверху: учора <b>≈{compact_number(value,2)} kWh</b>{qualifier}.')
    return ['♨️ Теплові насоси: '+' · '.join(short)+'.'] if compact and short else result


def hot_water_lines(config, client, now):
    entity = getattr(config, 'water_boiler_energy_entity', 'sensor.water_boiler_energy_calculated')
    if not entity:
        return []
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = (end-timedelta(days=1)).astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    try:
        stats = client.daily_energy_statistics(start, end, [entity])
        value = daily_value(stats.get(entity, []), start, end)
    except (ValueError, TypeError, AttributeError, HomeAssistantError, OSError):
        value = None
    if value is None:
        return ['🚿 Гаряча вода: даних недостатньо.']
    return [f'🚿 Гаряча вода: <b>{compact_number(value, 1)} kWh</b>.']
