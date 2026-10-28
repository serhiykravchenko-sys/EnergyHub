import json
import unittest
from pathlib import Path
from datetime import datetime
import yaml
from datetime import timedelta
import test_update_3615 as fixture


class QuietBudgetTests(unittest.TestCase):
    setUp=fixture.TemplatesTests.setUp
    render=fixture.TemplatesTests.render
    window=fixture.TemplatesTests.window

    def permits(self,budget,previous=None,desired='on'):
        self.values['switch.first_floor_heat_pump_quiet']='off' if desired=='on' else 'on'
        return self.render(self.script[2]['value_template'],profile='quiet',desired=desired,
            entity='switch.first_floor_heat_pump_quiet',tick=self.now.timestamp(),
            previous=previous or {},quiet_budget=json.loads(json.dumps(budget)),overrides={},window=self.window())

    def test_hour_spacing_and_three_per_night_even_after_off(self):
        self.assertTrue(self.permits({}))
        budget=dict(w=self.window(),n=1,at=self.now.timestamp())
        previous=dict(t='off',n=1,at=self.now.timestamp())
        self.now+=timedelta(minutes=59)
        self.assertFalse(self.permits(budget,previous))
        self.now+=timedelta(minutes=1)
        self.assertTrue(self.permits(budget,previous))
        budget.update(n=3)
        self.assertFalse(self.permits(budget,previous))

    def test_off_always_available_and_midnight_no_reset_next_night_reset(self):
        budget=dict(w=self.window(),n=3,at=self.now.timestamp())
        self.assertTrue(self.permits(budget,desired='off'))
        self.now+=timedelta(hours=2)
        self.assertEqual(budget['w'],self.window())
        self.assertFalse(self.permits(budget))
        self.now+=timedelta(hours=22)
        self.assertTrue(self.permits(budget))

    def test_budget_is_persisted_before_device_command_and_off_cannot_clear_it(self):
        step=self.script[3]
        self.assertIn("desired == 'on'",step['if'])
        self.assertEqual('input_text.energyhub_hp1_quiet_budget',step['then'][0]['target']['entity_id'])
        self.assertTrue(self.script[-1]['action'].startswith('{{'))

    def test_queued_on_is_rejected_at_end_of_night(self):
        self.values.update({'climate.first_floor_heat_pump':'heat',
                            'input_boolean.energyhub_climate_quiet_enabled':'on'})
        condition=self.script[0]['value_template']
        self.assertTrue(self.render(condition,profile='quiet',desired='on'))
        self.now+=timedelta(hours=8,seconds=20)
        self.assertFalse(self.render(condition,profile='quiet',desired='on'))
        self.assertTrue(self.render(condition,profile='quiet',desired='off'))

    def test_early_hp_start_requires_fresh_coverage_and_active_br_margin(self):
        path=Path(__file__).resolve().parents[1]/'live/config/automations.yaml'
        rows=yaml.safe_load(path.read_text(encoding='utf-8'))
        controller=next(r for r in rows if r.get('id')=='energyhub_smart_heating_first_floor')
        condition=next(r['variables']['forecast_hp_start'] for r in controller['actions'] if 'forecast_hp_start' in r.get('variables',{}))
        attrs=dict(hp_start_permitted=True,predicted_minimum_soc=46,checked_at=self.now.isoformat(),forecast_source_at=self.now.isoformat())
        def permits(**kw):
            return self.render(condition,fresh=True,solar_only=kw.get('solar_only',False),soc=46,
                reserve=kw.get('reserve',40),state_attr=lambda e,k:attrs.get(k),
                as_timestamp=lambda v,d=0:datetime.fromisoformat(v).timestamp() if v else d)
        self.assertTrue(permits())
        self.assertFalse(permits(reserve=50))
        self.assertFalse(permits(solar_only=True))
        attrs['checked_at']=(self.now-timedelta(seconds=91)).isoformat()
        self.assertFalse(permits())
