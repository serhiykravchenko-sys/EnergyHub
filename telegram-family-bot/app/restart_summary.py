"""Read-only HA restart summaries, keyed by the bridge's HA-start session."""
from datetime import datetime
from math import isfinite
from .control_notifications import control_view, HELPERS
from .presentation import mode_label

SESSION = 'input_text.energyhub_load_bridge_session'
MINIMUM_WAIT_SECONDS = 60
MAXIMUM_WAIT_SECONDS = 300


def boot_id(client):
    value = (client.state(SESSION) or {}).get('state')
    try:
        parsed = datetime.fromisoformat(value)
        return value if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def summary(client, now, session):
    def value(entity):
        return (client.state(entity) or {}).get('state')
    fresh = value('sensor.energyhub_telemetry_freshness') == 'fresh'
    mode = mode_label(value('sensor.energyhub_operating_mode')) if fresh else None
    try:
        minimum = float(value('input_number.ahm_minimum_soc'))
        minimum_text = f'{minimum:g}%' if isfinite(minimum) and 20 <= minimum <= 95 else 'невідомий'
    except (TypeError, ValueError):
        minimum_text = 'невідомий'
    try:
        soc = float(value('sensor.powmr_10_2m_battery_soc'))
        soc_text = f'{soc:g}%' if isfinite(soc) and 0 <= soc <= 100 else 'невідомий'
    except (TypeError, ValueError):
        soc_text = 'невідомий'
    overload = control_view(client, 'overload', now)
    overload_text = {'off':'вимкнено — лише попередження', 'ready':'увімкнено',
                     'blocked':'увімкнено, очікуємо готовності'}.get(overload, 'стан невідомий')
    guard = (client.state('sensor.energyhub_peak_load_guard') or {}).get('attributes') or {}
    battery = guard.get('battery_protection')
    stamp = datetime.fromisoformat(session).astimezone(now.tzinfo)
    try:
        guard_at = datetime.fromisoformat(str(guard.get('load_snapshot_at')))
        guard_current = guard_at >= datetime.fromisoformat(session) and 0 <= (now-guard_at).total_seconds() <= 30
    except (TypeError, ValueError):
        guard_current = False
    battery_text = ('увімкнено (50% попередження · 40% вимкнення · 60% відновлення)'
                    if guard_current and guard.get('control_schema') == 5
                    and isinstance(battery, dict) else 'стан ще не підтверджено')
    smart = value(HELPERS['smart_heating'])
    solar_only = value(HELPERS['solar_only'])
    heating_text = ('керує EH · лише сонце + обмежений заряд батареї'
                    if smart == 'on' and solar_only == 'on' else
                    'керує EH · за потреби з допомогою ДТЕК'
                    if smart == 'on' else 'ручне керування')
    protection = (
        'активний'
        if battery_text.startswith('увімкнено') and overload_text.startswith('увімкнено')
        else f'батарея — {battery_text}; навантаження — {overload_text}'
    )
    strategy = mode or 'стратегія уточнюється'
    return '\n'.join([
        f'🔄 <b>{stamp:%H:%M} · HA перезапущено, EH працює</b>',
        f'🔋 <b>{soc_text}</b> · {strategy} · резерв {minimum_text}',
        f'🛡 Захист батареї та перевантаження: {protection}',
        f'♨️ Опалення: {heating_text}.',
    ])


def restart_state_ready(client, now, session):
    """Require current-boot evidence before announcing restored controls."""
    try:
        started = datetime.fromisoformat(session)
    except (TypeError, ValueError):
        return False

    telemetry = client.state('sensor.energyhub_telemetry_freshness') or {}
    if telemetry.get('state') != 'fresh':
        return False
    if (client.state('sensor.energyhub_operating_mode') or {}).get('state') in (
        None, 'unknown', 'unavailable'
    ):
        return False
    if (client.state(HELPERS['autopilot']) or {}).get('state') not in ('on', 'off'):
        return False

    reserve = (client.state('sensor.energyhub_ahm_weather_buffer') or {}).get('attributes') or {}
    if not isinstance(reserve.get('automatic_control_enabled'), bool):
        return False
    try:
        reserve_at = datetime.fromisoformat(str(reserve.get('evaluated_at')))
        if reserve_at < started:
            return False
    except (TypeError, ValueError):
        return False

    guard = (client.state('sensor.energyhub_peak_load_guard') or {}).get('attributes') or {}
    if guard.get('control_schema') != 5 or not isinstance(guard.get('battery_protection'), dict):
        return False
    try:
        snapshot_at = datetime.fromisoformat(str(guard.get('load_snapshot_at')))
        if snapshot_at < started:
            return False
    except (TypeError, ValueError):
        return False
    return control_view(client, 'overload', now) in ('off', 'ready')


def observe_restart(client, state, now):
    session = boot_id(client)
    if session is None:
        return False
    age = (now-datetime.fromisoformat(session)).total_seconds()
    if age < 0:
        return False
    previous = state.get('ha_restart_seen')
    if previous == session:
        return False
    # Installing/restarting the bot is not evidence that HA just restarted.
    if previous is None and age > 600:
        state['ha_restart_seen'] = session
        state['restart_summary_pending'] = False
        return True
    state['restart_summary_pending'] = True
    if age < MINIMUM_WAIT_SECONDS:
        return True
    if age < MAXIMUM_WAIT_SECONDS and not restart_state_ready(client, now, session):
        return True
    queue = state.setdefault('pending_notifications', [])
    queue[:] = [x for x in queue if x.get('kind') != 'ha_restart_summary'
                and not str(x.get('kind','')).startswith('dashboard_control_')]
    queue.append(dict(kind='ha_restart_summary', boot_id=session,
                      message=summary(client, now, session), created_at=now.isoformat()))
    for key in HELPERS:
        current = control_view(client, key, now)
        if current is not None:
            state.setdefault('dashboard_control_observations', {})[key] = {'value':current}
    state['ha_restart_seen'] = session
    state['restart_summary_pending'] = False
    return True
