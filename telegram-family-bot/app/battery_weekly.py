"""Weekly counter differences with coverage; no balancing-session inference."""
from datetime import datetime, timedelta
from .bms_freshness import latest_primary_report, number


def observe(state, config, snapshot, now):
    mapping = {row.label: row.entity for row in getattr(config, 'bms_entities', ())}
    readings = {}
    for field in ('soc', 'current', 'voltage'):
        row = snapshot.get(mapping.get(field)) or {}
        readings[field] = dict(value=row.get('state'), reported_at=row.get('last_reported') or row.get('last_updated'))
    tick = latest_primary_report(readings, now.timestamp())
    cycles = number((snapshot.get(mapping.get('cycles')) or {}).get('state'))
    counter_row = snapshot.get(getattr(config, 'soc_anomaly_latest_entity', '')) or {}
    jumps = number((counter_row.get('attributes') or {}).get('event_count'))
    if tick is None or cycles is None or cycles < 0 or cycles != int(cycles):
        return
    if jumps is not None and (jumps < 0 or jumps != int(jumps)):
        jumps = None
    journal = state.setdefault('battery_weekly', {'days': {}})
    last = journal.get('last')
    if last and tick <= last['tick']:
        return
    day = now.date().isoformat()
    sample = dict(tick=tick, at=now.isoformat(), cycles=int(cycles), jumps=jumps)
    entry = journal['days'].setdefault(day, dict(first=sample, last=sample, seconds=0, reset=False))
    if last:
        elapsed = now.timestamp()-datetime.fromisoformat(last['at']).timestamp()
        if 0 < elapsed <= 120:
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            entry['seconds'] += min(elapsed, (now-midnight).total_seconds())
        if cycles < last['cycles']:
            entry['cycles_reset'] = True
            entry['reset'] = True
        if jumps is not None and last['jumps'] is not None and jumps < last['jumps']:
            entry['jumps_reset'] = True
            entry['reset'] = True
    entry['last'] = sample
    journal['last'] = sample
    cutoff = (now.date()-timedelta(days=15)).isoformat()
    journal['days'] = {k:v for k,v in journal['days'].items() if k >= cutoff}


def lines(state, now):
    """Independent observed counter deltas; missing coverage is never zero."""
    if now.weekday() != 0:
        return []
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end-timedelta(days=7)
    days = (state.get('battery_weekly') or {}).get('days') or {}
    entries = [days.get((start+timedelta(days=i)).date().isoformat()) for i in range(7)]
    coverage = sum(max(0, number(e.get('seconds')) or 0) for e in entries if e)
    expected = end.timestamp()-start.timestamp()
    observed = sum(bool(e) for e in entries)
    samples = []
    for key, entry in days.items():
        if not isinstance(entry, dict):
            continue
        for name in ('first', 'last'):
            sample = entry.get(name) or {}
            try:
                at = datetime.fromisoformat(sample['at'])
                if at.tzinfo is not None and start.timestamp() <= at.timestamp() <= end.timestamp()+120:
                    samples.append((at, sample))
            except (KeyError, ValueError, TypeError):
                pass
    samples.sort(key=lambda item: item[0].timestamp())
    result = ['🔋 <b>Батарея · за останні 7 днів</b>']
    result.append(f'Дані за <b>{observed} із 7 днів</b> · покриття <b>{min(100, coverage/expected*100):.0f}%</b>.')
    for field, label in [('jumps', 'Стрибків заряду за спостереженнями'), ('cycles', 'Цикли')]:
        valid = [(at, sample) for at, sample in samples
                 if number(sample.get(field)) is not None and sample[field] >= 0
                 and sample[field] == int(sample[field])]
        reset = any(e and (e.get(field+'_reset') or
                    (e.get('reset') and 'cycles_reset' not in e and 'jumps_reset' not in e)) for e in entries)
        values = [sample[field] for _, sample in valid]
        if reset or any(b < a for a, b in zip(values, values[1:])):
            result.append(f'{label}: лічильник скинуто; різницю не підтверджено.')
        elif len(valid) >= 2 and valid[-1][0].timestamp() > valid[0][0].timestamp():
            a, b = int(values[0]), int(values[-1])
            left, right = valid[0][0].astimezone(now.tzinfo), valid[-1][0].astimezone(now.tzinfo)
            span = f'{left:%d.%m %H:%M}–{right:%d.%m %H:%M}'
            value = f'{a} → {b} (+{b-a})' if field == 'cycles' else str(b-a)
            result.append(f'{label}: <b>{value}</b> · {span}.')
        else:
            result.append(f'{label}: даних недостатньо.')
    return result
