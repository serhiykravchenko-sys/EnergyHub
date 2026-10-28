"""Bounded native integration reload; no cloud login or hardware commands."""
from datetime import datetime
from .home_assistant import HomeAssistantError

LAMP = 'light.battery_beacon'
DELAYS = (0, 300, 900)


def recent_control_error(entries, now):
    for row in entries:
        name = str(row.get('name') or row.get('logger') or '')
        message = str(row.get('message') or '').lower()
        try:
            at = float(row.get('last_occurred') or row.get('timestamp') or 0)
        except (TypeError, ValueError):
            continue
        if ('battery_lamp_color_4_levels' in name and 0 <= now.timestamp()-at <= 120
                and any(w in message for w in ('network error', 'timeout', 'connection'))):
            return at
    return None


def recent_transport_error(entries, now, title):
    if not title:
        return False
    for row in entries:
        try:
            at = float(row.get('last_occurred') or row.get('timestamp') or 0)
        except (TypeError, ValueError):
            continue
        message = str(row.get('message') or '')
        error = (message+' '+str(row.get('exception') or '')).lower()
        if (0 <= now.timestamp()-at <= 120 and title in message and 'tuya' in message.lower()
                and any(word in error for word in ('timeouterror', 'connectionerror', 'clientconnector', 'sslerror'))):
            return True
    return False


def isolated_entry(registry, entries, lamp=LAMP):
    matches = [r for r in registry.get('entities', []) if r.get('entity_id') == lamp
               and not r.get('disabled_by')]
    if len(matches) != 1:
        return None
    row = matches[0]
    entry = next((e for e in entries if e.get('entry_id') == row.get('config_entry_id')
                  and e.get('domain') == 'tuya' and not e.get('disabled_by')), None)
    if not entry or not row.get('device_id'):
        return None
    devices = [d for d in registry.get('devices', [])
               if entry['entry_id'] in d.get('config_entries', [])
               or entry['entry_id'] == d.get('config_entry_id')]
    if len(devices) != 1 or devices[0].get('id') != row['device_id'] or devices[0].get('disabled_by'):
        return None
    if any(e.get('device_id') != row['device_id'] for e in registry.get('entities', [])
           if e.get('config_entry_id') == entry['entry_id']):
        return None
    return entry


def observe(state, now, registry, entries, lamp_row, *, persist, reload, control_error=False, transport_error=False):
    r = state.setdefault('beacon_recovery', {})
    tick = now.timestamp()
    continuous = 0 <= tick-r.get('last', tick) <= 90
    r['last'] = tick
    entry = isolated_entry(registry, entries)
    if not entry:
        r.pop('bad_since', None)
        r.pop('good_since', None)
        r['status'] = 'blocked' if lamp_row.get('state') not in {'on', 'off'} else 'not_isolated'
        if r['status'] == 'blocked' and not r.get('manual_notified'):
            r['pending'] = '⚠️ Beacon: автоматичне відновлення недоступне. Перевірте реєстр і стан інтеграції Tuya в HA.'
            r['manual_notified'] = True
        return
    if r.get('entry') not in (None, entry['entry_id']):
        r.clear()
        r['last'] = tick
    r['entry'] = entry['entry_id']
    if (type(r.get('attempts', 0)) is not int or not 0 <= r.get('attempts', 0) <= 3):
        r['status'] = 'manual'
        if not r.get('journal_warned'):
            r.update(journal_warned=True, pending='⚠️ Beacon: журнал відновлення некоректний. Перевірте стан у HA.')
        return
    health = entry.get('state')
    if transport_error:
        r['current_failure_transport'] = True
    reason = str(entry.get('reason') or '').lower()
    auth = any(word in reason for word in ('auth', 'token', 'login', 'credential'))
    available = lamp_row.get('state') in {'on', 'off'}
    good = health == 'loaded' and available and not control_error
    if not continuous:
        r.pop('bad_since', None)
        r.pop('good_since', None)
    if good:
        r.pop('current_failure_transport', None)
        if str(r.get('pending', '')).startswith(('⚠️', '🔄')):
            r.pop('pending', None)
        r.pop('bad_since', None)
        # A loaded entry and available entity must include feedback after reload.
        try:
            at = datetime.fromisoformat(lamp_row.get('last_reported') or lamp_row['last_updated']).timestamp()
        except (ValueError, TypeError, KeyError):
            at = 0
        if r.get('attempts') and at < r.get('attempt_at', tick):
            r.pop('good_since', None)
            return
        r.setdefault('good_since', tick)
        if r.get('incident') and tick-r['good_since'] >= 300:
            r['pending'] = '✅ Beacon: зв’язок відновлено, дані стабільні 5 хв. Втручання не потрібне.'
            r.update(incident=False, attempts=0, cooldown_until=tick+3600, status='recovered')
        else:
            r['status'] = 'healthy'
            if tick-r['good_since'] >= 300:
                r['manual_notified'] = False
        return
    r.pop('good_since', None)
    if str(r.get('pending', '')).startswith('✅'):
        r.pop('pending', None)
    transient = (r.get('current_failure_transport') is True
                 or any(word in reason for word in ('timeout', 'connect', 'network', 'ssl', 'tls')))
    retryable = (health in {'setup_retry', 'loaded'} or health == 'setup_error' and transient)
    retryable = (retryable and not auth and
                 (not available or control_error))
    if not retryable:
        if not r.get('manual_notified'):
            r['pending'] = '⚠️ Beacon: потрібна ручна перевірка Tuya в HA (авторизація або стан інтеграції).'
            r['manual_notified'] = True
        r['status'] = 'manual'
        return
    r.setdefault('bad_since', tick)
    if tick-r['bad_since'] < 180 or tick < r.get('cooldown_until', 0):
        return
    if not r.get('incident'):
        r.update(incident=True, started=tick, attempts=0, manual_notified=False)
    attempts = r.get('attempts', 0)
    if attempts >= 3:
        if tick-r.get('attempt_at', tick) >= 300 and not r.get('manual_notified'):
            r['pending'] = '⚠️ Beacon: автоматичне відновлення не допомогло. Перевірте Tuya в HA; за потреби увійдіть повторно.'
            r['manual_notified'] = True
        r['status'] = 'manual'
        return
    if tick-r['started'] < DELAYS[attempts]:
        return
    # Write the attempt BEFORE the service call. Uncertain delivery consumes it.
    r.update(attempts=attempts+1, attempt_at=tick, status='recovering')
    if attempts == 0:
        r['pending'] = '🔄 Beacon: пробуємо відновити зв’язок через перезавантаження інтеграції Tuya.'
    try:
        persist(state)
    except (OSError, ValueError):
        r['status'] = 'persistence_failed'
        return
    try:
        reload(entry['entry_id'])
    except HomeAssistantError:
        r['status'] = 'delivery_unconfirmed'


def deliver(state, telegram, chat):
    r = state.get('beacon_recovery', {})
    if not chat or not r.get('pending'):
        return False
    telegram.send_message(chat, r['pending'])
    r.pop('pending', None)
    return True
