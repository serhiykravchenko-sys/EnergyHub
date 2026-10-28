"""Persisted net SOC interval evidence, including solar, never HP metering."""
from datetime import datetime
from .report import number, compact_number
from .events import format_duration


def begin(now, soc):
    value = number(soc)
    return dict(start=now.isoformat(), start_soc=value, last_at=now.isoformat(),
                last_soc=value, valid=value is not None and 0 <= value <= 100)


def sample(record, now, soc, fresh=True):
    if not isinstance(record, dict):
        return
    value = number(soc)
    try:
        gap = (now-datetime.fromisoformat(record['last_at'])).total_seconds()
        if not fresh or value is None or not 0 <= value <= 100:
            record['has_gaps'] = True
            return
        if gap > 120:
            record['has_gaps'] = True
        if (gap < 0 or record.get('last_soc') is None
                or (gap <= 120 and abs(value-record['last_soc']) > 3)):
            record['valid'] = False
    except (ValueError, KeyError, TypeError):
        record['valid'] = False
    record.update(last_at=now.isoformat(), last_soc=value)


def values(record, now, soc):
    if not isinstance(record, dict) or record.get('valid') is not True:
        return None
    try:
        first = number(record['start_soc']); final = number(soc)
        seconds = (now-datetime.fromisoformat(record['start'])).total_seconds()
        age = (now-datetime.fromisoformat(record['last_at'])).total_seconds()
        if first is None or final is None or not 60 <= seconds <= 48*3600 or not 0 <= age <= 120:
            return None
        return first, final, seconds, (final-first)*3600/seconds
    except (KeyError, TypeError, ValueError):
        return None


def net_line(record, now, soc):
    data = values(record, now, soc)
    if data is None:
        return ''
    first, final, seconds, rate = data
    sign = '+' if rate > 0 else '−' if rate < 0 else ''
    qualification = ' · за крайніми показниками' if record.get('has_gaps') else ''
    return (f'🔋 <b>{compact_number(first)}% → {compact_number(final)}%</b> · '
            f'<b>≈{sign}{compact_number(round(abs(rate), 1))} %/год</b>{qualification}.')


def preparation_notice(state, client, now, data):
    """One completion per actual charging episode, only after acknowledged hold."""
    try:
        if not 0 <= (now-datetime.fromisoformat(data['checked_at'])).total_seconds() <= 120:
            return None
        key = data['start']
        start, end = datetime.fromisoformat(key), datetime.fromisoformat(data['end'])
        soc, target = number(data.get('current_soc')), number(data.get('target_soc'))
        if soc is None or target is None or not 0 <= soc <= 100 or not 20 <= target <= 95:
            return None
    except (KeyError, ValueError, TypeError):
        return None
    session = state.get('precharge_soc_session')
    if isinstance(session, dict) and session.get('key') != key:
        session = None
        state.pop('precharge_soc_session', None)
    mode = (client.state('sensor.energyhub_operating_mode') or {}).get('state')
    if data.get('phase') == 'charging' and data.get('acknowledged') is True and mode == 'panic':
        amps = number(data.get('observed_charge_a'))
        if amps is not None and amps > 0:
            if session is None:
                session = dict(begin(now,soc),key=key)
                state['precharge_soc_session'] = session
    if session:
        sample(session, now, soc)
        if (not session.get('completed') and now<start and soc>=target
                and data.get('phase')=='holding' and data.get('acknowledged') is True
                and data.get('acknowledged_target_soc') == target
                and mode=='panic_grid_hold'):
            session['completed']=True
            observed=values(session,now,soc)
            detail=f'🔋 Заряд: <b>{compact_number(soc)}%</b>.'
            if observed:
                first,final,seconds,rate=observed
                if rate>0:
                    detail=(f'🔋 <b>{compact_number(first)}% → {compact_number(final)}%</b> за '
                            f'<b>{format_duration(seconds)}</b> · швидкість заряджання '
                            f'<b>≈{compact_number(round(rate))} %/год</b>.')
            title = '✅ <b>Дозаряджання завершено.</b>'
            return (title+'\n'+detail+
                    f'\n🕒 Планове відключення: <b>{start:%H:%M}–{end:%H:%M}</b>.'+
                    f'\n🔌 <b>Підтримуємо близько {compact_number(target)}% за допомогою ДТЕК до відключення.</b>')
    return None
