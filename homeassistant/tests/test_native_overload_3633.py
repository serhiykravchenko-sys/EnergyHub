import json
import unittest
from native_overload_fixture import Runner


class NativeOverloadTests(unittest.TestCase):
    def setUp(self):
        self.r = Runner()

    def ons(self):
        return [(at, entity) for at, action, entity in self.r.commands if action == 'switch.turn_on']

    def test_five_minutes_then_microwave_first_and_one_minute_steps(self):
        self.r.shutdown(); self.r.load(20)
        self.r.advance(299); self.assertEqual([], self.ons())
        self.r.advance(1); self.assertEqual([(300, self.r.plugs['microwave'])], self.ons())
        self.r.advance(60); self.assertEqual(self.r.plugs['water_pump'], self.ons()[1][1])
        self.r.advance(240)
        self.assertEqual(list(self.r.plugs.values()), [entity for _, entity in self.ons()])
        self.assertEqual('idle', self.r.state['input_select.energyhub_overload_phase'])

    def test_initial_manual_off_is_not_restored(self):
        boiler = self.r.plugs['water_boiler']; self.r.state[boiler] = 'off'
        self.r.shutdown(); self.r.load(20); self.r.advance(600)
        self.assertNotIn(boiler, [entity for _, entity in self.ons()])

    def test_stove_cycle_at_50_resets_continuous_window(self):
        self.r.shutdown(); self.r.load(20); self.r.advance(240)
        self.r.load(50); self.r.advance(1); self.r.load(20)
        self.r.advance(299); self.assertFalse(self.ons())
        self.r.advance(1); self.assertEqual(1, len(self.ons()))

    def test_80_during_restore_cancels_delay_and_retries_after_three_minutes(self):
        self.r.shutdown(); self.r.load(20); self.r.advance(420)
        self.assertEqual(3, len(self.ons()))
        original = self.r.state['input_text.energyhub_overload_saved']
        self.r.load(80)
        self.assertTrue(all(self.r.state[e] == 'off' for e in self.r.plugs.values()))
        self.assertEqual(original, self.r.state['input_text.energyhub_overload_saved'])
        self.r.load(20); self.r.advance(179); self.assertEqual(3, len(self.ons()))
        self.r.advance(1); self.assertEqual(self.r.plugs['microwave'], self.ons()[-1][1])

    def test_jump_to_95_during_restore_is_also_interrupted(self):
        self.r.shutdown(); self.r.load(20); self.r.advance(300)
        self.r.load(95); self.assertEqual('retry', self.r.state['input_select.energyhub_overload_phase'])
        self.r.advance(60); self.assertEqual(1, len(self.ons()))

    def test_restart_keeps_snapshot_but_restarts_wait(self):
        self.r.shutdown(); self.r.load(20); self.r.advance(240)
        original = self.r.state['input_text.energyhub_overload_saved']; self.r.restart()
        self.r.advance(299); self.assertFalse(self.ons())
        self.r.advance(1); self.assertTrue(self.ons())
        self.assertEqual(original, self.r.state['input_text.energyhub_overload_saved'])

    def test_unknown_load_cannot_qualify_recovery(self):
        self.r.shutdown(); self.r.load('unavailable'); self.r.advance(600)
        self.assertFalse(self.ons())

    def test_battery_block_allows_only_microwave_then_restores_when_released(self):
        self.r.shutdown(); self.r.state['input_boolean.energyhub_battery_plugs_blocked'] = 'on'
        self.r.load(20); self.r.advance(600)
        self.assertEqual([self.r.plugs['microwave']], [entity for _, entity in self.ons()])
        self.r.state['input_boolean.energyhub_battery_plugs_blocked'] = 'off'
        self.r.advance(700)
        self.assertEqual(set(self.r.plugs.values()), {entity for _, entity in self.ons()})

    def test_battery_snapshot_inherits_original_on_from_active_overload(self):
        self.r.state[self.r.plugs['water_boiler']] = 'off'
        self.r.shutdown(); self.r.start('script.energyhub_battery_save_and_stop'); self.r.pump()
        saved = json.loads(self.r.state['input_text.energyhub_battery_plug_saved'])
        self.assertTrue(saved['water_pump']); self.assertFalse(saved['water_boiler'])

    def test_overload_snapshot_inherits_battery_owned_off(self):
        self.r.start('script.energyhub_battery_save_and_stop'); self.r.pump(); self.r.shutdown()
        saved = json.loads(self.r.state['input_text.energyhub_overload_saved'])
        self.assertTrue(all(saved.values()))

    def test_helpers_restore_state_without_forced_initial_values(self):
        for domain in ('input_select', 'input_text', 'input_boolean'):
            for config in self.r.package[domain].values():
                self.assertNotIn('initial', config)

    def test_off_has_no_grid_or_hp1_or_fridge_dependency(self):
        text = str(self.r.package['script']['energyhub_overload_shutdown'])
        for excluded in ('grid_confirmed', 'grid_voltage', 'climate.', 'fridge', 'first_floor'):
            self.assertNotIn(excluded, text)

    def test_retry_window_resets_on_a_stove_pulse_at_50(self):
        self.r.shutdown(); self.r.load(20); self.r.advance(300); self.r.load(80)
        self.r.load(20); self.r.advance(120); self.r.load(50)
        self.r.advance(1); self.r.load(20); self.r.advance(179)
        self.assertEqual(1,len(self.ons()))
        self.r.advance(1); self.assertEqual(2,len(self.ons()))

    def test_next_on_waits_if_load_is_between_50_and_80(self):
        self.r.shutdown(); self.r.load(20); self.r.advance(300)
        self.r.load(60); self.r.advance(120); self.assertEqual(1,len(self.ons()))
        self.r.load(20); self.assertEqual(2,len(self.ons()))

    def test_cached_release_cannot_restore_below_battery_threshold_after_restart(self):
        self.r.shutdown()
        self.r.state['binary_sensor.energyhub_grid_confirmed']='off'
        self.r.state['sensor.powmr_10_2m_grid_voltage']='0'
        self.r.state['sensor.powmr_10_2m_battery_soc']='35'
        self.r.load(20); self.r.advance(600)
        self.assertEqual([self.r.plugs['microwave']],[entity for _,entity in self.ons()])

    def test_battery_shutdown_interrupts_active_on_sequence(self):
        self.r.shutdown(); self.r.load(20); self.r.advance(300)
        self.r.start('script.energyhub_battery_save_and_stop'); self.r.pump()
        self.r.advance(120)
        self.assertEqual(1,len(self.ons()))
        self.assertTrue(all(self.r.state[e]=='off' for key,e in self.r.plugs.items() if key!='microwave'))

    def test_all_package_templates_compile(self):
        def walk(value):
            if isinstance(value,dict):
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
            elif isinstance(value,str) and ('{{' in value or '{%' in value):
                self.r.env.from_string(value)
        walk(self.r.package)


class FridgeMemoryTests(unittest.TestCase):
    def setUp(self):
        import yaml
        from native_overload_fixture import ROOT
        rows=yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        self.rule=next(a for a in rows if a['id']=='energyhub_fridge_battery_protection')
        self.r=Runner()
        self.r.state['input_boolean.energyhub_fridge_owned_off']='off'

    def run_branch(self,index):
        from native_overload_fixture import Halt
        try:
            list(self.r.sequence(self.rule['actions'][-1]['choose'][index]['sequence'],{}))
        except Halt:
            pass

    def test_originally_off_fridge_has_no_restore_ownership(self):
        branch=self.rule['actions'][-1]['choose'][1]
        self.assertFalse(self.r.conditions(branch['conditions'][1:],{}))

    def test_owned_off_restores_and_releases_memory(self):
        self.r.state['switch.first_floor_hp_meter']='on';self.run_branch(0)
        self.assertEqual('on',self.r.state['input_boolean.energyhub_fridge_owned_off'])
        self.run_branch(1)
        self.assertEqual('on',self.r.state['switch.first_floor_hp_meter'])
        self.assertEqual('off',self.r.state['input_boolean.energyhub_fridge_owned_off'])

    def test_unavailable_fridge_keeps_pending_ownership(self):
        self.r.state['switch.first_floor_hp_meter']='unavailable'
        self.r.state['input_boolean.energyhub_fridge_owned_off']='on'
        self.run_branch(1)
        self.assertFalse(self.r.commands)
        self.assertEqual('on',self.r.state['input_boolean.energyhub_fridge_owned_off'])
