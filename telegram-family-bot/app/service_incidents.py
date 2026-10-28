"""Persisted family service incidents; no refresh requests or control actions."""
from datetime import datetime
from .message_schedule import quiet_phase
from .log_privacy import redact

TOOLKIT_LINK = '<a href="https://toolkit.solcast.com.au/">Перевірити прогноз у кабінеті Solcast</a>'
HA_LINK = '<a href="http://homeassistant.local:8123/config/logs">Журнал HA</a>'


def kind(name, text):
    if name.startswith('custom_components.solcast_solar'):
        if '429' in text and ('try again later' in text.lower() or 'status' in text.lower()):
            return 'solcast'
        if 'all attempts failed' in text.lower():
            return 'solcast_retry'
    if name.startswith('homeassistant.components.hassio') and '/ingress/validate_session' in text:
        return 'ingress'
    return None


def source_refresh(entities, config, now):
    """Only an explicitly commissioned successful-source timestamp is authority.

    HA last_updated/last_reported and a forecast value are not source evidence.
    The configured entity's meaning must be verified for the installed version.
    """
    entity = getattr(config, 'solcast_last_success_entity', '') or 'sensor.solcast_pv_forecast_api_last_polled'
    row = entities.get(entity) or {}
    try:
        at = datetime.fromisoformat(row['state'].replace('Z', '+00:00'))
        if at.tzinfo and 0 <= (now-at).total_seconds() <= 7*86400:
            return at.timestamp()
    except (KeyError, ValueError, TypeError, AttributeError):
        pass
    return None


def observe(state, entries, now, successful_refresh=None):
    tick = now.timestamp()
    records = state.setdefault('service_incidents', {})
    rows = []
    for row in entries[:200]:
        try:
            at = float(row['timestamp'])
            if not 0 <= tick-at <= 86400:
                continue
            message = row.get('message', [])
            text = str(message[-1] if isinstance(message, list) and message else message)
            name = str(row.get('name', ''))
            category = kind(name, text)
            if category:
                rows.append((at, category, row, name, text))
        except (KeyError, ValueError, TypeError):
            continue
    for at, category, row, name, text in sorted(rows, key=lambda r: r[0]):
        if category == 'solcast_retry':
            incident = records.get('solcast') or {}
            if not incident or not 0 <= at-incident.get('last_429', at+1) <= 600:
                continue
            category = 'solcast'
        record = records.setdefault(category, {})
        if at <= record.get('resolved_at', 0):
            continue
        if category == 'ingress' and at-record.get('last', at) >= 86400:
            record.clear()
        if not record.get('active'):
            record.clear()
            record.update(active=True, first=at, last=at, notified=False)
        record['last'] = max(at, record['last'])
        if record.get('recovery_at', 0) <= at:
            record.pop('recovery_at', None)
        if kind(name, text) == 'solcast':
            record['last_429'] = max(at, record.get('last_429', 0))
        try:
            count = max(1, int(row.get('count', 1)))
        except (ValueError, TypeError):
            count = 1
        record['count'] = max(count, record.get('count', 0))
        record['component'] = name
        record['detail'] = redact(text)[:700]
        # Ingress does not expose an add-on identity. Never guess the affected app.
        if category == 'ingress':
            record['addon'] = 'unknown'
    record = records.get('solcast') or {}
    if successful_refresh is not None:
        state['solcast_last_success'] = successful_refresh
    if record.get('active') and successful_refresh is not None and record['last'] < successful_refresh <= tick:
        record.setdefault('recovery_at', tick)
        if tick-record['recovery_at'] >= 3600:
            record.update(active=False, resolved_at=successful_refresh,
                          recovery_pending=record.get('notified', False))


def forecast_stamp(state, now):
    try:
        at = datetime.fromtimestamp(float(state['solcast_last_success']), now.tzinfo)
        if at <= now:
            return at.strftime('%d.%m о %H:%M')
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return None


def warning_active(state):
    record = state.get('service_incidents', {}).get('solcast', {})
    return record.get('active') and not record.get('recovery_at')


def deliver(state, telegram, chat, now, config):
    if not chat or quiet_phase(now, config, report_buffer_minutes=0) is not None:
        return False
    changed = False
    tick = now.timestamp()
    for category, record in state.get('service_incidents', {}).items():
        if record.get('recovery_pending'):
            stamp = forecast_stamp(state, now)
            telegram.send_message(chat, '✅ <b>Прогноз генерації Solcast знову оновлюється.</b>'
                                 + (f'\n☀️ Нові дані отримано <b>{stamp}</b>.' if stamp else ''))
            record['recovery_pending'] = False
            changed = True
        if not record.get('active'):
            continue
        message = None
        if category == 'solcast':
            if record.get('recovery_at'):
                continue
            first_due = not record.get('notified') and tick-record.get('first', tick) >= 3600
            repeat_due = record.get('notified') and tick-record.get('delivered_at', tick) >= 86400
            if first_due or repeat_due:
                stamp = forecast_stamp(state, now)
                title = 'Прогноз генерації Solcast досі не оновлюється.' if repeat_due else 'Прогноз генерації Solcast тимчасово не оновлюється.'
                cached = f'від <b>{stamp}</b>' if stamp else '— час останнього успішного оновлення не підтверджено'
                message = (f'⚠️ <b>{title}</b>\n☀️ Використовуємо останній збережений прогноз {cached}.\n'
                           'ℹ️ Змінювати налаштування чи перезапускати HA не потрібно.\n'+TOOLKIT_LINK)
        elif category == 'ingress' and 0 <= tick-record['last'] <= 600 and (record.get('count', 0) >= 3 or record['last']-record['first'] >= 300):
            if not record.get('notified'):
                message = ('⚠️ <b>HA повторно відхиляє сесію сторінки застосунку.</b>\n'
                    'Це помилка входу через HA (ingress), не Solcast. Відкрийте сторінку заново; '
                    'якщо не допоможе — повторно увійдіть у HA. Застосунок не визначено.\n'+HA_LINK)
        if message:
            telegram.send_message(chat, message)
            if record.get('notified'):
                record['followup_sent'] = True
            record.update(notified=True, delivered_at=tick)
            changed = True
    return changed
