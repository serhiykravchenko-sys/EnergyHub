"""Preserve the HP1 boundary while native HA owns overload switching."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from app.services.peak_load_control import PeakLoadGuardController, ORDER


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,24,12,tzinfo=timezone.utc)
        self.sent=[];self.guard=PeakLoadGuardController(self.sent.append,path=None)
        self.rows={k:dict(key=k,state='on',context_id='before-'+k,intent_revision=0,
            power_w=500,power_observed_at=self.now.isoformat(),state_observed_at=self.now.isoformat(),
            availability='not_applicable',control_ready=True,restore_allowed=True,settings={}) for k in ORDER}

    def tick(self, seconds=1, soc=35, load=20, valid=True):
        self.now+=timedelta(seconds=seconds)
        self.guard.update_load_snapshot(dict(control_schema=6,observed_at=self.now.isoformat(),
            bridge_session='boot',armed=True,hp1_battery_control_ready=True,loads=list(self.rows.values())))
        self.guard.evaluate(telemetry_valid=valid,telemetry_freshness='fresh',load_percent=load,
            load_w=load*100,battery_soc=soc,grid_available=False,now=self.now)

    def confirm(self,power=0):
        command=self.sent[-1];self.rows['heat_pump_floor_1'].update(state='off',context_id=command['command_id'],
            intent_revision=1,power_w=power,state_observed_at=(self.now+timedelta(seconds=1)).isoformat(),
            power_observed_at=(self.now+timedelta(seconds=1)).isoformat())
        self.guard.update_ack(dict(command_id=command['command_id'],bridge_session='boot',result='accepted',context_id=command['command_id']))
        self.tick()

    def test_high_load_cannot_dispatch_overload_commands(self):
        for load in (49,75,85,95,120):self.tick(soc=80,load=load)
        self.assertEqual([],self.sent);self.assertEqual([],self.guard.events)

    def test_battery_sheds_only_hp1(self):
        self.tick()
        self.assertEqual([('heat_pump_floor_1','battery')],[(c['key'],c['reason']) for c in self.sent])

    def test_command_boundary_rejects_other_devices_and_reasons(self):
        # ORDER is HP1-only after migration; iterating it made this rejection
        # assertion vacuous. Explicitly probe every retired plug and the fridge.
        for key in ('water_pump', 'water_boiler', 'heat_pump_floor_2',
                    'heat_pump_floor_3', 'microwave', 'fridge'):
            for action in ('shed', 'restore'):
                with self.subTest(key=key, action=action), self.assertRaises(ValueError):
                    self.guard._command(key, action, self.now)
        with self.assertRaises(ValueError):self.guard._command('heat_pump_floor_1','shed',self.now,reason='overload')
        self.assertFalse(self.sent)

    def test_ownership_requires_acknowledged_fresh_state(self):
        self.tick();self.assertFalse(self.guard.cycle['owned'])
        self.confirm();self.assertIn('heat_pump_floor_1',self.guard.cycle['owned'])

    def test_fresh_high_power_vetoes_off_confirmation(self):
        self.tick();self.confirm(power=500);self.assertFalse(self.guard.cycle['owned'])

    def test_external_off_intent_releases_owned_hp1(self):
        self.tick();self.confirm();self.guard.update_intent(dict(context_id='family',keys=['heat_pump_floor_1']))
        self.tick(soc=80);self.assertFalse(self.guard.cycle['owned'])

    def test_persistence_failure_prevents_command(self):
        with tempfile.TemporaryDirectory() as folder:
            self.guard.path=Path(folder)/'state.json'
            with patch('app.services.peak_load_control.atomic_write_json',side_effect=OSError('test')):self.tick()
        self.assertFalse(self.sent);self.assertEqual('ownership_journal_write_failed',self.guard.fault)

    def test_pending_restart_quarantines_without_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            self.guard.path=Path(folder)/'state.json';self.tick()
            restored=PeakLoadGuardController(self.sent.append,path=self.guard.path)
            self.assertIsNone(restored.pending)
            self.assertEqual('uncertain_command_after_restart',restored.cycle['blocked']['heat_pump_floor_1'])
            self.assertEqual(1,len(self.sent))

    def test_old_overload_ownership_retires_without_switching(self):
        with tempfile.TemporaryDirectory() as folder:
            self.guard.path=Path(folder)/'state.json';self.tick();self.confirm()
            data=json.loads(self.guard.path.read_text(encoding='utf-8'))
            owner=copy.deepcopy(data['cycle']['owned']['heat_pump_floor_1']);owner['reason']='overload'
            data['cycle']['owned']['water_boiler']=owner;self.guard.path.write_text(json.dumps(data),encoding='utf-8')
            self.sent.clear();restored=PeakLoadGuardController(self.sent.append,path=self.guard.path)
            self.assertEqual({'heat_pump_floor_1'},set(restored.cycle['owned']));self.assertFalse(self.sent)

    def test_invalid_telemetry_never_sheds(self):
        self.tick(valid=False);self.assertFalse(self.sent)
