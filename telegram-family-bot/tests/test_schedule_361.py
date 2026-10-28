import unittest
from datetime import datetime,timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import patch
from app import outage_schedule as schedule, dtek_emergency as emergency, hp_summary
from app import bezsvitla
from test_bezsvitla import page
import test_schedule_monitor_revisions
from concurrent.futures import Future

NOW=datetime(2026,10,8,8,tzinfo=ZoneInfo('Europe/Kyiv'))


class Schedule361Tests(unittest.TestCase):
    def setUp(self):
        self.config=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_apartment_group='2.2')
        self.client=SimpleNamespace(state=lambda e:{'state':'40'})
        def row(day,a,b):
            return dict(start=NOW.replace(day=day,hour=a).isoformat(),end=NOW.replace(day=day,hour=b).isoformat())
        self.doc=dict(source='bezsvitla',source_status='fresh',validated=True,checked_at=NOW.isoformat(),
                      dates=['2026-10-08','2026-10-09'],groups={'1.1':[row(8,0,4),row(8,10,15),row(9,18,22)],'2.2':[]},
                      source_url='https://bezsvitla.com.ua/kyivska-oblast/grafik-na-2026-10-08')

    def test_morning_omits_finished_and_tomorrow_and_preparation(self):
        text='\n'.join(schedule.morning_lines(self.config,{'dtek_snapshot':self.doc},NOW,self.client))
        self.assertIn('до кінця дня',text)
        self.assertIn('10:00–15:00',text)
        self.assertNotIn('00:00–04:00',text)
        self.assertNotIn('9 жовтня',text)
        self.assertNotIn('Готуємо батарею',text)

    def test_evening_only_tomorrow_and_deduplicated(self):
        now=NOW.replace(hour=20);self.doc['checked_at']=now.isoformat()
        state={'dtek_snapshot':self.doc}
        self.assertTrue(schedule.queue_evening(self.config,self.client,state,now))
        text=next(i['message'] for i in state['pending_notifications'] if i['kind']=='dtek_tomorrow')
        self.assertIn('9 жовтня',text);self.assertNotIn('8 жовтня',text)
        self.assertFalse(schedule.queue_evening(self.config,self.client,state,now+timedelta(minutes=1)))

    def test_third_completed_failure_only_then_recovery(self):
        now=NOW.replace(hour=21)
        state={'schedule_evening':{'attempts':3,'completed':2},'dtek_snapshot':{}}
        self.assertFalse(schedule.queue_evening(self.config,self.client,state,now))
        state['schedule_evening']['completed']=3
        self.assertFalse(schedule.queue_evening(self.config,self.client,state,now))
        self.assertFalse(any(i['kind']=='dtek_tomorrow_missing' for i in state.get('pending_notifications',[])))
        self.doc['checked_at']=now.isoformat();state['dtek_snapshot']=self.doc
        self.assertTrue(schedule.queue_evening(self.config,self.client,state,now))
        self.assertEqual(['dtek_tomorrow'],[i['kind'] for i in state['pending_notifications'] if not i['kind'].startswith('technical_')])

    def test_emergency_region_match_and_local_restoration_dedup(self):
        self.assertTrue(emergency.classify('‼️Київ та Київська область: за командою Укренерго застосовані екстрені відключення'))
        self.assertIsNone(emergency.classify('Донеччина: екстрені відключення скасовані'))
        self.assertIsNone(emergency.classify('Київ: застосовані екстрені відключення'))
        self.assertFalse(emergency.classify('Київщина: екстрені відключення скасовані'))
        state={'grid_online':False}
        posts=[dict(id=4575,active=True,url='https://t.me/dtek_ua/4575')]
        emergency.apply(state,posts,NOW)
        self.assertEqual('suspended',emergency.authority(self.doc,state,NOW)['source_status'])
        self.assertFalse(emergency.restore(state))
        state['grid_online']=True
        self.assertTrue(emergency.restore(state))
        self.assertFalse(emergency.apply(state,posts,NOW))
        self.assertEqual('fresh',emergency.authority(self.doc,state,NOW)['source_status'])

    def test_previous_day_eco_not_in_morning(self):
        segment=dict(start=(NOW-timedelta(hours=17)).isoformat(),end=(NOW-timedelta(hours=15)).isoformat())
        client=SimpleNamespace(state=lambda e:{'state':'Smart'} if e==hp_summary.MASTER else None)
        text='\n'.join(hp_summary.lines({'hp_operation_summary':{'eco_segments':[segment]}},client,NOW))
        self.assertNotIn('Eco',text)

    def test_tomorrow_failure_preserves_valid_today_without_inventing_no_outages(self):
        def fetch(url,deadline):
            if url.endswith('2026-10-09'):
                raise TimeoutError('offline')
            return page(NOW.date())
        with patch.object(bezsvitla,'fetch',side_effect=fetch):
            doc=bezsvitla.read_snapshot(NOW)
        self.assertEqual(['2026-10-08'],doc['dates'])
        self.assertEqual('TimeoutError',doc['day_errors']['2026-10-09'])
        self.assertTrue(doc['validated'])

    def test_emergency_historical_activation_cannot_override_later_house_restoration(self):
        state={'grid_online':True,'grid_restored_at':NOW.isoformat()}
        emergency.apply(state,[dict(id=10,active=True,places=['дача'],url='https://t.me/dtek_ua/10',at=(NOW-timedelta(hours=1)).isoformat())],NOW)
        self.assertFalse(state['dtek_emergency']['active'])
        self.assertFalse(state.get('pending_notifications'))

    def test_known_eco_outage_with_brief_unknown_samples_is_one_incomplete_line(self):
        state={};now=NOW.replace(hour=0,minute=5)
        rows={hp_summary.MASTER:{'state':'Smart'},hp_summary.HP:{'state':'heat','attributes':{'temperature':18}},
              'switch.first_floor_heat_pump_eco':{'state':'on'},
              'sensor.energyhub_telemetry_freshness':{'state':'fresh'},
              'sensor.powmr_10_2m_grid_voltage':{'state':'0'}}
        hp_summary.observe(state,rows,now)
        hp_summary.observe(state,rows,now+timedelta(seconds=30))
        rows['sensor.energyhub_telemetry_freshness']['state']='stale'
        hp_summary.observe(state,rows,now+timedelta(seconds=60))
        rows['sensor.energyhub_telemetry_freshness']['state']='fresh'
        hp_summary.observe(state,rows,now+timedelta(seconds=90))
        self.assertEqual(1,len(state['hp_operation_summary']['eco_segments']))
        self.assertTrue(state['hp_operation_summary']['eco_segments'][0]['incomplete'])

    def test_real_monitor_waits_for_third_result_at_aligned_checkpoints(self):
        fixture=test_schedule_monitor_revisions.MonitorTests('test_evening_checkpoint_overrides_later_due_once')
        fixture.setUp()
        fixture.monitor.executor.submit.side_effect=lambda *a:Future()
        for minute in (0,30,60):
            now=NOW.replace(hour=20)+timedelta(minutes=minute)
            fixture.monitor.poll(fixture.cfg,fixture.client,fixture.state,now)
            self.assertFalse(any(i['kind']=='dtek_tomorrow_missing' for i in fixture.state['pending_notifications']))
            fixture.monitor.future.set_exception(TimeoutError('offline'))
            fixture.monitor.poll(fixture.cfg,fixture.client,fixture.state,now+timedelta(seconds=30))
        self.assertEqual(3,fixture.state['schedule_evening']['completed'])
        self.assertEqual(0,sum(i['kind']=='dtek_tomorrow_missing' for i in fixture.state['pending_notifications']))

    def test_post_4578_does_not_match_either_household_district(self):
        config=SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv')
        text='Київщина: у Броварському, Бучанському, Вишгородському та Бориспільському районах запроваджено екстрені відключення'
        self.assertTrue(emergency.classify(text))
        self.assertEqual([],emergency.affected_places(text,config))
        state={}
        emergency.apply(state,[dict(id=4578,active=True,places=[],url='https://t.me/dtek_ua/4578')],NOW)
        self.assertFalse(state.get('pending_notifications'))
        self.assertFalse(state['dtek_emergency'].get('active'))

    def test_fastiv_only_notice_does_not_suspend_dacha(self):
        config=SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv')
        places=emergency.affected_places('Київщина: у Фастівському районі застосовані екстрені відключення',config)
        self.assertEqual(['квартира'],places)
        state={};emergency.apply(state,[dict(id=20,active=True,places=places,url='https://t.me/dtek_ua/20')],NOW)
        self.assertTrue(state['dtek_emergency']['apartment_active'])
        self.assertEqual('fresh',emergency.authority(self.doc,state,NOW)['source_status'])

    def test_entire_region_applies_to_both_but_unknown_district_does_not(self):
        self.assertEqual(['дача','квартира'],emergency.affected_places('Київ та Київська область: застосовані екстрені відключення'))
        self.assertEqual([],emergency.affected_places('Київщина: у деяких районах застосовані екстрені відключення'))

    def test_newer_unrelated_notice_replaces_older_relevant_notice(self):
        state={}
        posts=[dict(id=20,active=True,places=['дача'],url='https://t.me/dtek_ua/20'),
               dict(id=21,active=True,places=[],url='https://t.me/dtek_ua/21')]
        self.assertTrue(emergency.apply(state,posts,NOW))
        self.assertFalse(state['dtek_emergency']['active'])
        self.assertEqual(21,state['dtek_emergency']['last_id'])
        self.assertEqual(0,len(state['pending_notifications']))
        self.assertFalse(emergency.apply(state,posts,NOW))
