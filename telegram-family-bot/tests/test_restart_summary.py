import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
from app.restart_summary import SESSION, observe_restart, restart_state_ready, summary
from app.main import deliver_pending_notifications


class RestartTests(TestCase):
    def setUp(self):
        self.now = datetime(2026,9,8,12,tzinfo=timezone.utc)
        self.session = (self.now-timedelta(seconds=65)).isoformat()
        self.entities = {SESSION:{'state':self.session},
            'input_boolean.energyhub_autopilot':{'state':'on'},
            'input_boolean.energyhub_load_control_armed':{'state':'on'},
            'sensor.energyhub_telemetry_freshness':{'state':'fresh'},
            'sensor.energyhub_operating_mode':{'state':'solar'},
            'sensor.powmr_10_2m_battery_soc':{'state':'98'},
            'input_number.ahm_minimum_soc':{'state':'20'},
            'sensor.energyhub_ahm_weather_buffer':{'attributes':{
                'automatic_control_enabled':False,
                'evaluated_at':self.now.isoformat(),
            }},
            'sensor.energyhub_peak_load_guard':{'state':'normal','attributes':dict(mode='automatic',
                automatic_requested=True,armed=True,control_ready=True,eligible_loads=['pump'],
                control_schema=5,battery_protection={'active':False},
                load_snapshot_at=self.now.isoformat())}}
        self.client = SimpleNamespace(state=lambda entity:self.entities.get(entity))

    def test_recent_restart_once_after_bot_restart(self):
        state = {}
        self.assertTrue(observe_restart(self.client,state,self.now))
        restored = json.loads(json.dumps(state))
        self.assertFalse(observe_restart(self.client,restored,self.now))
        self.assertEqual(1,len(restored['pending_notifications']))
        msg = restored['pending_notifications'][0]['message']
        self.assertIn('<b>98%</b>', msg)
        self.assertIn('резерв 20%',msg)
        self.assertIn('Захист батареї та перевантаження: активний',msg)
        self.assertIn('Опалення: ручне керування',msg)

    def test_old_initial_baseline_is_silent(self):
        self.entities[SESSION]['state'] = (self.now-timedelta(days=1)).isoformat()
        state = {}
        observe_restart(self.client,state,self.now)
        self.assertFalse(state.get('pending_notifications'))

    def test_waits_then_consolidates_startup_control_messages(self):
        self.entities[SESSION]['state'] = (self.now-timedelta(seconds=10)).isoformat()
        state = {'ha_restart_seen':'older','pending_notifications':[{'kind':'dashboard_control_overload'}]}
        observe_restart(self.client,state,self.now)
        self.assertTrue(state['restart_summary_pending'])
        self.entities['sensor.energyhub_ahm_weather_buffer']['attributes']['evaluated_at'] = (self.now+timedelta(seconds=60)).isoformat()
        self.entities['sensor.energyhub_peak_load_guard']['attributes']['load_snapshot_at'] = (self.now+timedelta(seconds=60)).isoformat()
        observe_restart(self.client,state,self.now+timedelta(seconds=60))
        self.assertFalse(state['restart_summary_pending'])
        self.assertEqual(['ha_restart_summary'],[x['kind'] for x in state['pending_notifications']])

    def test_waits_up_to_five_minutes_for_current_boot_evidence(self):
        self.entities[SESSION]['state'] = (self.now-timedelta(seconds=65)).isoformat()
        self.entities['sensor.energyhub_ahm_weather_buffer']['attributes'].pop('evaluated_at')
        state = {'ha_restart_seen':'older'}
        observe_restart(self.client,state,self.now)
        self.assertTrue(state['restart_summary_pending'])
        self.assertFalse(state.get('pending_notifications'))
        observe_restart(self.client,state,self.now+timedelta(seconds=236))
        self.assertFalse(state['restart_summary_pending'])
        self.assertEqual(['ha_restart_summary'], [x['kind'] for x in state['pending_notifications']])

    def test_ready_requires_post_restart_reserve_and_guard_evidence(self):
        session = self.entities[SESSION]['state']
        self.entities['sensor.energyhub_ahm_weather_buffer']['attributes']['evaluated_at'] = (datetime.fromisoformat(session)-timedelta(seconds=1)).isoformat()
        self.assertFalse(restart_state_ready(self.client, self.now, session))
        self.entities['sensor.energyhub_ahm_weather_buffer']['attributes']['evaluated_at'] = self.now.isoformat()
        self.entities['sensor.energyhub_peak_load_guard']['attributes']['load_snapshot_at'] = self.now.isoformat()
        self.assertTrue(restart_state_ready(self.client, self.now, session))

    def test_unknown_never_claims_automatic_reserve_or_ready(self):
        self.entities.pop('sensor.energyhub_ahm_weather_buffer')
        self.entities.pop('sensor.energyhub_peak_load_guard')
        msg = summary(self.client,self.now,self.session)
        self.assertIn('стан ще не підтверджено',msg)
        self.assertIn('очікуємо готовності',msg)

    def test_timeout_summary_marks_stale_post_restart_states_unconfirmed(self):
        self.entities['sensor.energyhub_ahm_weather_buffer']['attributes'].pop('evaluated_at')
        self.entities['sensor.energyhub_peak_load_guard']['attributes']['load_snapshot_at'] = (self.now-timedelta(minutes=6)).isoformat()
        msg = summary(self.client, self.now, self.session)
        self.assertIn('стан ще не підтверджено', msg)
        self.assertIn('очікуємо готовності', msg)

    def test_delivery_refreshes_state(self):
        state = {}
        observe_restart(self.client,state,self.now)
        self.entities['input_boolean.energyhub_load_control_armed']['state']='off'
        calls=[]
        deliver_pending_notifications(SimpleNamespace(timezone='UTC',destination_chat_id='test'),
            SimpleNamespace(send_message=lambda chat,msg:calls.append(msg)),state,self.now,self.client)
        self.assertIn('вимкнено',calls[0])

    def test_missing_boot_signal_waits(self):
        self.entities.pop(SESSION)
        self.assertFalse(observe_restart(self.client,{},self.now))
