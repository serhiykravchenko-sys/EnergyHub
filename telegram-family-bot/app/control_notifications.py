"""Read-only dashboard mode observation; never requests device control."""
import re
from datetime import datetime


HELPERS = {
    'autopilot': 'input_boolean.energyhub_autopilot',
    'overload': 'input_boolean.energyhub_load_control_armed',
    'reserve_mode': 'input_select.energyhub_ahm_weather_authority',
    'smart_heating': 'input_boolean.energyhub_smart_heating',
    'solar_only': 'input_boolean.energyhub_solar_only_heating',
    'smart_status': 'input_select.energyhub_smart_heating_status',
    'climate_policy': 'input_select.energyhub_climate_policy',
    'quiet': 'switch.first_floor_heat_pump_quiet',
    'eco': 'switch.first_floor_heat_pump_eco',
}
OBSERVED_CONTROLS = tuple(key for key in HELPERS
                          if key not in {'overload', 'smart_heating', 'solar_only', 'smart_status', 'quiet', 'eco'})
MESSAGES = {
    ('autopilot', 'on'): '🧭 Автопілот EH увімкнено.',
    ('autopilot', 'off'): '🧭 Автопілот EH вимкнено.',
    ('reserve_mode', 'Automatic'): '🔋 Автокерування мін. зарядом увімкнено — керує EH.',
    ('reserve_mode', 'Manual'): '🔋 Автокерування мін. зарядом вимкнено — вручну; EH рекомендує.',
    ('climate_policy', 'Smart'): '♨️ <b>Тепловий насос 1-го поверху: режим Smart увімкнено.</b>\nEH керує автоматичною роботою. Температуру задаєте з пульта або мобільного застосунку.',
    ('climate_policy', 'Off'): None,
    ('climate_policy', 'Solar-only'): '☀️ <b>Тепловий насос 1-го поверху: режим тільки від сонця увімкнено.</b>\nEH запустить насос за достатніх сонячних умов і призупинить роботу, коли їх не вистачатиме.',
    ('quiet', 'on'): '🌙 Тихий режим теплового насоса 1-го поверху увімкнено.',
    ('quiet', 'off'): '🌙 Тихий режим теплового насоса 1-го поверху вимкнено.',
    ('eco', 'on'): '🍃 Eco режим теплового насоса 1-го поверху увімкнено.',
    ('eco', 'off'): '🍃 Eco режим теплового насоса 1-го поверху вимкнено.',
}


def control_view(client, key, now):
    value = (client.state(HELPERS[key]) or {}).get('state')
    if key == 'climate_policy':
        return value if value in {'Off', 'Smart', 'Solar-only'} else None
    if key in ('smart_status', 'reserve_mode'):
        return value if (key, value) in MESSAGES else None
    if value not in ('on', 'off'):
        return None
    if key != 'overload' or value == 'off':
        return value
    native = (client.state('automation.energyhub_inverter_overload_protection') or {}).get('state')
    phase = (client.state('input_select.energyhub_overload_phase') or {}).get('state')
    return 'ready' if native == 'on' and phase in {'idle','waiting','restoring','retry','deferred'} else 'blocked'


def observe_controls(client, state, now):
    """Silent baseline; profile changes require two minutes of stable feedback."""
    observations = state.setdefault('dashboard_control_observations', {})
    if state.get('hp_control_observer_version') != '3.3':
        # Effective-policy observations from 3.2 are not selection events.
        observations.pop('climate_policy', None)
        state['hp_control_observer_version'] = '3.3'
    queue = state.setdefault('pending_notifications', [])
    legacy = {'dashboard_control_smart_heating', 'dashboard_control_solar_only',
              'dashboard_control_smart_status'}
    old_length = len(queue)
    queue[:] = [item for item in queue if item.get('kind') not in legacy
                and item.get('kind') not in {'dashboard_control_quiet', 'dashboard_control_eco'}
                and not (item.get('kind') == 'dashboard_control_climate_policy'
                         and item.get('control_value') == 'Off')]
    changed = len(queue) != old_length
    for key in OBSERVED_CONTROLS:
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
        if elapsed < (120 if key in {'quiet', 'eco'} else 10):
            continue
        kind = f'dashboard_control_{key}'
        queue[:] = [item for item in queue if item.get('kind') != kind]
        message = MESSAGES.get((key, current))
        if message and key == 'climate_policy' and current == 'Off':
            master = (client.state('input_select.energyhub_climate_policy') or {}).get('state')
            operation = (client.state('input_select.energyhub_climate_operation') or {}).get('state')
            if master in {'Smart', 'Solar-only'} and operation == 'Scheduled':
                message = ('♨️ Поточне вікно опалення / охолодження завершено. '
                           'Режим EH залишається активним; наступний запуск — за розкладом і дозволом захисту.')
            elif master != 'Off':
                message = ('♨️ Автоматична робота теплового насоса 1-го поверху зараз не активна. '
                           'Режим і розклад перевірте на панелі EH.')
        if message and key == 'climate_policy' and current == 'Smart':
            operation = (client.state('input_select.energyhub_climate_operation') or {}).get('state')
            if operation == 'Continuous':
                message += '\nРежим діє без розкладу, доки ви не оберете Off або Solar-only на панелі EH. Ручне вимкнення насоса призупиняє автоматичні старти до ручного ввімкнення.'
            elif operation == 'Scheduled':
                end = (client.state('input_datetime.energyhub_climate_smart_end') or {}).get('state', '')
                valid = isinstance(end, str) and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]', end)
                message += ('\nПоточне Smart вікно діє до '+end[:5]+'.' if valid
                            else '\nРежим працює за розкладом; час завершення перевірте на панелі EH.')
                message += ' Ручне вимкнення насоса не скасовує Smart: EH чекатиме ручного ввімкнення.'
            else:
                message += '\nРозклад і умови завершення перевірте на панелі EH.'
        if message:
            if key == 'quiet':
                hp = client.state('climate.first_floor_heat_pump') or {}
                from .report import number, compact_number
                target = number((hp.get('attributes') or {}).get('temperature'))
                if target is not None and hp.get('state') in {'heat', 'cool'}:
                    message += f' Цільова температура за даними HA: {compact_number(target)} °C.'
            queue.append({'kind': kind, 'control_key': key, 'control_value': current,
                          'message': message, 'created_at': now.isoformat(),
                          'profile_stable': key in {'quiet', 'eco'}})
        record['value'] = current
        record.pop('candidate', None)
        changed = True
    return changed


def queued_control_is_current(client, item, now):
    key = item.get('control_key')
    if key in {'quiet', 'eco'} and item.get('profile_stable') is not True:
        # Old persisted notifications only required ten seconds of feedback.
        return False
    return (client is not None and key in OBSERVED_CONTROLS
            and control_view(client, key, now) == item.get('control_value'))
