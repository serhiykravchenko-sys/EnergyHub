"""Bounded, acknowledged technical notices from HA's structured error buffer."""
import hashlib
import re
from html import escape
from .log_privacy import redact


def maintenance_warning(name, text):
    return ('xiaomi_miot' in text and name in {'homeassistant.helpers.frame', 'homeassistant.const'}
            and any(value in text for value in ('wrong domain', 'deprecated constant', 'will be removed', 'stop working')))


def classify(name, text):
    """Known diagnostic churn is summarized; functional incidents have owners."""
    from .service_incidents import kind
    if maintenance_warning(name, text):
        return 'maintenance', text
    if kind(name, text) in {'solcast', 'ingress'}:
        return 'digest', text
    if name.startswith('custom_components.hisense_aircon') and (
            'Device connection failed' in text or 'Ignoring unrecognized t_fan_speed' in text):
        return 'digest', text
    if name == 'custom_components.xiaomi_miot.core.xiaomi_cloud' and 'timeout' in text.lower():
        return 'digest', text
    if name == 'pychromecast.socket_client' and 'Failed to connect to service' in text:
        return 'digest', text
    if name == 'homeassistant.components.automation.battery_lamp_color_4_levels':
        return 'beacon', 'Не вдалося змінити колір маячка EH; індикація може бути застарілою'
    return 'actionable', re.sub(r'packed in t_control_value=\d+', 'packed in t_control_value=<value>', text)


def observe(state, entries, now, boot=None):
    tick = now.timestamp()
    monitor = state.setdefault('system_log_monitor', {'seen': {}, 'pending': []})
    if monitor.get('schema') != 2:
        monitor.update(schema=2, pending=[])
    monitor['pending'] = [item for item in monitor['pending'] if 0 <= tick-item['at'] <= 86400]
    monitor['pending'] = [item for item in monitor['pending'] if item.get('level') != 'WARNING' or not any(
        maintenance_warning(name, item.get('message', ''))
        for name in ('homeassistant.helpers.frame', 'homeassistant.const'))]
    # Retire queued generic wrappers now owned by family service incidents.
    from .service_incidents import kind
    monitor['pending'] = [item for item in monitor['pending']
        if not (kind('homeassistant.components.hassio', item.get('message', '')) == 'ingress'
                or ('custom_components.solcast_solar' in item.get('message', '')
                    and kind('custom_components.solcast_solar', item.get('message', '')) == 'solcast')
                or ('custom_components.solcast_solar' in item.get('message', '')
                    and 'all attempts failed' in item.get('message', '')
                    and state.get('service_incidents', {}).get('solcast', {}).get('active')))]
    if boot in {'unknown', 'unavailable', ''}:
        boot = None
    if boot and monitor.get('boot') != boot:
        monitor['boot'] = boot
        monitor['grace_until'] = tick+300
        monitor['pending'] = []
    grace = tick < monitor.get('grace_until', 0)
    for row in entries[:200]:
        if not isinstance(row, dict):
            continue
        level = str(row.get('level', '')).upper()
        if level not in {'WARNING', 'ERROR', 'CRITICAL'}:
            continue
        try:
            stamp = float(row['timestamp'])
            count = max(1, int(row.get('count', 1)))
            if not 0 <= tick-stamp <= 86400:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        message = row.get('message', [])
        text = str(message[-1] if isinstance(message, list) and message else message)
        name = str(row.get('name', 'unknown'))
        category, normalized = classify(name, text)
        if category == 'maintenance' and level == 'WARNING':
            monitor['xiaomi_maintenance_at'] = stamp
            continue
        from .service_incidents import kind
        if kind(name, text) == 'solcast_retry' and state.get('service_incidents', {}).get('solcast', {}).get('active'):
            category = 'digest'
        if category == 'digest':
            continue
        identity = hashlib.sha256((name+normalized).encode()).hexdigest()
        previous = monitor['seen'].get(identity, {})
        # Severity can change without a new timestamp/count. An unacknowledged
        # entry suppressed by startup grace (or cleared on boot) must be eligible
        # again; reading it is not delivery acknowledgement.
        version = [stamp, count, level]
        if previous.get('version') == version and (
                (previous.get('notified_at') is not None
                 and previous.get('delivered_level') == level)
                or any(item['id'] == identity for item in monitor['pending'])):
            continue
        monitor['seen'][identity] = {**previous, 'version': version, 'at': tick, 'level': level}
        # Ignore a first transient during restart; repeated failures and critical
        # entries remain actionable. Summaries still include suppressed entries.
        if grace and level != 'CRITICAL' and count < 3:
            continue
        if level == 'WARNING' and count < 3:
            continue
        if category == 'beacon' and count < 3:
            continue
        escalating = level == 'CRITICAL' and previous.get('delivered_level') != 'CRITICAL'
        if not escalating and tick-previous.get('notified_at', -86400) < 86400:
            monitor['seen'][identity]['notified_at'] = previous['notified_at']
            continue
        pending = monitor['pending']
        pending[:] = [item for item in pending if item['id'] != identity]
        pending.append(dict(id=identity, at=tick, level=level, message=
            f'⚠️ <b>Журнал HA потребує уваги</b>\n{escape(level)} · '
            f'<code>{escape(redact(name)[:100])}</code>: {escape(redact(normalized)[:350])} (×{count})'))
        monitor['pending'] = pending[-8:]
    monitor['seen'] = dict(sorted(monitor['seen'].items(), key=lambda item: item[1]['at'])[-200:])


def deliver(state, telegram, chat, now):
    monitor = state.get('system_log_monitor', {})
    pending = monitor.get('pending', [])
    # The read path may be unavailable for hours. Enforce expiry here as well,
    # including during quiet hours, before sending persisted queued evidence.
    kept = [item for item in pending if 0 <= now.timestamp()-item['at'] <= 86400]
    changed = len(kept) != len(pending)
    pending[:] = kept
    if not chat or now.hour >= 23 or now.hour < 8:
        return changed
    if not pending:
        return changed
    message = '\n\n'.join(item['message'] for item in pending[:4])
    telegram.send_message(chat, message)
    for item in pending[:4]:
        if item['id'] in monitor.get('seen', {}):
            monitor['seen'][item['id']]['notified_at'] = now.timestamp()
            monitor['seen'][item['id']]['delivered_level'] = item.get('level')
    del pending[:4]
    return True
