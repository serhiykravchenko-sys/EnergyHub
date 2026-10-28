"""Render installed control templates for the observed grid-present SOC defect."""
import unittest
from types import SimpleNamespace
from pathlib import Path
from jinja2.nativetypes import NativeEnvironment
import yaml

ROOT = Path(__file__).resolve().parents[2]


class GridRecoveryTests(unittest.TestCase):
    def setUp(self):
        rows = yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        self.policy = next(r for r in rows if r['id'] == 'energyhub_smart_heating_first_floor')
        self.variables = self.policy['actions'][1]['variables']
        self.branches = self.policy['actions'][2]['choose']
        self.env = NativeEnvironment()

    def render(self, text, **context):
        context.setdefault('states',lambda e:40 if e.endswith('off_soc') else 50)
        return bool(self.env.from_string(text).render(**context))

    def battery(self, grid, soc, fresh=True, paused=False, pending=False, confirmed=True, age=0, window=180):
        on_battery = self.render(self.variables['on_battery'], fresh=fresh, grid=grid)
        attributes = dict(confirmation_seconds=window, transition_pending=pending, checked_at=1000-age)
        confirmed_grid = ('on' if grid > 180 else 'off') if confirmed else 'unknown'
        confirmation_ready = self.render(self.variables['grid_confirmation_ready'],
            fresh=fresh, confirmed_grid=confirmed_grid,
            now=lambda: SimpleNamespace(timestamp=lambda:1000),
            state_attr=lambda e,k: attributes.get(k))
        grid_ready = self.render(self.variables['grid_ready'], grid=grid,
            grid_confirmation_ready=confirmation_ready, confirmed_grid=confirmed_grid)
        stop = self.render(self.branches[4]['conditions'], on_battery=on_battery, soc=soc)
        hold = self.render(self.branches[5]['conditions'], battery_fresh=True,
                           fresh=fresh, on_battery=on_battery, grid_ready=grid_ready,
                           forecast_hp_start=False, soc=soc,
                           is_state=lambda e,v: paused and e.endswith('battery_paused'))
        return stop, hold

    def test_grid_present_does_not_stop_at_40_or_lower(self):
        for soc in (40, 39, 20):
            self.assertEqual((False, False), self.battery(224.1, soc))

    def test_off_grid_stops_at_40_and_holds_until_50(self):
        self.assertEqual((True, False), self.battery(0,40))
        self.assertEqual((False,True), self.battery(0,49,paused=True))
        self.assertEqual((False,False), self.battery(0,50,paused=True))

    def test_grid_return_releases_existing_hold_below_50(self):
        self.assertEqual((False,False), self.battery(220,30,paused=True))
        self.assertEqual((False,True), self.battery(220,30,fresh=False,paused=True))
        # Releasing the hold still passes restart delay and availability/protection gates.
        self.assertIn('hp_age < 300', str(self.branches[-1]))
        self.assertIn('protected or not fresh', str(self.branches[-2]))

    def test_unconfirmed_return_does_not_release_battery_pause(self):
        for changes in (dict(pending=True), dict(confirmed=False), dict(age=31), dict(window=60)):
            with self.subTest(changes=changes):
                self.assertEqual((False,True), self.battery(220,30,paused=True,**changes))
        # Critical battery shutdown still uses raw voltage and does not wait.
        self.assertEqual((True,False), self.battery(0,40,pending=True,confirmed=False))

    def test_low_soc_start_waits_for_grid_or_independent_recovery(self):
        condition = self.branches[-2]['conditions']
        for grid_ready,soc,forecast,wait in ((False,49,False,True),
                (True,49,False,False),(False,50,False,False),(False,49,True,False)):
            with self.subTest(grid_ready=grid_ready,soc=soc,forecast=forecast):
                self.assertEqual(wait,self.render(condition,night_stop=False,
                    hp_available=True,protected=False,fresh=True,solar_only=False,
                    is_state=lambda e,v: e=='climate.first_floor_heat_pump' and v=='off',
                    grid_ready=grid_ready,soc=soc,forecast_hp_start=forecast))

    def test_invalid_thresholds_never_allow_solar_operation(self):
        for start,pause,expected in ((600,400,True),(400,600,False),(400,400,False),
                                     (None,400,False),(600,None,False),(10001,400,False)):
            valid=self.render(self.variables['solar_thresholds_valid'],solar_start_w=start,solar_pause_w=pause)
            self.assertEqual(expected,valid)
            if not valid:
                self.assertFalse(self.render(self.variables['solar_inputs_ready'],fresh=True,
                    solar_thresholds_valid=valid,states=lambda e:'solar'))

    def test_helper_values_restore_instead_of_resetting_on_restart(self):
        package=yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))
        for key in ('energyhub_solar_start_power','energyhub_solar_pause_power'):
            self.assertNotIn('initial',package['input_number'][key])
        seed=next(r for r in package['automation'] if r['id']=='energyhub_initialize_installation')
        text=seed['actions'][2]['if'][0]['value_template']
        self.assertTrue(self.render(text,states=lambda e:'0'))
        self.assertFalse(self.render(text,states=lambda e:'800' if 'start' in e else '500'))
