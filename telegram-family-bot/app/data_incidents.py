"""Persistable data-availability observations; never controls hardware."""
from datetime import datetime, timedelta
from math import isfinite
import logging
from html import escape
from .home_assistant import HomeAssistantError
from .control_notifications import control_view

LABELS = {'ha':'Home Assistant', 'inverter':'інвертора', 'pv2':'сонячної генерації PV2',
          'bridge':'зв’язку з керуванням ТН 1-го поверху', 'weather':'УГМЦ',
          'forecast':'прогнозу генерації', 'reserve':'розрахунку запасу батареї',
          'control':'стану HA-захисту від перевантаження'}
LOGGER = logging.getLogger(__name__)
DEVICES = {'water_pump':'насоса','water_boiler':'бойлера','heat_pump_floor_1':'теплового насоса 1-го поверху',
           'heat_pump_floor_2':'теплового насоса 2-го поверху','heat_pump_floor_3':'теплового насоса 3-го поверху',
           'microwave':'мікрохвильовки'}
LABELS.update({'load_'+k:'споживання '+v for k,v in DEVICES.items()})


def alert_after(key):
    if key in ('inverter', 'bridge'):
        return 300
    return 180


def label(state, key):
    return escape(state.get('data_source_labels', {}).get(key, LABELS.get(key, 'джерела даних')))


def numeric(value):
    try:
        return value is not None and isfinite(float(value))
    except (ValueError, TypeError):
        return False


def fresh(stamp, now, seconds):
    try:
        return -5 <= (now-datetime.fromisoformat(str(stamp))).total_seconds() <= seconds
    except (TypeError, ValueError):
        return False


def collect(client, config, state, now):
    """Return known source health. HA loss masks, never recovers, child sources."""
    try:
        def entity(key):
            return client.state(key) or {}
        inverter = entity(config.telemetry_freshness_entity)
        battery = entity(config.battery_soc_entity).get('state')
        voltage = entity(config.grid_voltage_entity).get('state')
        health = {'ha':True, 'inverter':inverter.get('state') == 'fresh'
                  and numeric(battery) and 0 <= float(battery) <= 100
                  and numeric(voltage) and float(voltage) >= 0}
        pv2 = entity('sensor.energyhub_pv2_telemetry_freshness')
        if pv2 or state.get('data_pv2_seen'):
            state['data_pv2_seen'] = True
            health['pv2'] = pv2.get('state') == 'fresh'
        guard = entity('sensor.energyhub_peak_load_guard')
        attrs = guard.get('attributes') or {}
        # HA publishes the normal bridge snapshot every 30 seconds. A
        # 90-second acceptance window avoids turning scheduler jitter into an
        # outage while remaining shorter than the three-minute alert window.
        bridge_ok = fresh(attrs.get('load_snapshot_at'), now, 90)
        health['bridge'] = bridge_ok
        # Native overload readiness is independent of the HP-only bridge.
        if health['inverter']:
            requested = entity('input_boolean.energyhub_load_control_armed').get('state')
            health['control'] = requested == 'off' or (requested == 'on' and control_view(client,'overload',now) == 'ready')
        # Migrated plugs are absent from the HP-only participant snapshot.
        # Their connectivity belongs to configured household device monitoring.
        forecast = entity(config.solar_forecast_entity)
        health['forecast'] = numeric(forecast.get('state')) and float(forecast['state']) >= 0
        reserve = entity(config.weather_buffer_entity)
        health['reserve'] = (reserve.get('state') not in (None,'unknown','unavailable')
            and not (reserve.get('attributes') or {}).get('evidence_issues'))
        # UHMC has its own hourly poll, five-minute retry and deduplicated
        # family warning. Do not create a competing generic data incident.
        return health
    except (HomeAssistantError, OSError):
        return {'ha':False}


def observe(state, health, now):
    if state.get('data_health_schema') not in (2, 3):
        # Pre-v2 history mixed unchanged power age and 30-second scheduling
        # jitter with real availability. It cannot be migrated honestly.
        state['data_incidents'] = {}
        state['data_incident_history'] = []
        state['data_health_schema'] = 2
    if state['data_health_schema'] == 2:
        # The old 30-second control-view gate manufactured long "control"
        # incidents despite healthy 60-second guard heartbeats. Preserve all
        # independently observed sources, but do not carry that false history.
        state.setdefault('data_incidents', {}).pop('control', None)
        state['data_incident_history'] = [r for r in state.get('data_incident_history', [])
                                          if r.get('key') != 'control']
        state['data_health_schema'] = 3
    records = state.setdefault('data_incidents', {})
    history = state.setdefault('data_incident_history', [])
    stamp = now.timestamp()
    if health.get('ha') is False:
        health = {**{key: None for key in records if key != 'ha'}, **health}
    for key, good in health.items():
        record = records.get(key)
        if key.startswith('device:') and record is not None and stamp-record.get('last_seen', stamp) > 90:
            # Missing observation across bot/HA downtime cannot count towards
            # either continuous unavailability or stable recovery.
            if record['bad_since'] is not None:
                right = record.get('last_seen', stamp)
                if right > record['bad_since']:
                    record['intervals'].append([record['bad_since'], right])
            record['bad_since'] = None
            record['recovered_since'] = None
        if good is None:
            if record is not None and record['bad_since'] is not None:
                right = min(stamp, record.get('last_seen', stamp) + 90)
                if right > record['bad_since']:
                    record['intervals'].append([record['bad_since'], right])
                record['bad_since'] = None
            if record is not None:
                record['recovered_since'] = None
            continue
        if not good:
            if record is None:
                record = records[key] = dict(start=stamp, bad_since=stamp, intervals=[], warned=False,
                                             recovered_since=None, last_seen=stamp)
                LOGGER.info('Data incident started: source=%s at=%s',key,now.isoformat())
            if record['bad_since'] is None:
                record['bad_since'] = stamp
            record['recovered_since'] = None
        elif record is not None:
            if record['bad_since'] is not None:
                record['intervals'].append([record['bad_since'],stamp])
                record['bad_since'] = None
                record['recovered_since'] = stamp
            elif record['recovered_since'] is None:
                record['recovered_since'] = stamp
            # Missing observation (HA/bot unavailable) is not proof of stability.
            if stamp-record.get('last_seen',stamp) > 90:
                record['recovered_since'] = stamp
            if stamp-record['recovered_since'] >= 300 and not record['warned']:
                history.append(dict(record,key=key,end=stamp))
                del records[key]
                record = None
        if record is not None:
            record['last_seen'] = stamp
            record['intervals'] = [x for x in record['intervals'] if x[1] >= stamp-14*86400][-2000:]
    state['data_incident_history'] = [x for x in history if x.get('end',0) >= stamp-14*86400][-500:]


def deliver(state, telegram, config, now, client):
    """One combined warning/recovery per observation. Save after caller returns.

Only confirmed Telegram delivery marks warned. A crash after send before save
may duplicate a notification; there is no exactly-once Telegram API contract.
"""
    from .message_schedule import quiet_phase
    destination = getattr(config, 'technical_chat_id', '') or config.destination_chat_id
    if destination == config.destination_chat_id and quiet_phase(now, config) is not None:
        return False
    stamp = now.timestamp()
    records = state.setdefault('data_incidents',{})
    current = lambda r: 0 <= stamp-r.get('last_seen',0) <= 90
    warning = [k for k,r in records.items() if current(r) and not r['warned']
               and r['bad_since'] is not None
               and stamp-r['bad_since'] >= alert_after(k)]
    if warning:
        labels = ', '.join(f"{label(state,k)} (>{alert_after(k)//60} хв)"
                           for k in warning)
        if any(k in ('ha', 'inverter', 'bridge') for k in warning):
            tail = 'Спільні дані не підтверджені; нові команди EH можуть бути призупинені. Перевірте панель EH.'
        elif 'control' in warning:
            tail = 'Готовність автозахисту не підтверджена; перевірте панель EH. Це не доказ, що всі пристрої зупинені.'
        elif any(k.startswith('load_') for k in warning):
            tail = 'Пристрій без підтверджених даних пропускається; захист інших доступних пристроїв продовжується.'
        else:
            tail = 'Оцінки EH обмежені; перевірте джерела даних.'
        technical_chat = getattr(config, 'technical_chat_id', '') or config.destination_chat_id
        message_id = telegram.send_message(technical_chat,
            f'⚠️ EH: дані недоступні: {labels}. {tail}')
        for k in warning:
            records[k]['warned']=True
        LOGGER.info('Data warning delivered: sources=%s message_id=%s',','.join(warning),message_id)
    recovered = [k for k,r in records.items() if current(r) and r['warned'] and r['bad_since'] is None
                 and r['recovered_since'] is not None and stamp-r['recovered_since'] >= 300]
    if recovered:
        affects_control = any(k in ('ha', 'inverter', 'control') for k in recovered)
        suffix = 'Стан джерела знову стабільний.'
        if affects_control:
            # Read native readiness only when reporting its dependencies.
            try:
                status = control_view(client, 'overload', now)
            except (HomeAssistantError, OSError):
                return bool(warning)
            suffix = {'ready': 'HA-захист від перевантаження знову готовий.',
                      'off': 'Автозахист вимкнений вручну; налаштування не змінено.',
                      'blocked': 'Автозахист поки обмежений; перевірте панель EH.'}.get(
                          status, 'Готовність автокерування ще не підтверджена.')
        elif 'bridge' in recovered:
            suffix = 'Зв’язок із керуванням ТН відновлено; це не підтвердження роботи насоса.'
        technical_chat = getattr(config, 'technical_chat_id', '') or config.destination_chat_id
        message_id = telegram.send_message(technical_chat,
            '✅ Дані '+', '.join(label(state,k) for k in recovered)+
            ' відновлено (стабільні 5 хв). '+suffix)
        for key in recovered:
            state.setdefault('data_incident_history',[]).append(dict(records.pop(key),key=key,end=stamp))
        LOGGER.info('Data recovery delivered after stable window: sources=%s message_id=%s',','.join(recovered),message_id)
    return bool(warning or recovered)


def morning_lines(state, now):
    finish = now.timestamp()
    start = (now-timedelta(hours=24)).timestamp()
    groups = {}
    records = list(state.get('data_incident_history',[])) + [dict(r,key=k)
        for k,r in state.get('data_incidents',{}).items()]
    for r in records:
        intervals = list(r['intervals'])
        if r['bad_since'] is not None:
            intervals.append([r['bad_since'],now.timestamp()])
        for left,right in intervals:
            clipped = [max(left,start), min(right,finish)]
            if clipped[1] > clipped[0]:
                groups.setdefault(r['key'],[]).append(clipped)
    thresholds = {
        'ha': (120, 300), 'bridge': (300, 600),
        'inverter': (300, 600),
    }
    lines=[]
    for key,intervals in sorted(groups.items()):
        # Collapse poll-level flaps separated by less than two minutes into one
        # operational interruption before applying reporting thresholds.
        merged=[]
        for left,right in sorted(intervals):
            if merged and left-merged[-1][1] < 120:
                merged[-1][1] = max(merged[-1][1], right)
            else:
                merged.append([left,right])
        durations = [right-left for left,right in merged]
        longest_limit, total_limit = thresholds.get(key, (180, 300))
        if max(durations) < longest_limit and sum(durations) < total_limit:
            continue
        active = state.get('data_incidents',{}).get(key)
        status = 'дані ще недоступні' if active and active['bad_since'] is not None else 'перебій завершився'
        lines.append(f'📡 За 24 год, дані {label(state,key)}: перебоїв — {len(durations)}; '
                     f'разом {sum(durations)/60:.0f} хв, найдовший {max(durations)/60:.0f} хв; {status}.')
    return lines[:4] + ([f'📡 Ще джерел із перебоями: {len(lines)-4}. Подробиці — у журналі.'] if len(lines)>4 else [])
