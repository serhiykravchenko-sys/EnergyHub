"""Acknowledged CO alarms, solar waiting notices and configured-address changes."""
from html import escape
from .report import number
from . import solar_settings, solar_session
from datetime import datetime, timedelta
import json


CLIMATE = 'climate.first_floor_heat_pump'


def climate_cause(row, client, now, entity=CLIMATE):
    if (row.get('context') or {}).get('user_id'):
        return 'ручне керування'
    if client is not None:
        try:
            start = (now-timedelta(minutes=2)).isoformat()
            entries = client._request('/logbook/'+start+'?entity='+entity)
            changed = datetime.fromisoformat(row['last_changed']).timestamp()
            for entry in entries:
                at = datetime.fromisoformat(entry['when']).timestamp()
                if entry.get('entity_id') != entity or entry.get('state') != row['state'] or abs(at-changed) > 2:
                    continue
                source = entry.get('context_entity_id')
                if source in {'automation.energyhub_2_4_first_floor_smart_heating',
                              'automation.energyhub_first_floor_smart_heating'}:
                    return 'керування опаленням/охолодженням EH'
                if source == 'automation.energyhub_load_control_executor':
                    return 'захист EH'
                if entry.get('context_user_id'):
                    return 'ручне керування'
        except Exception:
            pass  # Unavailable attribution must not suppress the transition notice.
    return 'причина не встановлена'


def pause(state):
    session = state.get('solar_running_session')
    if session:
        session.update(running=False, complete=False, energy_valid=False)
    monitor = state.get('household_events', {})
    monitor.get('seen', {}).pop('solar_recovery_since', None)
    if monitor.get('pending', {}).pop('solar', None) is not None:
        monitor.get('seen', {}).pop('solar_phase', None)


def observe(state, targets, entities, now, client=None, quiet=None):
    monitor = state.setdefault('household_events', {'seen': {}, 'pending': {}})
    seen, pending = monitor['seen'], monitor['pending']
    tick = now.timestamp()
    previous_tick = seen.get('solar_observed_at', tick)
    if not 0 <= tick-previous_tick <= 90:
        seen.pop('solar_recovery_since', None)
    seen['solar_observed_at'] = tick

    def queue(key, text, urgent=False):
        pending[key] = dict(text=text, urgent=urgent, at=tick)

    retire_plug_notifications(state)
    seen.pop('fridge_protection', None)  # Retired custom controller.
    for key in list(pending):
        if key.startswith('fridge:'):
            pending.pop(key)

    ended = solar_session.observe(state, entities, now)
    if ended:
        queue('solar_summary:'+now.isoformat(), '☀️ Підсумок сонячної роботи насоса 1-го поверху.\n'+ended)
    limits = solar_settings.thresholds(entities)
    climate = entities.get(CLIMATE) or {}
    value = climate.get('state')
    previous = seen.get('hp1_climate') or {}
    if value in {'off', 'heat', 'cool', 'auto', 'dry', 'fan_only', 'heat_cool'} and climate.get('last_changed'):
        if (previous.get('value') and (previous['value'] == 'off') != (value == 'off')
                and 0 <= tick-previous.get('at', 0) <= 90):
            cause = climate_cause(climate, client, now, CLIMATE)
            title = 'вимкнено' if value == 'off' else 'увімкнено'
            try:
                at = datetime.fromisoformat(climate['last_changed']).astimezone(now.tzinfo).strftime('%H:%M')
            except (ValueError, TypeError):
                at = now.strftime('%H:%M')
            detail = ''
            if cause == 'керування опаленням/охолодженням EH' and value == 'off':
                status = (entities.get('input_select.energyhub_smart_heating_status') or {}).get('state')
                if status == 'Battery paused':
                    grid = number((entities.get('sensor.powmr_10_2m_grid_voltage') or {}).get('state'))
                    confirmed = (entities.get('sensor.energyhub_telemetry_freshness') or {}).get('state') == 'fresh' and grid is not None and 0 <= grid <= 180
                    detail = (' Пауза для збереження батареї без мережі (40%; відновлення від 50% або після повернення ДТЕК).'
                              if confirmed else ' EH повідомляє Battery paused; робота без мережі не підтверджена. Перевірте панель EH.')
                elif status == 'Solar paused':
                    detail = ' Сонячні умови не виконані; докладна причина — у повідомленні сонячного режиму.'
            elif cause == 'керування опаленням/охолодженням EH':
                detail = ' Автоматичний запуск або відновлення роботи.'
            during_quiet = (now.hour >= 23 or now.hour < 8) if quiet is None else quiet
            if during_quiet and cause in {'ручне керування', 'причина не встановлена'}:
                message = f'Тепловий насос 1-го поверху {title}'
                message += ' вручну.' if cause == 'ручне керування' else ' (за даними HA; причина не підтверджена).'
                event = dict(kind='hp_manual_transition', created_at=now.isoformat(), message=message)
                archive = state.setdefault('overnight_family_events', [])
                if event not in archive:
                    archive.append(event)
                    state['overnight_family_events'] = archive[-50:]
            detail = detail or (' Ручне керування.' if cause == 'ручне керування'
                                else ' За даними HA; причина не підтверджена.')
            queue('climate:'+str(climate['last_changed'])+':'+value,
                  f'♨️ Тепловий насос 1-го поверху {title}. '
                  f'{detail.strip()} 🕒 {at}', True)
        seen['hp1_climate'] = dict(value=value, at=tick)
    else:
        seen.pop('hp1_climate', None)

    selected = {target.entity for target in targets}
    for target in targets:
        row = entities.get(target.entity) or {}
        value = row.get('state')
        if value not in {'on', 'off'} or (target.parent and
                entities.get(target.parent, {}).get('state') != 'on'):
            continue
        key = 'co:'+target.entity
        previous = seen.get(key)
        seen[key] = value
        if value == 'on' and previous != 'on':
            pending.pop(key+':clear', None)
            queue(key+':alarm', f'🚨 <b>Спрацював датчик CO: {escape(target.label)}.</b> '
                  'Негайно перевірте сигнал тривоги та дотримуйтесь інструкції датчика.', True)
        elif value == 'off' and previous == 'on':
            queue(key+':clear', f'✅ Датчик CO {escape(target.label)} більше не повідомляє тривогу. '
                  'Це не підтвердження безпечності приміщення.')
    for key in list(seen):
        if key.startswith('co:') and key[3:] not in selected:
            seen.pop(key, None)
            pending.pop(key+':alarm', None)
            pending.pop(key+':clear', None)

    inventory = entities.get('sensor.energyhub_network_inventory') or {}
    addresses = inventory.get('attributes', {}).get('addresses')
    if isinstance(addresses, dict) and inventory.get('state') not in {'verifying', 'recovering'}:
        previous = seen.get('addresses')
        if isinstance(previous, dict):
            for key, value in addresses.items():
                if key in previous and value != previous[key]:
                    label = key.split(':', 1)[-1]
                    queue('address:'+key, f'🌐 Налаштована адреса {escape(label)} змінилася: '
                        f'{escape(str(previous[key]))} → {escape(str(value))}. '
                        f'Перевірка: {escape(str(inventory.get("state")))}.')
        seen['addresses'] = dict(addresses)

    master = (entities.get('input_select.energyhub_climate_policy') or {}).get('state')
    previous_master = seen.get('master_policy')
    try:
        cancelled = json.loads((entities.get('input_text.energyhub_hp1_solar_cancelled') or {}).get('state', '{}'))
    except (ValueError, TypeError):
        cancelled = {}
    cancelled_at = number(cancelled.get('at')) if isinstance(cancelled, dict) else None
    if (master == 'Off' and cancelled_at is not None and seen.get('solar_cancelled_at') != cancelled_at
            and 0 <= tick-cancelled_at <= 120 and (entities.get(CLIMATE) or {}).get('state') == 'off'):
        manual = ' вручну' if cancelled.get('manual') is True else ''
        queue('solar_cancelled', f'♨️ Тепловий насос вимкнено{manual}. Сонячний режим скасовано; керування насосом — вручну.')
        seen['solar_cancelled_at'] = cancelled_at
    if master in {'Smart', 'Solar-only', 'Off'}:
        seen['master_policy'] = master
    current_status = (entities.get('input_select.energyhub_smart_heating_status') or {}).get('state')
    grid_now = number((entities.get('sensor.powmr_10_2m_grid_voltage') or {}).get('state'))
    if (master == 'Smart' and current_status == 'Battery paused'
            and not seen.get('hp_battery_pause_episode')
            and (entities.get(CLIMATE) or {}).get('state') == 'off'
            and (entities.get('input_boolean.energyhub_hp1_battery_paused') or {}).get('state') == 'on'
            and seen.get('protection_status') not in {None, current_status}
            and (entities.get('sensor.energyhub_telemetry_freshness') or {}).get('state') == 'fresh'
            and grid_now is not None and 0 <= grid_now <= 180):
        seen['hp_battery_pause_episode'] = True
        queue('hp_battery_pause', '🔋 Тепловий насос призупинено для збереження батареї без ДТЕК (поріг 40%). Smart залишається увімкненим.')
    if (entities.get(CLIMATE) or {}).get('state') in {'heat', 'cool'} and (entities.get('input_boolean.energyhub_hp1_battery_paused') or {}).get('state') == 'off':
        seen.pop('hp_battery_pause_episode', None)
    if current_status:
        seen['protection_status'] = current_status
    policy = (entities.get('input_select.energyhub_climate_effective_policy') or {}).get('state')
    status = (entities.get('input_select.energyhub_smart_heating_status') or {}).get('state')
    fresh = (entities.get('sensor.energyhub_telemetry_freshness') or {}).get('state') == 'fresh'
    if policy != 'Solar-only':
        seen.pop('solar_waiting', None)
        seen.pop('solar_phase', None)
        pending.pop('solar', None)
        seen.pop('solar_recovery_since', None)
    else:
        hp = (entities.get('climate.first_floor_heat_pump') or {}).get('state')
        phase = None
        reason = None
        if fresh and status in {'Normal', 'Eco', 'Quiet'} and hp in {'heat', 'cool'}:
            phase = 'running'
        elif status in {'Solar paused', 'Battery paused', 'Waiting'}:
            phase = 'waiting'
            soc = number((entities.get('sensor.powmr_10_2m_battery_soc') or {}).get('state'))
            reserve = number((entities.get('input_number.ahm_minimum_soc') or {}).get('state'))
            grid = number((entities.get('sensor.powmr_10_2m_grid_voltage') or {}).get('state'))
            pv = number((entities.get('sensor.powmr_10_2m_total_pv_power') or {}).get('state'))
            if fresh and (status == 'Battery paused' or (soc is not None and reserve is not None and soc <= reserve)):
                reason = 'зберігаємо заряд батареї'
            elif not fresh or (status == 'Solar paused' and any(value is None for value in (soc, reserve, grid, pv))):
                reason = 'немає актуальних даних інвертора'
            elif hp in {None, 'unknown', 'unavailable'}:
                reason = 'тепловий насос недоступний у HA'
            elif status == 'Waiting':
                guard = (entities.get('sensor.energyhub_peak_load_guard') or {}).get('attributes') or {}
                reason = 'захист EH не дозволяє запуск' if guard.get('fault') or guard.get('pending') or guard.get('cycle') else 'очікуємо завершення паузи перед запуском'
            elif (entities.get('sensor.energyhub_operating_mode') or {}).get('state') != 'solar':
                reason = 'інвертор не в сонячному режимі'
            elif (entities.get('sun.sun') or {}).get('state') == 'below_horizon':
                reason = 'сонце зайшло'
            else:
                pv = number((entities.get('sensor.powmr_10_2m_total_pv_power') or {}).get('state'))
                if limits is None:
                    reason = 'некоректні пороги сонячної генерації на панелі EH'
                elif pv is not None and pv < limits[1]:
                    reason = f'сонячна генерація {pv:g} Вт нижче порогу {limits[1]:g} Вт'
                else:
                    reason = 'сонячні умови не виконані; падіння нижче порогу не підтверджено'
        if phase == 'running' and seen.get('solar_phase') == 'waiting':
            since = seen.setdefault('solar_recovery_since', tick)
            if tick-since < 120:
                phase = None
        else:
            seen.pop('solar_recovery_since', None)
        if phase and phase != seen.get('solar_phase'):
            seen['solar_phase'] = phase
            seen['solar_waiting'] = phase == 'waiting'
            if phase == 'running':
                queue('solar', '☀️ Тепловий насос 1-го поверху увімкнено в сонячному режимі. '
                      'За недостатніх сонячних умов EH призупинить роботу й повідомить вас.'
                      + (f' Пороги PV: запуск {limits[0]:g} Вт, призупинення нижче {limits[1]:g} Вт.' if limits else ''))
            else:
                queue('solar', f'⏸ Сонячне керування тепловим насосом 1-го поверху призупинено: {reason}. '
                      'Сонячний режим залишається активним; EH відновить роботу за відповідних умов '
                      'і в межах розкладу, якщо він увімкнений.'
                      + ('\n'+solar_session.summary(state['solar_running_session'], solar_session.meter(entities, now))
                         if state.get('solar_running_session') else ''))
        if phase is None:
            pending.pop('solar', None)
    for key in list(pending):
        if tick-pending[key]['at'] > 86400:
            pending.pop(key)
    ordinary = [key for key in pending if not pending[key]['urgent']]
    for key in ordinary[:-12]:
        pending.pop(key)
    plug_pending = [key for key in pending if key.startswith(('plug:', 'climate:', 'solar_summary:'))]
    for key in plug_pending[:-32]:
        pending.pop(key)


def deliver(state, telegram, chat, now, quiet=False, technical_chat=None):
    pending = state.get('household_events', {}).get('pending', {})
    changed = retire_plug_notifications(state)
    for key, item in list(pending.items()):
        diagnostic = key.startswith(('plug:', 'climate:', 'solar_summary:', 'fridge:'))
        destination = (chat if technical_chat is None else technical_chat) if diagnostic else chat
        if not destination:
            continue  # Missing monitoring configuration must not send diagnostics to family.
        if quiet and destination == chat and not (key.startswith('co:') and item['urgent']):
            continue
        if quiet and not item['urgent'] and (not diagnostic or technical_chat is None):
            continue
        telegram.send_message(destination, item['text'])
        pending.pop(key)
        changed = True
    return changed


def retire_plug_notifications(state):
    """Drop persisted relay/recovery notices; never replay retired plug actions."""
    changed = False
    for key in ('hp_recovery_notice', 'heat_pump_restart_event_id'):
        if key in state:
            state.pop(key)
            changed = True
    monitor = state.get('household_events', {})
    if monitor.get('seen', {}).pop('hp1_plug', None) is not None:
        changed = True
    pending = monitor.get('pending', {})
    for key in list(pending):
        if key.startswith('plug:'):
            pending.pop(key)
            changed = True
    queue = state.get('pending_notifications', [])
    kept = [item for item in queue if item.get('kind') != 'heat_pump_restart_restored']
    if len(kept) != len(queue):
        state['pending_notifications'] = kept
        changed = True
    return changed
