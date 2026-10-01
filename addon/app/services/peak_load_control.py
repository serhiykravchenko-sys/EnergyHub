"""Deterministic, acknowledged load control; never sends inverter commands.

The HA executor is a separate allow-listed boundary. Commands are non-retained,
expire quickly and are never retried automatically. Unknown outcomes require
attention, not an invented successful shutdown or an automatic restart.
"""
import copy
import json
import math
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.utils.json_store import atomic_write_json
from app.services.battery_load_policy import BatteryLoadPolicy, LOADS as BATTERY_LOADS

ORDER = ('water_pump', 'water_boiler', 'heat_pump_floor_1',
         'heat_pump_floor_2', 'heat_pump_floor_3', 'microwave')
PARTICIPANT_NAMES = {
    'water_pump': 'Water pump',
    'water_boiler': 'Water boiler',
    'heat_pump_floor_1': '1st-floor heat pump',
    'heat_pump_floor_2': '2nd-floor heat pump',
    'heat_pump_floor_3': '3rd-floor heat pump',
    'microwave': 'Microwave',
}
THRESHOLDS = dict(shed_percent=85, relief_percent=75, restore_percent=50)
RECOVERY_SECONDS = 300
RESTORE_SETTLE_SECONDS = 60
COMMAND_TOPIC = 'energyhub/control/peak_load_guard'
CONTROL_FILE = Path('/data/energyhub_peak_load_control.json')
DEVICE_BLOCK_REASONS = {
    'command_delivery_uncertain', 'command_outcome_unconfirmed',
    'executor_rejected_command', 'executor_restarted_during_command',
    'uncertain_command_after_restart', 'external_control_during_command',
    'load_unavailable', 'restoration_load_unavailable',
    'native_settings_restore_unverified', 'restore_rejected_requires_attention',
}


def _finite_number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


class PeakLoadGuardController:
    def __init__(self, send, path=CONTROL_FILE, clock=None):
        self.send = send
        self.path = path
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.lock = threading.RLock()
        self.loads = {}
        self.observed_at = None
        self.armed = False
        self.automatic_requested = False
        self.control_ready = False
        self.warning_active = False
        self.warning_recovery_since = None
        self.bridge_session = None
        self.phase = 'disarmed'
        self.stream_id = uuid4().hex
        self.sequence = 0
        self.events = []
        self.cycle = None
        self.pending = None
        self.recovery_since = None
        self.recovery_qualified = False
        self.missing_since = None
        self.missing_notified = False
        self.last_sample_at = None
        self.last_load_percent = None
        self.fault = None
        self.intents = []
        self.battery = BatteryLoadPolicy()
        self.battery_ready = False
        self.grid_since = None
        self.battery_decision = None
        self.last_battery_soc = None
        self.smart_heating_enabled = False
        self.last_grid_available = False
        self._saved_battery = None
        self.legacy_lockouts_imported = False
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not self._valid_journal(data):
                    raise ValueError('Unsupported ownership journal')
                self.stream_id = data['stream_id']
                self.sequence = data['sequence']
                self.events = data['events'][-64:]
                self.cycle = data['cycle']
                self.pending = data['pending']
                self.battery = BatteryLoadPolicy.restore(data.get('battery', {'active': False, 'attempted': []}))
                self.legacy_lockouts_imported = data.get('legacy_lockouts_imported') is True
                self.fault = data.get('fault')
                self.warning_active = data.get('warning_active') is True
                self.missing_since = _parse_datetime(data.get('missing_since'))
                self.missing_notified = data.get('missing_notified') is True
                if self.pending:
                    # A persisted intent does not prove delivery or execution.
                    # Quarantine only that participant; never invent ownership
                    # and never freeze protection for the other loads.
                    key = self.pending.get('key')
                    if self.cycle is not None and key in ORDER:
                        self.cycle['blocked'][key] = 'uncertain_command_after_restart'
                    self.pending = None
                    if self.fault in DEVICE_BLOCK_REASONS or self.fault is None:
                        self.fault = None
                    self.phase = 'device_skipped'
                elif self.fault in DEVICE_BLOCK_REASONS:
                    # Migrate 2.4.1 command-scoped global faults. The affected
                    # key is already retained in cycle.blocked when known.
                    self.fault = None
                    self.phase = 'device_skipped'
                elif self.fault:
                    self.phase = 'attention_required'
            except (OSError, ValueError, KeyError, TypeError):
                self.fault = 'ownership_journal_unreadable'
                self.phase = 'attention_required'

    @staticmethod
    def _valid_journal(data):
        if not isinstance(data, dict) or data.get('schema') != 1:
            return False
        if (not isinstance(data.get('stream_id'), str)
                or not isinstance(data.get('sequence'), int) or data['sequence'] < 0
                or not isinstance(data.get('events'), list)):
            return False
        if any(not isinstance(e, dict) or not e.get('event_id') for e in data['events']):
            return False
        cycle = data.get('cycle')
        if cycle is not None:
            if (not isinstance(cycle, dict) or not cycle.get('cycle_id')
                    or not isinstance(cycle.get('owned'), dict)
                    or not isinstance(cycle.get('blocked'), dict)
                    or not isinstance(cycle.get('shed'), list)
                    or not isinstance(cycle.get('restored'), list)
                    or _finite_number(cycle.get('settle_until')) is None):
                return False
            for key, owner in cycle['owned'].items():
                if (key not in ORDER or not isinstance(owner, dict)
                        or not isinstance(owner.get('original'), dict)
                        or not owner.get('context_id')
                        or _finite_number(owner.get('intent_revision')) is None
                        or _parse_datetime(owner.get('confirmed_off_at')) is None):
                    return False
        # Any pending journal is deliberately locked after restart, never replayed.
        return data.get('pending') is None or isinstance(data['pending'], dict)

    def _persist(self):
        if self.path is None:
            self._saved_battery = self.battery.export()
            return True
        try:
            atomic_write_json(self.path, dict(schema=1, stream_id=self.stream_id,
                sequence=self.sequence, events=self.events, cycle=self.cycle,
                pending=self.pending, fault=self.fault, warning_active=self.warning_active,
                battery=self.battery.export(),
                legacy_lockouts_imported=self.legacy_lockouts_imported,
                missing_since=self.missing_since.isoformat() if self.missing_since else None,
                missing_notified=self.missing_notified))
            self._saved_battery = self.battery.export()
            return True
        except Exception:
            self.fault = 'ownership_journal_write_failed'
            self.phase = 'attention_required'
            return False

    def _persist_battery(self):
        return self._saved_battery == self.battery.export() or self._persist()

    def _event(self, kind, now, **details):
        self.sequence += 1
        event = dict(event_id=f'peak-live-{self.sequence}', sequence=self.sequence,
            stream_id=self.stream_id, cycle_id=(self.cycle or {}).get('cycle_id'),
            occurred_at=now.isoformat(), type=kind,
            mode='warnings_only' if kind in ('load_warning', 'load_warning_cleared') else 'automatic',
            thresholds=THRESHOLDS, load_percent=self.last_load_percent, **details)
        self.events = (self.events + [event])[-64:]
        self._persist()
        return event

    def update_load_snapshot(self, payload):
        try:
            data = json.loads(payload) if isinstance(payload, str) else payload
            observed = _parse_datetime(data.get('observed_at'))
            rows = data.get('loads')
            # Older bridge policies must not arm newly upgraded code.
            if data.get('control_schema') != 5 or observed is None or not isinstance(rows, list):
                return False
            parsed = {item['key']: copy.deepcopy(item) for item in rows
                      if isinstance(item, dict) and item.get('key') in ORDER}
            if len(parsed) != len(ORDER) or not data.get('bridge_session'):
                return False
        except (ValueError, TypeError, AttributeError):
            return False
        with self.lock:
            if self.observed_at and observed <= self.observed_at:
                return False
            if self.bridge_session and self.bridge_session != data['bridge_session']:
                # Preserve user intent/ownership, not pre-restart recovery credit.
                self.recovery_since = None
                self.recovery_qualified = False
                self.warning_recovery_since = None
                self.grid_since = None
            self.loads, self.observed_at = parsed, observed
            self.armed = data.get('armed') is True
            self.automatic_requested = data.get('automatic_requested', self.armed) is True
            self.armed = self.armed and self.automatic_requested
            self.bridge_session = data['bridge_session']
            self.battery_ready = data.get('battery_control_ready') is True
            self.smart_heating_enabled = data.get('smart_heating_enabled') is True
            if not self.legacy_lockouts_imported and type(data.get('legacy_battery_lockout')) is bool:
                # One-time upgrade import: clearing old automation writers must
                # not silently clear a pre-existing remembered critical lock.
                if data['legacy_battery_lockout']:
                    self.battery.active = True
                    self.battery.locked = True
                    self.battery.attempted.update(BATTERY_LOADS)
                self.legacy_lockouts_imported = True
                if not self._persist():
                    return False
        return True

    def _evaluate_warning(self, percent, overload_warning, now):
        """Independent of participant availability: fresh inverter load is enough."""
        if not self.warning_active:
            if percent >= THRESHOLDS['shed_percent'] or overload_warning:
                self.warning_active = True
                self.warning_recovery_since = None
                self._event('load_warning', now, overload_warning=bool(overload_warning))
            return
        if percent >= THRESHOLDS['restore_percent'] or overload_warning:
            self.warning_recovery_since = None
            return
        if self.warning_recovery_since is None:
            self.warning_recovery_since = now
        if (now-self.warning_recovery_since).total_seconds() >= RECOVERY_SECONDS:
            self.warning_active = False
            self.warning_recovery_since = None
            self._event('load_warning_cleared', now)

    def _observe_ownership(self, now):
        if not self.cycle:
            return
        for key, owner in list(self.cycle['owned'].items()):
            row = self.loads[key]
            changed = row.get('state') == 'on' or (row.get('state') == 'off'
                and row.get('context_id') != owner['context_id'])
            if row.get('intent_revision') != owner.get('intent_revision'):
                changed = True
            intent = any(key in x.get('keys', []) and x['context_id'] != owner['context_id'] for x in self.intents)
            if changed or intent:
                del self.cycle['owned'][key]
                self._attention('external_control_ownership_released', now, key)

    def _missing_data(self, missing, now):
        """Persist one notification per outage while EH still owns OFF devices."""
        owned = (self.cycle or {}).get('owned', {})
        if not missing or not owned:
            if self.missing_since is not None or self.missing_notified:
                self.missing_since, self.missing_notified = None, False
                self._persist()
            return
        self.recovery_since = None
        self.recovery_qualified = False
        if self.missing_since is None:
            self.missing_since = now
            self._persist()
        if not self.missing_notified and (now-self.missing_since).total_seconds() >= 300:
            self.missing_notified = True
            self._event('control_attention', now, reason='restoration_telemetry_missing',
                        affected_loads=[dict(key=k) for k in ORDER if k in owned])

    def update_ack(self, payload):
        try:
            ack = json.loads(payload) if isinstance(payload, str) else payload
        except (ValueError, TypeError):
            return False
        with self.lock:
            if not isinstance(ack, dict) or not self.pending:
                return False
            if ack.get('command_id') != self.pending['command_id']:
                return False
            if ack.get('bridge_session') != self.pending['bridge_session']:
                return False
            self.pending['ack'] = copy.deepcopy(ack)
            self._persist()
            return True

    def update_intent(self, payload):
        """HA service-call evidence also catches OFF while already OFF."""
        try:
            item = json.loads(payload) if isinstance(payload, str) else payload
            if (not isinstance(item, dict) or not item.get('context_id')
                    or not isinstance(item.get('keys'), list)
                    or not item['keys']
                    or any(key not in ORDER for key in item['keys'])):
                return False
        except (ValueError, TypeError):
            return False
        with self.lock:
            self.intents.append(item)
            if len(self.intents) > 128:
                evicted = self.intents.pop(0)
                # An OFF request can leave the switch state/context unchanged.
                # If its evidence is evicted, ownership of that load is no
                # longer safe even when unrelated intents filled the queue.
                now = self.observed_at or self.clock()
                for key in evicted['keys']:
                    if (self.pending and self.pending['key'] == key
                            and evicted['context_id'] != self.pending['command_id']):
                        # A restore can already be pending for an owned load.
                        # Clearing only the pending command would let the
                        # recovery loop request another restore.
                        if self.cycle and key in self.cycle['owned']:
                            del self.cycle['owned'][key]
                        self._block_device(key, 'external_intent_evicted', now)
                    elif (self.cycle and key in self.cycle['owned']
                            and evicted['context_id'] != self.cycle['owned'][key]['context_id']):
                        del self.cycle['owned'][key]
                        self._attention('external_control_ownership_released', now, key)
            return True

    def _fresh(self, value, now, age=30):
        stamp = _parse_datetime(value) if not isinstance(value, datetime) else value
        return stamp is not None and -2 <= (now-stamp).total_seconds() <= age

    def _usable(self, row, now):
        power = _finite_number(row.get('power_w'))
        return (row.get('availability') in ('online', 'not_applicable')
                and row.get('state') in ('on', 'off') and bool(row.get('context_id'))
                and _finite_number(row.get('intent_revision')) is not None
                and float(row['intent_revision']) >= 0
                and power is not None and power >= 0)

    def _attention(self, reason, now, key=None):
        self.phase = 'attention_required'
        if self.cycle is not None and key:
            self.cycle['blocked'][key] = reason
        return self._event('control_attention', now, reason=reason, key=key,
                           affected_loads=([dict(key=key)] if key else []))

    def _block_device(self, key, reason, now):
        """Quarantine one uncertain participant without stopping the cycle."""
        if self.cycle is None:
            return None
        previous = self.cycle['blocked'].get(key)
        self.cycle['blocked'][key] = reason
        if self.pending and self.pending.get('key') == key:
            self.pending = None
        self.phase = 'device_skipped'
        if previous == reason:
            self._persist()
            return None
        return self._event('control_attention', now, reason=reason, key=key,
                           affected_loads=[dict(key=key)])

    def _command(self, key, action, now, reason='overload'):
        row = self.loads[key]
        owner = self.cycle['owned'].get(key)
        command = dict(command_id=uuid4().hex, cycle_id=self.cycle['cycle_id'],
            control_schema=5, reason=reason, battery_locked=self.battery.locked,
            key=key, action=action, issued_at=now.isoformat(),
            expires_at=now.timestamp()+20, bridge_session=self.bridge_session,
            expected_context=row['context_id'], expected_state=row['state'],
            expected_revision=row.get('intent_revision'),
            expected_settings=copy.deepcopy(row.get('settings', {})),
            original=copy.deepcopy(owner['original'] if owner else row),
            before_load_percent=self.last_load_percent,
            trigger_load_percent=(self.cycle or {}).get('trigger_load_percent'),
            trigger_reason=(self.cycle or {}).get('trigger_reason', reason))
        if (key == 'heat_pump_floor_1' and action == 'restore' and reason == 'battery'
                and self.smart_heating_enabled and not self.last_grid_available):
            command['restore_profile'] = 'eco'
        self.pending = command
        self.phase = f'{action}_pending'
        # Durable write-before-send. Never publish if persistence failed.
        if not self._persist():
            return None
        try:
            self.send(copy.deepcopy(command))
        except Exception:
            self._block_device(key, 'command_delivery_uncertain', now)
        return None

    def _reconcile(self, now):
        if not self.pending:
            return False
        p = self.pending
        key = p['key']
        ack = p.get('ack') or {}
        age = (now-_parse_datetime(p['issued_at'])).total_seconds()
        if self.bridge_session != p['bridge_session']:
            self._block_device(key, 'executor_restarted_during_command', now)
            return True
        if ack and ack.get('result') != 'accepted':
            self._block_device(key, 'executor_rejected_command', now)
            return True
        row = self.loads[key]
        wanted = 'off' if p['action'] == 'shed' else 'on'
        state_observed = _parse_datetime(row.get('state_observed_at'))
        issued_at = _parse_datetime(p['issued_at'])
        confirmed = (ack.get('context_id') and row.get('context_id') == ack['context_id']
                     and row.get('state') == wanted and self._usable(row, now)
                     and self.observed_at > issued_at
                     and state_observed is not None and state_observed > issued_at)
        if key == 'heat_pump_floor_1' and p['action'] == 'restore':
            if p.get('restore_profile') == 'eco':
                confirmed = confirmed and row.get('settings', {}).get('eco') == 'on'
            else:
                confirmed = confirmed and row.get('settings') == p['original'].get('settings')
        if p['action'] == 'shed':
            power_observed = _parse_datetime(row.get('power_observed_at'))
            fresh_power = power_observed is not None and power_observed > issued_at
            # A fresh contradictory measurement vetoes confirmation. An old
            # unchanged 0/1 W sample is diagnostic only; the fresh target-state
            # transition and matching command context are the acknowledgement.
            confirmed = confirmed and (not fresh_power
                or (_finite_number(row.get('power_w')) is not None
                    and float(row['power_w']) <= 100))
        if not confirmed:
            if age > 90:
                self._block_device(key, 'command_outcome_unconfirmed', now)
            return True
        own_context = ack['context_id']
        conflicts = [x for x in self.intents if key in x.get('keys', [])
                     and x['context_id'] != own_context]
        self.intents = [x for x in self.intents if key not in x.get('keys', [])]
        self.pending = None
        if conflicts:
            self.cycle['owned'].pop(key, None)
            self._block_device(key, 'external_control_during_command', now)
            return True
        if p['action'] == 'shed':
            self.cycle['owned'][key] = dict(original=p['original'],
                context_id=own_context, intent_revision=row.get('intent_revision'),
                reason=p.get('reason', 'overload'), off_settings=copy.deepcopy(row.get('settings')),
                confirmed_off_at=now.isoformat())
            self.cycle['shed'].append(key)
            self._event('load_shed', now, affected_loads=[dict(key=key)],
                        reason=p.get('reason', 'overload'), battery_soc=self.last_battery_soc,
                        trigger_load_percent=p.get('trigger_load_percent'),
                        action_load_percent=p.get('before_load_percent'),
                        trigger_reason=p.get('trigger_reason'))
        else:
            self.cycle['owned'].pop(key, None)
            self.cycle['restored'].append(key)
            self._event('load_restored', now, affected_loads=[dict(key=key)], reason=p.get('reason', 'overload'))
        if p['action'] == 'shed':
            self.recovery_since = None
            self.recovery_qualified = False
        self.cycle['settle_until'] = now.timestamp()+(RESTORE_SETTLE_SECONDS if p['action'] == 'restore' else 30)
        self._persist()
        return True

    def evaluate(self, *, telemetry_valid, telemetry_freshness, load_percent,
                 load_w, load_va=None, grid_available=False, operating_mode='',
                 overload_warning=False, battery_soc=None, now=None):
        now = now or self.clock()
        with self.lock:
            percent, watts = _finite_number(load_percent), _finite_number(load_w)
            self.last_load_percent = percent
            self.control_ready = False
            gap_ok = self.last_sample_at is None or 0 <= (now-self.last_sample_at).total_seconds() <= 30
            self.last_sample_at = now
            if not gap_ok:
                self.recovery_since = None
                self.recovery_qualified = False
                self.warning_recovery_since = None
            snapshot_fresh = self._fresh(self.observed_at, now)
            self.last_battery_soc = _finite_number(battery_soc)
            self.last_grid_available = grid_available is True
            battery_enabled = self.battery_ready and snapshot_fresh
            self.battery_decision = None
            if not gap_ok or not grid_available:
                self.grid_since = None
            if snapshot_fresh and not self.pending:
                self._observe_ownership(now)
            if not telemetry_valid or telemetry_freshness != 'fresh' or percent is None or watts is None or percent < 0 or watts < 0:
                self.recovery_since = None
                self.recovery_qualified = False
                self.warning_recovery_since = None
                self._missing_data(True, now)
                self.phase = 'waiting_for_telemetry'
                self.grid_since = None
                return None
            if battery_enabled:
                if grid_available and self.grid_since is None:
                    self.grid_since = now
                grid_recovered = (grid_available and self.grid_since is not None
                    and (now-self.grid_since).total_seconds() >= 60)
                try:
                    self.battery_decision = self.battery.evaluate(soc=self.last_battery_soc,
                        grid_present=grid_available, grid_recovered=grid_recovered,
                        occupied_heating=self.smart_heating_enabled)
                except ValueError:
                    self.grid_since = None
                if self.battery_decision and self.battery_decision.get('warning'):
                    self._event('battery_reserve_warning', now,
                                battery_soc=self.last_battery_soc,
                                reason='battery_discharge')
                if not self._persist_battery():
                    return None
            self._missing_data(not snapshot_fresh or
                               (battery_enabled and self.battery_decision is None), now)
            if (not self.armed and not battery_enabled) or not snapshot_fresh or self.fault:
                self._evaluate_warning(percent, overload_warning, now)
                self.recovery_since = None
                self.recovery_qualified = False
                # Observe acknowledgement/family changes even while OFF, but
                # never dispatch another command or forget an owned device.
                if snapshot_fresh and not self.fault:
                    reconciled = self._reconcile(now)
                    if not reconciled:
                        self._observe_ownership(now)
                    if not self.pending:
                        self.intents = []
                self.phase = ('attention_required' if self.fault else
                              'waiting_for_load_data' if not snapshot_fresh else
                              'automatic_blocked' if self.automatic_requested else 'warnings_only')
                return None
            if self.warning_active and self.armed:
                # Switching ON supersedes advice; do not issue a fake recovery.
                self.warning_active = False
                self.warning_recovery_since = None
                if not self._persist():
                    return None
            self.control_ready = self.armed
            if not self.armed:
                self._evaluate_warning(percent, overload_warning, now)
            if percent >= 50 or overload_warning:
                self.recovery_since = None
                self.recovery_qualified = False
            if self._reconcile(now):
                return None
            self._observe_ownership(now)
            self.intents = []
            trigger = self.armed and (percent >= 85 or overload_warning)
            requested_battery_stop = (self.battery_decision or {}).get('stop', [])
            needs_battery_cycle = any(
                self.loads[key].get('state') != 'off'
                for key in requested_battery_stop
            )
            if self.cycle is None and (trigger or needs_battery_cycle):
                self.cycle = dict(cycle_id=uuid4().hex, owned={}, blocked={}, shed=[],
                                  restored=[], settle_until=0, shedding=True,
                                  started_at=now.isoformat(),
                                  trigger_load_percent=percent,
                                  trigger_reason=('inverter_warning'
                                      if overload_warning else
                                      'battery' if needs_battery_cycle else 'load_percent'))
                if not self._persist():
                    return None
            for key in requested_battery_stop:
                row = self.loads[key]
                if row.get('state') == 'off':
                    self.battery.attempted_stop(key)
                elif not (self._usable(row, now) and row.get('control_ready') is True):
                    self.battery.attempted_stop(key)
                    self._block_device(key, 'battery_load_unavailable', now)
            battery_stop = [key for key in requested_battery_stop
                            if self.loads[key].get('state') == 'on'
                            and self._usable(self.loads[key], now)
                            and self.loads[key].get('control_ready') is True]
            if not self._persist_battery():
                return None
            if self.cycle is None:
                self.phase = 'normal' if self.armed else 'warnings_only'
                return None
            if trigger:
                self.cycle['shedding'] = True
            if percent <= 75 and not overload_warning:
                self.cycle['shedding'] = False
            if now.timestamp() < self.cycle['settle_until'] and not trigger and not battery_stop:
                self.phase = 'settling'
                return None
            if self.armed and self.cycle.get('shedding', True) and (percent > 75 or overload_warning):
                self.recovery_since = None
                for key in ORDER:
                    row = self.loads[key]
                    if key in self.cycle['owned']:
                        continue
                    if self.cycle['blocked'].get(key) == 'load_unavailable':
                        if not (self._usable(row, now) and row.get('control_ready') is True):
                            continue
                        self.cycle['blocked'].pop(key, None)
                    elif key in self.cycle['blocked']:
                        continue
                    if row.get('state') == 'on' and self._usable(row, now) and row.get('control_ready') is True:
                        return self._command(key, 'shed', now)
                    if row.get('state') not in ('off',):
                        self._block_device(key, 'load_unavailable', now)
                if self.phase != 'no_candidates':
                    self._event('control_attention', now, reason='no_available_loads')
                self.phase = 'no_candidates'
                return None
            for key in battery_stop:
                row = self.loads[key]
                # Remember already-OFF devices too: a deliberate subsequent ON
                # is permitted in the soft band, but never below the hard floor.
                if row.get('state') == 'off':
                    self.battery.attempted_stop(key)
                    continue
                if key in self.cycle['owned']:
                    continue
                if row.get('state') == 'on' and self._usable(row, now) and row.get('control_ready') is True:
                    blocked_reason = self.cycle['blocked'].get(key)
                    if blocked_reason:
                        if blocked_reason in DEVICE_BLOCK_REASONS:
                            continue
                        if not self.battery_decision['locked']:
                            continue
                        self.cycle['blocked'].pop(key, None)
                    self.battery.attempted_stop(key)
                    return self._command(key, 'shed', now, reason='battery')
            unavailable = [k for k in requested_battery_stop
                           if k not in self.cycle['owned'] and k not in battery_stop]
            if unavailable:
                if self.cycle.get('battery_unavailable') != unavailable:
                    self.cycle['battery_unavailable'] = unavailable
                    self._event('control_attention', now, reason='battery_load_unavailable',
                                affected_loads=[dict(key=k) for k in unavailable])
                self.phase = 'battery_load_unavailable'
                return None
            if not self._persist_battery():
                return None
            if percent >= 50 or overload_warning:
                self.recovery_since = None
                self.phase = 'holding'
                return None
            battery_owned = [k for k in self.cycle['owned'] if k in BATTERY_LOADS]
            hp_early_allowed = ((self.battery_decision or {}).get('hp_restore_allowed')
                                and 'heat_pump_floor_1' in battery_owned)
            if (self.battery_ready and battery_owned
                    and not (self.battery_decision or {}).get('restore_allowed')
                    and not hp_early_allowed):
                self.recovery_since = None
                self.recovery_qualified = False
                self.phase = 'battery_recovery_waiting'
                return None
            if self.recovery_since is None:
                self.recovery_since = now
            self.phase = 'recovery_pending'
            if not self.recovery_qualified and (now-self.recovery_since).total_seconds() < RECOVERY_SECONDS:
                return None
            self.recovery_qualified = True
            restore_order = (('heat_pump_floor_1',) + tuple(
                key for key in ORDER if key != 'heat_pump_floor_1')
                if hp_early_allowed and not (self.battery_decision or {}).get('restore_allowed')
                else ORDER)
            for key in restore_order:
                owner = self.cycle['owned'].get(key)
                if not owner:
                    continue
                row = self.loads[key]
                hp_early = (key == 'heat_pump_floor_1' and self.battery_decision
                            and self.battery_decision.get('hp_restore_allowed'))
                if key in BATTERY_LOADS and (not self.battery_decision or
                        (not self.battery_decision['restore_allowed'] and not hp_early)) and self.battery_ready:
                    self.phase = 'battery_recovery_waiting'
                    return None
                if owner.get('reason') == 'overload' and not self.armed:
                    self.phase = 'restoration_waiting'
                    return None
                hp_eco_restore = (key == 'heat_pump_floor_1'
                    and owner.get('reason') == 'battery' and self.smart_heating_enabled
                    and not self.last_grid_available)
                if (key == 'heat_pump_floor_1' and not hp_eco_restore
                        and row.get('settings') != owner['original'].get('settings')):
                    if self.cycle['blocked'].get(key) != 'native_settings_restore_unverified':
                        self._block_device(key, 'native_settings_restore_unverified', now)
                    continue
                off_age = (now-_parse_datetime(owner['confirmed_off_at'])).total_seconds()
                min_off = 300 if 'heat_pump' in key or key == 'water_pump' else 60
                if (not self._usable(row, now) or row.get('restore_allowed') is not True
                        or row.get('control_ready') is not True):
                    self._block_device(key, 'restoration_load_unavailable', now)
                    continue
                if self.cycle['blocked'].get(key) in DEVICE_BLOCK_REASONS:
                    self.cycle['blocked'].pop(key, None)
                if off_age < min_off:
                    self.phase = 'restoration_waiting'
                    continue
                return self._command(key, 'restore', now, reason=owner.get('reason', 'overload'))
            if self.cycle['owned']:
                self.phase = 'restoration_waiting'
                return None
            self._event('control_complete', now,
                        affected_loads=[dict(key=k) for k in self.cycle['restored']],
                        skipped_loads=[dict(key=k, reason=v)
                                       for k, v in self.cycle['blocked'].items()])
            self.cycle = None
            self.recovery_since = None
            self.recovery_qualified = False
            self.phase = 'normal'
            self._persist()
            return None

    def status_state(self):
        return self.phase

    def status_attributes(self):
        with self.lock:
            return copy.deepcopy(dict(control_schema=5, mode='automatic' if self.automatic_requested else 'warnings_only',
                armed=self.armed, control_ready=self.control_ready and not self.fault,
                automatic_requested=self.automatic_requested, warning_active=self.warning_active,
                eligible_loads=[k for k in ORDER if self.loads.get(k, {}).get('control_ready') is True],
                shed_threshold_percent=85, relief_target_percent=75,
                restore_threshold_percent=50, recovery_confirmation_seconds=RECOVERY_SECONDS,
                restore_settle_seconds=RESTORE_SETTLE_SECONDS,
                telemetry_missing_since=self.missing_since.isoformat() if self.missing_since else None,
                battery_protection=self.battery_decision, battery_episode=self.battery.export(),
                participant_order=list(ORDER), participants=[dict(self.loads[k],
                name=PARTICIPANT_NAMES[k]) for k in ORDER if k in self.loads],
                load_snapshot_at=self.observed_at.isoformat() if self.observed_at else None,
                cycle=self.cycle, pending=self.pending, fault=self.fault,
                latest_event_id=self.events[-1]['event_id'] if self.events else None))

    def event_state(self):
        return self.events[-1]['type'] if self.events else 'No event'

    def event_attributes(self):
        with self.lock:
            return copy.deepcopy(dict(event=self.events[-1] if self.events else None,
                                      events=self.events, stream_id=self.stream_id))
