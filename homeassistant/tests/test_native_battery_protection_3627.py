"""Offline policy/bridge checks; physical switching needs attended commissioning."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[2]
ENTITY = 'automation.energyhub_battery_discharge_protection'
TARGETS = {'switch.water_pump_plug_switch', 'switch.water_boiler_plug_switch',
           'switch.second_floor_heat_pump_plug', 'switch.third_floor_heat_pump_plug_switch'}


class NativeProtectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        cls.by_id = {str(row['id']): row for row in cls.rows}
        cls.rule = cls.by_id['energyhub_battery_discharge_protection']

    def test_strict_crossings_and_grid_events_without_hidden_timers(self):
        low, high = self.rule['triggers'][:2]
        self.assertEqual(40, low['below'])
        self.assertEqual(50, high['above'])
        self.assertEqual('numeric_state', low['trigger'])
        self.assertEqual('numeric_state', high['trigger'])
        self.assertNotIn('value_template', low)
        self.assertNotIn('for', low)
        self.assertNotIn('initial_state', self.rule)  # Restore owner enable selection.
        self.assertEqual({'on','off'}, {t['to'] for t in self.rule['triggers']
                         if t.get('entity_id')=='binary_sensor.energyhub_grid_confirmed'})
        self.assertEqual('{{ grid_valid }}', self.rule['actions'][2]['value_template'])

    def test_both_branches_target_all_four_even_with_mixed_manual_states(self):
        branches = self.rule['actions'][-1]['choose']
        self.assertEqual('script.energyhub_battery_save_and_stop',branches[0]['sequence'][0]['action'])
        self.assertEqual('script.energyhub_battery_restore_saved',branches[1]['sequence'][-1]['action'])

    def test_soc_restoration_cannot_cancel_active_or_stale_overload_evidence(self):
        from native_overload_fixture import Runner
        r = Runner(); r.shutdown(); r.state['sensor.powmr_10_2m_load']='20'
        r.start('script.energyhub_battery_restore_saved'); r.pump()
        self.assertFalse([cmd for cmd in r.commands if cmd[1]=='switch.turn_on'])
        self.assertNotIn('sensor.energyhub_peak_load_guard',str(self.rule))

    def test_old_restore_and_timer_writers_are_absent_for_migrated_hp_plugs(self):
        for ident in ('1784300000102', '1783103977336'):
            self.assertNotIn(ident, self.by_id)
        self.assertNotIn('1784300000101', self.by_id)
        self.assertNotIn('energyhub_heat_pump_restart_restore', self.by_id)
        for filename, removed in [('timer', 'floor_2_heat_pump_auto_off'),
                                  ('input_number','input_number_floor2_heat_pump_timer_hours')]:
            data = json.loads((ROOT/'homeassistant/live/storage'/filename).read_text(encoding='utf-8'))
            self.assertNotIn(removed, {row['id'] for row in data['data']['items']})

    def test_mission_control_uses_actual_automation_without_duplicate_helper(self):
        dashboard = json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        def walk(n):
            if isinstance(n,dict):
                yield n
                for v in n.values(): yield from walk(v)
            elif isinstance(n,list):
                for v in n: yield from walk(v)
        buttons = [n for n in walk(dashboard) if n.get('type')=='button' and n.get('entity')==ENTITY]
        self.assertEqual(1,len(buttons))
        self.assertEqual('Захист розеток · 40–50%',buttons[0]['name'])
        self.assertEqual('toggle',buttons[0]['tap_action']['action'])
        source = (ROOT/'homeassistant/live/config/configuration.yaml').read_text(encoding='utf-8')
        for old in ('energyhub_water_boiler_soc_lockout','energyhub_heat_pump_soc_lockout'):
            self.assertNotIn(old,source)
