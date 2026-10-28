"""Persisted ventilation episodes; diagnostics only, never appliance control."""
from datetime import datetime
from html import escape
import math


ADVISORY_PPM = 1200
URGENT_PPM = 2000


def current_reading(target, entities, now):
    """Return a fresh valid reading, never a cached or offline-parent value."""
    row = entities.get(target.entity) or {}
    try:
        value = float(row.get('state'))
        reported = datetime.fromisoformat(str(row.get('last_reported') or row.get('last_updated'))).timestamp()
        if (math.isfinite(value) and 400 <= value <= 5000
                and -5 <= now.timestamp()-reported <= 180
                and (not target.parent or entities.get(target.parent, {}).get('state') == 'on')):
            return value
    except (TypeError, ValueError):
        pass
    return None


def history_maxima(targets, history, now):
    """Maximum of valid recorded samples in the exact preceding24hours."""
    selected = {target.entity for target in targets}
    maxima = {}
    for rows in history if isinstance(history, list) else []:
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or row.get('entity_id') not in selected:
                continue
            try:
                ppm = float(row.get('state'))
                observed = datetime.fromisoformat(str(row.get('last_updated') or row.get('last_changed')))
                if observed.tzinfo is None:
                    continue
                at = observed.timestamp()
                if math.isfinite(ppm) and 400 <= ppm <= 5000 and 0 <= now.timestamp()-at <= 86400:
                    key = row['entity_id']
                    maxima[key] = max(maxima.get(key, ppm), ppm)
            except (ValueError, TypeError):
                continue
    return maxima


def morning_lines(targets, entities, now, maxima=None):
    if not targets:
        return []
    readings = []
    for target in targets:
        value = current_reading(target, entities, now)
        reading = f'{round(value)} ppm' if value is not None else 'дані недоступні'
        maximum = (maxima or {}).get(target.entity)
        if maximum is not None:
            maximum = max(maximum, value) if value is not None else maximum
        reading += ' · макс. за 24 год: ' + (f'{round(maximum)} ppm' if maximum is not None else 'дані недоступні')
        if len(targets) > 1:
            reading = f'{escape(target.label)} — {reading}'
        readings.append(reading)
    return ['🌿 CO₂ — вуглекислий газ: ' + '; '.join(readings)]


def observe(state, targets, entities, now):
    tick = now.timestamp()
    records = state.setdefault('co2_monitor', {})
    selected = {target.entity for target in targets}
    for key in list(records):
        if key not in selected:
            del records[key]
    for target in targets:
        record = records.setdefault(target.entity, dict(level=0, delivered=0))
        previous = record.get('observed_at')
        record['observed_at'] = tick
        record['label'] = target.label
        value = current_reading(target, entities, now)
        valid = value is not None
        gap = previous is None or not 0 <= tick-previous <= 90
        if not valid or gap:
            for key in ('advisory_since', 'urgent_since', 'clear_since'):
                record.pop(key, None)
        record['valid'] = valid
        if not valid:
            record.pop('pending', None)
            continue
        record['ppm'] = value
        for key, active in (('advisory_since', value >= ADVISORY_PPM),
                            ('urgent_since', value >= URGENT_PPM), ('clear_since', value < 1000)):
            if active:
                record.setdefault(key, tick)
            else:
                record.pop(key, None)
        level = record['level']
        qualified = 0
        if tick-record.get('urgent_since', tick) >= 180:
            qualified = 2
            level = 2
        elif tick-record.get('advisory_since', tick) >= 600:
            qualified = 1
            level = max(level, 1)
        cleared = tick-record.get('clear_since', tick) >= 300
        if cleared:
            level = 0
        record['level'] = level
        delivered = record['delivered']
        if qualified > delivered:
            record['pending'] = qualified
        elif cleared and level == 0 and delivered > 0:
            record['pending'] = 0
        else:
            record.pop('pending', None)


def deliver(state, telegram, chat_id, now, quiet=False):
    changed = False
    for record in state.get('co2_monitor', {}).values():
        if 'pending' not in record or not record.get('valid'):
            continue
        if not 0 <= now.timestamp()-record.get('observed_at', 0) <= 90:
            continue
        level = record['pending']
        if quiet and level != 2:
            continue
        label = escape(record['label'])
        ppm = round(record['ppm'])
        if level == 2:
            text = f'⚠️ <b>Високий CO₂: {label} — {ppm} ppm.</b> Будь ласка, провітріть кімнату зараз.'
        elif level == 1:
            text = f'🌬️ Підвищений CO₂: {label} — {ppm} ppm. Прохання провітрити кімнату, коли вам зручно.'
        else:
            text = f'✅ CO₂ знизився: {label} — {ppm} ppm. Нижче 1000 ppm протягом 5 хв.'
        telegram.send_message(chat_id, text)
        record['delivered'] = level
        record.pop('pending', None)
        changed = True
    return changed
