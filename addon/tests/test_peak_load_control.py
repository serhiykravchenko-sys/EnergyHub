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
        self.guard.update_load_snapshot(dict(control_schema=5,
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
        self.now += timedelta(seconds=seconds)
        for row in self.rows.values():
            row['power_observed_at'] = self.now.isoformat()
        self.guard.update_load_snapshot(dict(control_schema=5, observed_at=self.now.isoformat(),
            bridge_session='ha-1', armed=armed, loads=list(self.rows.values())))
        self.guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
            load_percent=percent, load_w=percent*100, now=self.now, **kwargs)

    def on(self, key='water_boiler', power=1000):
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

    def test_no_commands_below_85_or_disarmed(self):
        self.on()
        self.tick(10, 84.9)
        self.tick(10, 90, armed=False)
        self.assertEqual([], self.sent)

    def test_unchanged_power_age_does_not_make_online_switch_unusable(self):
        self.on('water_boiler', 1)
        self.rows['water_boiler']['availability'] = 'online'
        old_power_report = (self.now - timedelta(hours=3)).isoformat()
        self.now += timedelta(seconds=10)
        self.rows['water_boiler']['power_observed_at'] = old_power_report
        self.guard.update_load_snapshot(dict(
            control_schema=5,
            observed_at=self.now.isoformat(),
            bridge_session='ha-1',
            armed=True,
            loads=list(self.rows.values()),
        ))

        self.guard.evaluate(
            telemetry_valid=True,
            telemetry_freshness='fresh',
            load_percent=90,
            load_w=9000,
            now=self.now,
        )

        self.assertEqual('water_boiler', self.sent[-1]['key'])

    def test_missing_or_offline_required_availability_fails_closed(self):
        self.on('heat_pump_floor_2', 1)
        self.rows['heat_pump_floor_2'].pop('availability')
        self.tick(10, 90)
        self.assertEqual([], self.sent)

        self.rows['heat_pump_floor_2']['availability'] = 'unknown'
        self.tick(10, 90)
        self.assertEqual([], self.sent)

        self.rows['heat_pump_floor_2']['availability'] = 'offline'
        self.tick(10, 90)
        self.assertEqual([], self.sent)

    def test_order_and_zero_watt_still_shed(self):
        for key in ORDER:
            self.on(key, 0)
        self.tick(10, 90)
        self.assertEqual('water_pump', self.sent[-1]['key'])
        self.confirm(90)
        self.tick(30, 90)
        self.assertEqual('water_boiler', self.sent[-1]['key'])
        self.confirm(90)
        self.tick(30, 90)
        self.assertEqual('heat_pump_floor_1', self.sent[-1]['key'])

    def test_ownership_only_after_ack_and_power(self):
        self.on()
        self.tick(10, 90)
        self.assertFalse(self.guard.cycle['owned'])
        self.rows['water_boiler']['state']='off'
        self.tick(10, 70)
        self.assertFalse(self.guard.cycle['owned'])
        self.confirm()
        self.assertIn('water_boiler', self.guard.cycle['owned'])

    def test_fresh_switch_transition_confirms_with_unchanged_old_power(self):
        self.on('water_boiler', 1)
        self.tick(10, 90)
        command = self.sent[-1]
        issued = self.now
        self.rows['water_boiler'].update(
            state='off', context_id='ack', power_w=1,
            power_observed_at=(issued-timedelta(hours=2)).isoformat(),
            state_observed_at=(issued+timedelta(seconds=1)).isoformat(),
            intent_revision=1,
        )
        self.guard.update_ack(dict(command_id=command['command_id'], bridge_session='ha-1',
                                   result='accepted', context_id='ack'))
        self.now += timedelta(seconds=10)
        self.guard.update_load_snapshot(dict(control_schema=5, observed_at=self.now.isoformat(),
            bridge_session='ha-1', armed=True, loads=list(self.rows.values())))
        self.guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
            load_percent=45, load_w=4500, now=self.now)
        self.assertIn('water_boiler', self.guard.cycle['owned'])
        event=self.guard.events[-1]
        self.assertEqual(90,event['trigger_load_percent'])
        self.assertEqual(45,event['load_percent'])

    def test_fresh_contradictory_power_rejects_shed_confirmation(self):
        self.on('water_boiler', 1000)
        self.tick(10, 90)
        command = self.sent[-1]
        self.rows['water_boiler'].update(
            state='off', context_id='ack', power_w=900,
            power_observed_at=(self.now+timedelta(seconds=1)).isoformat(),
            state_observed_at=(self.now+timedelta(seconds=1)).isoformat(),
            intent_revision=1,
        )
        self.guard.update_ack(dict(command_id=command['command_id'], bridge_session='ha-1',
                                   result='accepted', context_id='ack'))
        self.tick(10, 45)
        self.assertNotIn('water_boiler', self.guard.cycle['owned'])

    def test_optimistic_off_with_high_power_not_confirmed(self):
        self.on('heat_pump_floor_1')
        self.tick(10, 90)
        c=self.sent[-1]
        self.guard.update_ack(dict(command_id=c['command_id'], bridge_session='ha-1',
            result='accepted', context_id='off-context'))
        self.rows['heat_pump_floor_1'].update(state='off', context_id='off-context')
        self.tick(10, 70)
        self.assertFalse(self.guard.cycle['owned'])

    def test_hysteresis_and_restore_confirmation(self):
        self.on()
        self.tick(10, 90)
        self.confirm()
        for _ in range(4): self.tick(20, 60)
        self.assertEqual(1, len(self.sent))
        for _ in range(18): self.tick(20, 49)
        self.assertEqual('restore', self.sent[-1]['action'])
        self.confirm(65)
        self.assertFalse(self.guard.cycle['owned'])
        self.assertEqual(['load_shed', 'load_restored'], [e['type'] for e in self.guard.events])

    def test_family_same_state_off_request_revokes_ownership(self):
        self.on()
        self.tick(10, 90)
        self.confirm()
        self.rows['water_boiler']['intent_revision'] += 1
        self.tick(20, 49)
        self.assertFalse(self.guard.cycle['owned'])
        for _ in range(5): self.tick(20, 49)
        self.assertEqual(1,len(self.sent))

    def test_passive_settings_refresh_does_not_release_native_hp(self):
        self.on('heat_pump_floor_1')
        self.tick(10, 90)
        self.confirm()
        self.rows['heat_pump_floor_1']['settings']={'temperature':26}
        self.tick(20, 49)
        self.assertIn('heat_pump_floor_1', self.guard.cycle['owned'])

    def test_zero_budget_does_not_block_but_reserve_permission_does(self):
        self.on()
        self.tick(10,90)
        self.confirm()
        self.rows['water_boiler']['restore_budget_w']=0
        self.rows['water_boiler']['restore_allowed']=False
        for _ in range(18): self.tick(20, 49)
        self.assertEqual(1,len(self.sent))
        self.rows['water_boiler']['restore_budget_w']=1000
        self.rows['water_boiler']['restore_allowed']=False
        self.tick(20, 49)
        self.assertEqual(1,len(self.sent))

    def test_stale_snapshot_and_telemetry_never_command(self):
        self.on()
        self.guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
            load_percent=90,load_w=9000,now=self.now+timedelta(seconds=40))
        self.assertEqual([],self.sent)
        self.guard.evaluate(telemetry_valid=False,telemetry_freshness='stale',
            load_percent=90,load_w=9000,now=self.now)
        self.assertEqual([],self.sent)

    def test_gap_resets_recovery(self):
        self.on()
        self.tick(10,90)
        self.confirm()
        self.tick(30, 49)
        self.tick(20, 49)
        self.tick(40, 49)
        self.tick(20, 49)
        self.assertEqual(1,len(self.sent))

    def test_unconfirmed_device_is_skipped_without_stopping_other_shedding(self):
        self.on('water_pump')
        self.on('water_boiler')
        self.tick(10,90)
        self.assertFalse(self.guard.update_ack({'command_id':'wrong'}))
        for _ in range(10): self.tick(10,90)
        self.assertEqual(1,len(self.sent))
        self.assertIsNone(self.guard.fault)
        self.assertEqual('command_outcome_unconfirmed',
                         self.guard.cycle['blocked']['water_pump'])
        self.tick(10, 90)
        self.assertEqual(('water_boiler', 'shed'),
                         (self.sent[-1]['key'], self.sent[-1]['action']))

    def test_pending_restart_quarantines_only_uncertain_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            self.guard.path=path
            self.on()
            self.tick(10,90)
            new=PeakLoadGuardController(self.sent.append,path=path)
            self.assertIsNone(new.fault)
            self.assertIsNone(new.pending)
            self.assertEqual('uncertain_command_after_restart',
                             new.cycle['blocked']['water_boiler'])
            self.assertEqual(1,len(self.sent))

    def test_unknown_participant_is_skipped_during_shedding(self):
        self.rows['water_pump'].update(state='unknown', power_w=None)
        self.on('water_boiler')
        self.tick(10, 90)
        self.assertEqual('load_unavailable', self.guard.cycle['blocked']['water_pump'])
        self.assertEqual('water_boiler', self.sent[-1]['key'])

    def test_unavailable_owned_device_does_not_block_other_restoration(self):
        self.on('water_pump')
        self.on('water_boiler')
        self.tick(10, 90)
        self.confirm(90)
        self.tick(30, 90)
        self.confirm(40)
        self.rows['water_pump'].update(state='unknown', power_w=None)
        for _ in range(17):
            self.tick(20, 40)
        self.assertEqual(('water_boiler', 'restore'),
                         (self.sent[-1]['key'], self.sent[-1]['action']))
        self.assertIn('water_pump', self.guard.cycle['owned'])

    def test_persistence_failure_prevents_command(self):
        self.guard.path=Path('unused.json')
        self.on()
        with patch('app.services.peak_load_control.atomic_write_json',side_effect=OSError):
            self.tick(10,90)
        self.assertEqual([],self.sent)
        self.assertEqual('ownership_journal_write_failed',self.guard.fault)

    def test_duplicate_snapshot_and_ack_do_not_duplicate_action(self):
        self.on()
        self.tick(10,90)
        self.confirm()
        self.assertFalse(self.guard.update_ack({'command_id':self.sent[-1]['command_id']}))
        self.tick(10,70)
        self.assertEqual(1,len(self.sent))

    def test_hp_minimum_off_time(self):
        self.on('heat_pump_floor_1')
        self.tick(10,90)
        self.confirm()
        for _ in range(10): self.tick(20, 49)
        self.assertEqual(1,len(self.sent))
        for _ in range(7): self.tick(20, 49)
        self.assertEqual('restore',self.sent[-1]['action'])

    def test_manual_intent_during_command_prevents_ownership(self):
        self.on()
        self.tick(10,90)
        self.guard.update_intent(dict(context_id='family',keys=['water_boiler']))
        self.confirm()
        self.assertFalse(self.guard.cycle['owned'])

    def test_corrupt_journal_locks_instead_of_resetting_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.json'
            path.write_text(json.dumps(dict(schema=1, stream_id='a', sequence=0,
                events=[], cycle={'owned': {}}, pending=None)))
            guard = PeakLoadGuardController(self.sent.append, path=path)
            self.assertEqual('ownership_journal_unreadable', guard.fault)

    def test_confirmed_ownership_survives_and_old_command_fault_migrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.guard.path = Path(tmp)/'state.json'
            self.on()
            self.tick(10, 90)
            self.confirm()
            new = PeakLoadGuardController(self.sent.append, path=self.guard.path)
            self.assertIn('water_boiler', new.cycle['owned'])
            self.assertIsNone(new.fault)
            self.guard.fault = 'restore_rejected_requires_attention'
            self.guard._persist()
            new = PeakLoadGuardController(self.sent.append, path=self.guard.path)
            self.assertIsNone(new.fault)
            self.assertIn('water_boiler', new.cycle['owned'])

    def test_malformed_intent_and_nonfinite_revision_rejected(self):
        self.assertFalse(self.guard.update_intent(dict(context_id='x', keys=None)))
        self.assertFalse(self.guard.update_intent(dict(context_id='x', keys=['other'])))
        self.on()
        self.rows['water_boiler']['intent_revision'] = float('inf')
        self.tick(10, 90)
        self.assertFalse(self.sent)

    def test_intent_queue_pressure_does_not_permanently_disable_guard(self):
        for index in range(130):
            self.assertTrue(self.guard.update_intent(dict(
                context_id=f'family-{index}', keys=['water_boiler'])))
        self.assertEqual(128, len(self.guard.intents))
        self.assertIsNone(self.guard.fault)

    def test_evicted_family_off_during_shed_never_restores_that_load(self):
        self.on()
        self.tick(10, 90)
        self.guard.update_intent(dict(context_id='family-off', keys=['water_boiler']))
        self.rows['water_boiler']['intent_revision'] += 1
        for index in range(128):
            self.guard.update_intent(dict(
                context_id=f'unrelated-{index}', keys=['microwave']))
        self.assertEqual('external_intent_evicted',
                         self.guard.cycle['blocked']['water_boiler'])
        self.confirm(40)
        for _ in range(18):
            self.tick(20, 40)
        self.assertEqual([('water_boiler', 'shed')],
                         [(command['key'], command['action']) for command in self.sent])

    def test_evicted_family_off_releases_existing_ownership(self):
        self.on()
        self.tick(10, 90)
        self.confirm(40)
        self.guard.update_intent(dict(context_id='family-off', keys=['water_boiler']))
        for index in range(128):
            self.guard.update_intent(dict(
                context_id=f'unrelated-{index}', keys=['microwave']))
        self.assertNotIn('water_boiler', self.guard.cycle['owned'])

    def test_evicted_family_off_during_pending_restore_stops_replay_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            self.guard.path = Path(directory) / 'state.json'
            self.on()
            self.tick(10, 90)
            self.confirm(40)
            for _ in range(18):
                if self.guard.pending:
                    break
                self.tick(20, 40)
            self.assertEqual('restore', self.guard.pending['action'])
            command_count = len(self.sent)
            self.guard.update_intent(dict(context_id='family-off', keys=['water_boiler']))
            for index in range(128):
                self.guard.update_intent(dict(
                    context_id=f'unrelated-{index}', keys=['microwave']))
            self.assertIsNone(self.guard.pending)
            self.assertNotIn('water_boiler', self.guard.cycle['owned'])
            self.assertEqual('external_intent_evicted',
                             self.guard.cycle['blocked']['water_boiler'])
            # The last snapshot is fresh, but predates the family OFF intent.
            self.guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
                load_percent=40, load_w=4000, now=self.now)
            self.assertEqual(command_count, len(self.sent))
            restarted = PeakLoadGuardController(self.sent.append, path=self.guard.path)
            self.assertFalse(restarted.cycle and restarted.cycle['owned'])
            if restarted.cycle:
                self.assertEqual('external_intent_evicted',
                                 restarted.cycle['blocked']['water_boiler'])

    def test_off_uses_85_not_old_trial_thresholds(self):
        self.on()
        for pct in (41, 75, 84.9): self.tick(10, pct, armed=False)
        self.assertFalse(self.guard.events)
        self.tick(10, 85, armed=False)
        self.tick(10, 91, armed=False)
        self.assertEqual(['load_warning'], [e['type'] for e in self.guard.events])
        self.assertFalse(self.sent)
        self.assertEqual('warnings_only', self.guard.status_attributes()['mode'])

    def test_warning_recovery_requires_strict_50_and_continuity(self):
        self.tick(10, 90, armed=False)
        for _ in range(5): self.tick(20, 50, armed=False)
        self.assertEqual(1, len(self.guard.events))
        self.tick(10, 49, armed=False)
        self.tick(40, 49, armed=False)  # Gap restarts confirmation.
        for _ in range(15): self.tick(20, 49, armed=False)
        self.assertEqual('load_warning_cleared', self.guard.events[-1]['type'])
        self.assertFalse(self.sent)

    def test_on_during_warning_uses_current_load_not_old_advice(self):
        self.on()
        self.tick(10, 90, armed=False)
        self.tick(10, 49, armed=True)
        self.assertFalse(self.sent)
        self.assertFalse(self.guard.warning_active)
        self.tick(10, 90, armed=True)
        self.assertEqual('shed', self.sent[-1]['action'])
        self.assertNotIn('load_warning_cleared', [e['type'] for e in self.guard.events])

    def test_off_preserves_ownership_without_restoring(self):
        self.on()
        self.tick(10, 90)
        self.confirm()
        for _ in range(10): self.tick(20, 49, armed=False)
        self.assertIn('water_boiler', self.guard.cycle['owned'])
        self.assertEqual(1, len(self.sent))
        for _ in range(17): self.tick(20, 49, armed=True)
        self.assertEqual('restore', self.sent[-1]['action'])

    def test_off_manual_changes_are_observed_and_not_undone(self):
        self.on()
        self.tick(10, 90)
        self.confirm()
        self.rows['water_boiler']['intent_revision'] += 1
        self.tick(20, 49, armed=False)
        self.assertFalse(self.guard.cycle['owned'])
        for _ in range(6): self.tick(20, 49)
        self.assertEqual(1, len(self.sent))

    def test_off_during_pending_command_confirms_without_more_commands(self):
        self.on()
        self.tick(10, 90)
        command = self.sent[-1]
        self.rows['water_boiler'].update(state='off', power_w=0, context_id='ack',
            state_observed_at=(self.now+timedelta(seconds=1)).isoformat())
        self.guard.update_ack(dict(command_id=command['command_id'], bridge_session='ha-1',
                                   result='accepted', context_id='ack'))
        self.tick(10, 49, armed=False)
        self.assertIn('water_boiler', self.guard.cycle['owned'])
        self.assertEqual(1, len(self.sent))

    def test_no_participant_data_still_warns_from_fresh_inverter(self):
        self.guard = PeakLoadGuardController(self.sent.append, path=None)
        self.guard.evaluate(telemetry_valid=True, telemetry_freshness='fresh',
            load_percent=90, load_w=9000, now=self.now)
        self.assertEqual('load_warning', self.guard.events[-1]['type'])
        self.assertFalse(self.sent)

    def test_old_retained_bridge_cannot_arm(self):
        self.assertFalse(self.guard.update_load_snapshot(dict(control_schema=1,
            observed_at=(self.now+timedelta(seconds=1)).isoformat(), bridge_session='old',
            armed=True, loads=list(self.rows.values()))))

    def test_fault_still_warns_but_never_commands(self):
        self.guard.fault = 'uncertain_command_after_restart'
        self.on()
        self.tick(10, 90)
        self.assertEqual('load_warning', self.guard.events[-1]['type'])
        self.assertFalse(self.sent)

    def test_warning_episode_survives_restart_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.guard.path = Path(tmp)/'state.json'
            self.tick(10, 90, armed=False)
            self.guard = PeakLoadGuardController(self.sent.append, path=self.guard.path)
            self.tick(10, 90, armed=False)
            self.assertEqual(1, len(self.guard.events))

    def test_stale_telemetry_does_not_warn_or_clear(self):
        self.guard.evaluate(telemetry_valid=False, telemetry_freshness='stale',
            load_percent=90, load_w=9000, now=self.now)
        self.assertFalse(self.guard.events)

    def test_runtime_does_not_select_legacy_trial(self):
        source = (Path(__file__).resolve().parents[1]/'app/main.py').read_text(encoding='utf-8')
        self.assertNotIn('PeakLoadGuardDryRun', source)
        self.assertNotIn("options.get('peak_load_control_enabled'", source)

    def test_zero_allowance_sheds_and_restores_with_five_minutes(self):
        self.on()
        self.rows['water_boiler']['restore_budget_w'] = 0
        self.tick(10, 90)
        self.assertNotIn('restore_budget_w', self.sent[-1])
        self.assertEqual(5, self.sent[-1]['control_schema'])
        self.confirm(40)
        self.tick(30, 40)
        for _ in range(14): self.tick(20, 40)
        self.assertEqual(1, len(self.sent))
        self.tick(20, 40)
        self.assertEqual('restore', self.sent[-1]['action'])

    def test_one_minute_between_confirmed_restorations(self):
        self.on('water_pump')
        self.on('water_boiler')
        self.tick(10, 90)
        self.confirm(90)
        self.tick(30, 90)
        self.confirm(40)
        for _ in range(17): self.tick(20, 40)
        self.assertEqual(('water_pump', 'restore'), (self.sent[-1]['key'], self.sent[-1]['action']))
        self.confirm(40)
        for _ in range(2): self.tick(20, 40)
        self.assertEqual(3, len(self.sent))
        self.tick(20, 40)
        self.assertEqual(('water_boiler', 'restore'), (self.sent[-1]['key'], self.sent[-1]['action']))

    def test_stove_cycle_at_50_resets_five_minute_window(self):
        self.on()
        self.tick(10, 90)
        self.confirm(40)
        for _ in range(4):
            for _ in range(12): self.tick(20, 40)
            self.tick(10, 50)
        self.assertEqual(1, len(self.sent))

    def missing_tick(self, seconds=20):
        self.now += timedelta(seconds=seconds)
        self.guard.evaluate(telemetry_valid=False, telemetry_freshness='stale',
                            load_percent=None, load_w=None, now=self.now)

    def test_missing_telemetry_warns_once_and_never_restores(self):
        self.on()
        self.tick(10, 90)
        self.confirm(40)
        for _ in range(15): self.missing_tick()
        self.assertNotIn('restoration_telemetry_missing', [e.get('reason') for e in self.guard.events])
        self.missing_tick()
        for _ in range(10): self.missing_tick()
        notices = [e for e in self.guard.events if e.get('reason') == 'restoration_telemetry_missing']
        self.assertEqual(1, len(notices))
        self.assertEqual([{'key': 'water_boiler'}], notices[0]['affected_loads'])
        self.assertEqual(1, len(self.sent))
        for _ in range(15): self.tick(20, 40)
        self.assertEqual(1, len(self.sent))
        self.tick(20, 40)
        self.assertEqual('restore', self.sent[-1]['action'])

    def test_missing_notice_survives_restart_without_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.guard.path = Path(tmp)/'state.json'
            self.on()
            self.tick(10, 90)
            self.confirm(40)
            for _ in range(16): self.missing_tick()
            self.guard = PeakLoadGuardController(self.sent.append, path=self.guard.path)
            self.missing_tick(20)
            self.assertEqual(1, len([e for e in self.guard.events if e.get('reason') == 'restoration_telemetry_missing']))

    def test_scheduled_same_state_off_releases_ownership_during_missing_data(self):
        self.on()
        self.tick(10, 90)
        self.confirm(40)
        self.guard.update_intent(dict(context_id='scheduled-0100', keys=['water_boiler']))
        self.missing_tick(10)
        self.assertFalse(self.guard.cycle['owned'])
        for _ in range(20): self.tick(20, 40)
        self.assertEqual(1, len(self.sent))

    def test_restored_load_above_50_pauses_then_85_resheds(self):
        self.on()
        self.tick(10, 90)
        self.confirm(40)
        for _ in range(17): self.tick(20, 40)
        self.confirm(80)
        self.tick(20, 80)
        self.assertEqual(2, len(self.sent))
        self.tick(10, 85)
        self.assertEqual('shed', self.sent[-1]['action'])
        self.assertEqual(3, len(self.sent))

    def test_schema_two_does_not_arm_new_policy(self):
        self.assertFalse(self.guard.update_load_snapshot(dict(control_schema=2,
            observed_at=(self.now+timedelta(seconds=1)).isoformat(), bridge_session='old',
            armed=True, loads=list(self.rows.values()))))

    def test_owned_device_data_missing_also_pauses_and_notifies(self):
        self.on()
        self.tick(10, 90)
        self.confirm(40)
        self.rows['water_boiler']['power_w'] = None
        for _ in range(17): self.tick(20, 40)
        self.assertEqual(1, len(self.sent))
        self.assertEqual('restoration_load_unavailable', self.guard.events[-1]['reason'])

    def test_restart_requires_new_full_low_load_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.guard.path = Path(tmp)/'state.json'
            self.on()
            self.tick(10, 90)
            self.confirm(40)
            for _ in range(14): self.tick(20, 40)
            self.guard = PeakLoadGuardController(self.sent.append, path=self.guard.path)
            for _ in range(15): self.tick(20, 40)
            self.assertEqual(1, len(self.sent))
            self.tick(20, 40)
            self.assertEqual('restore', self.sent[-1]['action'])

    def test_inverter_exception_paths_tick_missing_observer(self):
        source = (Path(__file__).resolve().parents[1]/'app/main.py').read_text(encoding='utf-8')
        tail = source[source.rindex('except subprocess.TimeoutExpired:'):]
        self.assertEqual(2, tail.count("peak_load_guard.evaluate(telemetry_valid=False"))


if __name__ == '__main__':
    unittest.main()
