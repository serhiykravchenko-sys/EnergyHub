"""Read-only night-plan messages; EnergyHub owns all charging decisions."""
from datetime import datetime
from .report import number, compact_number
from .grid_evidence import qualified

ENTITY = 'sensor.energyhub_night_charge'


def snapshot(client, now):
    data = (client.state(ENTITY) or {}).get('attributes') or {}
    try:
        if 0 <= (now-datetime.fromisoformat(data['checked_at'])).total_seconds() <= 120:
            return data
    except (KeyError, TypeError, ValueError):
        pass
    return {}


def decision(config, client, now, data):
    phase = data.get('phase')
    if phase == 'skipped':
        return '⚠️ Даних прогнозу або споживання недостатньо. Нічне дозаряджання за дефіцитом пропускаємо; резерв і підготовка за графіком залишаються активними.'
    if phase in {'inactive', 'guarded', None}:
        return ''
    gap, soc = [number(data.get(k)) for k in ('deficit_kwh', 'current_soc')]
    target = number(data.get('planned_target_soc', data.get('target_soc')))
    if gap is None:
        return ''
    fallback = ('⚠️ Даних недостатньо; використовуємо останній підтверджений дефіцит.\n'
                if data.get('source') == 'fallback' else '')
    if gap <= 0:
        return fallback+'☀️ Прогноз сонця покриває споживання. Нічне дозаряджання не потрібне.'
    if soc is None or target is None:
        return ''
    if soc >= target:
        return fallback+f'🌙 Заряд <b>{soc:g}%</b> · ціль <b>{target:g}%</b>. Дозаряджання не потрібне; плануємо зберігати заряд до <b>07:00</b>, поки ДТЕК доступний.'
    consumption, solar = number(data.get('consumption_kwh')), number(data.get('solar_kwh'))
    energy = (f'☀️ Споживання <b>{consumption:g} kWh</b> · сонце <b>{solar:g} kWh</b> · дефіцит <b>{gap:g} kWh</b>.\n'
              if consumption is not None and solar is not None else f'☀️ Очікуваний дефіцит: <b>{gap:g} kWh</b>.\n')
    online = qualified(config, client, now) is True
    charging = online and data.get('acknowledged') is True and (number(data.get('observed_charge_a')) or 0) > 0
    action = 'Дозаряджаємо нічним тарифом' if charging else 'Плануємо нічне дозаряджання'
    return fallback+energy+f'🌙 {action}: <b>{soc:g}% → {target:g}%</b>.'+(' Очікуємо підтверджене живлення ДТЕК.' if not online else '')


def observe(config, client, state, now):
    data = snapshot(client, now)
    text = decision(config, client, now, data)
    if not text:
        return False
    key = [data.get('day'), data.get('source'), data.get('deficit_kwh'), data.get('target_soc'), data.get('phase') == 'skipped']
    if state.get('night_charge_decision') == key:
        return False
    state['night_charge_decision'] = key
    state.setdefault('pending_notifications', []).append(dict(kind='night_charge_decision',
        message=text, created_at=now.isoformat(), day=data.get('day')))
    return True


def completed_snapshot(client, now):
    # Completed evidence is historical, not a live control snapshot. Report
    # construction may outlive the two-minute live-status freshness limit.
    data = ((client.state(ENTITY) or {}).get('attributes') or {}).get('completed') or {}
    try:
        ended = datetime.fromisoformat(data['end'])
        finished = datetime.fromisoformat(data['finished_at'])
        valid = (data.get('day') == now.date().isoformat() and data.get('finished') is True
                 and ended.tzinfo is not None and finished.tzinfo is not None
                 and ended.date() == now.date() and ended.hour == 7 and ended.minute == 0
                 and 0 <= (now-ended).total_seconds() < 86400
                 and 0 <= (finished-ended).total_seconds() < 86400
                 and finished <= now)
    except (KeyError, TypeError, ValueError):
        valid = False
    return data if valid else {}


def morning(client, now, *, compact=False):
    data = completed_snapshot(client, now)
    if not data or data.get('source') == 'unavailable':
        return '🌙 Підготовка до дефіциту генерації: розрахунок або нічний підсумок не підтверджено.'
    demand, solar, gap, target, reserve = [number(data.get(k)) for k in
        ('consumption_kwh', 'solar_kwh', 'deficit_kwh', 'target_soc', 'reserve_soc')]
    if any(v is None for v in (demand, solar, gap, target, reserve)):
        return ('ℹ️ Використано останній підтверджений розрахунок.\n' if data.get('source') == 'fallback' else '')+'🌙 Підготовка до дефіциту генерації: розрахунок або нічний підсумок не підтверджено.'
    capacity = number(data.get('capacity_kwh'))
    compensation = f'<b>{compact_number(gap/capacity*100, 1)}%</b>' if capacity is not None and capacity > 0 else 'компенсація дефіциту'
    result = [f'🌙 <b>Підготовка до дефіциту генерації</b>',
        f'🏠 Споживання <b>{demand:.1f}</b> − прогноз <b>{solar:.1f}</b> → дефіцит <b>≈{gap:.1f} kWh</b>.',
        f'🔋 Ціль: резерв <b>{reserve:g}%</b> + {compensation} → <b>{compact_number(target, 1)}%</b>.']
    if data.get('source') == 'fallback':
        result.append('ℹ️ Використано останній підтверджений розрахунок.')
    if capacity is not None and capacity > 0 and reserve + gap/capacity*100 > target + 0.1:
        result[-1] += f' Максимум <b>{compact_number(target, 1)}%</b>.'
    start, end = number(data.get('start_soc')), number(data.get('end_soc'))
    operations = data.get('operations') or {}
    night, scheduled = operations.get('night') or {}, operations.get('scheduled') or {}
    if scheduled:
        a, b = number(scheduled.get('start_soc')), number(scheduled.get('end_soc'))
        try:
            at = datetime.fromisoformat(scheduled.get('outage_start')).astimezone(now.tzinfo)
            when = f' перед відключенням о <b>{at:%H:%M}</b>'
        except (ValueError, TypeError):
            when = ' перед запланованим відключенням'
        if a is not None and b is not None:
            result.append(f'🔋 Окремо зафіксовано заряджання{when}: <b>{a:g}% → {b:g}%</b>.')
    if end is not None and end < target:
        result.append(f'⚠️ О 07:00 заряд <b>{end:g}%</b>; розрахованої цілі не досягнуто.')
    return '\n'.join(result)
