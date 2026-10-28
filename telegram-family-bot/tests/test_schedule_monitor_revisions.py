import unittest
from concurrent.futures import Future
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo
from app import outage_schedule as schedule

NOW=datetime(2026,10,7,20,tzinfo=ZoneInfo('Europe/Kyiv'))

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.monitor=schedule.ScheduleMonitor()
        self.monitor.executor.shutdown(wait=True)
        self.monitor.executor=Mock()
        self.monitor.executor.submit.return_value=Future()
        self.cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_apartment_group='2.2',
            solar_forecast_entity='forecast',battery_soc_entity='soc',telemetry_freshness_entity='fresh')
        self.client=SimpleNamespace(state=lambda entity:{},publish_mqtt=Mock())
        self.state={'pending_notifications':[],'dtek_publish_due':NOW.timestamp()+600}

    def snapshot(self,shift=0):
        a=NOW+timedelta(hours=2,minutes=shift)
        row=dict(start=a.isoformat(),end=(a+timedelta(hours=2)).isoformat())
        return dict(source='bezsvitla',source_status='fresh',validated=True,checked_at=NOW.isoformat(),
            dates=[NOW.date().isoformat()],groups={'1.1':[row],'2.2':[row]},source_url='https://bezsvitla.com.ua/kyivska-oblast')

    def finish(self,doc,now=NOW):
        self.monitor.future=Future();self.monitor.future.set_result((doc,{}))
        self.monitor.poll(self.cfg,self.client,self.state,now)

    def test_evening_checkpoint_overrides_later_due_once(self):
        self.monitor.due=NOW.timestamp()+1800
        self.monitor.poll(self.cfg,self.client,self.state,NOW)
        self.assertEqual(1,self.monitor.executor.submit.call_count)
        self.assertEqual(NOW.date().isoformat(),self.state['schedule_evening_check'])
        self.monitor.poll(self.cfg,self.client,self.state,NOW+timedelta(seconds=30))
        self.assertEqual(1,self.monitor.executor.submit.call_count)

    def test_revision_replaces_snapshot_obsolete_queue_and_notifies_once(self):
        original=self.snapshot()
        self.finish(original)
        self.state['pending_notifications']=[]
        row=original['groups']['1.1'][0]
        self.state['pending_notifications'].append(dict(kind='dtek_reminder',group='1.1',**row))
        revised=self.snapshot(30)
        self.finish(revised,NOW+timedelta(seconds=30))
        self.assertEqual(dict(revised,emergency_notice_active=False,emergency_notice_confirmed_clear=False,
                              emergency_grid_state='unknown'),self.state['dtek_snapshot'])
        queue=self.state['pending_notifications']
        self.assertEqual(1,len(queue));self.assertIn('оновлено',queue[0]['message'])
        self.state['pending_notifications']=[]
        revised['checked_at']=(NOW+timedelta(minutes=1)).isoformat()
        self.finish(revised,NOW+timedelta(minutes=1))
        self.assertFalse(self.state['pending_notifications'])

    def test_failed_read_invalidates_schedule_and_alerts_owner_once(self):
        self.state['dtek_snapshot']=self.snapshot()
        for _ in range(2):
            self.monitor.future=Future();self.monitor.future.set_exception(ValueError('bad source'))
            self.monitor.poll(self.cfg,self.client,self.state,NOW)
        self.assertEqual('unavailable',self.state['dtek_snapshot']['source_status'])
        self.assertEqual(1,len(self.state['pending_notifications']))
        self.assertEqual('technical_dtek_source',self.state['pending_notifications'][0]['kind'])

    def test_new_sources_replace_extended_restoration_and_start_reminders(self):
        original=self.snapshot();self.finish(original)
        self.state['pending_notifications']=[]
        row=original['groups']['1.1'][0]
        self.state['pending_notifications']=[dict(kind=k,group='1.1',**row) for k in ('dtek_reminder','dtek_restoration')]
        revised=self.snapshot();revised['source']='alerts_energy'
        revised['groups']['1.1'][0]['end']=(NOW+timedelta(hours=6)).isoformat()
        self.finish(revised,NOW+timedelta(seconds=30))
        self.assertEqual(['dtek_schedule'],[i['kind'] for i in self.state['pending_notifications']])
        self.assertEqual(schedule.next_poll(NOW+timedelta(seconds=30)).timestamp(),self.monitor.due)

    def test_primary_failure_with_valid_mirror_alerts_private_once(self):
        doc=self.snapshot();doc.update(source='alerts_energy',source_failures={'dtek_official':'ValueError'})
        self.finish(doc)
        self.finish(dict(doc,checked_at=(NOW+timedelta(seconds=30)).isoformat()),NOW+timedelta(seconds=30))
        self.assertEqual(1,sum(i['kind']=='technical_dtek_sources' for i in self.state['pending_notifications']))
