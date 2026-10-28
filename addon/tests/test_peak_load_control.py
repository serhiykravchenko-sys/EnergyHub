import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.services.peak_load_control import PeakLoadGuardController, ORDER


class ControlTests(unittest.TestCase):
    def test_bridge_restart_preserves_arm_but_resets_recovery_credit(self):
        self.guard.recovery_since = self.now
        self.guard.recovery_qualified = True
        self.guard.update_load_snapshot(dict(control_schema=6,
            observed_at=(self.now+timedelta(seconds=1)).isoformat(),bridge_session='ha-2',
            armed=True,loads=list(self.rows.values())))
        self.assertTrue(self.guard.armed)
        self.assertIsNone(self.guard.recovery_since)
        self.assertFalse(self.guard.recovery_qualified)

    def setUp(self):
        self.now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
        self.sent = []
        self.guard = PeakLoadGuardController(self.sent.append, path=None)
        self.rows = {key: dict(key=key, state='off', context_id='original-'+key,
            intent_revision=0, power_w=0, power_observed_at=self.now.isoformat(),
            state_observed_at=self.now.isoformat(),
            availability='not_applicable', control_ready=True,
            restore_allowed=True, restore_budget_w=1000,
            settings={}) for key in ORDER}
        self.tick(0, 20)

    def tick(self, seconds, percent, armed=True, **kwargs):
        kwargs.setdefault('grid_available', False)
        self.now += timedelta(seconds=seconds)
        for row in self.rows.values():
            row['power_observed_at'] = self.now.isoformat()
        self.guard.update_load_snapshot(dict(control_schema=6, observed_at=self.now.isoformat(),
            bridge_session='ha-1', armed=armed, loads=list(self.rows.values())))
        self.guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
            load_percent=percent, load_w=percent*100, now=self.now, **kwargs)

    def on(self, key='heat_pump_floor_1', power=1000):
        self.rows[key].update(state='on', power_w=power)

    def confirm(self, percent=70):
        command = self.sent[-1]
        row = self.rows[command['key']]
        row.update(state='off' if command['action']=='shed' else 'on',
                   power_w=0 if command['action']=='shed' else 1000,
                   context_id=command['command_id'], intent_revision=row['intent_revision']+1,
                   state_observed_at=(self.now+timedelta(seconds=1)).isoformat())
        self.guard.update_ack(dict(command_id=command['command_id'], bridge_session='ha-1',
            result='accepted', context_id=command['command_id']))
        self.tick(10, percent)


    def test_corrupt_journal_locks_instead_of_resetting_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.json'
            path.write_text(json.dumps(dict(schema=1, stream_id='a', sequence=0,
                events=[], cycle={'owned': {}}, pending=None)))
            guard = PeakLoadGuardController(self.sent.append, path=path)
            self.assertEqual('ownership_journal_unreadable', guard.fault)


    def test_malformed_intent_and_nonfinite_revision_rejected(self):
        self.assertFalse(self.guard.update_intent(dict(context_id='x', keys=None)))
        self.assertFalse(self.guard.update_intent(dict(context_id='x', keys=['other'])))
        self.on()
        self.rows['heat_pump_floor_1']['intent_revision'] = float('inf')
        self.tick(10, 90)
        self.assertFalse(self.sent)


    def test_old_retained_bridge_cannot_arm(self):
        self.assertFalse(self.guard.update_load_snapshot(dict(control_schema=1,
            observed_at=(self.now+timedelta(seconds=1)).isoformat(), bridge_session='old',
            armed=True, loads=list(self.rows.values()))))


    def test_runtime_does_not_select_legacy_trial(self):
        source = (Path(__file__).resolve().parents[1]/'app/main.py').read_text(encoding='utf-8')
        self.assertNotIn('PeakLoadGuardDryRun', source)
        self.assertNotIn("options.get('peak_load_control_enabled'", source)


    def missing_tick(self, seconds=20):
        self.now += timedelta(seconds=seconds)
        self.guard.evaluate(telemetry_valid=False, telemetry_freshness='stale',
                            load_percent=None, load_w=None, now=self.now)


    def test_schema_two_does_not_arm_new_policy(self):
        self.assertFalse(self.guard.update_load_snapshot(dict(control_schema=2,
            observed_at=(self.now+timedelta(seconds=1)).isoformat(), bridge_session='old',
            armed=True, loads=list(self.rows.values()))))


    def test_inverter_exception_paths_tick_missing_observer(self):
        source = (Path(__file__).resolve().parents[1]/'app/main.py').read_text(encoding='utf-8')
        tail = source[source.rindex('except subprocess.TimeoutExpired:'):]
        self.assertEqual(2, tail.count("peak_load_guard.evaluate(telemetry_valid=False"))


if __name__ == '__main__':
    unittest.main()
