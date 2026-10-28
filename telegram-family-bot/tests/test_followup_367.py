import json
import unittest
from datetime import datetime,timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import Mock
from app import source_policy,apartment_grid,outage_schedule,co_morning
from app.main import notification_chat

NOW=datetime(2026,10,9,12,tzinfo=ZoneInfo('Europe/Kyiv'))
CFG=SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv',
                    apartment_grid_proxy_entity='light.test',apartment_grid_cloud_enabled=True)


class FollowupTests(unittest.TestCase):
    def test_fault_without_schedule_phrase_suspends_both_places(self):
        notice=source_policy.parse('Через атаку на Київщині зафіксовані аварійні відключення у Фастівському та Обухівському районах.',NOW.isoformat(),NOW)
        state={}; source_policy.apply(state,notice,CFG,NOW)
        for place in ('дача','квартира'): self.assertTrue(source_policy.suspended(state,place))
        resumed=source_policy.parse('На Київщині діють стабілізаційні відключення.',(NOW+timedelta(hours=1)).isoformat(),NOW)
        source_policy.apply(state,resumed,CFG,NOW)
        for place in ('дача','квартира'): self.assertFalse(source_policy.suspended(state,place))

    def test_other_district_and_historical_advice_do_not_activate(self):
        notice=source_policy.parse('Застосовані екстрені відключення у Броварському районі.',NOW.isoformat(),NOW)
        state={};source_policy.apply(state,notice,CFG,NOW)
        self.assertFalse(source_policy.suspended(state,'дача'))
        self.assertIsNone(source_policy.parse('Щоб уникнути аварійних відключень, заощаджуйте електроенергію.',NOW.isoformat(),NOW))

    def test_poll_slots_midnight_and_exact_slot(self):
        for minute,expected in [(0,10),(9,10),(10,40),(39,40)]:
            self.assertEqual(expected,outage_schedule.next_poll(NOW.replace(minute=minute)).minute)
        self.assertEqual(NOW.replace(hour=13,minute=10),outage_schedule.next_poll(NOW.replace(minute=40)))
        self.assertEqual(0,outage_schedule.next_poll(NOW.replace(hour=23,minute=58)).hour)

    def test_cloud_gaps_do_not_qualify_offline_and_known_transitions_debounce(self):
        state={};client=Mock()
        def sample(online,seconds):
            at=NOW+timedelta(seconds=seconds)
            state['apartment_cloud_sample']=dict(online=online,checked_at=at.isoformat())
            apartment_grid.observe(CFG,client,state,at)
        sample(False,0);sample(False,180)
        self.assertFalse(state.get('pending_notifications'))
        sample(True,200);sample(True,260)
        self.assertTrue(state['apartment_grid']['online'])
        sample(False,300);sample(False,360);sample(False,420)
        self.assertFalse(state['apartment_grid']['online'])
        self.assertEqual('apartment_grid',state['pending_notifications'][0]['kind'])
        state=json.loads(json.dumps(state))
        sample(True,500);sample(True,560)
        self.assertTrue(state['apartment_grid']['online'])
        self.assertIn('відновився',state['pending_notifications'][1]['message'])

    def test_failed_cloud_read_is_unknown_not_outage(self):
        state={'apartment_grid':dict(entity='light.test',online=True,candidate=False,since=NOW.isoformat())}
        apartment_grid.observe(CFG,Mock(),state,NOW)
        self.assertTrue(state['apartment_grid']['online'])
        self.assertNotIn('candidate',state['apartment_grid'])

    def test_private_diagnostics_routing(self):
        config=SimpleNamespace(technical_chat_id='personal',destination_chat_id='family')
        for kind in ('hp_eco_change','technical_apartment_cloud','technical_dtek_source'):
            self.assertEqual('personal',notification_chat(config,kind))
        self.assertEqual('family',notification_chat(config,'dtek_preparation'))

    def test_restoration_uses_preparation_target_not_base_reserve(self):
        start=NOW+timedelta(hours=6);end=start+timedelta(hours=4)
        row=dict(start=start.isoformat(),end=end.isoformat())
        state={'dtek_snapshot':dict(validated=True,source_status='fresh',checked_at=NOW.isoformat(),groups={'1.1':[row]})}
        client=Mock();client.state.return_value=dict(attributes=dict(row,target_soc=80,checked_at=NOW.isoformat()))
        config=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1')
        text=outage_schedule.recovery_plan(config,client,state,NOW)
        self.assertIn('80%',text);self.assertIn('18:00',text);self.assertNotIn('40%',text)
        self.assertNotIn('сонц',text)  # Wording also works at night.

    def test_charging_requires_ack_and_reports_estimated_grid_contribution(self):
        attrs=dict(phase='charging',target_soc=80,current_soc=65,capacity_kwh=16,required_grid_kwh=2.4,
                   checked_at=NOW.isoformat(),start=(NOW+timedelta(hours=2)).isoformat(),end=(NOW+timedelta(hours=6)).isoformat(),
                   outage_forecast_complete=True,outage_credited_solar_kwh=1,acknowledged=False)
        client=Mock();client.state.return_value=dict(state='charging',attributes=attrs)
        from grid_fixture_3623 import qualify
        original_row=client.state.return_value
        client.state=lambda entity: original_row
        qualify(client,NOW)
        self.assertEqual('',outage_schedule.preparation_line(client,NOW))
        attrs['acknowledged']=True
        attrs['observed_charge_a']=10
        text=outage_schedule.preparation_line(client,NOW)
        self.assertIn('65% → 80%',text);self.assertNotIn('прогноз',text)
        attrs.update(phase='holding',current_soc=80)
        original_row['state']='holding'
        text=outage_schedule.preparation_line(client,NOW)
        self.assertIn('готова',text);self.assertNotIn('Використовуємо ДТЕК',text)

    def test_co_summary_normal_alarm_and_missing(self):
        target=SimpleNamespace(entity='binary_sensor.basement_co_carbon_monoxide',label='Підвал')
        config=SimpleNamespace(co_alarms=[target])
        rows={target.entity:'off','sensor.basement_co_co':'0','sensor.basement_co_battery':'94'}
        client=Mock();client.state.side_effect=lambda entity:dict(state=rows.get(entity),last_updated=NOW.isoformat())
        text='\n'.join(co_morning.lines(config,client,NOW))
        self.assertIn('в нормі',text);self.assertIn('94%',text)
        rows[target.entity]='on'
        self.assertIn('тривога','\n'.join(co_morning.lines(config,client,NOW)))
        client.state.return_value={};client.state.side_effect=None
        self.assertNotIn('в нормі','\n'.join(co_morning.lines(config,client,NOW)))

    def test_apartment_history_does_not_project_stale_offline_status(self):
        from app import apartment_grid
        from unittest.mock import patch
        state={'apartment_grid': {'online':False,'events':[{'online':False,'at':(NOW-timedelta(hours=1)).isoformat()}]}}
        with patch('app.outage_schedule.context',return_value='expected restoration') as context:
            text='\n'.join(apartment_grid.morning_lines(state,NOW,'2.2'))
            context.assert_not_called()
            self.assertNotIn('expected restoration',text)
            state['apartment_cloud_sample']={'online':False,'checked_at':NOW.isoformat()}
            apartment_grid.morning_lines(state,NOW,'2.2')
            context.assert_called_once()
