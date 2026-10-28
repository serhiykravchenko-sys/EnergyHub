import json
import unittest
from datetime import datetime,timezone,timedelta
from app import solar_session, solar_settings


class SolarSessionTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,4,10,tzinfo=timezone.utc)
        self.rows={k:{'state':v} for k,v in {
            'input_select.energyhub_climate_effective_policy':'Solar-only',
            'sensor.energyhub_telemetry_freshness':'fresh',
            'climate.first_floor_heat_pump':'heat'}.items()}
        self.rows[solar_session.ENERGY]={'state':'10','last_updated':self.now.isoformat()}
        self.state={}

    def test_running_time_and_counter_survive_restart(self):
        solar_session.observe(self.state,self.rows,self.now)
        self.state=json.loads(json.dumps(self.state))
        later=self.now+timedelta(seconds=60)
        self.rows[solar_session.ENERGY].update(state='10.02',last_updated=later.isoformat())
        solar_session.observe(self.state,self.rows,later)
        text=solar_session.summary(self.state['solar_running_session'],10.02)
        self.assertIn('0 год 1 хв',text)
        self.assertIn('0.02 кВт',text)
        self.assertIn('не перевірені',text)

    def test_pause_excludes_stopped_time(self):
        solar_session.observe(self.state,self.rows,self.now)
        self.rows['climate.first_floor_heat_pump'].update(state='off',last_changed=(self.now+timedelta(seconds=30)).isoformat())
        solar_session.observe(self.state,self.rows,self.now+timedelta(seconds=60))
        solar_session.observe(self.state,self.rows,self.now+timedelta(seconds=120))
        self.assertEqual(30,self.state['solar_running_session']['seconds'])

    def test_gap_and_counter_reset_never_invent_consumption(self):
        for seconds,energy in ((180,'10.2'),(60,'0.1')):
            state={};solar_session.observe(state,self.rows,self.now)
            self.rows[solar_session.ENERGY].update(state=energy)
            solar_session.observe(state,self.rows,self.now+timedelta(seconds=seconds))
            self.assertIn('недоступне',solar_session.summary(state['solar_running_session'],float(energy)))
            self.rows[solar_session.ENERGY]['state']='10'

    def test_invalid_and_partial_thresholds(self):
        for start,pause in [('400','600'),('nan','400'),('600','unavailable')]:
            self.assertIsNone(solar_settings.thresholds({solar_settings.START:{'state':start},solar_settings.PAUSE:{'state':pause}}))
        self.assertEqual((800,500),solar_settings.thresholds({solar_settings.START:{'state':'800'},solar_settings.PAUSE:{'state':'500'}}))

    def test_unavailable_telemetry_invalidates_energy(self):
        solar_session.observe(self.state,self.rows,self.now)
        self.rows['sensor.energyhub_telemetry_freshness']['state']='stale'
        solar_session.observe(self.state,self.rows,self.now+timedelta(seconds=60))
        self.assertIn('недоступне',solar_session.summary(self.state['solar_running_session'],10.1))

    def test_counter_reset_at_policy_exit_is_not_reported_as_consumption(self):
        solar_session.observe(self.state,self.rows,self.now)
        self.rows[solar_session.ENERGY]['state']='11'
        solar_session.observe(self.state,self.rows,self.now+timedelta(seconds=60))
        self.rows[solar_session.ENERGY]['state']='10.5'
        self.rows['input_select.energyhub_climate_effective_policy']['state']='Smart'
        text=solar_session.observe(self.state,self.rows,self.now+timedelta(seconds=90))
        self.assertIn('недоступне',text)

    def test_policy_exit_after_gap_invalidates_energy(self):
        solar_session.observe(self.state,self.rows,self.now)
        solar_session.observe(self.state,self.rows,self.now+timedelta(seconds=60))
        self.rows['input_select.energyhub_climate_effective_policy']['state']='Smart'
        self.rows[solar_session.ENERGY]['state']='10.5'
        text=solar_session.observe(self.state,self.rows,self.now+timedelta(seconds=240))
        self.assertIn('недоступне',text)
