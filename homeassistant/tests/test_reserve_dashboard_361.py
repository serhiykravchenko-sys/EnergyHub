import json
import unittest
from datetime import datetime
from pathlib import Path
from jinja2 import Environment
from test_presentation import contents

ROOT = Path(__file__).resolve().parents[2]


class ReserveDashboardTests(unittest.TestCase):
    def render(self, phase='charging', source='fresh', auto=True, panic=False, fresh=True, notice=False):
        document=json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        text=next(x for x in contents(document) if 'Battery Reserve Auto:' in x)
        env=Environment()
        env.filters['timestamp_custom']=lambda value, fmt: datetime.fromtimestamp(value).strftime(fmt)
        plan={'target_soc':95,'start':'2026-10-08T10:30:00+03:00','end':'2026-10-08T15:00:00+03:00',
              'source_status':source,'source_checked_at':'2026-10-08T08:00:00+03:00',
              'control_active':phase in ('charging','holding'),
              'emergency_notice_active':notice,'emergency_grid_state':'online'}
        reserve={'reserve_planning_source':'grid_confidence' if source=='suspended' else 'dtek_schedule',
                 'recommendation_status':'ready','recommended_soc':40,'weather_modifier_percent':0}
        values={'sensor.energyhub_outage_preparation':phase,'input_number.ahm_minimum_soc':'40',
                'sensor.energyhub_panic_target_source':'Manual Panic: power-bank reserve' if panic else 'Validated DTEK outage preparation',
                'sensor.energyhub_telemetry_freshness':'fresh' if fresh else 'stale'}
        return env.from_string(text).render(states=lambda key:values.get(key,'unknown'),
            state_attr=lambda entity,key:(plan if entity=='sensor.energyhub_outage_preparation' else reserve).get(key),
            is_state=lambda entity,state: auto and entity=='binary_sensor.energyhub_battery_reserve_auto' and state=='on',
            as_timestamp=lambda value:datetime.fromisoformat(value).timestamp())

    def test_schedule_separates_base_reserve_and_target(self):
        text=self.render()
        self.assertIn('**Current reserve:** 40%',text)
        self.assertIn('**Preparation target:** 95%',text)
        self.assertIn('Scheduled outage preparation',text)
        self.assertIn('Grid charging requested',text)
        self.assertNotIn('Forecast plan:',text)

    def test_emergency_uses_confidence_and_has_no_outage_target(self):
        text=self.render(phase='source_unavailable',source='suspended')
        self.assertIn('Emergency reserve — schedule unavailable',text)
        self.assertNotIn('Preparation target:',text)

    def test_panic_dominates_schedule_presentation(self):
        text=self.render(panic=True)
        self.assertIn('Manual Panic — power-bank mode; target 95%',text)
        self.assertNotIn('Preparation target:',text)
        self.assertNotIn('Base reserve calculation:',text)

    def test_unavailable_evidence_and_actual_charging_are_not_confirmed(self):
        self.assertIn('Schedule evidence is unavailable or stale',self.render(phase='unavailable'))
        self.assertIn('Actual charging is unconfirmed',self.render(fresh=False))

    def test_manual_reserve_remains_selected(self):
        text=self.render(phase='guarded',auto=False)
        self.assertIn('Family-selected reserve',text)
        self.assertIn('**Selected reserve:** 40%',text)
        self.assertIn('Automatic preparation paused',text)

    def test_online_emergency_is_information_and_preparation_remains_active(self):
        text=self.render(notice=True)
        self.assertIn('emergency reserve allowance remains active',text)
        self.assertIn('Usable schedule preparation continues',text)
        self.assertIn('Scheduled outage preparation',text)
        self.assertNotIn('schedule suspended',text)
