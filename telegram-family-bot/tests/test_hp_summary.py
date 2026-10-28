import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from app import hp_summary

class HPSummaryTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,5,23,tzinfo=timezone(timedelta(hours=3)))
        self.rows={hp_summary.MASTER:{'state':'Smart'},hp_summary.HP:{'state':'heat','attributes':{'temperature':19}},
            'switch.first_floor_heat_pump_quiet':{'state':'on'},
            'switch.first_floor_heat_pump_eco':{'state':'off'},
            'sensor.energyhub_telemetry_freshness':{'state':'fresh'},
            'sensor.powmr_10_2m_grid_voltage':{'state':'0'},
            'binary_sensor.energyhub_hp_night_window':{'state':'on'},
            'sensor.energyhub_hp1_connection':{'attributes':{'ha_temperature_unit':'°C'}}}
        self.state={}
        self.client=SimpleNamespace(state=lambda e:self.rows.get(e))

    def tick(self, seconds=60):
        hp_summary.observe(self.state,self.rows,self.now)
        self.now+=timedelta(seconds=seconds)

    def test_night_off_hides_automatic_profile_reset_noise(self):
        for _ in range(5):self.tick()
        self.rows[hp_summary.HP]['state']='off'
        self.rows['switch.first_floor_heat_pump_quiet']['state']='off'
        for _ in range(3):self.tick()
        lines=hp_summary.lines(self.state,self.client,self.now)
        self.assertEqual(3,len(lines))
        self.assertIn('задана температура 19 °C',lines[1])
        self.assertIn('насос вимкнений',lines[2])
        self.assertNotIn('Eco',' '.join(lines))

    def test_manual_temperature_change_is_reported_not_overwritten(self):
        self.tick();self.tick()
        self.rows[hp_summary.HP]['attributes']['temperature']=22
        self.tick();self.tick()
        lines=hp_summary.lines(self.state,self.client,self.now)
        self.assertIn('остання підтверджена задана температура 22 °C',' '.join(lines))
        self.assertIn('протягом ночі змінювалася',' '.join(lines))
        self.assertEqual(22,self.rows[hp_summary.HP]['attributes']['temperature'])

    def test_gap_does_not_invent_continuous_quiet_interval(self):
        self.tick();self.tick(600);self.tick();self.tick()
        lines=hp_summary.lines(self.state,self.client,self.now)
        self.assertIn('із перервами',' '.join(lines))

    def test_unavailable_night_never_claims_requested_temperature(self):
        self.rows[hp_summary.HP]['state']='unavailable'
        self.tick();self.tick()
        text=' '.join(hp_summary.lines(self.state,self.client,self.now))
        self.assertIn('підтверджено не повністю',text)
        self.assertNotIn('19 °C',text)

    def test_unavailable_interval_never_bridges_quiet_segments(self):
        self.tick();self.tick()
        self.rows[hp_summary.HP]['state']='unavailable'
        for _ in range(5):self.tick()
        self.rows[hp_summary.HP]['state']='heat'
        self.tick();self.tick()
        text=' '.join(hp_summary.lines(self.state,self.client,self.now))
        self.assertIn('із перервами',text)
        self.assertIn('підтверджено не повністю',text)

    def test_unknown_window_does_not_claim_morning_restoration(self):
        self.tick()
        self.rows['binary_sensor.energyhub_hp_night_window']['state']='unavailable'
        self.rows['switch.first_floor_heat_pump_quiet']['state']='off'
        self.tick()
        self.assertNotIn('night_exit',self.state['hp_operation_summary'])

    def test_confirmed_night_exit_reports_actual_target(self):
        self.now=self.now.replace(hour=6,minute=59)+timedelta(days=1)
        self.tick()
        self.rows['binary_sensor.energyhub_hp_night_window']['state']='off'
        self.rows['switch.first_floor_heat_pump_quiet']['state']='off'
        self.rows[hp_summary.HP]['attributes']['temperature']=21
        self.tick()
        text=' '.join(hp_summary.lines(self.state,self.client,self.now))
        self.assertIn('07:00 — тихий режим вимкнено; цільова температура 21 °C',text)
        self.assertNotIn('24 °C',text)

    def test_eco_intervals_require_confirmed_eco_and_grid_absence(self):
        self.rows['switch.first_floor_heat_pump_eco']['state']='on'
        self.tick();self.tick()
        self.rows['sensor.powmr_10_2m_grid_voltage']['state']='230'
        self.tick()
        self.tick()
        text=' '.join(hp_summary.lines(self.state,self.client,self.now))
        self.assertIn('23:00–23:02',text)
        self.assertIn('Eco під час відключення ДТЕК',text)
        self.assertEqual(1,len(self.state['hp_operation_summary']['eco_segments']))

    def test_delayed_night_exit_confirmation_uses_confirmed_target(self):
        self.now=self.now.replace(hour=6,minute=59)+timedelta(days=1)
        self.tick()
        self.rows['binary_sensor.energyhub_hp_night_window']['state']='off'
        self.tick()
        self.rows['switch.first_floor_heat_pump_quiet']['state']='off'
        self.rows[hp_summary.HP]['attributes']['temperature']=21
        self.tick()
        text=' '.join(hp_summary.lines(self.state,self.client,self.now))
        self.assertIn('07:01 — тихий режим вимкнено; цільова температура 21 °C',text)

    def test_outage_with_sufficient_solar_does_not_invent_eco(self):
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']={'state':'on'}
        self.tick();self.tick()
        self.assertNotIn('Eco під час',' '.join(hp_summary.lines(self.state,self.client,self.now)))

    def test_solar_energy_uses_actual_counter_delta(self):
        self.rows[hp_summary.MASTER]['state']='Solar-only'
        self.rows['binary_sensor.energyhub_hp_night_window']['state']='off'
        for energy in (1,1.02,1.04):
            self.rows['sensor.first_floor_heat_pump_plug_energy']={'state':str(energy),'last_updated':self.now.isoformat()}
            self.tick()
        self.now+=timedelta(days=1)
        text=' '.join(hp_summary.lines(self.state,self.client,self.now))
        self.assertIn('0.04 кВт·год',text)
        self.assertIn('Учора',text)

    def test_counter_reset_keeps_duration_but_marks_energy_incomplete(self):
        self.rows[hp_summary.MASTER]['state']='Solar-only'
        for energy in (4,0):
            self.rows['sensor.first_floor_heat_pump_plug_energy']={'state':str(energy),'last_updated':self.now.isoformat()}
            self.tick()
        self.now+=timedelta(days=1)
        self.assertIn('неповні дані',' '.join(hp_summary.lines(self.state,self.client,self.now)))

    def test_outage_combines_eco_only_for_running_smart(self):
        text=hp_summary.outage_detail(self.client)
        self.assertIn('40%',text)
        self.rows['binary_sensor.energyhub_hp_solar_sufficient']={'state':'on'}
        self.assertEqual(text,hp_summary.outage_detail(self.client))
        self.rows[hp_summary.HP]['state']='off'
        self.assertEqual('',hp_summary.outage_detail(self.client))

    def test_solar_cancellation_waits_for_off_feedback_once(self):
        import json
        from app import household_events
        self.rows[hp_summary.MASTER]['state']='Off'
        self.rows['input_text.energyhub_hp1_solar_cancelled']={'state':json.dumps({'at':self.now.timestamp(),'manual':True})}
        household_events.observe(self.state,[],self.rows,self.now)
        self.assertNotIn('solar_cancelled',self.state['household_events']['pending'])
        self.rows[hp_summary.HP]['state']='off'
        self.now+=timedelta(seconds=30)
        household_events.observe(self.state,[],self.rows,self.now)
        item=self.state['household_events']['pending'].pop('solar_cancelled')
        self.assertIn('вручну',item['text'])
        household_events.observe(self.state,[],self.rows,self.now)
        self.assertNotIn('solar_cancelled',self.state['household_events']['pending'])

    def test_old_effective_policy_does_not_become_new_activation_notice(self):
        from app.control_notifications import observe_controls
        self.state['dashboard_control_observations']={'climate_policy':{'value':'Solar-only'}}
        observe_controls(self.client,self.state,self.now)
        observe_controls(self.client,self.state,self.now+timedelta(seconds=30))
        self.assertEqual([],self.state['pending_notifications'])
