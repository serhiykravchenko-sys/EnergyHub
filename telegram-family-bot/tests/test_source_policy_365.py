import json
import unittest
from datetime import timedelta
from types import SimpleNamespace
from app import source_policy as policy, apartment_grid, dtek_emergency
from test_schedule_sources import NOW,CFG,pro,alerts,sources
from unittest.mock import patch


class PolicyTests(unittest.TestCase):
    def notice(self,kind='fault',invalid=False,text='Обухівський район'):
        return dict(kind=kind,schedules_invalid=invalid,cancelled=False,text=text,revision=NOW.isoformat(),checked_at=NOW.isoformat())

    def snapshot(self,at=NOW,groups=None):
        return dict(validated=True,groups=groups or {'1.1':[{'start':'a','end':'b'}]},day_sources={'today':dict(published_at=at.isoformat())})

    def test_fault_schedule_emergency_and_restoration(self):
        state={'grid_online':False}
        policy.apply(state,self.notice(),CFG,NOW)
        self.assertTrue(policy.suspended(state,'дача'))
        policy.apply(state,self.notice(kind='emergency'),CFG,NOW)
        self.assertTrue(policy.suspended(state,'дача'))
        state['grid_online']=True
        dtek_emergency.restore(state)
        self.assertTrue(policy.suspended(state,'дача',self.snapshot(NOW+timedelta(hours=1))))
        cancel=self.notice(kind='emergency');cancel['cancelled']=True;cancel['revision']=(NOW+timedelta(hours=1)).isoformat()
        policy.apply(state,cancel,CFG,NOW+timedelta(hours=1))
        self.assertFalse(policy.suspended(state,'дача'))

    def test_invalidation_needs_changed_newer_schedule_not_recheck(self):
        state={};old=self.snapshot()
        policy.apply(state,self.notice(invalid=True),CFG,NOW,old)
        self.assertTrue(policy.suspended(state,'дача',old))
        self.assertTrue(policy.suspended(state,'дача',self.snapshot(NOW+timedelta(minutes=30))))
        new=self.snapshot(NOW+timedelta(minutes=30),{'1.1':[{'start':'c','end':'d'}]})
        self.assertTrue(policy.suspended(state,'дача',new))  # A new timetable does not cancel fault status.

    def test_exclusion_unknown_restart_and_no_duplicates(self):
        state={}
        policy.apply(state,self.notice(kind='emergency'),CFG,NOW)
        state=json.loads(json.dumps(state))
        self.assertFalse(policy.apply(state,None,CFG,NOW))
        self.assertTrue(policy.suspended(state,'дача'))
        count=len(state['pending_notifications'])
        policy.apply(state,self.notice(kind='emergency'),CFG,NOW)
        self.assertEqual(count,len(state['pending_notifications']))
        policy.apply(state,self.notice(kind='emergency',text='Броварський район'),CFG,NOW)
        self.assertTrue(policy.suspended(state,'дача'))  # Unrelated district notice cannot clear our status.

    def test_only_region_section_no_official_requests(self):
        bodies={sources.URLS['pro_kyiv']:pro(),sources.URLS['alerts_energy']:alerts()}
        with patch.object(sources,'fetch',side_effect=lambda u,d:bodies[u]) as fetch:
            doc=sources.read_snapshot(NOW)
        self.assertEqual('pro_kyiv',doc['source'])
        self.assertIsNone(doc['source_notice'])  # Kyiv-city emergency excluded.
        self.assertNotIn(sources.URLS['dtek_official'],[c.args[0] for c in fetch.call_args_list])


class Client:
    def __init__(self,state):self.value=state
    def state(self,entity):
        if isinstance(self.value,Exception):raise self.value
        return {'state':self.value} if self.value is not None else None


class ApartmentTests(unittest.TestCase):
    config=SimpleNamespace(apartment_grid_proxy_entity='light.test_hub')
    def test_debounce_restart_and_elapsed(self):
        state={};client=Client('on')
        apartment_grid.observe(self.config,client,state,NOW)
        apartment_grid.observe(self.config,client,state,NOW+timedelta(seconds=60))
        self.assertNotIn('pending_notifications',state)
        client.value='unavailable';t=NOW+timedelta(minutes=2)
        apartment_grid.observe(self.config,client,state,t)
        apartment_grid.observe(self.config,client,state,t+timedelta(seconds=119))
        self.assertNotIn('pending_notifications',state)
        state=json.loads(json.dumps(state))
        apartment_grid.observe(self.config,client,state,t+timedelta(seconds=120))
        self.assertEqual(1,len(state['pending_notifications']))
        client.value='off';end=t+timedelta(hours=3)
        apartment_grid.observe(self.config,client,state,end)
        apartment_grid.observe(self.config,client,state,end+timedelta(seconds=60))
        self.assertIn('3 год',state['pending_notifications'][-1]['message'])
        self.assertIn('Xiaomi Hub',state['pending_notifications'][-1]['message'])
        self.assertNotIn('батаре',state['pending_notifications'][-1]['message'])

    def test_unknown_and_ha_error_reset_candidate(self):
        state={};client=Client('unavailable')
        apartment_grid.observe(self.config,client,state,NOW)
        client.value='unknown';apartment_grid.observe(self.config,client,state,NOW+timedelta(minutes=1))
        client.value='unavailable';apartment_grid.observe(self.config,client,state,NOW+timedelta(minutes=3))
        self.assertNotIn('pending_notifications',state)
        client.value=OSError('HA unavailable')
        with self.assertRaises(OSError):apartment_grid.observe(self.config,client,state,NOW)
        self.assertNotIn('candidate',state['apartment_grid'])


class MessageTests(unittest.TestCase):
    def test_restoration_release_is_coalesced(self):
        from app.main import observe_grid_hold
        from test_events import FakeClient
        config=SimpleNamespace(operating_mode_entity='mode',grid_voltage_entity='voltage',battery_soc_entity='soc',ahm_minimum_soc_entity='minimum',telemetry_freshness_entity='freshness',dtek_schedule_enabled=False)
        for candidate in (True,False):
            state={'operating_mode_observed':'panic_grid_hold','grid_hold_context':{'release_soc':50},'grid_candidate':candidate,'grid_restored_at':NOW.isoformat()}
            client=FakeClient({'mode':'solar','voltage':230,'soc':77,'minimum':40,'freshness':'fresh'})
            observe_grid_hold(config,client,state,NOW)
            observe_grid_hold(config,client,state,NOW+timedelta(seconds=10))
            self.assertEqual([],state.get('pending_notifications',[]))

    def test_recovery_reserve_and_charging_confirmation(self):
        from app.main import recovery_reserve_context
        from test_events import FakeClient
        config=SimpleNamespace(battery_soc_entity='soc',ahm_minimum_soc_entity='minimum',operating_mode_entity='mode')
        client=FakeClient({'soc':30,'minimum':40,'mode':'panic'})
        text=recovery_reserve_context(config,client)
        self.assertIn('40%',text);self.assertIn('Заряджаємо',text)
        client.values['mode']='solar'
        text=recovery_reserve_context(config,client)
        self.assertIn('поки не підтверджено',text)
        self.assertIn('без допомоги ДТЕК',text)
