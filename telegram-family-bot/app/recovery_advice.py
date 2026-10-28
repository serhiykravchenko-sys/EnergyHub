"""Bounded manual recovery advice; no Supervisor or hardware control."""


def observe(state, entities, now):
    tick = now.timestamp()
    record = state.setdefault('host_recovery_advice', {})
    boot = (entities.get('input_text.energyhub_load_bridge_session') or {}).get('state')
    if boot in {'unknown', 'unavailable', ''}:
        boot = None
    if boot and boot != record.get('boot'):
        record.update(boot=boot, grace_until=tick+300, bad_since=None, pending=None)
    gap = tick-record.get('last_at', tick)
    record['last_at'] = tick
    fresh = (entities.get('sensor.energyhub_telemetry_freshness') or {}).get('state')
    zigbee = (entities.get('binary_sensor.zigbee2mqtt_bridge_connection_state') or {}).get('state')
    failed = fresh in {'stale', 'unavailable', 'unknown'} and zigbee in {'off', 'unavailable', 'unknown'}
    if not failed or not 0 <= gap <= 90 or tick < record.get('grace_until', 0):
        record.update(bad_since=None, pending=None)
        return
    if record.get('bad_since') is None:
        record['bad_since'] = tick
    if tick-record['bad_since'] >= 600 and tick-record.get('notified_at', -86400) >= 86400:
        record['pending'] = ('⚠️ Інвертор і Zigbee недоступні понад 10 хв. '
            'Перевірте USB-пристрої та журнал Host у HA. Якщо підтверджено збій USB, '
            'може знадобитися перезавантаження Raspberry Pi (ha host reboot). '
            'Автоматичного перезавантаження немає. Узгодьте відновлення з EH; '
            'уникайте 23:40–00:10, 04:45–05:15 та активних команд.')


def deliver(state, telegram, chat, now):
    record = state.get('host_recovery_advice', {})
    message = record.get('pending')
    if not message:
        return False
    telegram.send_message(chat, message)
    record['pending'] = None
    record['notified_at'] = now.timestamp()
    return True
