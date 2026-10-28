"""Regression: unchanged entity timestamps are not telemetry heartbeats.

Execute the actual automation wait/actions on the offline virtual clock. This
does not replace HA Core validation or attended physical switching checks.
"""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from native_overload_fixture import Runner
import test_grid_aware_battery_3627 as battery_tests

SOC, GRID, VOLT = battery_tests.SOC, battery_tests.GRID, battery_tests.VOLT


class BatteryFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        battery_tests.GridBatteryTests.setUpClass()

    def setup_rule(self, *, soc=39, grid='off', checked_age=0,
                   cause='low_soc', before='40', fresh='fresh'):
        self.rule = battery_tests.GridBatteryTests.by_id['energyhub_battery_discharge_protection']
        self.r = Runner()
        self.base = datetime(2026, 10, 25, 18, tzinfo=timezone.utc)
        self.checked = self.base.timestamp() - checked_age
        self.r.state.update({SOC: str(soc), GRID: grid, VOLT: '0' if grid == 'off' else '230',
                             'sensor.energyhub_telemetry_freshness': fresh})
        self.attrs = {'confirmation_seconds': 180, 'transition_pending': False}
        self.r.env.globals.update(
            now=lambda: self.base + timedelta(seconds=self.r.now),
            state_attr=lambda entity, key: (self.checked if key == 'checked_at'
                                            else self.attrs.get(key)) if entity == GRID else entity)
        self.trigger = SimpleNamespace(id=cause,
            from_state=SimpleNamespace(state=before),
            to_state=SimpleNamespace(state=str(soc) if cause.endswith('soc') else grid))

    def launch(self):
        ctx = {'trigger': self.trigger}
        for key, value in self.rule['variables'].items():
            ctx[key] = self.r.render(value, ctx)
        if not self.r.conditions(self.rule['conditions'], ctx):
            return False
        self.r.package['script']['correction'] = {
            'variables': ctx, 'sequence': self.rule['actions']}
        self.r.start('script.correction')
        self.r.pump()
        return True

    def off_commands(self):
        return [entity for _, action, entity in self.r.commands if action == 'switch.turn_off']

    def test_long_unchanged_zero_voltage_and_soc_allow_real_crossing(self):
        # No State.last_reported accessor exists in this runner. Freshness must
        # come from timestamped confirmed-grid checks, not unchanged values.
        self.setup_rule()
        self.assertTrue(self.launch())
        self.assertEqual(4, len(self.off_commands()))
        self.assertEqual('on', self.r.state['input_boolean.energyhub_battery_plugs_blocked'])

    def test_rejected_evidence_is_rechecked_without_another_soc_crossing(self):
        self.setup_rule(checked_age=90)
        self.launch()
        self.assertFalse(self.r.commands)
        self.r.advance(20)
        self.checked = (self.base + timedelta(seconds=self.r.now)).timestamp()
        self.r.pump()
        self.assertEqual(4, len(self.off_commands()))

    def test_timeout_does_not_act_on_stale_evidence(self):
        self.setup_rule(checked_age=90)
        self.launch()
        self.r.advance(120)
        self.assertFalse(self.r.commands)
        self.assertNotIn('script.correction', self.r.tasks)

    def test_grid_return_while_waiting_cancels_old_off_intent(self):
        self.setup_rule(checked_age=90)
        self.launch()
        self.r.state.update({GRID: 'on', VOLT: '230'})
        self.checked = self.base.timestamp()
        self.r.pump()
        self.assertFalse(self.r.commands)

    def test_soc_recovery_while_waiting_cancels_old_off_intent(self):
        self.setup_rule(checked_age=90)
        self.launch()
        self.r.state[SOC] = '42'
        self.checked = self.base.timestamp()
        self.r.pump()
        self.assertFalse(self.r.commands)

    def test_partial_manual_off_state_stays_off_after_saved_recovery(self):
        self.setup_rule()
        boiler = self.r.plugs['water_boiler']
        self.r.state[boiler] = 'off'
        self.launch()
        # Group OFF commands are idempotent; the snapshot, not the command
        # target list, must preserve a plug that was already manually OFF.
        self.assertEqual(4, len(self.off_commands()))
        self.r.state.update({GRID: 'on', VOLT: '230',
                             'input_boolean.energyhub_battery_plugs_blocked': 'off',
                             'sensor.powmr_10_2m_load': '20'})
        self.r.start('script.energyhub_battery_restore_saved')
        self.r.pump()
        self.assertEqual('off', self.r.state[boiler])

    def test_recovery_of_unknown_sensor_never_creates_on_event(self):
        for before in ['unknown', 'unavailable']:
            self.setup_rule(soc=67, cause='recovered_soc', before=before)
            self.assertFalse(self.launch())
            self.assertFalse(self.r.commands)

    def test_stale_pending_or_contradictory_evidence_never_switches(self):
        for case in ['freshness', 'pending', 'voltage', 'future_check']:
            self.setup_rule()
            if case == 'freshness':
                self.r.state['sensor.energyhub_telemetry_freshness'] = 'stale'
            elif case == 'pending':
                self.attrs['transition_pending'] = True
            elif case == 'voltage':
                self.r.state[VOLT] = '230'
            else:
                self.checked += 1000
            self.launch()
            self.r.advance(120)
            self.assertFalse(self.r.commands, case)

    def test_both_rules_use_bounded_dynamic_wait_and_recheck(self):
        for ident in ['energyhub_battery_discharge_protection', 'energyhub_fridge_battery_protection']:
            rule = battery_tests.GridBatteryTests.by_id[ident]
            self.assertEqual('restart', rule['mode'])
            wait = rule['actions'][0]
            self.assertEqual('00:02:00', wait['timeout'])
            self.assertIs(False, wait['continue_on_timeout'])
            self.assertNotIn('last_reported', str(rule['variables']))
            self.assertNotIn('grid_state', wait['wait_template'])
            self.assertEqual(rule['variables'], rule['actions'][1]['variables'])
            self.assertEqual('{{ grid_valid }}', rule['actions'][2]['value_template'])


if __name__ == '__main__':
    unittest.main()
