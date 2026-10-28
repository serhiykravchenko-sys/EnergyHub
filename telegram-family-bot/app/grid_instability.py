"""One unstable-supply incident and stable recovery; no current-limit writes."""
from .report import number


def observe(state, client, now):
    entity = client.state('binary_sensor.energyhub_grid_confirmed') or {}
    attrs = entity.get('attributes') or {}
    checked, last = number(attrs.get('checked_at')), number(attrs.get('last_raw_transition_at'))
    count = number(attrs.get('raw_transitions_10m'))
    if checked is None or not 0 <= now.timestamp()-checked <= 90:
        return False
    record = state.setdefault('grid_instability', {})
    if count is not None and count >= 4 and last is not None and 0 <= now.timestamp()-last <= 300:
        record.pop('stable_since', None)
        if not record.get('active'):
            record.update(active=True, started_at=now.isoformat())
            state.setdefault('pending_notifications', []).append(dict(kind='grid_unstable',
                created_at=now.isoformat(), message=(
                    '⚠️ <b>ДТЕК працює нестабільно.</b>\n'
                    'За останні 10 хв живлення неодноразово зникало й поверталося.\n'
                    '🔋 Перебої можуть переривати заряджання батареї.')))
            return True
    elif record.get('active') and entity.get('state') == 'on' and last is not None and now.timestamp()-last >= 300:
        record.update(active=False, recovered_at=now.isoformat())
        state.setdefault('pending_notifications', []).append(dict(kind='grid_stable',
            created_at=now.isoformat(), message='🟢 <b>Живлення ДТЕК стабільне вже 5 хв.</b>'))
        return True
    return False
