import copy
import json
import unittest
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import Mock,patch
from zoneinfo import ZoneInfo
from app import source_policy,outage_schedule as dtek,restoration_messages,hp_eco,soc_interval
from app.schedule_context import loss_context,delivery_gate
from app.main import deliver_pending_notifications

NOW=datetime(2026,10,17,16,50,tzinfo=ZoneInfo('Europe/Kyiv'))


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_apartment_group='2.2',
            dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv',battery_soc_entity='soc',
            ahm_minimum_soc_entity='reserve',operating_mode_entity='mode',grid_voltage_entity='voltage',
            telemetry_freshness_entity='fresh',weather_buffer_entity='weather',destination_chat_id='family',
            technical_chat_id='owner',timezone='Europe/Kyiv')
        self.interval=dict(start=NOW.replace(hour=15,minute=0).isoformat(),end=NOW.replace(hour=19,minute=0).isoformat())
        self.document=dict(schema=1,validated=True,source='pro_kyiv',source_status='fresh',
            checked_at=NOW.isoformat(),dates=[NOW.date().isoformat()],groups={'1.1':[self.interval],'2.2':[self.interval]},
            source_url='https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/')
        self.state=dict(dtek_raw_snapshot=self.document,dtek_snapshot=self.document)
        self.rows={'soc':dict(state='89'),'reserve':dict(state='60'),'mode':dict(state='panic'),
                   'fresh':dict(state='fresh'),'voltage':dict(state='230')}
        self.client=SimpleNamespace(state=lambda key:self.rows.get(key))

    def activate(self):
        text='За командою Укренерго діють екстрені відключення у Фастівському та Обухівському районах.'
        notice=source_policy.parse(text,(NOW-timedelta(hours=1)).isoformat(),NOW-timedelta(hours=1))
        source_policy.apply(self.state,notice,self.cfg,NOW-timedelta(hours=1),self.document)

    def apply(self,text):
        notice=source_policy.parse(text,NOW.isoformat(),NOW)
        if notice:source_policy.apply(self.state,notice,self.cfg,NOW,self.document)
        return notice

    def test_remaining_districts_clear_old_household_emergency(self):
        self.activate()
        notice=self.apply('У частині Бучанського району зникло світло через локальну аварію в мережі. В решті районів за наказом НЕК Укренерго 17.10 діють стабілізаційні відключення електроенергії.')
        for place in ['дача','квартира']:self.assertFalse(source_policy.suspended(self.state,place))
        self.assertEqual('fault',notice['district_statuses']['Bucha']['kind'])
        authority=source_policy.authority(self.document,self.state,NOW)
        self.assertTrue(authority['emergency_notice_confirmed_clear'])
        self.assertFalse(authority['emergency_notice_active'])
        text=source_policy.notification_text(self.cfg,self.state,NOW)
        self.assertIn('стабілізаційні',text)
        self.assertIn('Екстрені відключення скасовано',text)
        self.assertFalse(source_policy.suspended(json.loads(json.dumps(self.state)),'дача'))

    def test_missing_or_other_local_notice_does_not_clear_household_emergency(self):
        self.activate()
        for text in ['', 'У Бучанському районі сталася локальна аварія.','У деяких районах діють стабілізаційні відключення.']:
            self.apply(text)
            self.assertTrue(source_policy.suspended(self.state,'дача'))

    def test_explicit_all_districts_stabilization_clears_and_deduplicates(self):
        self.activate()
        self.apply('В усіх районах діють стабілізаційні відключення.')
        self.assertFalse(source_policy.suspended(self.state,'квартира'))
        count=len(self.state['pending_notifications'])
        self.apply('В усіх районах діють стабілізаційні відключення.')
        self.assertEqual(count,len(self.state['pending_notifications']))

    def test_mixed_household_status_does_not_clear_the_fault_district(self):
        self.activate()
        self.apply('В Обухівському районі зникло світло через локальну аварію в мережі. В інших районах діють стабілізаційні відключення.')
        self.assertTrue(source_policy.suspended(self.state,'дача'))
        self.assertFalse(source_policy.suspended(self.state,'квартира'))
        text='\n'.join(source_policy.status_lines(self.state,NOW))
        self.assertIn('Дача: аварійні',text)
        self.assertIn('Квартира: стабілізаційні',text)
        morning=source_policy.morning_line(self.state,NOW)
        self.assertIn('Дача: аварійні',morning)
        self.assertIn('Квартира: стабілізаційні',morning)

    def test_cancellation_survives_repeated_read_and_queue_restart(self):
        self.activate()
        self.apply('В усіх районах діють стабілізаційні відключення.')
        self.state=json.loads(json.dumps(self.state))
        self.apply('В усіх районах діють стабілізаційні відключення.')
        self.assertIn('Екстрені відключення скасовано',source_policy.notification_text(self.cfg,self.state,NOW))
        count=len(self.state['pending_notifications'])
        self.apply('У Бучанському районі зникло світло через локальну аварію в мережі. В решті районів діють стабілізаційні відключення.')
        self.assertEqual(count,len(self.state['pending_notifications']))

    def test_older_clear_cannot_override_newer_notice(self):
        self.activate()
        notice=source_policy.parse('В усіх районах діють стабілізаційні відключення.',(NOW-timedelta(days=1)).isoformat(),NOW)
        self.assertFalse(source_policy.apply(self.state,notice,self.cfg,NOW))
        self.assertTrue(source_policy.suspended(self.state,'дача'))

    def test_early_outage_context_is_bounded_and_informational(self):
        at=NOW.replace(hour=14,minute=59)
        self.document['checked_at']=at.isoformat()
        self.assertIn('15:00–19:00',loss_context(self.state,at,'1.1','дача'))
        self.document['checked_at']=(at-timedelta(minutes=5)).isoformat()
        self.assertNotIn('15:00–19:00',loss_context(self.state,at-timedelta(minutes=5),'1.1','дача'))

    def test_both_places_keep_published_end_during_emergencies(self):
        self.activate()
        for place,group in [('дача','1.1'),('квартира','2.2')]:
            text=loss_context(self.state,NOW,group,place)
            self.assertIn('19:00',text)
            self.assertIn('графіки можуть не витримуватись',text)

    def test_invalid_stale_or_undated_schedule_does_not_invent_restore_time(self):
        for change in [dict(validated=False),dict(source_status='unavailable'),dict(dates=[]),dict(checked_at=(NOW-timedelta(minutes=36)).isoformat())]:
            state=dict(dtek_raw_snapshot=dict(self.document,**change))
            self.assertNotIn('19:00',loss_context(state,NOW,'1.1','дача'))
        self.assertNotIn('19:00',loss_context(self.state,NOW.replace(hour=20),'1.1','дача',NOW))

    def test_restoration_shows_ongoing_window_before_no_more_today(self):
        text='\n'.join(restoration_messages.schedule_lines(self.cfg,self.state,NOW,'дача','1.1'))
        self.assertIn('триває до <b>19:00',text)
        self.assertIn('Можливе повторне',text)
        self.assertNotIn('більше не заплановано',text)

    def test_restoration_never_invents_active_window_from_undated_rows(self):
        self.document['dates']=[]
        text='\n'.join(restoration_messages.schedule_lines(self.cfg,self.state,NOW,'дача','1.1'))
        self.assertNotIn('19:00',text)
        self.assertNotIn('більше не заплановано',text)

    def test_poll_slots_and_midnight_rollover(self):
        for minute,expected in [(0,10),(9,10),(10,40),(39,40),(40,10),(59,10)]:
            result=dtek.next_poll(NOW.replace(minute=minute))
            self.assertEqual(expected,result.minute)
            self.assertGreater(result,NOW.replace(minute=minute))
        self.assertEqual((NOW+timedelta(days=1)).date(),dtek.next_poll(NOW.replace(hour=23,minute=59)).date())

    def test_refresh_defers_only_schedule_reminders_and_drops_hung_read(self):
        self.state['dtek_read_pending']=dict(since=NOW.timestamp())
        self.assertEqual('defer',delivery_gate(self.state,NOW+timedelta(seconds=89)))
        self.assertEqual('drop',delivery_gate(self.state,NOW+timedelta(seconds=90)))
        item=dict(kind='dtek_restoration',place='квартира',group='2.2',**self.interval,created_at=NOW.isoformat())
        self.state['pending_notifications']=[item,dict(kind='technical_probe',message='independent',created_at=NOW.isoformat())]
        tg=Mock()
        deliver_pending_notifications(self.cfg,tg,self.state,NOW,self.client)
        tg.send_message.assert_called_once_with('owner','independent')
        self.assertEqual([item],self.state['pending_notifications'])

    def test_changed_end_invalidates_queued_restoration_after_refresh(self):
        item=dict(kind='dtek_restoration',place='квартира',group='2.2',
                  start=self.interval['start'],end=NOW.replace(hour=17,minute=0).isoformat())
        self.assertEqual('',dtek.restoration_text(self.cfg,self.client,self.state,NOW,item))

    def test_preparation_target_energy_and_zero_surplus_wording(self):
        total,split=dtek.preparation_energy_details(dict(capacity_kwh=16,solar_forecast_complete=True,
            forecast_net_solar_kwh=0,required_grid_kwh=1.76),84,95)
        self.assertIn('1.8 kWh',total)
        self.assertIn('надлишок сонця',split)
        self.assertNotIn('Сонце: <b>≈0',split)
        self.assertIn('ДТЕК: <b>≈1.8 kWh</b>',split)
        total,_=dtek.preparation_energy_details(dict(capacity_kwh=32),84,95)
        self.assertIn('3.5 kWh',total)

    def test_completion_once_without_routine_shortfall_alarm(self):
        start=(NOW+timedelta(minutes=30)).isoformat()
        data=dict(start=start,end=(NOW+timedelta(hours=4)).isoformat(),checked_at=NOW.isoformat(),
            phase='holding',acknowledged=True,acknowledged_target_soc=95,current_soc=95,target_soc=95,
            coverage_capacity_insufficient=True)
        self.rows['sensor.energyhub_operating_mode']=dict(state='panic_grid_hold')
        record=soc_interval.begin(NOW-timedelta(minutes=54),84)
        record.update(key=start,last_at=(NOW-timedelta(seconds=60)).isoformat(),last_soc=95)
        self.state['precharge_soc_session']=record
        text=soc_interval.preparation_notice(self.state,self.client,NOW,data)
        self.assertEqual(1,text.count('Дозаряджання завершено'))
        self.assertIn('84% → 95%',text)
        self.assertIn('54 хв',text)
        self.assertIn('Підтримуємо близько 95%',text)
        self.assertNotIn('не вистачить',text)
        self.assertIsNone(soc_interval.preparation_notice(self.state,self.client,NOW,data))

    def test_parent_poll_is_before_delivery_and_does_not_wait_for_network(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parents[1]/'app/main.py').read_text(encoding='utf-8')
        body=source[source.index('def run('):]
        self.assertLess(body.index('observe_safely(dtek_monitor.poll'),body.index('changed |= deliver_pending_notifications'))
        poll=dtek.ScheduleMonitor.poll
        import inspect
        text=inspect.getsource(poll)
        self.assertLess(text.index('self.future.done()'),text.index('self.future.result()'))

    def test_eco_failure_is_private_deduplicated_and_episode_bound(self):
        rows={hp_eco.HP:dict(state='heat'),hp_eco.ECO:dict(state='off'),
            'input_select.energyhub_climate_policy':dict(state='Smart'),
            'sensor.energyhub_telemetry_freshness':dict(state='fresh'),
            'binary_sensor.energyhub_grid_confirmed':dict(state='off',attributes=dict(transition_at=1000,
                checked_at=NOW.timestamp(),transition_pending=False,confirmation_seconds=180,episode_persisted=True)),
            'input_text.energyhub_hp1_eco_budget':dict(state=json.dumps(dict(e='off:1000',t='on',n=3,at=NOW.timestamp()-40)))}
        client=SimpleNamespace(state=lambda e:rows.get(e))
        state={}
        self.assertTrue(hp_eco.observe(state,client,NOW))
        self.assertEqual('technical_hp_eco_unconfirmed',state['pending_notifications'][0]['kind'])
        hp_eco.observe(state,client,NOW)
        self.assertEqual(1,len(state['pending_notifications']))
        rows[hp_eco.ECO]['state']='on'
        self.assertIsNone(hp_eco.failure(client,NOW))
        rows[hp_eco.ECO]['state']='off'
        rows['binary_sensor.energyhub_grid_confirmed']['attributes']['transition_at']=2000
        self.assertIsNone(hp_eco.failure(client,NOW))
