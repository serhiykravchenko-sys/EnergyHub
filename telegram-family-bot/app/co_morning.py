"""CO summary is separate from CO2 ventilation information."""
from datetime import datetime
from html import escape
from .report import number


def lines(config,client,now,state=None, *, compact=False):
    if compact:
        return compact_lines(config, client, now, state)
    targets=getattr(config,'co_alarms',())
    if not targets: return []
    result=['🛡 <b>CO — чадний газ:</b>']
    for target in targets:
        stem=target.entity.removeprefix('binary_sensor.').removesuffix('_carbon_monoxide')
        cached = (state or {}).get('co_last_valid', {})
        live_alarm = (client.state(target.entity) or {}).get('state')
        def fresh(entity):
            try:
                row=client.state(entity) or {}
                at=datetime.fromisoformat(row.get('last_reported') or row.get('last_updated'))
                if -5<=(now-at).total_seconds()<=86400: return row.get('state')
            except Exception: pass  # Missing evidence must not suppress the whole report.
            return None
        alarm=fresh(target.entity)
        ppm=number(fresh('sensor.'+stem+'_co'))
        battery=number(fresh('sensor.'+stem+'_battery'))
        if live_alarm not in {'on', 'off'} or ppm is None:
            from .co_cache import reading as last_reading
            value, at = last_reading(cached, 'sensor.'+stem+'_co', now)
            old_battery, battery_at = last_reading(cached, 'sensor.'+stem+'_battery', now)
            label = {'First-floor CO':'1-й поверх', 'Basement CO':'Підвал'}.get(target.label, target.label)
            if number(value) is not None and at is not None:
                detail = f'останні дані <b>{number(value):g} ppm</b> від {at:%d.%m %H:%M}'
                if number(old_battery) is not None and battery_at is not None:
                    detail += f' · батарея {number(old_battery):g}% (від {battery_at:%d.%m %H:%M})'
                result.append(f'• {escape(label)}: поточні дані не підтверджені; {detail}.')
                if alarm == 'on':
                    result.append('🚨 Датчик повідомляє тривогу CO.')
                continue
            if cached.get('sensor.'+stem+'_co'):
                result.append(f'• {escape(label)}: немає підтверджених даних за останні 24 год.')
            else:
                result.append(f'• {escape(label)}: дані недоступні; час останнього показника невідомий.')
            if alarm == 'on':
                result.append('🚨 Датчик повідомляє тривогу CO.')
            continue
        reading=f'<b>{ppm:g} ppm</b>' if ppm is not None and ppm>=0 else 'дані недоступні'
        status=('⚠️ тривога' if alarm=='on' else 'показники в нормі' if alarm=='off' and ppm==0 else 'стан потребує перевірки')
        battery_text=f'<b>{battery:g}%</b>' if battery is not None and 0<=battery<=100 else 'дані недоступні'
        label = {'First-floor CO':'1-й поверх', 'Basement CO':'Підвал'}.get(target.label, target.label)
        if alarm not in {'on','off'} and ppm is None:
            result.append(f'• {escape(label)}: немає даних. Перевірте зв’язок і живлення датчика.')
            continue
        parts=[reading,status]
        try:
            ppm_row = client.state('sensor.'+stem+'_co') or {}
            ppm_at = datetime.fromisoformat(ppm_row.get('last_reported') or ppm_row.get('last_updated'))
            parts.append(f'показник у HA від {ppm_at:%d.%m %H:%M}')
        except (TypeError, ValueError):
            pass
        if battery is not None and 0<=battery<=100:
            parts.append('батарея '+battery_text)
        result.append(f'• {escape(label)}: '+' · '.join(parts)+'.')
    return result


def compact_lines(config, client, now, state=None):
    """Dated observations, low batteries only; never a claim of current safety."""
    targets = getattr(config, 'co_alarms', ())
    if not targets:
        return []
    result = ['🛡 <b>CO — останні показники:</b>']
    normal = 0
    cache = (state or {}).get('co_last_valid', {})
    for target in targets:
        stem = target.entity.removeprefix('binary_sensor.').removesuffix('_carbon_monoxide')
        def reading(entity):
            row = client.state(entity) or {}
            try:
                at = datetime.fromisoformat(row.get('last_reported') or row.get('last_updated'))
                value = row.get('state')
                valid = value in {'on', 'off'} if entity.startswith('binary_sensor.') else number(value) is not None and number(value) >= 0
                if valid and -5 <= (now-at).total_seconds():
                    return row.get('state'), at.astimezone(now.tzinfo)
            except (TypeError, ValueError):
                pass
            from .co_cache import reading as cached_reading
            value, at = cached_reading(cache, entity, now)
            return value, at.astimezone(now.tzinfo) if at else None
        value, at = reading('sensor.'+stem+'_co')
        ppm = number(value)
        available = False
        label = escape({'First-floor CO': '1-й поверх', 'Basement CO': 'Підвал'}.get(target.label, target.label))
        if ppm is None or ppm < 0 or at is None:
            result.append(f'• {label}: показник недоступний; час останнього показника невідомий.')
        else:
            live_ppm = number((client.state('sensor.'+stem+'_co') or {}).get('state'))
            available = ((client.state(target.entity) or {}).get('state') in {'on', 'off'}
                         and live_ppm is not None and live_ppm >= 0)
            status = (' · поточний стан недоступний' if not available else '')
            if (now-at).total_seconds() > 86400:
                status += ' · показник застарілий'
            result.append(f'• {label}: <b>{ppm:g} ppm</b> · показник у HA від {at:%d.%m %H:%M}{status}.')
        alarm, alarm_at = reading(target.entity)
        if (ppm == 0 and available and at is not None
                and -5 <= (now-at).total_seconds() <= 86400
                and alarm == 'off' and alarm_at is not None
                and -5 <= (now-alarm_at).total_seconds() <= 86400):
            normal += 1
        if alarm == 'on':
            result.append(f'🚨 {label}: остання передана тривога CO · {alarm_at:%d.%m %H:%M}.')
        battery, battery_at = reading('sensor.'+stem+'_battery')
        battery = number(battery)
        if battery is not None and 0 <= battery <= 20 and battery_at:
            result.append(f'🪫 {label}: батарея <b>{battery:g}%</b> · {battery_at:%d.%m %H:%M}.')
    return result
