"""Persist bounded observed solar running time; never infer missing energy."""
from datetime import datetime
from math import isfinite
from .report import number

ENERGY = 'sensor.first_floor_heat_pump_plug_energy'


def meter(entities, now):
    row = entities.get(ENERGY) or {}
    value = number(row.get('state'))
    try:
        age = (now-datetime.fromisoformat(row['last_updated'])).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None
    return value if value is not None and isfinite(value) and value >= 0 and -5 <= age <= 900 else None


def observe(state, entities, now):
    policy = (entities.get('input_select.energyhub_climate_effective_policy') or {}).get('state')
    hp = (entities.get('climate.first_floor_heat_pump') or {}).get('state')
    fresh = (entities.get('sensor.energyhub_telemetry_freshness') or {}).get('state') == 'fresh'
    running = policy == 'Solar-only' and fresh and hp in {'heat', 'cool'}
    session = state.get('solar_running_session')
    tick, energy = now.timestamp(), meter(entities, now)
    ended = None
    if session and (policy != 'Solar-only' or session['date'] != now.date().isoformat()):
        session['complete'] = False  # Boundary between polls is not exact.
        if (not fresh or hp not in {'heat', 'cool', 'off'}
                or not 0 <= tick-session['at'] <= 90):
            session['energy_valid'] = False
        ended = summary(session, energy) if session["seconds"] > 0 else None
        state.pop('solar_running_session', None)
        session = None
    if session is None and running:
        session = dict(date=now.date().isoformat(), seconds=0, at=tick,
                       running=True, base=energy, last_energy=energy, complete=True,
                       energy_valid=energy is not None)
        state['solar_running_session'] = session
    elif session:
        gap = tick-session['at']
        if not fresh or hp not in {'heat', 'cool', 'off'}:
            session['energy_valid'] = False
        if not 0 <= gap <= 90:
            session['complete'] = False
            session['energy_valid'] = False
        elif session['running'] and running:
            session['seconds'] += gap
        elif session['running'] and hp == 'off' and fresh:
            try:
                stopped = datetime.fromisoformat(entities['climate.first_floor_heat_pump']['last_changed']).timestamp()
                if session['at'] <= stopped <= tick:
                    session['seconds'] += stopped-session['at']
                else:
                    session['complete'] = False
            except (KeyError, TypeError, ValueError):
                session['complete'] = False
        elif session['running'] or running:
            session['complete'] = False
        if energy is None or (session['last_energy'] is not None and energy < session['last_energy']):
            session['energy_valid'] = False
        if energy is not None:
            session['last_energy'] = energy
        session.update(at=tick, running=running)
    return ended


def summary(session, energy):
    minutes = int(session['seconds']//60)
    qualifier = '' if session['complete'] else 'за наявними даними '
    duration = f'⏱ Працював {qualifier}{minutes//60} год {minutes%60} хв.'
    if (session['energy_valid'] and energy is not None and session['base'] is not None
            and energy >= session['base']
            and (session['last_energy'] is None or energy >= session['last_energy'])):
        consumption = f'⚡ За період приблизно {energy-session["base"]:.2f} кВт·год (покази розетки ще не перевірені).'
    else:
        consumption = '⚡ Споживання за період недоступне: неповні або некоректні покази розетки.'
    return duration+'\n'+consumption
