"""Retirement must never turn an old battery-owned plug back on."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from app.services.peak_load_control import PeakLoadGuardController, ORDER


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
        self.sent = []
        self.rows = [dict(key=k, state='on', power_w=500, availability='online',
                          context_id=k, intent_revision=0, settings={},
                          control_ready=True, restore_allowed=True) for k in ORDER]

    def snapshot(self, guard, schema=6, armed=False):
        return guard.update_load_snapshot(dict(control_schema=schema,
            observed_at=self.now.isoformat(), bridge_session='new-boot', armed=armed,
            loads=self.rows))

    def tick(self, guard, load=10):
        guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
                       load_percent=load, load_w=1000, grid_available=False, now=self.now)

    def test_old_schema_cannot_arm_new_controller(self):
        guard = PeakLoadGuardController(self.sent.append, path=None)
        self.assertFalse(self.snapshot(guard, schema=5, armed=True))
        self.tick(guard, 95)
        self.assertFalse(self.sent)

    def test_battery_flags_no_longer_dispatch_even_on_repeated_ticks(self):
        guard = PeakLoadGuardController(self.sent.append, path=None)
        for _ in range(45):
            self.snapshot(guard)
            self.tick(guard)
            self.now += timedelta(seconds=10)
        self.assertFalse(self.sent)
        self.assertNotIn('battery_protection', guard.status_attributes())
        from app.services.hp1_battery_policy import LOADS
        self.assertEqual(('heat_pump_floor_1',), LOADS)

    def test_br_70_soc_65_grid_absent_does_not_shed_or_warn(self):
        guard=PeakLoadGuardController(self.sent.append,path=None)
        guard.battery.configure(dict(load_off_soc=40,load_restore_soc=50))
        for _ in range(12):
            payload=dict(control_schema=6,observed_at=self.now.isoformat(),
                         bridge_session='audit-boot',armed=True,
                         hp1_battery_control_ready=True,loads=self.rows)
            self.assertTrue(guard.update_load_snapshot(payload))
            guard.evaluate(telemetry_valid=True,telemetry_freshness='fresh',load_percent=10,
                           load_w=1000,grid_available=False,battery_soc=65,now=self.now)
            self.assertEqual([],guard.battery.evaluate(soc=65,grid_present=False,hard_floor=70)['stop'])
            self.now+=timedelta(seconds=10)
        self.assertFalse(self.sent)
        self.assertIsNone(guard.cycle)
        self.assertFalse(any(e.get('type') in {'battery_reserve_warning','hp1_battery_warning'}
                             for e in guard.events))

    def test_mixed_journal_retires_migrated_ownership_without_replay(self):
        original = dict(self.rows[0], state='on')
        owner = dict(original=original, context_id='off', intent_revision=0,
                     confirmed_off_at=self.now.isoformat(), reason='battery')
        cycle = dict(cycle_id='old', trigger_reason='battery', owned={'water_pump': owner,
                     'microwave': dict(owner, reason='overload')}, blocked={},
                     shed=['water_pump', 'microwave'], restored=[], settle_until=0)
        cycle['blocked'] = {'water_pump':'battery_load_unavailable',
                            'microwave':'command_outcome_unconfirmed'}
        pending = dict(command_id='old-battery-request', reason='battery', key='water_pump')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'journal.json'
            path.write_text(json.dumps(dict(schema=1, stream_id='old', sequence=0,
                events=[], cycle=cycle, pending=pending,
                battery=dict(active=True, attempted=['water_pump','heat_pump_floor_1']))), encoding='utf-8')
            guard = PeakLoadGuardController(self.sent.append, path=path)
            self.assertIsNone(guard.fault)
            self.assertIsNone(guard.pending)
            self.assertEqual(set(), set(guard.cycle['owned']))
            self.assertNotIn('water_pump', guard.cycle['blocked'])
            self.assertEqual('command_outcome_unconfirmed', guard.cycle['blocked']['microwave'])
            self.assertFalse(self.sent)
            guard._persist()
            self.assertNotIn('battery', json.loads(path.read_text(encoding='utf-8')))

    def test_python_overload_dispatch_is_retired(self):
        guard = PeakLoadGuardController(self.sent.append, path=None)
        self.snapshot(guard, armed=True)
        self.tick(guard, 95)
        self.assertEqual([], self.sent)

    def test_deferred_hp1_battery_control_cannot_target_the_migrated_plugs(self):
        guard = PeakLoadGuardController(self.sent.append, path=None)
        guard.update_load_snapshot(dict(control_schema=6, observed_at=self.now.isoformat(),
            bridge_session='new-boot', armed=False, hp1_battery_control_ready=True,
            loads=self.rows, hp1_smart_heating_enabled=True))
        guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
            load_percent=10, load_w=1000, battery_soc=35, grid_available=False, now=self.now)
        self.assertEqual('heat_pump_floor_1', self.sent[0]['key'])
        self.assertEqual('battery', self.sent[0]['reason'])
        self.assertEqual(1,len(self.sent))
