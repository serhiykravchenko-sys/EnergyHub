from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
import json

from app import house_monitor as house, data_incidents as incidents


class HouseTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        self.state = {}
        self.config = SimpleNamespace(monitored_devices=house.parse_targets(
            'Heat pump|climate.hp;CO|binary_sensor.co|binary_sensor.zigbee2mqtt_bridge_connection_state'),
            smart_plugs=(SimpleNamespace(label='Plug', switch_entity='switch.plug'),),
            environment_sensors=(), destination_chat_id='test', technical_chat_id='')
        self.sent = []
        self.telegram = SimpleNamespace(send_message=lambda chat, text: self.sent.append(text))
        self.client = SimpleNamespace(state=lambda key: {'state': 'off'})

    def tick(self, seconds, health):
        now = self.now + timedelta(seconds=seconds)
        incidents.observe(self.state, health, now)
        incidents.deliver(self.state, self.telegram, self.config, now, self.client)

    def test_climate_off_is_available_and_missing_climate_independent_of_plug(self):
        snapshot = {'climate.hp': {'state': 'off'}, 'switch.plug': {'state': 'on'}}
        health = house.observe_snapshot(self.config, self.state, snapshot, self.now)
        self.assertTrue(health['device:climate.hp'])
        self.assertNotIn('device:switch.plug',health)
        snapshot.pop('climate.hp')
        health = house.observe_snapshot(self.config, self.state, snapshot, self.now)
        self.assertFalse(health['device:climate.hp'])
        self.assertNotIn('device:switch.plug',health)
        self.assertNotIn('device:binary_sensor.co',health)

    def test_sleeping_co_clear_state_is_not_stale_by_value_age(self):
        snapshot = {'binary_sensor.zigbee2mqtt_bridge_connection_state': {'state': 'on'},
                    'binary_sensor.co': {'state': 'off', 'last_updated': '2020-01-01'}}
        self.assertNotIn('device:binary_sensor.co',house.observe_snapshot(self.config,self.state,snapshot,self.now))

    def test_warning_three_minutes_recovery_five_and_restart_gap(self):
        key = 'device:climate.hp'
        self.state['data_source_labels'] = {key: 'Heat pump <test>'}
        for second in range(0, 180, 30):
            self.tick(second, {key: False})
        self.assertFalse(self.sent)
        self.tick(180, {key: False})
        self.assertIn('Heat pump &lt;test&gt;', self.sent[0])
        self.state = json.loads(json.dumps(self.state))
        self.tick(600, {key: True})
        for second in range(630, 900, 30):
            self.tick(second, {key: True})
        self.assertEqual(1, len(self.sent))
        self.tick(900, {key: True})
        self.assertEqual(2, len(self.sent))

    def test_unobserved_outage_does_not_count_toward_warning(self):
        key = 'device:climate.hp'
        self.tick(0, {key: False})
        self.tick(300, {key: False})
        self.assertFalse(self.sent)
        for second in range(330, 481, 30):
            self.tick(second, {key: False})
        self.assertEqual(1, len(self.sent))

    def test_parent_masks_pending_recovery_and_ha_masks_pending_warning(self):
        key = 'device:climate.hp'
        for second in range(0, 181, 30):
            self.tick(second, {key: False})
        for second in range(210, 481, 30):
            self.tick(second, {key: True})
        self.tick(510, {key: None})
        self.assertEqual(1, len(self.sent))
        self.assertIsNone(self.state['data_incidents'][key]['recovered_since'])
        self.state = {}
        self.sent.clear()
        for second in range(0, 180, 30):
            self.tick(second, {key: False})
        self.tick(180, {'ha': False})
        self.assertFalse(self.sent)

    def test_morning_snapshot_is_current_and_escapes_labels(self):
        house.observe_snapshot(self.config, self.state, {}, self.now)
        self.assertIn('0/1', house.morning_lines(self.state, self.now)[0])
        self.assertIn('недоступна', house.morning_lines(self.state, self.now + timedelta(seconds=91))[0])

    def test_explicit_parent_override_deduplicates_plug(self):
        self.config.monitored_devices = house.parse_targets('Override|switch.plug|binary_sensor.parent')
        self.assertEqual(0,len(house.targets_for(self.config)))

    def test_bms_retained_soc_requires_fresh_report(self):
        self.config.bms_entities = house.parse_targets('soc|sensor.bms')
        entities = {'sensor.bms': {'state': '100', 'last_reported': self.now.isoformat()}}
        key = 'device:sensor.bms'
        self.assertTrue(house.observe_snapshot(self.config, self.state, entities, self.now)[key])
        self.assertFalse(house.observe_snapshot(self.config, self.state, entities, self.now + timedelta(seconds=91))[key])

    def test_invalid_inventory_rejected(self):
        for value in ('Bad', 'a|sensor.x;b|sensor.x', 'a|sensor.x|sensor.x'):
            with self.assertRaises(ValueError):
                house.parse_targets(value)

    def test_unchanged_bms_soc_uses_same_source_primary_updates(self):
        self.config.bms_entities = house.parse_targets('soc|sensor.bms;current|sensor.amps;voltage|sensor.volts')
        old = (self.now-timedelta(hours=2)).isoformat()
        entities = {'sensor.bms': {'state': '99', 'last_updated': old},
                    'sensor.amps': {'state': '20', 'last_updated': self.now.isoformat()},
                    'sensor.volts': {'state': '53.7', 'last_updated': old}}
        key = 'device:sensor.bms'
        self.assertTrue(house.observe_snapshot(self.config,self.state,entities,self.now)[key])
        self.assertFalse(house.observe_snapshot(self.config,self.state,entities,self.now+timedelta(seconds=91))[key])
        entities['sensor.volts']['last_updated'] = (self.now+timedelta(seconds=91)).isoformat()
        self.assertTrue(house.observe_snapshot(self.config,self.state,entities,self.now+timedelta(seconds=91))[key])

    def test_fresh_sibling_never_masks_invalid_bms_primary_channel(self):
        self.config.bms_entities = house.parse_targets('soc|sensor.bms;current|sensor.amps;voltage|sensor.volts')
        key = 'device:sensor.bms'
        for field,bad in [('sensor.bms','nan'),('sensor.bms','101'),('sensor.bms','unavailable'),
                          ('sensor.amps','unknown'),('sensor.volts','0')]:
            entities={e:{'state':v,'last_updated':self.now.isoformat()}
                      for e,v in [('sensor.bms','99'),('sensor.amps','20'),('sensor.volts','53.7')]}
            entities[field]['state']=bad
            self.assertFalse(house.observe_snapshot(self.config,self.state,entities,self.now)[key])
        entities['sensor.volts']['state']='53.7'
        entities['sensor.volts']['last_updated']=(self.now+timedelta(minutes=5)).isoformat()
        self.assertFalse(house.observe_snapshot(self.config,self.state,entities,self.now)[key])
