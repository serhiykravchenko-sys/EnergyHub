import json
import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock
from app import apartment_grid, source_policy, published_schedule, co_morning, outage_schedule

NOW=datetime(2026,10,11,10,16,tzinfo=timezone(timedelta(hours=3)))
CFG=SimpleNamespace(dtek_dacha_group='1.1',dtek_apartment_group='2.2',dtek_schedule_enabled=True)


class AgreedChangesTests(unittest.TestCase):
    def document(self):
        return dict(validated=True,source_status='fresh',checked_at=NOW.isoformat(),dates=['2026-10-11'],
                    source_url='https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/',groups={
            '1.1':[dict(start='2026-10-11T22:30:00+03:00',end='2026-10-12T00:00:00+03:00')],'2.2':[]})

    def test_emergency_includes_both_informational_schedules(self):
        state={};doc=self.document()
        notice=dict(kind='emergency',cancelled=False,schedules_invalid=True,text='У Київській області введені екстрені відключення.',
                    revision=NOW.isoformat(),checked_at=NOW.isoformat())
        source_policy.apply(state,notice,CFG,NOW,doc)
        text=state['pending_notifications'][0]['message']
        self.assertIn('22:30–24:00',text)
        self.assertIn('Квартира: <b>планових відключень до кінця дня немає',text)
        self.assertEqual(1,text.count('Графіки можуть не витримуватись.'))
        self.assertNotIn('Фактичні відключення',text)
        self.assertNotIn('Додатковий резерв',text)
        self.assertNotIn('BR +20',text)
        self.assertNotIn('До опублікованих відключень',text)
        self.assertIn('Джерело — Pro Kyiv',text)
        state['dtek_raw_snapshot']=doc
        state['dtek_snapshot']=source_policy.authority(doc,state,NOW)
        morning='\n'.join(outage_schedule.morning_lines(CFG,state,NOW,Mock()))
        self.assertIn('екстрені',morning)
        self.assertIn('22:30–24:00',morning)
        self.assertTrue(state['dtek_snapshot']['validated'])
        self.assertTrue(state['dtek_snapshot']['emergency_notice_active'])
        source_policy.apply(state,notice,CFG,NOW,doc)
        self.assertEqual(1,len(state['pending_notifications']))
        cancelled=dict(notice,cancelled=True,schedules_invalid=False,revision=(NOW+timedelta(minutes=1)).isoformat())
        source_policy.apply(state,cancelled,CFG,NOW+timedelta(minutes=1),doc)
        self.assertFalse(source_policy.suspended(state,'дача'))
        self.assertIn('22:30–24:00',state['pending_notifications'][-1]['message'])

    def test_changed_schedule_updates_notice_and_delivery_uses_fresh_rows(self):
        state={};doc=self.document()
        notice=dict(kind='emergency',cancelled=False,schedules_invalid=True,text='Київська область',
                    revision=NOW.isoformat(),checked_at=NOW.isoformat())
        source_policy.apply(state,notice,CFG,NOW,doc)
        doc['groups']['1.1'][0]['start']='2026-10-11T23:00:00+03:00'
        source_policy.apply(state,notice,CFG,NOW,doc)
        self.assertEqual(1,len(state['pending_notifications']))
        self.assertIn('23:00–24:00',state['pending_notifications'][0]['message'])
        state['dtek_raw_snapshot']=dict(doc,checked_at=(NOW-timedelta(hours=2)).isoformat())
        self.assertNotIn('23:00–24:00',source_policy.notification_text(CFG,state,NOW))

    def test_stale_or_missing_group_never_means_no_outages(self):
        for doc in (dict(self.document(),checked_at=(NOW-timedelta(hours=2)).isoformat()),
                    dict(self.document(),groups={'1.1':[]})):
            self.assertIn('ще не підтверджено',published_schedule.lines(CFG,{},NOW,doc)[0])

    def test_read_health_delays_and_only_acknowledged_recovery(self):
        state={}
        for t in range(0,180,30):
            apartment_grid.observe_read_health(state,NOW+timedelta(seconds=t),False)
        self.assertFalse(state.get('pending_notifications'))
        apartment_grid.observe_read_health(state,NOW+timedelta(seconds=180),False)
        item=state['pending_notifications'].pop()
        apartment_grid.acknowledge_read_health(state,item)
        state=json.loads(json.dumps(state))
        for t in range(210,510,30):
            apartment_grid.observe_read_health(state,NOW+timedelta(seconds=t),True,False)
        self.assertFalse(state.get('pending_notifications'))
        apartment_grid.observe_read_health(state,NOW+timedelta(seconds=510),True,False)
        text=state['pending_notifications'][0]['message']
        self.assertIn('Hub офлайн',text)
        self.assertNotIn('ДТЕК відновився',text)

    def test_flapping_gap_and_undelivered_alert_stay_silent(self):
        state={}
        for t in range(0,180,30):
            apartment_grid.observe_read_health(state,NOW+timedelta(seconds=t),False)
        apartment_grid.observe_read_health(state,NOW+timedelta(seconds=180),True,True)
        apartment_grid.observe_read_health(state,NOW+timedelta(seconds=210),False)
        apartment_grid.observe_read_health(state,NOW+timedelta(seconds=600),False)
        self.assertFalse(state.get('pending_notifications'))
        for t in range(630,781,30):
            apartment_grid.observe_read_health(state,NOW+timedelta(seconds=t),False)
        self.assertEqual(1,len(state['pending_notifications']))
        apartment_grid.observe_read_health(state,NOW+timedelta(seconds=810),True,True)
        for t in range(840,1141,30):
            apartment_grid.observe_read_health(state,NOW+timedelta(seconds=t),True,True)
        self.assertFalse(state['pending_notifications'])

    def test_missing_co_data_does_not_imply_alarm(self):
        client=Mock();client.state.return_value={}
        cfg=SimpleNamespace(co_alarms=[SimpleNamespace(entity='binary_sensor.floor_carbon_monoxide',label='First-floor CO')])
        text='\n'.join(co_morning.lines(cfg,client,NOW))
        self.assertIn('дані недоступні',text)
        self.assertNotIn('тривога',text)
        self.assertNotIn('батарея дані',text)
