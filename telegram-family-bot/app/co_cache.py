"""Persist last observed valid CO fields separately; never claims live safety."""
from datetime import datetime
from .report import number


def observe(state, targets, entities, now):
    cache = state.setdefault('co_last_valid', {})
    for target in targets:
        stem = target.entity.removeprefix('binary_sensor.').removesuffix('_carbon_monoxide')
        for entity in (target.entity, 'sensor.'+stem+'_co', 'sensor.'+stem+'_battery'):
            row = entities.get(entity) or {}
            value = row.get('state')
            valid = value in {'on', 'off'} if entity == target.entity else number(value) is not None and number(value) >= 0
            try:
                at = datetime.fromisoformat(row.get('last_reported') or row.get('last_updated'))
                if valid and 0 <= (now-at).total_seconds():
                    cache[entity] = dict(state=value, at=at.isoformat())
            except (TypeError, ValueError):
                pass
    selected = {t.entity.removeprefix('binary_sensor.').removesuffix('_carbon_monoxide') for t in targets}
    for entity in list(cache):
        if not any(stem in entity for stem in selected):
            cache.pop(entity, None)


def reading(cache, entity, now):
    row = cache.get(entity) or {}
    try:
        at = datetime.fromisoformat(row['at'])
        if 0 <= (now-at).total_seconds():
            return row.get('state'), at
    except (KeyError, TypeError, ValueError):
        pass
    return None, None
