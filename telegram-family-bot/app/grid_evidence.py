"""Qualified current supply evidence, independent of published schedules."""
from .report import number


def qualified(config, client, now):
    if client is None:
        return None
    def row(entity):
        return client.state(entity) or {}
    fresh = row(getattr(config, 'telemetry_freshness_entity', 'sensor.energyhub_telemetry_freshness')).get('state')
    voltage = number(row(getattr(config, 'grid_voltage_entity', 'sensor.powmr_10_2m_grid_voltage')).get('state'))
    confirmed = row('binary_sensor.energyhub_grid_confirmed')
    attrs = confirmed.get('attributes') or {}
    at = number(attrs.get('checked_at'))
    duration = number(attrs.get('confirmation_seconds'))
    if (fresh != 'fresh' or voltage is None or not 0 <= voltage <= 300
            or at is None or not 0 <= now.timestamp()-at <= 30
            or duration is None or duration < 180 or attrs.get('transition_pending') is not False):
        return None
    if confirmed.get('state') == 'on' and voltage > 180:
        return True
    if confirmed.get('state') == 'off' and voltage <= 180:
        return False
    return None
