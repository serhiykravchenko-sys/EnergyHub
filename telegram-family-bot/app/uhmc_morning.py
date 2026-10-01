"""Brief morning source status; unavailable evidence is never an all-clear."""
from datetime import datetime, timedelta
from html import escape

UNKNOWN = ''
CLEAR = ''
from .events import WEATHER_HAZARDS_UK


def timestamp(value):
    result = datetime.fromisoformat(str(value))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Timezone required')
    return result


def morning_status(snapshot, now):
    """now must be in the household timezone; tolerate one hourly poll cycle."""
    try:
        if not isinstance(snapshot, dict) or snapshot.get('source_status') != 'fresh':
            return UNKNOWN
        observed = timestamp(snapshot.get('observed_at'))
        if not 0 <= (now - observed).total_seconds() <= 75 * 60:
            return UNKNOWN
        warnings = snapshot.get('warnings')
        if not isinstance(warnings, list):
            return UNKNOWN
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        active = []
        for warning in warnings:
            if not isinstance(warning, dict):
                return UNKNOWN
            begins = timestamp(warning.get('valid_from'))
            expires = timestamp(warning.get('valid_until'))
            if expires < begins:
                return UNKNOWN
            # Snapshot adapter already selects Kyiv-region warnings. Level I
            # still counts here even though it adds no battery reserve.
            if warning.get('active', True) and begins < end and expires >= now:
                severity = warning.get('severity')
                hazards = warning.get('hazards')
                if not isinstance(severity, int) or severity not in (1, 2, 3) or not isinstance(hazards, list):
                    return UNKNOWN
                label = ', '.join(WEATHER_HAZARDS_UK.get(str(h), str(h)) for h in hazards)
                marker = {1: '🟡', 2: '🟠', 3: '🔴'}[severity]
                line = f'{marker} <b>УГМЦ: рівень {severity}</b> — {escape(label or "небезпечні погодні умови")}.'
                url = str(warning.get('url') or '').strip()
                if url.startswith('https://t.me/'):
                    line += f' <a href="{escape(url, quote=True)}">Джерело</a>'
                active.append(line)
        return '\n'.join(dict.fromkeys(active)) if active else CLEAR
    except (ValueError, TypeError, OverflowError):
        return UNKNOWN
