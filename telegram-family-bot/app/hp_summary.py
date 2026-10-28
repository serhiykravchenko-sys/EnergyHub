"""Read-only, bounded HP operation summaries from actual observed states."""
from datetime import datetime, timedelta
from .report import number, compact_number
from .solar_session import meter
from .events import format_duration

HP = 'climate.first_floor_heat_pump'
MASTER = 'input_select.energyhub_climate_policy'


def observe(state, entities, now):
    journal = state.setdefault('hp_operation_summary', {'segments': [], 'solar_days': {}})
    def value(key):
        return (entities.get(key) or {}).get('state')
    hp = entities.get(HP) or {}
    attrs = hp.get('attributes') or {}
    target = number(attrs.get('temperature'))
    unit = (entities.get('sensor.energyhub_hp1_connection') or {}).get('attributes', {}).get('ha_temperature_unit')
    sample = dict(at=now.isoformat(), policy=value(MASTER), hp=hp.get('state'),
                  quiet=value('switch.first_floor_heat_pump_quiet'),
                  eco=value('switch.first_floor_heat_pump_eco'), target=target, unit=unit,
                  night=({'on': True, 'off': False}.get(value('binary_sensor.energyhub_hp_night_window'))),
                  energy=meter(entities, now))
    if sample['night'] and sample['policy'] == 'Smart':
        import json
        try:
            memory = json.loads(value('input_text.energyhub_hp1_night_temperature') or '{}')
            base = number(memory.get('base'))
            if base is not None:
                journal['night_baseline'] = dict(target=base, at=now.isoformat())
            if memory.get('blocked'):
                journal['night_restore_released_at']=now.isoformat()
        except (ValueError, TypeError):
            pass
    previous = journal.get('last')
    gap = 0
    if previous:
        try:
            gap = (now-datetime.fromisoformat(previous['at'])).total_seconds()
        except (ValueError, TypeError, KeyError):
            gap = -1
    valid = previous is not None and 0 <= gap <= 90
    if sample['night'] and sample['policy'] == 'Smart' and (sample['hp'] not in {'heat', 'cool', 'off'} or (previous and not valid)):
        journal['night_unconfirmed_at'] = now.isoformat()
    # Describe confirmed state on leaving the window, without claiming who
    # changed it or that the room maintained the target temperature.
    if valid and previous.get('night') and sample['night'] is False and previous.get('policy') == 'Smart':
        journal['night_exit'] = dict(sample)
        journal['night_exit']['window_end'] = now.isoformat()
    exit_sample = journal.get('night_exit')
    if (exit_sample and sample['night'] is False and sample['policy'] == 'Smart'
            and 0 <= (now-datetime.fromisoformat(exit_sample.get('window_end', exit_sample['at']))).total_seconds() <= 180
            and any(sample.get(k) != exit_sample.get(k) for k in ('hp', 'quiet', 'target', 'unit'))):
        # HA may confirm the temperature/quiet command a few samples after the
        # window closes. Report that observed confirmation time, not a schedule.
        journal['night_exit'] = dict(sample, window_end=exit_sample.get('window_end', exit_sample['at']))
    grid = number(value('sensor.powmr_10_2m_grid_voltage'))
    eco_running = (sample['policy'] == 'Smart' and sample['hp'] in {'heat', 'cool'}
        and sample['eco'] == 'on' and value('sensor.energyhub_telemetry_freshness') == 'fresh'
        and grid is not None and 0 <= grid <= 180)
    eco_segments = journal.setdefault('eco_segments', [])
    if eco_running:
        if valid and previous.get('eco_running') and eco_segments:
            eco_segments[-1]['end'] = now.isoformat()
        else:
            same_outage = (eco_segments and previous and previous.get('eco') == 'on'
                           and sample['eco'] == 'on' and gap <= 90
                           and previous.get('hp') in {'heat', 'cool'}
                           and previous.get('grid_online') is not True)
            if same_outage:
                eco_segments[-1]['end'] = now.isoformat()
                eco_segments[-1]['incomplete'] = True
            else:
                eco_segments.append(dict(start=now.isoformat(), end=now.isoformat()))
    elif valid and previous.get('eco_running') and eco_segments:
        # End at the next confirmed HP/grid state, never across unavailable data.
        if sample['hp'] in {'heat', 'cool', 'off'} and grid is not None and value('sensor.energyhub_telemetry_freshness') == 'fresh':
            eco_segments[-1]['end'] = now.isoformat()
    sample['grid_online'] = None if grid is None or value('sensor.energyhub_telemetry_freshness') != 'fresh' else grid > 180
    sample['eco_running'] = eco_running
    journal['eco_segments'] = [s for s in eco_segments
        if (now-datetime.fromisoformat(s['start'])).total_seconds() <= 172800][-96:]
    # Every segment is observed operation, not the requested schedule.
    if sample['night'] and sample['policy'] == 'Smart' and sample['hp'] in {'heat', 'cool', 'off'}:
        signature = tuple(sample[k] for k in ('hp', 'quiet', 'target', 'unit'))
        segments = journal['segments']
        if (valid and previous.get('night') and segments
                and tuple(previous.get(k) for k in ('hp', 'quiet', 'target', 'unit')) == signature
                and tuple(segments[-1].get(k) for k in ('hp', 'quiet', 'target', 'unit')) == signature):
            segments[-1]['end'] = now.isoformat()
        else:
            segments.append(dict(sample, start=now.isoformat(), end=now.isoformat()))
    elif (valid and previous.get('night') and sample['night'] is False and journal['segments']
            and previous.get('hp') in {'heat', 'cool', 'off'} and sample['hp'] in {'heat', 'cool', 'off'}):
        journal['segments'][-1]['end'] = now.isoformat()
    journal['segments'] = [s for s in journal['segments']
                           if (now-datetime.fromisoformat(s['start'])).total_seconds() <= 172800][-96:]
    running = sample['policy'] == 'Solar-only' and sample['hp'] in {'heat', 'cool'}
    if running or (previous and previous.get('policy') == 'Solar-only' and previous.get('hp') in {'heat', 'cool'}):
        date = now.date().isoformat()
        day = journal['solar_days'].setdefault(date, dict(seconds=0, kwh=0, intervals=[], complete=True, energy_valid=True))
        if running and (not valid or previous.get('policy') != 'Solar-only' or previous.get('hp') not in {'heat', 'cool'}):
            day['intervals'].append([now.isoformat(), now.isoformat()])
        if valid and previous.get('policy') == 'Solar-only' and previous.get('hp') in {'heat', 'cool'}:
            # Split midnight explicitly; no previous-day seconds assigned to today.
            start = datetime.fromisoformat(previous['at'])
            same_day = start.date() == now.date()
            if same_day:
                day['seconds'] += gap
                if day['intervals']:
                    day['intervals'][-1][1] = now.isoformat()
                before, after = previous.get('energy'), sample['energy']
                if before is None or after is None or after < before:
                    day['energy_valid'] = False
                else:
                    day['kwh'] += after-before
            else:
                day['complete'] = False
                day['energy_valid'] = False
        elif previous and not valid:
            day['complete'] = False
            day['energy_valid'] = False
        day['intervals'] = day['intervals'][-64:]
    cutoff = (now.date()-timedelta(days=2)).isoformat()
    journal['solar_days'] = {date: day for date, day in journal['solar_days'].items() if date >= cutoff}
    journal['last'] = sample


def lines(state, client, now):
    policy = (client.state(MASTER) or {}).get('state')
    result = []
    if policy == 'Smart':
        result.append('♨️ <b>Тепловий насос — режим Smart.</b>')
    elif policy == 'Solar-only':
        result.append('☀️ <b>Тепловий насос — режим тільки від сонця.</b>')
    journal = state.get('hp_operation_summary') or {}
    clock = ((client.state('input_datetime.energyhub_climate_quiet_start') or {}).get('state') or '23:00:00')
    try:
        boundary = now.replace(hour=int(clock[:2]), minute=int(clock[3:5]), second=0, microsecond=0)
    except (ValueError, TypeError):
        boundary = now.replace(hour=23, minute=0, second=0, microsecond=0)
    if boundary > now:
        boundary -= timedelta(days=1)
    groups = {}
    for segment in journal.get('segments', []):
        start, end = datetime.fromisoformat(segment['start']), datetime.fromisoformat(segment['end'])
        if end <= boundary or start > now or end <= start:
            continue
        start = max(start, boundary)
        if segment['hp'] == 'off':
            label = 'насос вимкнений'
        elif segment['quiet'] == 'on':
            label = 'тихий режим'
        else:
            label = 'насос працював'
        key = label
        group = groups.setdefault(key, dict(start=start, end=end, seconds=0, targets=[]))
        group['end'] = end
        group['seconds'] += (end-start).total_seconds()
        if segment['hp'] != 'off' and segment.get('target') is not None and segment.get('unit') in {'°C', '°F'}:
            text = f"{compact_number(segment['target'])} {segment['unit']}"
            if not group['targets'] or group['targets'][-1] != text:
                group['targets'].append(text)
    for label, group in groups.items():
        span = (group['end']-group['start']).total_seconds()
        interrupted = ' (із перервами)' if span-group['seconds'] > 90 else ''
        text = f"🌙 {group['start']:%H:%M}–{group['end']:%H:%M} — {label}{interrupted}"
        if group['targets']:
            text += '; остання підтверджена задана температура ' + group['targets'][-1]
            if len(group['targets']) > 1:
                text += ' (протягом ночі змінювалася)'
        result.append(text+'.')
    unconfirmed = journal.get('night_unconfirmed_at')
    if unconfirmed and 0 <= (now-datetime.fromisoformat(unconfirmed)).total_seconds() <= 86400:
        result.append('⚠️ Нічні налаштування насоса підтверджено не повністю: зв’язок із HA був недоступний.')
    exit_sample = journal.get('night_exit') or {}
    if exit_sample and 0 <= (now-datetime.fromisoformat(exit_sample['at'])).total_seconds() <= 86400:
        if exit_sample['hp'] in {'heat', 'cool'} and exit_sample['quiet'] == 'off':
            text = f"☀️ {datetime.fromisoformat(exit_sample['at']):%H:%M} — тихий режим вимкнено"
            if exit_sample.get('target') is not None and exit_sample.get('unit') in {'°C', '°F'}:
                text += f"; цільова температура {compact_number(exit_sample['target'])} {exit_sample['unit']}"
            baseline_row = journal.get('night_baseline') or {}
            try:
                baseline = baseline_row.get('target') if datetime.fromisoformat(baseline_row['at']) >= boundary else None
            except (KeyError,ValueError,TypeError):
                baseline = None
            try:
                if datetime.fromisoformat(journal['night_restore_released_at']) >= boundary:
                    baseline = None
            except (KeyError,ValueError,TypeError):
                pass
            if baseline is not None and exit_sample.get('target') != baseline:
                text += f'; повернення до {compact_number(baseline)} {exit_sample.get("unit", "°C")} не підтверджено'
            result.append(text+'.')
    for segment in journal.get('eco_segments', []):
        start, end = datetime.fromisoformat(segment['start']), datetime.fromisoformat(segment['end'])
        if end > boundary and start <= now and end > start:
            start = max(start, boundary)
            note = ' (із прогалинами телеметрії)' if segment.get('incomplete') else ''
            result.append(f'🍃 {start:%H:%M}–{end:%H:%M} · {format_duration((end-start).total_seconds())} — Eco під час відключення ДТЕК{note}.')
    day = journal.get('solar_days', {}).get((now.date()-timedelta(days=1)).isoformat())
    if day and day['intervals']:
        intervals = day['intervals']
        clocks = [f"{datetime.fromisoformat(a):%H:%M}–{datetime.fromisoformat(b):%H:%M}" for a,b in intervals if a != b]
        minutes = int(day['seconds']//60)
        if clocks:
            result.append('☀️ Учора робота від сонця: '+', '.join(clocks[:8])+
                          f'; {minutes//60} год {minutes%60} хв'+(' (неповні дані).' if not day['complete'] else '.'))
        result.append(f"⚡ За показами розетки: {day['kwh']:.2f} кВт·год."
                      if day['energy_valid'] else '⚡ Споживання за розеткою: неповні дані.')
    return result


def outage_detail(client):
    policy = (client.state(MASTER) or {}).get('state')
    hp = (client.state(HP) or {}).get('state')
    if policy != 'Smart':
        return ''
    eco = (client.state('switch.first_floor_heat_pump_eco') or {}).get('state')
    if hp in {None, 'unknown', 'unavailable'} or eco in {None, 'unknown', 'unavailable'}:
        return '\n⚠️ Тепловий насос недоступний для керування в HA. Перехід в Eco не підтверджено.'
    if hp not in {'heat', 'cool'}:
        return ''
    if (client.state('sensor.energyhub_telemetry_freshness') or {}).get('state') != 'fresh':
        return '\n⚠️ Дані інвертора неактуальні. Автоматичний вибір Eco не підтверджено.'
    grid = number((client.state('sensor.powmr_10_2m_grid_voltage') or {}).get('state'))
    if grid is None or not 0 <= grid <= 300:
        return '\n⚠️ Стан ДТЕК не підтверджено. Автоматичний вибір Eco не підтверджено.'
    if grid > 180:
        return ''  # A delayed historical outage must not imply current Eco demand.
    action = 'працює в Eco' if eco == 'on' else 'перехід в Eco ще не підтверджено'
    return f'\n🍃 Тепловий насос: {action}. Без ДТЕК роботу буде призупинено при заряді 40%.'
