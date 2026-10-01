"""Shared executor tests: battery and overload never command independently."""
import unittest
from datetime import datetime, timedelta, timezone
from app.services.peak_load_control import PeakLoadGuardController, ORDER


class BatteryControlTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 9, tzinfo=timezone.utc)
        self.sent = []
        self.guard = PeakLoadGuardController(self.sent.append, path=None)
        self.rows = {k: dict(key=k, state='off', context_id=k, intent_revision=0,
            power_w=0, power_observed_at=self.now.isoformat(),
            state_observed_at=self.now.isoformat(), availability='not_applicable',
            control_ready=True,
            restore_allowed=True, settings={}) for k in ORDER}
        self.soc, self.grid, self.armed, self.smart = 40, False, False, False

    def tick(self, seconds=10, load=20, mode='solar', valid=True):
        self.now += timedelta(seconds=seconds)
        for row in self.rows.values(): row['power_observed_at'] = self.now.isoformat()
        self.guard.update_load_snapshot(dict(control_schema=5, observed_at=self.now.isoformat(),
            bridge_session='session', armed=self.armed, battery_control_ready=True,
            smart_heating_enabled=self.smart,
            loads=list(self.rows.values())))
        self.guard.evaluate(telemetry_valid=valid, telemetry_freshness='fresh' if valid else 'stale',
            battery_soc=self.soc, grid_available=self.grid, operating_mode=mode,
            load_percent=load, load_w=load*100, now=self.now)

    def on(self, key):
        self.rows[key].update(state='on', power_w=1000)

    def ack(self, *, settings=None):
        c = self.sent[-1]
        row = self.rows[c['key']]
        row.update(state='off' if c['action']=='shed' else 'on',
            power_w=0 if c['action']=='shed' else 1000,
            context_id=c['command_id'], intent_revision=row['intent_revision']+1,
            state_observed_at=(self.now+timedelta(seconds=1)).isoformat())
        if settings is not None: row['settings'] = settings
        self.guard.update_ack(dict(command_id=c['command_id'], bridge_session='session',
            result='accepted', context_id=c['command_id']))
        self.tick()

    def test_battery_works_with_overload_off_and_excludes_microwave(self):
        self.on('water_pump'); self.on('microwave'); self.tick()
        self.assertEqual(('water_pump', 'battery'), (self.sent[-1]['key'], self.sent[-1]['reason']))
        self.ack()
        for _ in range(40): self.tick()
        self.assertEqual(1, len(self.sent))

    def test_manual_on_soft_band_then_critical_enforced(self):
        self.on('water_pump'); self.tick(); self.ack()
        self.on('water_pump')
        self.rows['water_pump'].update(context_id='family', intent_revision=3)
        self.soc = 45; self.tick()
        self.assertEqual(1, len(self.sent))
        self.soc = 40; self.tick()
        self.assertEqual(2, len(self.sent))
        self.ack()
        self.soc = 55
        self.on('water_pump')
        self.rows['water_pump'].update(context_id='family-again', intent_revision=5)
        self.tick()
        self.assertEqual(2, len(self.sent))

    def test_grid_present_never_battery_sheds(self):
        self.on('water_pump'); self.grid=True; self.soc=30
        for _ in range(10): self.tick()
        self.assertEqual([], self.sent)

    def test_recovery_requires_continuous_battery_and_load_margin(self):
        self.on('water_pump'); self.tick(); self.ack()
        for _ in range(40): self.tick()
        self.soc = 60
        for _ in range(20): self.tick()
        self.assertEqual(1, len(self.sent))
        self.soc = 59; self.tick(); self.soc=60
        for _ in range(30): self.tick()
        self.assertEqual(1, len(self.sent))
        self.tick()
        self.assertEqual('restore', self.sent[-1]['action'])

    def test_grid_return_recovery_before_sixty(self):
        self.on('water_pump'); self.tick(); self.ack()
        self.grid=True
        for _ in range(45): self.tick(mode='panic_grid_hold')
        self.assertEqual('restore', self.sent[-1]['action'])

    def test_missing_soc_blocks_restore_not_overload_stop(self):
        self.on('water_pump'); self.soc=None; self.armed=True
        self.tick(load=90)
        self.assertEqual('overload', self.sent[-1]['reason'])

    def test_native_off_accepts_eco_and_preset_reset_but_no_blind_restore(self):
        self.on('heat_pump_floor_1')
        self.rows['heat_pump_floor_1']['settings']={'eco':'on'}
        self.tick(); self.ack(settings={'eco':'off'})
        self.assertIn('heat_pump_floor_1', self.guard.cycle['owned'])
        self.soc=60
        for _ in range(40): self.tick()
        self.assertEqual(1, len(self.sent))
        self.assertIn('heat_pump_floor_1', self.guard.cycle['owned'])

    def test_smart_heating_hp_restores_eco_at_fifty_before_other_loads(self):
        self.smart = True
        self.on('water_pump')
        self.on('heat_pump_floor_1')
        self.tick()
        self.ack()
        self.tick()
        self.ack(settings={})
        self.soc = 50
        for _ in range(34):
            self.tick()
        command = self.sent[-1]
        self.assertEqual(('heat_pump_floor_1', 'restore', 'eco'),
                         (command['key'], command['action'], command.get('restore_profile')))
        self.assertIn('water_pump', self.guard.cycle['owned'])

    def test_same_state_off_cancels_restoration(self):
        self.on('water_pump'); self.tick(); self.ack()
        self.rows['water_pump']['intent_revision'] += 1
        self.tick(); self.soc=60
        for _ in range(40): self.tick()
        self.assertEqual(1, len(self.sent))

    def test_all_already_off_does_not_spam_completion(self):
        for _ in range(50): self.tick()
        self.assertEqual([], self.sent)
        self.assertEqual(['battery_reserve_warning'], [event['type'] for event in self.guard.events])

    def test_legacy_lock_imported_once_not_relatched_after_recovery(self):
        payload = dict(control_schema=5, observed_at=self.now.isoformat(), bridge_session='session',
            armed=False, battery_control_ready=True,
            legacy_battery_lockout=True, loads=list(self.rows.values()))
        self.guard.update_load_snapshot(payload)
        self.assertTrue(self.guard.battery.locked)
        self.soc=60; self.tick()
        self.assertFalse(self.guard.battery.locked)
        payload['observed_at']=(self.now+timedelta(seconds=1)).isoformat()
        self.guard.update_load_snapshot(payload)
        self.assertFalse(self.guard.battery.locked)
