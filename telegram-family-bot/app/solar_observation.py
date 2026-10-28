"""Read-only, qualified five-minute PV power for grid-event notifications."""
from datetime import datetime, timedelta
from math import isfinite
import logging
from .home_assistant import HomeAssistantError
from .report import compact_number

ENTITY = 'sensor.powmr_10_2m_total_pv_power'
WINDOW = 300
MAX_AGE = 90
FUTURE_SKEW = 2
LOGGER = logging.getLogger(__name__)


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def qualification(rows, now):
    """Step-weighted power; require start coverage and reject unknown/gap/stale."""
    start = now - timedelta(seconds=WINDOW)
    points = []
    for row in rows:
        if not isinstance(row, dict):
            return None, 'invalid_history'
        at = stamp(row.get('last_updated') or row.get('last_changed'))
        if at is None or at > now:
            return None, 'invalid_history'
        raw = row.get('state')
        try:
            value = float(raw) if not isinstance(raw, bool) else float('nan')
        except (TypeError, ValueError):
            value = float('nan')
        points.append((at, value))
    points.sort(key=lambda p: p[0])
    previous = [p for p in points if p[0] <= start]
    if not previous:
        return None, 'insufficient_coverage'
    points = [previous[-1], *[p for p in points if p[0] > start]]
    if (start-points[0][0]).total_seconds() > MAX_AGE:
        return None, 'invalid_history'
    energy = 0.0
    for i, (at, value) in enumerate(points):
        end = points[i+1][0] if i+1 < len(points) else now
        if (not isfinite(value) or not 0 <= value <= 30000
                or not 0 <= (end-at).total_seconds() <= MAX_AGE):
            return None, 'invalid_history'
        energy += value * max(0, (end-max(at, start)).total_seconds())
    return energy/WINDOW, 'ready'


def average(rows, now):
    return qualification(rows, now)[0]


def diagnose(state, reason, now):
    """Persist the latest reason; cap transition logs at one per five minutes."""
    old = state.get('solar_event_diagnostic', {})
    logged = stamp(old.get('logged_at'))
    changed = old.get('reason') != reason
    can_log = logged is None or (now-logged).total_seconds() >= 300
    if changed and can_log:
        LOGGER.info('Five-minute solar observation: %s', reason)
        logged = now
    state['solar_event_diagnostic'] = dict(reason=reason, checked_at=now.isoformat(),
        logged_at=logged.isoformat() if logged else None)


def observe(client, config, state, now, *, clock=None):
    """Sample at read completion, not the earlier monitoring-loop timestamp.

    Production supplies its wall clock. The explicit reference remains usable for
    offline replay. A two-second source clock skew is allowed, never a future
    sample timestamp. No sensor or history request is created.
    """
    failure = None
    try:
        fresh = client.state(config.telemetry_freshness_entity) or {}
        pv2 = client.state('sensor.energyhub_pv2_telemetry_freshness') or {}
        current = client.state(ENTITY) or {}
    except (HomeAssistantError, OSError):
        failure = 'read_failed'
    observed = clock() if clock is not None else now
    if observed < now:
        failure = 'clock_reversed'
    if failure is None:
        at = stamp(current.get('last_reported') or current.get('last_updated'))
        try:
            raw = current.get('state')
            watts = float(raw) if not isinstance(raw, bool) else float('nan')
        except (TypeError, ValueError):
            watts = float('nan')
        if fresh.get('state') != 'fresh':
            failure = 'inverter_not_fresh'
        elif pv2.get('state') != 'fresh':
            failure = 'pv2_not_fresh'
        elif at is None:
            failure = 'missing_report_time'
        elif (observed-at).total_seconds() < -FUTURE_SKEW:
            failure = 'future_report'
        elif (observed-at).total_seconds() > MAX_AGE:
            failure = 'stale_report'
        elif not isfinite(watts) or not 0 <= watts <= 30000:
            failure = 'invalid_power'
    if failure is not None:
        state['solar_event_samples'] = []
        diagnose(state, failure, observed)
        return observed
    rows = [r for r in state.get('solar_event_samples', [])
            if isinstance(r, dict) and stamp(r.get('last_updated')) is not None
            and 0 <= (observed-stamp(r['last_updated'])).total_seconds() <= WINDOW+MAX_AGE]
    if rows and (observed-stamp(rows[-1]['last_updated'])).total_seconds() > MAX_AGE:
        rows = []
    if not rows or (observed-stamp(rows[-1]['last_updated'])).total_seconds() >= 30:
        rows.append({'last_updated': observed.isoformat(), 'state': watts})
    state['solar_event_samples'] = rows[-15:]
    diagnose(state, qualification(rows, observed)[1], observed)
    return observed


def line(state, now):
    """Freeze observation when queued; never replace it at delayed delivery."""
    value = average(state.get('solar_event_samples', []), now)
    if value is None:
        return '☀️ Генерація за 5 хв: дані не підтверджені.'
    return f'☀️ Генерація: <b>{compact_number(value/1000)} kW</b> · середнє за 5 хв.'
