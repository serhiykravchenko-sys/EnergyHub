"""Persist observed grid-use intervals; never manufacture missing history."""
from datetime import datetime
from math import isfinite
from .events import format_duration

COUNTERS = ('sensor.energyhub_grid_import_night_total_estimated',
            'sensor.energyhub_grid_import_normal_total_estimated')


def pause(state):
    episode = state.get('grid_use_episode')
    if isinstance(episode, dict):
        episode['complete'] = False
        episode['interrupted'] = True
        episode['data_gap'] = True
        episode['monitoring_gap'] = True
        episode['recovery_checked'] = False


def totals(client, now):
    values = []
    for key in COUNTERS:
        row = client.state(key) or {}
        if (row.get('attributes') or {}).get('unit_of_measurement') != 'kWh':
            return None
        try:
            value = float(row.get('state'))
            stamp = datetime.fromisoformat(row.get('last_reported') or row.get('last_updated'))
            # Recorder and MQTT omit unchanged totals. Producer freshness is
            # checked separately; an inactive tariff may stay unchanged all day.
            if not isfinite(value) or value < 0 or (now-stamp).total_seconds() < -5:
                return None
        except (ValueError, TypeError):
            return None
        values.append(value)
    return values


def begin(state, client, now, *, started_at=None, baseline=None):
    if isinstance(state.get('grid_use_episode'), dict):
        return
    counters = baseline.get('counters') if baseline is not None else totals(client, now)
    sampled_at = baseline.get('sampled_at') if baseline is not None else now.isoformat()
    state['grid_use_episode'] = dict(started_at=started_at.isoformat() if started_at else None,
        last_at=sampled_at, last_counters=counters, kwh=0.0,
        complete=started_at is not None and counters is not None, interrupted=False,
        data_gap=False, grid_outage=False, baseline_counters=counters,
        monitoring_gap=False, source_gap=False, counter_reset=False)


def history_continuous(client, start, end, freshness_entity, episode=None):
    """Validate change-only counter history and producer health across a gap."""
    from .home_assistant import HomeAssistantError
    if not freshness_entity or not hasattr(client, 'import_history'):
        return False
    try:
        history = client.import_history(start, end, (*COUNTERS, freshness_entity))
        if not isinstance(history, list):
            return False
        grouped = {}
        for rows in history:
            if not isinstance(rows, list):
                return False
            for row in rows:
                grouped.setdefault(row['entity_id'], []).append(row)
        recovered_baseline = []
        producer_continuous = True
        for entity in (*COUNTERS, freshness_entity):
            rows = grouped.get(entity, [])
            if not rows:
                return False
            cursor = start
            previous = None
            baseline = None
            for row in rows:
                stamp = datetime.fromisoformat(row.get('last_reported') or row['last_updated'])
                if stamp > end or stamp < cursor and stamp > start:
                    return False
                if entity == freshness_entity:
                    if row.get('state') != 'fresh':
                        producer_continuous = False
                else:
                    value = float(row['state'])
                    if (row.get('attributes') or {}).get('unit_of_measurement') != 'kWh':
                        return False
                    if previous is not None and value < previous:
                        if episode is not None:
                            episode['counter_reset'] = True
                        return False
                    if not isfinite(value) or value < 0:
                        return False
                    if stamp <= start:
                        baseline = value
                    previous = value
                cursor = max(cursor, stamp)
            # A first value after the start cannot establish a start baseline.
            first = datetime.fromisoformat(rows[0].get('last_reported') or rows[0]['last_updated'])
            if first > start:
                return False
            if entity != freshness_entity:
                recovered_baseline.append(baseline)
        if episode is not None and episode.get('baseline_counters') is None:
            episode['baseline_counters'] = recovered_baseline
        return producer_continuous
    except (HomeAssistantError, ValueError, TypeError, KeyError, OSError):
        return False


def observe(state, client, now, *, fresh, grid_online, freshness_entity=None):
    episode = state.get('grid_use_episode')
    if not isinstance(episode, dict):
        return
    counters = totals(client, now) if fresh else None
    try:
        gap = (now-datetime.fromisoformat(episode['last_at'])).total_seconds()
    except (ValueError, TypeError, KeyError):
        gap = -1
    previous = episode.get('last_counters')
    try:
        if previous is not None and (
                (len(previous) != 2 or not all(isfinite(float(value)) and float(value) >= 0 for value in previous))):
            raise ValueError('Invalid saved counters')
        if previous is not None:
            previous = [float(value) for value in previous]
    except (ValueError, TypeError):
        episode['complete'] = False
        episode['counter_reset'] = True
        previous = None
    if not 0 <= gap <= 90 or counters is None or previous is None:
        episode['complete'] = False
        episode['data_gap'] = True
        episode['monitoring_gap'] = True
        if gap > 90:
            episode['recovery_checked'] = False
        if not fresh or counters is None:
            episode['source_gap'] = True
    elif any(right < left for left, right in zip(previous, counters)):
        episode['complete'] = False
        episode['counter_reset'] = True
    # There is no separate incremental energy accumulator. The dashboard's
    # lifetime counters and the original start baseline are the sole authority.
    if not fresh or not grid_online:
        episode['interrupted'] = True
    if fresh and grid_online is False:
        episode['grid_outage'] = True
    if (counters is not None and episode.get('started_at')
            and not episode.get('recovery_checked')
            and (episode.get('monitoring_gap') or episode.get('baseline_counters') is None)):
        episode['recovery_checked'] = True
        try:
            start = datetime.fromisoformat(episode['started_at'])
            if history_continuous(client, start, now, freshness_entity, episode) and not episode.get('source_gap'):
                episode.update(complete=True, monitoring_gap=False, data_gap=False)
        except (ValueError, TypeError):
            episode['complete'] = False
    baseline = episode.get('baseline_counters')
    if counters is not None and baseline is not None:
        try:
            valid = (len(baseline) == 2 and all(isfinite(float(value)) and float(value) >= 0 for value in baseline))
            if not valid or any(right < float(left) for left, right in zip(baseline, counters)):
                episode['counter_reset'] = True
            if valid and not episode.get('counter_reset'):
                episode['kwh'] = sum(right-float(left) for left, right in zip(baseline, counters))
                episode['estimate_available'] = True
        except (ValueError, TypeError, KeyError):
            episode['complete'] = False
            episode['estimate_available'] = False
    if episode.get('counter_reset'):
        episode['complete'] = False
        episode['estimate_available'] = False
    episode['last_at'] = now.isoformat()
    episode['last_counters'] = counters


def finish(state, now, *, snapshot=None):
    episode = state.pop('grid_use_episode', None)
    if snapshot is not None:
        episode = snapshot
    if not isinstance(episode, dict):
        return ['🔌 Початок використання ДТЕК та імпорт за цей період невідомі.'], {}
    lines = []
    interval_known = False
    try:
        started = datetime.fromisoformat(episode.get('started_at'))
        duration = (now-started).total_seconds()
        if duration < 0:
            raise ValueError('Invalid interval')
        interval_known = True
        clock = started.strftime('%H:%M') if started.date() == now.date() else started.strftime('%d.%m %H:%M')
        prefix = 'Період стратегії з допомогою ДТЕК'
        lines.append(f'🔌 {prefix}: {clock}–{now:%H:%M} · {format_duration(duration)}.')
    except (ValueError, TypeError):
        lines.append('🔌 Початок використання ДТЕК невідомий.')
    try:
        energy_valid = isfinite(float(episode.get('kwh'))) and float(episode['kwh']) >= 0
    except (TypeError, ValueError):
        energy_valid = False
    if episode.get('complete') is True and energy_valid and interval_known:
        energy = f"{float(episode['kwh']):.2f}".replace('.', ',')
        lines.append(f'⚡ За цей період імпортовано ≈ {energy} кВт·год.')
    elif episode.get('estimate_available') and energy_valid and interval_known:
        energy = f"{float(episode['kwh']):.2f}".replace('.', ',')
        lines.append(f'⚡ За доступними лічильниками ≈ {energy} кВт·год — неповна оцінка: є прогалини в даних.')
    else:
        lines.append('⚡ Імпорт за весь період невідомий: неповні дані.')
    return lines, episode
