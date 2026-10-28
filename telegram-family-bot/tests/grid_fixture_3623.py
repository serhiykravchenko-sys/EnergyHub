"""Timestamped qualified supply fixture shared by notification regressions."""
def rows(now, online=True):
    return {
        'sensor.energyhub_telemetry_freshness': {'state': 'fresh'},
        'sensor.powmr_10_2m_grid_voltage': {'state': '227' if online else '0'},
        'binary_sensor.energyhub_grid_confirmed': {'state': 'on' if online else 'off',
            'attributes': {'checked_at': now.timestamp(), 'confirmation_seconds': 180,
                           'transition_pending': False}},
    }


def qualify(client, now):
    original = client.state
    supply = rows(now)
    client.state = lambda entity: supply[entity] if entity in supply else original(entity)
    return client
