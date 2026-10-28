"""Bounded BMS evidence capture, independent of the hardware control boundary."""
import json
import math
import os
import hashlib
from .bms_freshness import latest_primary_report
from datetime import datetime
from pathlib import Path


PRE_SECONDS = 1800
POST_SECONDS = 900
MAX_SAMPLES = 180
MAX_EVENTS = 20
MAX_GAP = 90


def parse_mapping(specification):
    from .house_monitor import parse_targets
    targets = parse_targets(specification)
    fields = {'soc', 'current', 'voltage', 'power', 'temperature', 'cells',
              'health', 'capacity', 'cycles', 'problem', 'charging', 'energy'}
    names = {row.label for row in targets}
    if (len(names) != len(targets) or names-fields or any(row.parent for row in targets)
            or (targets and not {'soc', 'current', 'voltage'} <= names)):
        raise ValueError('BMS mapping requires unique supported fields including soc, current, voltage')
    return targets


def stamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError):
        return None


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


class BmsEvidence:
    def __init__(self, path):
        self.path = Path(path)
        self.data = dict(schema=1, samples=[], events=[], totals=dict(charge_ah=0., discharge_ah=0.,
                         charge_wh=0., discharge_wh=0., observed_seconds=0., gaps=0), baseline=None)
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(loaded, dict) or loaded.get('schema') != 1:
                raise ValueError('Unsupported BMS evidence schema; preserve existing file')
            if (not isinstance(loaded.get('samples'), list) or not isinstance(loaded.get('events'), list)
                    or not isinstance(loaded.get('totals'), dict)
                    or any(number(loaded['totals'].get(k)) is None for k in self.data['totals'])):
                raise ValueError('Invalid BMS evidence file; preserve existing file')
            for item in loaded['events']:
                if isinstance(item, dict) and item.get('archive'):
                    name = str(item['archive'])
                    if Path(name).name != name or not name.endswith('.json'):
                        raise ValueError('Invalid BMS archive path; preserve existing file')
                    archived = json.loads((self.archive_directory / name).read_text(encoding='utf-8'))
                    if not isinstance(archived, dict) or archived.get('id') != item.get('id'):
                        raise ValueError('BMS archive identity mismatch; preserve existing file')
                    item.update(archived)
            for row in loaded['samples']:
                if not isinstance(row, dict) or stamp(row.get('timestamp')) is None:
                    raise ValueError('Invalid BMS sample; preserve existing file')
            for event in loaded['events']:
                if (not isinstance(event, dict) or not event.get('id') or not event.get('samples')
                        or number(event.get('until')) is None or 'complete' not in event):
                    raise ValueError('Invalid BMS event; preserve existing file')
            self.data = loaded
            self.data['samples'] = self.data['samples'][-MAX_SAMPLES:]
            self.data['events'] = self.data['events'][-MAX_EVENTS:]
            if self.data.get('baseline') is not None:
                self.data['totals']['gaps'] += 1
            # A restart is a coverage gap, never proof of continued charging.
            self.data['baseline'] = None
            self.data['soc_baseline'] = None

    def pause(self):
        if self.data.get('baseline') is not None:
            self.data['totals']['gaps'] += 1
        self.data['baseline'] = None
        self.data['soc_baseline'] = None

    @property
    def archive_directory(self):
        return self.path.with_suffix('.events')

    @staticmethod
    def _write(path, data):
        temporary = path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = dict(self.data, events=[])
        retained = set()
        for event in self.data['events']:
            if not event['complete']:
                document['events'].append(event)
                continue
            # Completed captures are written once, not rewritten every poll.
            name = hashlib.sha256(event['id'].encode()).hexdigest()+'.json'
            self.archive_directory.mkdir(parents=True, exist_ok=True)
            path = self.archive_directory / name
            if not path.exists():
                self._write(path, event)
            retained.add(name)
            document['events'].append(dict(id=event['id'], archive=name))
        self._write(self.path, document)
        if self.archive_directory.exists():
            for path in self.archive_directory.glob('*.json'):
                if (len(path.stem) == 64 and all(c in '0123456789abcdef' for c in path.stem)
                        and path.name not in retained):
                    path.unlink()

    def observe(self, entities, mapping, anomaly_entity, now):
        tick = now.timestamp()
        readings = {}
        for name, entity_id in mapping.items():
            row = entities.get(entity_id) or {}
            attributes = row.get('attributes') or {}
            # Keep only diagnostic attributes, never tokens or arbitrary HA state.
            readings[name] = dict(value=number(row.get('state')),
                                  state=row.get('state'),
                                  unit=attributes.get('unit_of_measurement'),
                                  reported_at=row.get('last_reported') or row.get('last_updated'))
            if name == 'cells':
                readings[name]['cell_voltages'] = [number(x) for x in attributes.get('cell_voltages', [])][:32]
            if name == 'temperature':
                readings[name]['temp_values'] = [number(x) for x in attributes.get('temp_values', [])][:16]
            if name == 'current':
                readings[name]['balance_current'] = number(attributes.get('balance_current'))
            if name == 'problem':
                readings[name]['problem_code'] = attributes.get('problem_code')
        sample = dict(timestamp=now.isoformat(), readings=readings)
        samples = self.data['samples']
        samples.append(sample)
        self.data['samples'] = [row for row in samples if (stamp(row['timestamp']) or 0) >= tick-PRE_SECONDS][-MAX_SAMPLES:]
        self._integrate(sample, tick)
        # BMS-origin jumps and EH-origin jumps both capture independently.
        soc = readings.get('soc', {})
        previous = self.data.get('soc_baseline')
        reported = latest_primary_report(readings, tick)
        fresh = reported is not None
        valid_soc = soc.get('value') is not None and 0 <= soc['value'] <= 100 and fresh
        triggers = []
        if valid_soc:
            if previous and 0 < reported-previous['reported'] <= 300 and abs(soc['value']-previous['value']) >= 5:
                triggers.append(dict(id=f"bms:{reported}:{previous['value']}:{soc['value']}",
                                     source='bms', previous_soc=previous['value'], current_soc=soc['value']))
            self.data['soc_baseline'] = dict(value=soc['value'], reported=reported)
        else:
            self.data['soc_baseline'] = None
        event = (entities.get(anomaly_entity, {}).get('attributes') or {}).get('latest_event') or {}
        event_time = stamp(event.get('timestamp'))
        if event_time is not None and -5 <= tick-event_time <= POST_SECONDS:
            event_id = 'inverter:' + str(event.get('timestamp'))
            triggers.append(dict(id=event_id, source='inverter', inverter_event=event))
        existing = {event['id'] for event in self.data['events']}
        added = False
        for trigger in triggers:
            if trigger['id'] in existing:
                continue
            added = True
            existing.add(trigger['id'])
            self.data['events'].append(dict(trigger, captured_at=now.isoformat(),
                                            until=tick+POST_SECONDS, complete=False,
                                            samples=list(self.data['samples']), totals=dict(self.data['totals'])))
        for event in self.data['events']:
            if event['complete']:
                continue
            if event['samples'][-1]['timestamp'] != sample['timestamp']:
                event['samples'].append(sample)
            event['samples'] = event['samples'][-MAX_SAMPLES:]
            if tick >= event['until']:
                event['complete'] = True
                event['finished_at'] = now.isoformat()
                event['totals_after'] = dict(self.data['totals'])
        self.data['events'] = self.data['events'][-MAX_EVENTS:]
        self.data['updated_at'] = now.isoformat()
        self.save()
        return added

    def _integrate(self, sample, tick):
        readings = sample['readings']
        current = readings.get('current', {})
        voltage = readings.get('voltage', {})
        reported = latest_primary_report(readings, tick, ('current', 'voltage'))
        valid = reported is not None
        previous = self.data.get('baseline')
        totals = self.data['totals']
        if not valid:
            if previous is not None:
                totals['gaps'] += 1
            self.data['baseline'] = None
            return
        if previous and reported == previous['reported']:
            return  # A repeated HA reading must never become another energy interval.
        if previous:
            elapsed = reported-previous['reported']
            if 0 < elapsed <= MAX_GAP:
                # Split sign crossings to avoid cancellation between charge/discharge.
                left, right = previous['current'], current['value']
                pieces = [(elapsed, left, right)]
                if left*right < 0:
                    before = elapsed*abs(left)/(abs(left)+abs(right))
                    pieces = [(before, left, 0.), (elapsed-before, 0., right)]
                mean_voltage = (previous['voltage']+voltage['value'])/2
                for seconds, a, b in pieces:
                    ah = abs((a+b)/2)*seconds/3600
                    direction = 'charge' if a+b >= 0 else 'discharge'
                    totals[direction+'_ah'] += ah
                    totals[direction+'_wh'] += ah*mean_voltage
                totals['observed_seconds'] += elapsed
            else:
                totals['gaps'] += 1
        self.data['baseline'] = dict(reported=reported, current=current['value'], voltage=voltage['value'])
