"""Persisted family diagnostics; no address changes or hardware commands."""
from datetime import datetime
from html import escape
from .message_schedule import quiet_phase

NETWORK_LINK = '<a href="http://homeassistant.local:8123/dashboard-powmr1/network">налаштуваннях EH</a>'
ENTITY = 'sensor.energyhub_hp1_connection'
GOOD = {'heat', 'cool', 'off', 'dry', 'fan_only', 'auto'}


def observe(state, entities, now):
    row = entities.get(ENTITY) or {}
    attrs = row.get('attributes') or {}
    try:
        fresh = -5 <= (now-datetime.fromisoformat(attrs['checked_at'])).total_seconds() <= 150
    except (KeyError, TypeError, ValueError):
        fresh = False
    record = state.setdefault('hp_connection_notice', {})
    previous = record.get('observed_at', 0)
    record.update(observed_at=now.timestamp(), fresh=fresh,
                  reachability=row.get('state'), attributes=attrs)
    if not fresh or (previous and now.timestamp()-previous > 150):
        record.pop('bad_since', None)
        record.pop('good_since', None)
    if not fresh:
        return
    hp = attrs.get('hp_state')
    if hp in GOOD:
        record.pop('bad_since', None)
        record.setdefault('good_since', now.timestamp())
    elif hp == 'unavailable':
        record.pop('good_since', None)
        record.setdefault('bad_since', now.timestamp())
    else:
        record.pop('bad_since', None)
        record.pop('good_since', None)


def message(record):
    attrs = record['attributes']
    lines = ['⚠️ <b>Тепловий насос 1-го поверху недоступний через HA вже годину.</b>']
    if record['reachability'] == 'unreachable':
        lines.append('Поточна IP-адреса не відповідає. Перевірте її; якщо змінилася — оновіть у '+NETWORK_LINK+'.')
    else:
        lines.append('Стан насоса через HA не підтверджено. Перевірте зв’язок у застосунку насоса.')
    return '\n'.join(lines)


def deliver(state, telegram, config, now):
    record = state.get('hp_connection_notice') or {}
    if (not getattr(config, 'house_monitor_enabled', False) or not record.get('fresh')
            or not 0 <= now.timestamp()-record.get('observed_at', 0) <= 90
            or quiet_phase(now, config, report_buffer_minutes=0) is not None):
        return False
    bad = record.get('bad_since')
    if bad is not None and now.timestamp()-bad >= 3600 and not record.get('notified'):
        started = datetime.fromtimestamp(bad, now.tzinfo)
        if ((started.date() < now.date() or quiet_phase(started, config) == 'overnight')
                and state.get('morning_delivered_date') != now.date().isoformat()):
            return False
        if not getattr(config, 'technical_chat_id', ''):
            return False
        telegram.send_message(config.technical_chat_id, message(record))
        record['notified'] = True
        return True
    good = record.get('good_since')
    if good is not None and now.timestamp()-good >= 300:
        sent = record.get('notified', False)
        if sent:
            if not getattr(config, 'technical_chat_id', ''):
                return False
            telegram.send_message(config.technical_chat_id,
                '✅ Керування тепловим насосом 1-го поверху через HA відновлено; зв’язок стабільний 5 хв.')
            record.pop('notified', None)
        return sent
    return False
