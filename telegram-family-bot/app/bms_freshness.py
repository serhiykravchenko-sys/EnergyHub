"""Shared-packet freshness for mapped channels of one BMS; never invent reports."""
from datetime import datetime
import math


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.timestamp() if result.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def latest_primary_report(readings, tick, required=('soc', 'current', 'voltage')):
    """Return latest real primary-field timestamp, only with valid same-BMS data.

    HA can omit writes for unchanged sensor values. An updated sibling from the
    same configured BMS packet is evidence of source activity, not a fabricated
    timestamp for the unchanged value. No new primary report means no new sample.
    """
    times = []
    for name in required:
        row = readings.get(name) or {}
        value = number(row.get('value'))
        reported = stamp(row.get('reported_at'))
        if (value is None or reported is None or reported > tick+5
                or name == 'soc' and not 0 <= value <= 100
                or name == 'voltage' and value <= 0):
            return None
        times.append(reported)
    latest = max(times) if times else None
    return latest if latest is not None and -5 <= tick-latest <= 90 else None
