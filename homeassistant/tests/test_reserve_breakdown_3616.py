import json
import unittest
from pathlib import Path
from jinja2 import Environment
from test_presentation import contents

ROOT = Path(__file__).resolve().parents[2]


class ReserveBreakdownTests(unittest.TestCase):
    def render(self, scheduled=True, minimum=20, baseline=40, weather=0,
               suspension=0, auto=True, panic=False):
        document = json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        template = next(c for c in contents(document) if 'Battery Reserve Auto:' in c)
        attrs = dict(reserve_planning_source='dtek_schedule' if scheduled else 'grid_confidence',
                     policy_base_soc=minimum, baseline_soc=baseline, recommendation_status='ready',
                     recommended_soc=95, weather_modifier_percent=weather,
                     schedule_suspension_modifier_percent=suspension,
                     grid_confidence='risk', grid_modifier_percent=0 if scheduled else 40,
                     schedule_modifier_percent=20 if scheduled else 0,
                     generation_modifier_percent=0 if scheduled else 20, forecast_deficit=True)
        values = {'input_number.ahm_minimum_soc':'95',
                  'sensor.energyhub_panic_target_source':'Manual Panic: test' if panic else 'Schedule'}
        return Environment().from_string(template).render(
            states=lambda key:values.get(key,'unknown'),
            state_attr=lambda entity,key:attrs.get(key) if entity=='sensor.energyhub_ahm_weather_buffer' else None,
            is_state=lambda entity,state:auto and state=='on')

    def test_schedule_overrides_confidence_and_deficit_without_stacking(self):
        text = self.render()
        self.assertIn('| Minimum BR (setting) | 20%', text)
        self.assertIn('| Schedule | +20 p.p.', text)
        self.assertIn('Grid Confidence is excluded. Energy deficit is handled by night charging.', text)
        self.assertIn('| Grid Confidence | +0 p.p.', text)
        self.assertNotIn('| Forecast deficit |', text)
        self.assertNotIn('Risk (+40%)', text)
        self.assertNotIn('generation: deficit (+20%)', text)

    def test_higher_minimum_weather_and_unknowns_are_reported_from_evidence(self):
        text = self.render(minimum=50, baseline=50, weather=20)
        self.assertIn('| Minimum BR (setting) | 50%', text)
        self.assertIn('| Schedule | +20 p.p.', text)
        self.assertIn('| Weather | +20 p.p.', text)
        self.assertIn('after 95% cap: 90%', text)
        text = self.render(minimum=None, baseline=None, weather=None)
        self.assertIn('| Minimum BR (setting) | Unconfirmed', text)
        self.assertIn('| Emergency / unscheduled outages | +0 p.p.', text)

    def test_suspended_schedule_explains_additional_modifier(self):
        text = self.render(scheduled=False, suspension=20, weather=20)
        self.assertIn('| Grid Confidence | +40 p.p.', text)
        self.assertIn('| Emergency / unscheduled outages | +20 p.p.', text)
        self.assertNotIn('Valid schedule:', text)

    def test_manual_and_panic_do_not_claim_automatic_control(self):
        self.assertIn('calculation is an EH recommendation', self.render(auto=False))
        self.assertNotIn('Base reserve calculation:', self.render(panic=True))

    def test_schedule_emergency_remains_in_schedule_branch(self):
        text=self.render(scheduled=True,suspension=20,weather=20)
        self.assertIn('| Schedule | +20 p.p.',text)
        self.assertIn('| Emergency / unscheduled outages | +20 p.p.',text)
        self.assertIn('published schedule remains usable',text)
        self.assertIn('| Weather | +20 p.p.',text)
        self.assertNotIn('Grid Confidence: Risk (+40%)',text)
