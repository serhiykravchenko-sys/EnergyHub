"""Read-only, explicit device inventory; one HA snapshot per observation."""
from dataclasses import dataclass
from html import escape
from datetime import datetime
from .bms_freshness import latest_primary_report, number

DEFAULT_DEVICES = ('First-floor heat pump|climate.first_floor_heat_pump;'
                   'Beacon lamp|light.battery_beacon')


@dataclass(frozen=True)
class DeviceTarget:
    label: str
    entity: str
    parent: str = ''

    @property
    def key(self):
        return 'device:' + self.entity


def parse_targets(specification):
    targets = []
    for item in str(specification or '').split(';'):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split('|')]
        if len(parts) not in (2, 3) or not parts[0] or '.' not in parts[1]:
            raise ValueError('Device inventory entries require label|entity[|parent_entity]')
        targets.append(DeviceTarget(*parts))
    if len({item.entity for item in targets}) != len(targets):
        raise ValueError('Duplicate device availability entities')
    if len(targets) > 100 or any(item.parent == item.entity for item in targets):
        raise ValueError('Device inventory must contain at most 100 targets without self parents')
    return tuple(targets)


def targets_for(config):
    targets = {item.entity: item for item in getattr(config, 'monitored_devices', ())}
    for sensor in getattr(config, 'co2_sensors', ()):
        targets.setdefault(sensor.entity, sensor)
    for sensor in getattr(config, 'environment_sensors', ()):
        targets.setdefault(sensor.temperature_entity, DeviceTarget(sensor.label, sensor.temperature_entity))
    for metric in getattr(config, 'bms_entities', ()):
        if metric.label == 'soc':
            targets.setdefault(metric.entity, DeviceTarget('BMS telemetry', metric.entity))
    return tuple(t for t in targets.values() if not t.entity.startswith('switch.') and not t.parent.endswith('zigbee2mqtt_bridge_connection_state') and not t.entity.endswith('_carbon_monoxide'))


def available(entity):
    return bool(entity) and str(entity.get('state') or '').lower() not in (
        '', 'unknown', 'unavailable', 'none', 'null')


def observe_snapshot(config, state, entities, now):
    health = {}
    inventory = []
    labels = state.setdefault('data_source_labels', {})
    for target in targets_for(config):
        parent_ok = not target.parent or available(entities.get(target.parent))
        good = available(entities.get(target.entity)) if parent_ok else None
        if any(row.label == 'soc' and row.entity == target.entity for row in getattr(config, 'bms_entities', ())):
            mapping = {row.label: row.entity for row in config.bms_entities
                       if row.label in ('soc', 'current', 'voltage')}
            readings = {}
            for field, entity in mapping.items():
                row = entities.get(entity) or {}
                readings[field] = dict(value=number(row.get('state')),
                    reported_at=row.get('last_reported') or row.get('last_updated'))
            good = good and latest_primary_report(readings, now.timestamp(), tuple(mapping)) is not None
        health[target.key] = good
        labels[target.key] = target.label
        inventory.append(dict(label=target.label, entity=target.entity, available=good))
    state['device_inventory_snapshot'] = dict(timestamp=now.isoformat(), devices=inventory)
    return health


def morning_lines(state, now):
    snapshot = state.get('device_inventory_snapshot') or {}
    try:
        age = (now - datetime.fromisoformat(snapshot['timestamp'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        return ['📡 Пристрої: актуальна перевірка недоступна.']
    if not 0 <= age <= 90:
        return ['📡 Пристрої: актуальна перевірка недоступна.']
    rows = snapshot['devices']
    good = sum(row['available'] is True for row in rows)
    bad = [escape(row['label']) for row in rows if row['available'] is False]
    masked = sum(row['available'] is None for row in rows)
    result = [f'📡 Пристрої: доступні {good}/{len(rows)} за даними HA.']
    if bad:
        result.append('⚠️ Недоступні: ' + ', '.join(bad))
    if masked:
        result.append(f'📡 Ще {masked}: стан не підтверджено через недоступне джерело.')
    return result
