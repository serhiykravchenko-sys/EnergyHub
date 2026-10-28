import json
import unittest
from concurrent.futures import Future
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from app import apartment_grid
from test_schedule_sources import NOW


class ApartmentOfflineTests(unittest.TestCase):
    def setUp(self):
        self.config=SimpleNamespace(apartment_grid_proxy_entity='light.test',apartment_grid_cloud_enabled=True,
                                    dtek_schedule_enabled=False)
        self.client=Mock()
        self.state={}

    def sample(self,online,seconds):
        now=NOW+timedelta(seconds=seconds)
        self.state['apartment_cloud_sample']=dict(online=online,checked_at=now.isoformat())
        apartment_grid.observe(self.config,self.client,self.state,now)

    def test_initial_cloud_offline_notifies_once_with_unknown_start(self):
        self.sample(False,0);self.sample(False,60)
        self.assertFalse(self.state.get('pending_notifications'))
        self.sample(False,120)
        items=self.state['pending_notifications']
        self.assertEqual(1,len(items))
        self.assertIn('імовірно недоступний',items[0]['message'])
        self.assertIn('початок відключення невідомий',items[0]['message'])
        self.assertNotIn('Початок відключення:',items[0]['message'])
        self.assertNotIn('outage_started',self.state['apartment_grid'])
        self.state=json.loads(json.dumps(self.state))
        self.sample(False,180);self.sample(False,240)
        self.assertEqual(1,len(self.state['pending_notifications']))

    def test_initial_offline_recovery_does_not_fabricate_duration(self):
        for seconds in (0,60,120):self.sample(False,seconds)
        self.sample(True,180);self.sample(True,240)
        text=self.state['pending_notifications'][-1]['message']
        self.assertIn('відновився',text)
        self.assertNotIn('Без ДТЕК:',text)
        self.assertNotIn('outage_detected',self.state['apartment_grid'])

    def test_failed_stale_or_non_boolean_sample_resets_qualification(self):
        for invalid in ({},{'online':False,'checked_at':(NOW-timedelta(seconds=120)).isoformat()},
                        {'online':'false','checked_at':NOW.isoformat()}):
            with self.subTest(invalid=invalid):
                self.state={};self.sample(False,0)
                self.state['apartment_cloud_sample']=invalid
                apartment_grid.observe(self.config,self.client,self.state,NOW+timedelta(seconds=30))
                self.sample(False,60);self.sample(False,120)
                self.assertFalse(self.state.get('pending_notifications'))
                self.sample(False,180)
                self.assertEqual(1,len(self.state['pending_notifications']))

    def test_long_observation_gap_and_restart_do_not_backdate_outage(self):
        self.sample(False,0)
        self.state=json.loads(json.dumps(self.state))
        self.sample(False,180)
        self.assertFalse(self.state.get('pending_notifications'))
        self.sample(False,240);self.sample(False,300)
        self.assertEqual((NOW+timedelta(seconds=180)).isoformat(),self.state['apartment_grid']['outage_detected'])

    def test_generic_ha_unavailability_still_needs_online_baseline(self):
        self.config.apartment_grid_cloud_enabled=False
        self.client.state.return_value={'state':'unavailable'}
        for seconds in (0,60,120,180):
            apartment_grid.observe(self.config,self.client,self.state,NOW+timedelta(seconds=seconds))
        self.assertFalse(self.state.get('pending_notifications'))

    def test_cloud_read_recovery_reports_offline_not_power_recovery(self):
        monitor=object.__new__(apartment_grid.CloudMonitor)
        monitor.executor=Mock();monitor.future=Future();monitor.future.set_result(False);monitor.due=0
        self.state['apartment_cloud_failed']=True
        self.state['apartment_cloud_health']=dict(alerted=True,candidate=True,
            since=(NOW-timedelta(seconds=300)).isoformat(),observed_at=NOW.timestamp()-30)
        monitor.poll(self.config,self.client,self.state,NOW)
        text=self.state['pending_notifications'][0]['message']
        self.assertIn('Hub офлайн',text)
        self.assertNotIn('ДТЕК відновився',text)
        self.assertIsNone(self.state['apartment_grid']['online'])

    def test_rejected_cloud_response_does_not_become_offline(self):
        monitor=object.__new__(apartment_grid.CloudMonitor)
        monitor.executor=Mock();monitor.future=Future();monitor.future.set_result(None);monitor.due=0
        monitor.poll(self.config,self.client,self.state,NOW)
        self.assertNotIn('apartment_cloud_sample',self.state)
        self.assertTrue(self.state['apartment_cloud_failed'])
        self.assertFalse(self.state.get('pending_notifications'))
