import json
import unittest
from pathlib import Path
from jinja2 import Environment
from test_presentation import contents


class CoverageDashboardTests(unittest.TestCase):
    def render(self, required=122, release=False):
        root=Path(__file__).resolve().parents[2]
        dashboard=json.loads((root/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        text=next(c for c in contents(dashboard) if 'Battery Reserve Auto:' in c)
        plan=dict(window_active=True,remaining_window_minutes=240,coverage_required_soc=required,
                  release_margin_percent=2,coverage_release=release,
                  coverage_reason='Insufficient remaining-window coverage',target_soc=95)
        env=Environment()
        env.filters['timestamp_custom']=lambda value,fmt:'test'
        return env.from_string(text).render(
            states=lambda key:'holding' if key=='sensor.energyhub_outage_preparation' else '40',
            state_attr=lambda entity,key:plan.get(key) if entity=='sensor.energyhub_outage_preparation' else None,
            is_state=lambda entity,state:True,as_timestamp=lambda value:0)

    def test_uncapped_requirement_and_margin_are_visible(self):
        text=self.render()
        self.assertIn('Remaining outage:** 240 min',text)
        self.assertIn('SOC needed to release:** 122%',text)
        self.assertIn('includes 2 p.p. margin',text)
        self.assertIn('Insufficient remaining-window coverage',text)

    def test_release_explains_ordinary_br_and_unknown_requirement(self):
        text=self.render(required=None,release=True)
        self.assertIn('SOC needed to release:** Unconfirmed',text)
        self.assertIn('Ordinary BR resumes after confirmed Solar',text)
