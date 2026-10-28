import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app import outage_schedule


class MissingTomorrowTests(unittest.TestCase):
    def test_missing_tomorrow_does_not_describe_today_as_fallback(self):
        now = datetime(2026, 10, 16, 21, tzinfo=ZoneInfo('Europe/Kyiv'))
        config = SimpleNamespace(ahm_minimum_soc_entity='reserve')
        client = SimpleNamespace(state=lambda _: {'state': '40'})
        document = dict(source_status='fresh', validated=True,
                        checked_at=now.isoformat(), dates=['2026-10-16'])
        item = dict(kind='dtek_tomorrow_missing', day='2026-10-17')
        state = dict(dtek_snapshot=document)
        text = outage_schedule.evening_text(config, client, state, now, item)
        self.assertIn('На сьогодні графік підтверджено', text)
        self.assertIn('сама по собі не підвищує', text)
        self.assertNotIn('останні 48 годин', text)
        for changes in ({'source_status': 'suspended'},
                        {'checked_at': (now-timedelta(hours=1)).isoformat()},
                        {'dates': []}):
            with self.subTest(changes=changes):
                state['dtek_snapshot'] = dict(document, **changes)
                text = outage_schedule.evening_text(config, client, state, now, item)
                self.assertNotIn('На сьогодні графік підтверджено', text)
                self.assertIn('останні 48 годин', text)
