from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
import json
from app import data_incidents as monitor
from app.home_assistant import HomeAssistantError
from app.events import soc_anomaly_report_lines


class IncidentTests(TestCase):
    def setUp(self):
        self.start=datetime(2026,9,8,12,tzinfo=timezone.utc)
        self.state={}
        self.sent=[]
        self.chats=[]
        self.config=SimpleNamespace(destination_chat_id='family', technical_chat_id='technical')
        self.telegram=SimpleNamespace(send_message=lambda chat,msg:(self.chats.append(chat),self.sent.append(msg)))
        self.client=SimpleNamespace(state=lambda key: {'state':'off'})

    def tick(self,seconds,health,send=True):
        now=self.start+timedelta(seconds=seconds)
        monitor.observe(self.state,health,now)
        if send:
            monitor.deliver(self.state,self.telegram,self.config,now,self.client)

    def test_old_false_control_history_is_dropped_without_losing_other_sources(self):
        past = self.start.timestamp() - 60
        record = dict(start=past, bad_since=past, intervals=[], warned=True,
                      recovered_since=None, last_seen=past)
        self.state.update(data_health_schema=2,
                          data_incidents={'control':dict(record), 'inverter':dict(record)},
                          data_incident_history=[dict(record,key='control',end=past),
                                                 dict(record,key='zigbee',end=past)])
        monitor.observe(self.state, {}, self.start)
        self.assertEqual(3, self.state['data_health_schema'])
        self.assertNotIn('control', self.state['data_incidents'])
        self.assertIn('inverter', self.state['data_incidents'])
        self.assertEqual(['zigbee'], [r['key'] for r in self.state['data_incident_history']])

    def test_inverter_five_minute_boundary(self):
        self.tick(0,{'inverter':False})
        self.tick(299,{'inverter':False})
        self.assertFalse(self.sent)
        self.tick(300,{'inverter':False})
        self.assertEqual(1,len(self.sent))
        self.assertIn('>5 хв',self.sent[0])

    def test_silent_short_failure_and_no_recovery_message(self):
        self.tick(0,{'inverter':False})
        for second in range(60,421,60):
            self.tick(second,{'inverter':True})
        self.assertFalse(self.sent)
        self.assertFalse(self.state['data_incidents'])

    def test_five_continuous_minutes_and_flap_one_incident(self):
        self.tick(0,{'inverter':False})
        self.tick(300,{'inverter':False})
        for second in (320,380,440):
            self.tick(second,{'inverter':True})
        self.tick(470,{'inverter':False})
        for second in range(520,820,60):
            self.tick(second,{'inverter':True})
        self.assertEqual(1,len(self.sent))
        self.tick(820,{'inverter':True})
        self.assertEqual(2,len(self.sent))
        self.assertIn('вимкнений вручну',self.sent[1])

    def test_restart_preserves_warning_and_requires_observed_recovery(self):
        self.tick(0,{'bridge':False})
        self.tick(300,{'bridge':False})
        self.state=json.loads(json.dumps(self.state))
        self.tick(320,{'bridge':True})
        self.tick(720,{'bridge':True})
        self.assertEqual(1,len(self.sent))
        for second in range(780,1021,60):
            self.tick(second,{'bridge':True})
        self.assertEqual(2,len(self.sent))
        self.assertEqual(['technical', 'technical'], self.chats)

    def test_simultaneous_sources_one_notice(self):
        values={'inverter':False,'load_water_pump':False}
        self.tick(0,values)
        self.tick(300,values)
        self.assertEqual(1,len(self.sent))
        self.assertIn('споживання насоса',self.sent[0])

    def test_failed_delivery_does_not_mark_warned(self):
        self.tick(0,{'inverter':False})
        def fail(*args): raise OSError('offline')
        self.telegram.send_message=fail
        with self.assertRaises(OSError):
            self.tick(300,{'inverter':False})
        self.assertFalse(self.state['data_incidents']['inverter']['warned'])

    def test_ha_failure_masks_children(self):
        def fail(key): raise HomeAssistantError('offline')
        result=monitor.collect(SimpleNamespace(state=fail),SimpleNamespace(telemetry_freshness_entity='fresh'),{},self.start)
        self.assertEqual({'ha':False},result)

    def test_morning_uses_actual_missing_time_not_recovery_wait(self):
        self.tick(0,{'inverter':False})
        self.tick(360,{'inverter':False})
        for second in range(420,721,60):
            self.tick(second,{'inverter':True})
        lines=monitor.morning_lines(self.state,self.start+timedelta(days=1))
        self.assertEqual(1,len(lines))
        self.assertIn('разом 7 хв',lines[0])
        self.assertIn('перебоїв — 1',lines[0])

    def test_single_brief_outage_omitted_from_morning(self):
        self.tick(0,{'inverter':False})
        self.tick(30,{'inverter':True})
        self.assertFalse(monitor.morning_lines(self.state,self.start+timedelta(days=1)))

    def test_repeated_brief_outages_in_morning(self):
        for second,good in ((0,False),(20,True),(40,False),(60,True),(80,False),(100,True)):
            self.tick(second,{'inverter':good})
        self.assertFalse(monitor.morning_lines(self.state,self.start+timedelta(days=1)))

    def test_morning_source_thresholds_are_applied_at_the_boundary(self):
        now=self.start+timedelta(hours=1)
        def lines(key,duration):
            state={'data_incident_history':[dict(key=key,bad_since=None,
                intervals=[[now.timestamp()-duration,now.timestamp()]],end=now.timestamp())]}
            return monitor.morning_lines(state,now)
        self.assertFalse(lines('zigbee',119))
        self.assertIn('Zigbee2MQTT',lines('zigbee',120)[0])
        self.assertFalse(lines('inverter',299))
        self.assertIn('інвертора',lines('inverter',300)[0])

    def test_recovery_not_sent_while_ha_is_unreachable(self):
        self.tick(0,{'inverter':False})
        self.tick(300,{'inverter':False})
        def fail(key): raise HomeAssistantError('offline')
        self.client=SimpleNamespace(state=fail)
        for second in range(320,621,60):
            self.tick(second,{'inverter':True})
        self.assertEqual(1,len(self.sent))
        self.assertTrue(self.state['data_incidents']['inverter']['warned'])

    def test_unobserved_child_is_not_recovered_by_ha_outage(self):
        self.tick(0,{'inverter':False})
        self.tick(300,{'inverter':False})
        self.tick(310,{'inverter':True})
        self.tick(620,{'ha':False})
        self.assertEqual(1,len(self.sent))

    def test_one_plug_notice_does_not_name_inverter(self):
        self.tick(0,{'load_water_pump':False})
        self.tick(180,{'load_water_pump':False})
        self.assertNotIn('інвертора',self.sent[0])

    def test_collect_distinguishes_one_missing_plug(self):
        config=SimpleNamespace(telemetry_freshness_entity='fresh',battery_soc_entity='charge',
            grid_voltage_entity='voltage',solar_forecast_entity='forecast',weather_buffer_entity='reserve')
        rows=[dict(key=k,state='on',availability='not_applicable',power_w=0,
                   power_observed_at=self.start.isoformat()) for k in monitor.DEVICES]
        rows[0]['power_w']=None
        entities={'fresh':{'state':'fresh'},'charge':{'state':'80'},'voltage':{'state':'230'},
            'forecast':{'state':'40'},'reserve':{'state':'ready','attributes':{'evidence_issues':[]}},
            'input_boolean.energyhub_load_control_armed':{'state':'off'},
            'sensor.energyhub_peak_load_guard':{'attributes':{'load_snapshot_at':self.start.isoformat(),'participants':rows}}}
        state={'uhmc_last_snapshot':{'source_status':'fresh','observed_at':self.start.isoformat()}}
        client=SimpleNamespace(state=lambda key:entities.get(key))
        health=monitor.collect(client,config,state,self.start)
        self.assertEqual(['load_water_pump'],[key for key,value in health.items() if not value])
        self.assertNotIn('pv2',health)
        entities['sensor.energyhub_pv2_telemetry_freshness']={'state':'fresh'}
        monitor.collect(client,config,state,self.start)
        entities.pop('sensor.energyhub_pv2_telemetry_freshness')
        self.assertFalse(monitor.collect(client,config,state,self.start)['pv2'])

    def test_online_unchanged_zigbee_power_is_healthy(self):
        config=SimpleNamespace(telemetry_freshness_entity='fresh',battery_soc_entity='charge',
            grid_voltage_entity='voltage',solar_forecast_entity='forecast',weather_buffer_entity='reserve')
        old=(self.start-timedelta(hours=8)).isoformat()
        rows=[dict(key=k,state='on',availability=('online' if 'floor_1' in k or 'floor_2' in k else 'not_applicable'),
                   power_w=1,power_observed_at=old) for k in monitor.DEVICES]
        entities={'fresh':{'state':'fresh'},'charge':{'state':'80'},'voltage':{'state':'230'},
            'forecast':{'state':'40'},'reserve':{'state':'ready','attributes':{'evidence_issues':[]}},
            'input_boolean.energyhub_load_control_armed':{'state':'off'},
            'binary_sensor.zigbee2mqtt_bridge_connection_state':{'state':'on'},
            'sensor.energyhub_peak_load_guard':{'attributes':{'load_snapshot_at':self.start.isoformat(),'participants':rows}}}
        health=monitor.collect(SimpleNamespace(state=lambda key:entities.get(key)),config,{},self.start)
        self.assertTrue(health['zigbee'])
        self.assertTrue(all(health['load_'+key] for key in monitor.DEVICES))

    def test_parent_bridge_outage_pauses_child_attribution(self):
        self.tick(0,{'load_water_pump':False})
        self.tick(60,{'load_water_pump':None,'bridge':False})
        record=self.state['data_incidents']['load_water_pump']
        self.assertIsNone(record['bad_since'])
        self.assertEqual(60,record['intervals'][0][1]-record['intervals'][0][0])

    def test_zigbee_bridge_outage_masks_only_its_two_child_plugs(self):
        config=SimpleNamespace(telemetry_freshness_entity='fresh',battery_soc_entity='charge',
            grid_voltage_entity='voltage',solar_forecast_entity='forecast',weather_buffer_entity='reserve')
        rows=[dict(key=k,state='on',availability=('unavailable' if 'floor_1' in k or 'floor_2' in k else 'not_applicable'),
                   power_w=1) for k in monitor.DEVICES]
        entities={'fresh':{'state':'fresh'},'charge':{'state':'80'},'voltage':{'state':'230'},
            'forecast':{'state':'40'},'reserve':{'state':'ready','attributes':{'evidence_issues':[]}},
            'input_boolean.energyhub_load_control_armed':{'state':'off'},
            'binary_sensor.zigbee2mqtt_bridge_connection_state':{'state':'off'},
            'sensor.energyhub_peak_load_guard':{'attributes':{'load_snapshot_at':self.start.isoformat(),'participants':rows}}}
        health=monitor.collect(SimpleNamespace(state=lambda key:entities.get(key)),config,{},self.start)
        self.assertFalse(health['zigbee'])
        self.assertIsNone(health['load_heat_pump_floor_1'])
        self.assertIsNone(health['load_heat_pump_floor_2'])
        self.assertTrue(health['load_water_pump'])

    def test_battery_recurrence_counts_days_not_event_count(self):
        event=dict(timestamp=self.start.isoformat(),previous_soc=90,current_soc=100)
        history={f'2026-09-{day:02d}':True for day in (6,7,8)}
        lines=soc_anomaly_report_lines([event,event],timezone.utc,history_days=history)
        self.assertIn('3 дні поспіль',lines[0])
        self.assertNotIn('SOC',lines[0])
        lines=soc_anomaly_report_lines([event,event],timezone.utc,history_days={'2026-09-08':True})
        self.assertNotIn('поспіль',lines[0])
