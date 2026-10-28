"""Read-only HA restart summaries, keyed by the bridge's HA-start session."""
from datetime import datetime
from .control_notifications import control_view, HELPERS
from .report import number

SESSION = 'input_text.energyhub_load_bridge_session'
MINIMUM_WAIT_SECONDS = 60
MAXIMUM_WAIT_SECONDS = 300


def compact_policy(client,now,config,state,session):
    """Compose once from structured evidence instead of concatenated reports."""
    def value(field,default):
        return (client.state(getattr(config,field,default)) or {}).get('state')
    fresh=value('telemetry_freshness_entity','sensor.energyhub_telemetry_freshness')=='fresh'
    soc=number(value('battery_soc_entity','sensor.powmr_10_2m_battery_soc')) if fresh else None
    reserve=number(value('ahm_minimum_soc_entity','input_number.ahm_minimum_soc'))
    battery='🔋 Заряд: <b>'+ (f'{soc:g}%' if soc is not None and 0<=soc<=100 else 'невідомий')+'</b>'
    battery+=' · резерв: <b>'+ (f'{reserve:g}%' if reserve is not None and 20<=reserve<=95 else 'не підтверджено')+'</b>.'
    plan=(client.state('sensor.energyhub_outage_preparation') or {}).get('attributes') or {}
    try:
        start,end=datetime.fromisoformat(plan['start']),datetime.fromisoformat(plan['end'])
        target=number(plan.get('target_soc'))
        valid=(fresh and getattr(config,'dtek_schedule_enabled',False)
               and plan.get('source_status')=='fresh'
               and plan.get('phase') in {'waiting','solar','charging','holding','waiting_for_grid'}
               and 0<=(now-datetime.fromisoformat(plan['checked_at'])).total_seconds()<=120
               and datetime.fromisoformat(plan['checked_at'])>=datetime.fromisoformat(session)
               and end>max(now,start) and target is not None and 20<=target<=95)
    except (KeyError,TypeError,ValueError):
        valid=False
    mode=value('operating_mode_entity','sensor.energyhub_operating_mode')
    source=(client.state('sensor.energyhub_panic_target_source') or {}).get('state','')
    manual=fresh and str(source).startswith('Manual Panic:') and mode in {'panic','panic_grid_hold'}
    if valid and not manual:
        battery=battery.rstrip('.')+f' · ціль підготовки: <b>{target:g}%</b>.'
    result=[battery]
    if manual:
        result.append('🛑 Режим Panic — батарея як павербанк; ціль <b>95%</b>.')
    from .source_policy import status_lines
    result+=status_lines(state,now,['дача'],only_active=True)
    from .schedule_context import rows
    windows=rows(state,now,getattr(config,'dtek_dacha_group','')) if getattr(config,'dtek_schedule_enabled',False) else None
    window=next(((a,b) for a,b in windows if b>now),None) if windows else None
    if window is None and valid:
        window=(start,end)
    if window:
        a,b=window
        day='' if a.date()==now.date() else f'{a:%d.%m} '
        result.append(f'📅 За графіком: <b>{day}{a:%H:%M}–{b:%H:%M}</b>.')
    grid=number(value('grid_voltage_entity','sensor.powmr_10_2m_grid_voltage')) if fresh else None
    from .grid_evidence import qualified
    confirmed = qualified(config, client, now)
    if grid is None or not 0<=grid<=300 or confirmed is None:
        result.append('⚡ Доступність ДТЕК уточнюється.')
    elif grid<=180:
        result.append('⚡ ДТЕК зараз недоступний.')
    elif mode=='solar':
        result.append('⚡ ДТЕК доступний; будинок працює без його допомоги.')
    elif mode in {'panic','panic_grid_hold','hybrid_charging','hybrid_grid_hold'}:
        result.append('🔌 ДТЕК підключено для '+('підготовки батареї.' if valid and plan.get('control_active') is True and plan.get('acknowledged') is True else 'збереження заряду.'))
    else:
        result.append('⚡ ДТЕК доступний; режим живлення уточнюється.')
    return result


def boot_id(client):
    value = (client.state(SESSION) or {}).get('state')
    try:
        parsed = datetime.fromisoformat(value)
        return value if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def summary(client, now, session, config=None, state=None):
    def value(entity):
        return (client.state(entity) or {}).get('state')
    overload = control_view(client, 'overload', now)
    overload_text = {'off':'вимкнено (HA)', 'ready':'увімкнено',
                     'blocked':'увімкнено, очікуємо готовності'}.get(overload, 'стан невідомий')
    guard = (client.state('sensor.energyhub_peak_load_guard') or {}).get('attributes') or {}
    stamp = datetime.fromisoformat(session).astimezone(now.tzinfo)
    battery_state = value('automation.energyhub_battery_discharge_protection')
    battery_text = {'on': 'увімкнено (HA)', 'off': 'вимкнено (HA)'}.get(battery_state, 'стан невідомий')
    smart = value(HELPERS['smart_heating'])
    solar_only = value(HELPERS['solar_only'])
    heating_text = ('керує EH · лише сонце + обмежений заряд батареї'
                    if smart == 'on' and solar_only == 'on' else
                    'керує EH · Smart'
                    if smart == 'on' else 'ручне керування')
    protection = (
        'активний'
        if battery_state == 'on' and overload == 'ready'
        else f'батарея — {battery_text}; навантаження — {overload_text}'
    )
    from types import SimpleNamespace
    policy = compact_policy(client,now,config or SimpleNamespace(),state or {},session)
    return '\n'.join([
        f'🔄 <b>{stamp:%H:%M} · HA перезапущено, EH працює</b>',
        *policy,
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
    if guard.get('control_schema') != 6:
        return False
    if (client.state('automation.energyhub_battery_discharge_protection') or {}).get('state') not in ('on', 'off'):
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
