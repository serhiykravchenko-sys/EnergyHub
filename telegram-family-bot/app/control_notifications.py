"""Read-only dashboard mode observation; never requests device control."""
from datetime import datetime


HELPERS = {
    'autopilot': 'input_boolean.energyhub_autopilot',
    'overload': 'input_boolean.energyhub_load_control_armed',
    'reserve_mode': 'input_select.energyhub_ahm_weather_authority',
    'smart_heating': 'input_boolean.energyhub_smart_heating',
    'solar_only': 'input_boolean.energyhub_solar_only_heating',
    'smart_status': 'input_select.energyhub_smart_heating_status',
}
MESSAGES = {
    ('autopilot', 'on'): '🧭 Автопілот EH увімкнено.',
    ('autopilot', 'off'): '🧭 Автопілот EH вимкнено.',
    ('overload', 'off'): '🛡 Автозахист від перевантаження вимкнено — лише попередження. Вимкнені пристрої не відновлюються автоматично.',
    ('overload', 'ready'): '🛡 Автозахист від перевантаження увімкнено для доступних пристроїв.',
    ('overload', 'blocked'): '⚠️ Автозахист від перевантаження запитано, але ще не готовий. Перевірте панель EH.',
    ('reserve_mode', 'Automatic'): '🔋 Автокерування мін. зарядом увімкнено — керує EH.',
    ('reserve_mode', 'Manual'): '🔋 Автокерування мін. зарядом вимкнено — вручну; EH рекомендує.',
    ('smart_heating', 'on'): '♨️ Розумне опалення увімкнено — керує EH.',
    ('smart_heating', 'off'): '♨️ Розумне опалення вимкнено — ручне керування.',
    ('solar_only', 'on'): '☀️ Опалення від сонця увімкнено — ДТЕК не використовується спеціально для опалення.',
    ('solar_only', 'off'): '🏠 Звичайне розумне опалення — за потреби використовується ДТЕК.',
    ('smart_status', 'Waiting'): '♨️ Опалення: очікуємо безпечних актуальних даних.',
    ('smart_status', 'Battery paused'): '🔋 Опалення призупинено — бережемо заряд батареї.',
    ('smart_status', 'Solar paused'): '☀️ Опалення призупинено — зберігаємо мінімальний заряд батареї.',
    ('smart_status', 'Eco'): '♨️ Тепловий насос 1-го поверху: Eco.',
    ('smart_status', 'Normal'): '♨️ Тепловий насос 1-го поверху: звичайний режим.',
    ('smart_status', 'Quiet'): '🌙 Тепловий насос 1-го поверху: тихий режим.',
    ('smart_status', 'Turbo'): '🔥 Тепловий насос 1-го поверху: Turbo, максимум на 1 годину.',
    ('smart_status', 'Manual'): '♨️ Тепловий насос 1-го поверху: ручне керування.',
}


def control_view(client, key, now):
    value = (client.state(HELPERS[key]) or {}).get('state')
    if key in ('smart_status', 'reserve_mode'):
        return value if (key, value) in MESSAGES else None
    if value not in ('on', 'off'):
        return None
    if key != 'overload' or value == 'off':
        return value
    entity = client.state('sensor.energyhub_peak_load_guard') or {}
    attrs = entity.get('attributes') or {}
    try:
        age = (now - datetime.fromisoformat(attrs.get('load_snapshot_at'))).total_seconds()
        # EnergyHub suppresses unchanged snapshots for up to 60 seconds.
        # Allow publish/scheduler jitter without calling a healthy guard blocked.
        fresh = -5 <= age <= 90
    except (ValueError, TypeError):
        fresh = False
    ready = (fresh and entity.get('state') not in (None, 'unknown', 'unavailable')
             and attrs.get('automatic_requested') is True
             and attrs.get('mode') == 'automatic' and attrs.get('armed') is True
             and attrs.get('control_ready') is True and not attrs.get('fault')
             and isinstance(attrs.get('eligible_loads'), list) and bool(attrs['eligible_loads']))
    return 'ready' if ready else 'blocked'


def observe_controls(client, state, now):
    """Silent first baseline, persisted dedup, ten-second stable transitions."""
    observations = state.setdefault('dashboard_control_observations', {})
    queue = state.setdefault('pending_notifications', [])
    changed = False
    for key in HELPERS:
        current = control_view(client, key, now)
        record = observations.get(key)
        if current is None:
            if record and record.pop('candidate', None) is not None:
                changed = True
            continue
        if record is None:
            observations[key] = {'value': current}
            changed = True
            continue
        if key == 'overload' and record['value'] in ('ready','blocked') and current in ('ready','blocked'):
            # ON stays ON during readiness fluctuations. Data incidents own
            # prolonged outage/recovery messages; toggles still notify normally.
            if record['value'] != current or record.get('candidate'):
                record['value'] = current
                record.pop('candidate',None)
                changed = True
            continue
        if record['value'] == current:
            if record.pop('candidate', None) is not None:
                changed = True
            continue
        candidate = record.get('candidate') or {}
        if candidate.get('value') != current:
            record['candidate'] = {'value': current, 'since': now.isoformat()}
            changed = True
            continue
        try:
            elapsed = (now - datetime.fromisoformat(candidate['since'])).total_seconds()
        except (ValueError, TypeError, KeyError):
            elapsed = -1
        if elapsed < 0:
            record.pop('candidate', None)
            changed = True
            continue
        if elapsed < 10:
            continue
        kind = f'dashboard_control_{key}'
        queue[:] = [item for item in queue if item.get('kind') != kind]
        queue.append({'kind': kind, 'control_key': key, 'control_value': current,
                      'message': MESSAGES[key, current], 'created_at': now.isoformat()})
        record['value'] = current
        record.pop('candidate', None)
        changed = True
    return changed


def queued_control_is_current(client, item, now):
    key = item.get('control_key')
    return (client is not None and key in HELPERS
            and control_view(client, key, now) == item.get('control_value'))
