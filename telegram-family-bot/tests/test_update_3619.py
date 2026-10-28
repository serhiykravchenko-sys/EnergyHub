import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app import schedule_sources, source_policy, planning_settings, co_cache, co_morning, soc_interval

NOW = datetime(2026,10,16,16,tzinfo=timezone(timedelta(hours=3)))
NOTICE = ('Укренерго надало команду про застосування екстрених відключень у '
    'Бучанському, Обухівському та Фастівському районах. '
    'В інших районах діють графіки стабілізаційних відключень. '
    'Екстрені відключення будуть скасовані, як тільки отримаємо таку команду від Укренерго.')


class UpdateTests(unittest.TestCase):
    def test_changed_region_heading_and_future_cancellation(self):
        body=('<h2>Відключення світла Київ</h2>Екстрені відключення скасовані.'
            '<h2>Відключення світла Київська область</h2>'
            '<a href="https://www.dtek-krem.com.ua/ua/shutdowns">ДТЕК</a>'
            'Оновлено 16.10.2026 15:59. '+NOTICE+'<h2>FAQ</h2>Не застосовуються.')
        section, at = schedule_sources.pro_context(body,NOW)
        notice = source_policy.parse(section,at.isoformat(),NOW)
        self.assertEqual('emergency',notice['kind'])
        self.assertFalse(notice['cancelled'])
        cfg=SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv')
        from app.dtek_emergency import affected_places
        self.assertEqual(['дача','квартира'],affected_places(notice['text'],cfg))
        with self.assertRaises(ValueError): schedule_sources.pro_context(body+body,NOW)

    def test_planning_settings_do_not_fall_back(self):
        client=SimpleNamespace(state=lambda _: {'state':'unavailable'})
        self.assertIsNone(planning_settings.read(client)['capacity_kwh'])

    def test_cached_co_is_historical_and_never_current_safe(self):
        target=SimpleNamespace(entity='binary_sensor.basement_co_carbon_monoxide',label='Basement CO')
        entities={'sensor.basement_co_co':dict(state='0',last_reported=(NOW-timedelta(hours=6)).isoformat())}
        state={};co_cache.observe(state,[target],entities,NOW)
        client=SimpleNamespace(state=lambda _:dict(state='unavailable'))
        text='\n'.join(co_morning.lines(SimpleNamespace(co_alarms=[target]),client,NOW,state))
        self.assertIn('10:00',text)
        self.assertIn('0 ppm',text)
        self.assertNotIn('показники в нормі',text)
        text='\n'.join(co_morning.lines(SimpleNamespace(co_alarms=[target]),client,NOW+timedelta(days=1),state))
        self.assertIn('останні дані',text)

    def test_net_endpoints_survive_communication_gap_but_known_jump_does_not(self):
        record=soc_interval.begin(NOW,60)
        soc_interval.sample(record,NOW+timedelta(hours=4),53)
        self.assertIn('−1.8',soc_interval.net_line(record,NOW+timedelta(hours=4),53))
        soc_interval.sample(record,NOW+timedelta(hours=4,seconds=30),90)
        self.assertEqual('',soc_interval.net_line(record,NOW+timedelta(hours=4,seconds=30),90))
