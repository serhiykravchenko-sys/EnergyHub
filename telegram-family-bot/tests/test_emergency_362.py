import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from app import dtek_emergency as emergency

NOW=datetime(2026,10,8,12,tzinfo=ZoneInfo('Europe/Kyiv'))


def post(identifier=4578,places=None):
    return dict(id=identifier,active=True,url=f'https://t.me/dtek_ua/{identifier}',
                at=(NOW-timedelta(hours=1)).isoformat(),places=['дача','квартира'] if places is None else places)


class Emergency362Tests(unittest.TestCase):
    def test_latest_district_exclusion_clears_legacy_same_id_state(self):
        state={'grid_online':False,'dtek_emergency':{'last_id':4578,'active':True,'apartment_active':True},
               'dtek_raw_snapshot':{'source_status':'fresh','validated':True},
               'pending_notifications':[{'kind':'dtek_emergency','message':'old'},{'kind':'other'}]}
        self.assertTrue(emergency.apply(state,[post(4575),post(places=[])],NOW))
        self.assertFalse(state['dtek_emergency']['active'])
        self.assertFalse(state['dtek_emergency']['apartment_active'])
        self.assertEqual('fresh',state['dtek_snapshot']['source_status'])
        self.assertEqual([{'kind':'other'}],state['pending_notifications'])
        self.assertFalse(emergency.apply(state,[post(places=[])],NOW))

    def test_online_notice_does_not_suspend_schedule(self):
        state={'grid_online':True};emergency.apply(state,[post()],NOW)
        self.assertFalse(emergency.place_active(state,'дача'))
        doc=emergency.authority({'source_status':'fresh','validated':True},state,NOW)
        self.assertTrue(doc['validated'])
        self.assertTrue(doc['emergency_notice_active'])
        self.assertIn('підготовку за графіком продовжуємо',state['pending_notifications'][0]['message'])
        state['grid_online']=False
        self.assertEqual('suspended',emergency.authority(doc,state,NOW)['source_status'])

    def test_restoration_resumes_raw_schedule_and_cannot_replay_same_notice(self):
        state={'grid_online':False,'dtek_raw_snapshot':{'source_status':'fresh','validated':True}}
        emergency.apply(state,[post()],NOW)
        state['grid_online']=True
        self.assertTrue(emergency.restore(state))
        self.assertFalse(emergency.apply(state,[post()],NOW))
        state['grid_online']=False
        self.assertFalse(emergency.place_active(state,'дача'))
        self.assertTrue(state['dtek_snapshot']['validated'])
        self.assertTrue(emergency.place_active(state,'квартира'))

    def test_restoration_does_not_invent_valid_schedule(self):
        state={'grid_online':False,'dtek_raw_snapshot':{'source_status':'error','validated':False}}
        emergency.apply(state,[post()],NOW);state['grid_online']=True
        emergency.restore(state)
        self.assertFalse(state['dtek_snapshot']['validated'])

    def test_unknown_grid_is_not_proof_of_emergency_outage(self):
        state={};emergency.apply(state,[post()],NOW)
        doc=emergency.authority({'source_status':'fresh','validated':True},state,NOW)
        self.assertTrue(doc['validated'])
        self.assertEqual('unknown',doc['emergency_grid_state'])

    def test_new_scope_replaces_both_locations_independently(self):
        state={'grid_online':False};emergency.apply(state,[post(4575)],NOW)
        emergency.apply(state,[post(places=['квартира'])],NOW)
        self.assertFalse(emergency.place_active(state,'дача'))
        self.assertTrue(emergency.place_active(state,'квартира'))

    def test_same_id_migration_does_not_duplicate_notice(self):
        state={'grid_online':False,'dtek_emergency':{'last_id':4578,'active':True}}
        emergency.apply(state,[post()],NOW)
        self.assertTrue(emergency.place_active(state,'дача'))
        self.assertFalse(state['pending_notifications'])

    def test_older_read_cannot_replace_newer_persisted_scope(self):
        state={'grid_online':False};emergency.apply(state,[post(places=[])],NOW)
        self.assertFalse(emergency.apply(state,[post(4575)],NOW))
        self.assertFalse(emergency.place_active(state,'дача'))

    def test_legacy_wrapper_without_raw_schedule_cannot_stay_suspended_or_become_valid(self):
        doc=emergency.authority({'source_status':'suspended','validated':False},{'grid_online':True},NOW)
        self.assertEqual('unavailable',doc['source_status'])
        self.assertFalse(doc['validated'])
