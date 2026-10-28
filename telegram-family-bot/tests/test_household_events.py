import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
from app.house_monitor import DeviceTarget
from app import household_events


class HouseholdEventsTests(unittest.TestCase):
    def test_diagnostics_route_to_monitoring_and_co_remains_family(self):
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        pending = {key: dict(text=key, urgent=True, at=now.timestamp())
                   for key in ('solar', 'plug:event:off', 'climate:event:off', 'co:room:alarm')}
        state, tg = {'household_events': {'pending': pending}}, Mock()
        household_events.deliver(state, tg, 'family', now, quiet=True, technical_chat='owner')
        self.assertEqual([('owner', 'climate:event:off'), ('family', 'co:room:alarm')],
                         [call.args for call in tg.send_message.call_args_list])

    def test_missing_monitoring_destination_does_not_fall_back_to_family(self):
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        state = {'household_events': {'pending': {'plug:event': dict(text='plug', urgent=True, at=now.timestamp())}}}
        tg = Mock()
        self.assertTrue(household_events.deliver(state, tg, 'family', now, technical_chat=''))
        tg.send_message.assert_not_called()

    def test_direct_climate_stop_and_resume_with_plug_on(self):
        state, tg = {}, Mock()
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        rows = {household_events.CLIMATE: {'state': 'heat', 'last_changed': now.isoformat()}}
        household_events.observe(state, [], rows, now)
        for value in ('off', 'heat'):
            now += timedelta(seconds=30)
            rows[household_events.CLIMATE] = {'state': value, 'last_changed': now.isoformat()}
            household_events.observe(state, [], rows, now)
            self.assertTrue(household_events.deliver(state, tg, 'family', now, technical_chat='owner'))
        self.assertEqual(2, tg.send_message.call_count)
        self.assertTrue(all(c.args[0] == 'owner' for c in tg.send_message.call_args_list))

    def test_initial_confirmed_solar_start_retry_and_smart_takeover(self):
        state, tg = {}, Mock()
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        rows = {key: {'state': value} for key, value in {
            'sensor.energyhub_telemetry_freshness': 'fresh',
            'input_select.energyhub_climate_effective_policy': 'Solar-only',
            'input_select.energyhub_smart_heating_status': 'Normal',
            'climate.first_floor_heat_pump': 'heat'}.items()}
        household_events.observe(state, [], rows, now)
        tg.send_message.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            household_events.deliver(state, tg, 'chat', now)
        tg.send_message.side_effect = None
        self.assertTrue(household_events.deliver(state, tg, 'chat', now))
        self.assertIn('увімкнено в сонячному режимі', tg.send_message.call_args.args[1])
        household_events.observe(state, [], rows, now)
        self.assertFalse(household_events.deliver(state, tg, 'chat', now))
        rows['input_select.energyhub_smart_heating_status']['state'] = 'Solar paused'
        rows['sensor.energyhub_operating_mode'] = {'state': 'solar'}
        rows['sensor.powmr_10_2m_battery_soc'] = {'state': '20'}
        rows['input_number.ahm_minimum_soc'] = {'state': '20'}
        household_events.observe(state, [], rows, now)
        self.assertIn('зберігаємо заряд батареї', state['household_events']['pending']['solar']['text'])
        rows['input_select.energyhub_climate_effective_policy']['state'] = 'Smart'
        household_events.observe(state, [], rows, now)
        self.assertFalse(household_events.deliver(state, tg, 'chat', now))

    def test_wait_overnight_then_resume_next_day(self):
        state, tg = {}, Mock()
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        rows = {key: {'state': value} for key, value in {
            'sensor.energyhub_telemetry_freshness': 'fresh',
            'input_select.energyhub_climate_effective_policy': 'Solar-only',
            'input_select.energyhub_smart_heating_status': 'Solar paused',
            'sensor.energyhub_operating_mode': 'solar',
            'sun.sun': 'below_horizon',
            'sensor.powmr_10_2m_battery_soc': '70',
            'input_number.ahm_minimum_soc': '20',
            'sensor.powmr_10_2m_total_pv_power': '2000',
            'sensor.powmr_10_2m_grid_voltage': '230',
            'climate.first_floor_heat_pump': 'off'}.items()}
        household_events.observe(state, [], rows, now)
        self.assertIn('сонце зайшло', state['household_events']['pending']['solar']['text'])
        household_events.deliver(state, tg, 'chat', now)
        rows['sun.sun']['state'] = 'above_horizon'
        rows['climate.first_floor_heat_pump']['state'] = 'heat'
        rows['input_select.energyhub_smart_heating_status']['state'] = 'Normal'
        household_events.observe(state, [], rows, now)
        self.assertFalse(household_events.deliver(state, tg, 'chat', now))
        household_events.observe(state, [], rows, now+timedelta(seconds=60))
        now += timedelta(seconds=120)
        household_events.observe(state, [], rows, now)
        self.assertTrue(household_events.deliver(state, tg, 'chat', now))

    def test_ha_failure_removes_pending_solar_claim_and_can_requeue(self):
        state, tg = {}, Mock()
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        rows = {key: {'state': value} for key, value in {
            'sensor.energyhub_telemetry_freshness': 'fresh',
            'input_select.energyhub_climate_effective_policy': 'Solar-only',
            'input_select.energyhub_smart_heating_status': 'Normal',
            'climate.first_floor_heat_pump': 'heat'}.items()}
        household_events.observe(state, [], rows, now)
        household_events.pause(state)
        self.assertFalse(household_events.deliver(state, tg, 'chat', now))
        household_events.observe(state, [], rows, now)
        self.assertTrue(household_events.deliver(state, tg, 'chat', now))

    def test_co_clear_does_not_erase_unacknowledged_alarm(self):
        state, tg = {}, Mock()
        now = datetime(2026,10,3,tzinfo=timezone.utc)
        targets = [DeviceTarget('Room', 'binary_sensor.co')]
        household_events.observe(state, targets, {'binary_sensor.co': {'state': 'on'}}, now)
        household_events.observe(state, targets, {'binary_sensor.co': {'state': 'off'}}, now)
        self.assertTrue(household_events.deliver(state,tg,'chat',now))
        self.assertEqual(2, tg.send_message.call_count)
        self.assertIn('Спрацював', tg.send_message.call_args_list[0].args[1])
        self.assertIn('більше не', tg.send_message.call_args_list[1].args[1])

    def test_co_urgent_ack_retry_and_clear(self):
        state, tg = {}, Mock()
        now = datetime(2026,10,3,tzinfo=timezone.utc)
        targets = [DeviceTarget('Room <one>', 'binary_sensor.co')]
        household_events.observe(state, targets, {'binary_sensor.co': {'state': 'on'}}, now)
        tg.send_message.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            household_events.deliver(state,tg,'chat',now,quiet=True)
        tg.send_message.side_effect = None
        self.assertTrue(household_events.deliver(state,tg,'chat',now,quiet=True))
        self.assertIn('&lt;one&gt;', tg.send_message.call_args.args[1])
        household_events.observe(state,targets,{'binary_sensor.co': {'state':'on'}},now)
        self.assertFalse(household_events.deliver(state,tg,'chat',now))
        household_events.observe(state,targets,{'binary_sensor.co': {'state':'off'}},now)
        self.assertFalse(household_events.deliver(state,tg,'chat',now,quiet=True))
        self.assertTrue(household_events.deliver(state,tg,'chat',now))

    def test_address_baseline_and_once_per_change(self):
        state,tg={},Mock()
        now=datetime(2026,10,3,tzinfo=timezone.utc)
        rows={'sensor.energyhub_network_inventory': {'state':'ready','attributes':{'addresses':{'entry:Pump':'192.168.10.10'}}}}
        household_events.observe(state,[],rows,now)
        self.assertFalse(household_events.deliver(state,tg,'chat',now))
        rows['sensor.energyhub_network_inventory']['attributes']['addresses']['entry:Pump']='192.168.10.11'
        rows['sensor.energyhub_network_inventory']['state']='verified'
        household_events.observe(state,[],rows,now)
        self.assertTrue(household_events.deliver(state,tg,'chat',now))
        household_events.observe(state,[],rows,now)
        self.assertFalse(household_events.deliver(state,tg,'chat',now))

    def test_solar_waiting_and_observed_start(self):
        state,tg={},Mock()
        now=datetime(2026,10,3,tzinfo=timezone.utc)
        rows={key:{'state':value} for key,value in {
            'sensor.energyhub_telemetry_freshness':'fresh',
            'input_select.energyhub_climate_effective_policy':'Solar-only',
            'input_select.energyhub_smart_heating_status':'Solar paused'}.items()}
        household_events.observe(state,[],rows,now)
        self.assertTrue(household_events.deliver(state,tg,'chat',now))
        household_events.observe(state,[],rows,now)
        self.assertFalse(household_events.deliver(state,tg,'chat',now))
        rows['input_select.energyhub_smart_heating_status']['state']='Normal'
        rows['climate.first_floor_heat_pump']={'state':'unavailable'}
        household_events.observe(state,[],rows,now)
        self.assertFalse(household_events.deliver(state,tg,'chat',now))
        rows['climate.first_floor_heat_pump']={'state':'heat'}
        household_events.observe(state,[],rows,now)
        self.assertFalse(household_events.deliver(state,tg,'chat',now))
        household_events.observe(state, [], rows, now+timedelta(seconds=60))
        now += timedelta(seconds=120)
        household_events.observe(state,[],rows,now)
        self.assertTrue(household_events.deliver(state,tg,'chat',now))

    def test_retired_plug_queue_and_recovery_state_are_removed_without_sending(self):
        now = datetime(2026,10,4,tzinfo=timezone.utc)
        state = dict(hp_recovery_notice={'phase':'power_off'}, heat_pump_restart_event_id='old',
            household_events=dict(seen={'hp1_plug':dict(value='off')},
                pending={'plug:event:off':dict(text='obsolete',urgent=True,at=now.timestamp())}),
            pending_notifications=[dict(kind='heat_pump_restart_restored',message='obsolete')])
        tg = Mock()
        self.assertTrue(household_events.deliver(state,tg,'family',now,technical_chat='owner'))
        tg.send_message.assert_not_called()
        self.assertNotIn('hp_recovery_notice',state)
        self.assertFalse(state['household_events']['pending'])
        self.assertFalse(state['pending_notifications'])

    def test_climate_attribution_requires_matching_transition_not_reaction(self):
        now = datetime(2026,10,4,tzinfo=timezone.utc)
        row = {'state':'off','last_changed':now.isoformat()}
        client = Mock()
        source = 'automation.energyhub_first_floor_smart_heating'
        client._request.return_value = [dict(entity_id=source,
            when=now.isoformat(),context_entity_id=household_events.CLIMATE)]
        self.assertEqual('причина не встановлена',household_events.climate_cause(row,client,now))
        client._request.return_value = [dict(entity_id=household_events.CLIMATE,
            state='off',when=now.isoformat(),context_entity_id=source)]
        self.assertEqual('керування опаленням/охолодженням EH',household_events.climate_cause(row,client,now))

    def test_waiting_reasons_share_episode_and_flaps_delay_recovery(self):
        state, tg = {}, Mock()
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        rows = {key: {'state': value} for key, value in {
            'input_select.energyhub_climate_effective_policy': 'Solar-only',
            'input_select.energyhub_smart_heating_status': 'Solar paused',
            'sensor.energyhub_telemetry_freshness': 'fresh',
            'sensor.powmr_10_2m_battery_soc': '99',
            'input_number.ahm_minimum_soc': '20',
            'sensor.powmr_10_2m_total_pv_power': '2000',
            'sensor.powmr_10_2m_grid_voltage': 'unavailable',
            'climate.first_floor_heat_pump': 'off'}.items()}
        household_events.observe(state, [], rows, now)
        household_events.deliver(state, tg, 'chat', now)
        self.assertIn('даних інвертора', tg.send_message.call_args.args[1])
        rows['input_select.energyhub_smart_heating_status']['state'] = 'Waiting'
        household_events.observe(state, [], rows, now)
        self.assertFalse(household_events.deliver(state, tg, 'chat', now))
        rows['input_select.energyhub_smart_heating_status']['state'] = 'Normal'
        rows['climate.first_floor_heat_pump']['state'] = 'heat'
        household_events.observe(state, [], rows, now)
        household_events.observe(state, [], rows, now+timedelta(seconds=60))
        household_events.observe(state, [], rows, now+timedelta(seconds=119))
        self.assertFalse(household_events.deliver(state, tg, 'chat', now))
        household_events.observe(state, [], rows, now+timedelta(seconds=120))
        self.assertTrue(household_events.deliver(state, tg, 'chat', now))

    def test_recovery_does_not_count_unobserved_gap(self):
        state = {'household_events': {'seen': {'solar_phase': 'waiting',
                  'solar_recovery_since': 0, 'solar_observed_at': 0}, 'pending': {}}}
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        rows = {key: {'state': value} for key, value in {
            'input_select.energyhub_climate_effective_policy': 'Solar-only',
            'input_select.energyhub_smart_heating_status': 'Normal',
            'sensor.energyhub_telemetry_freshness': 'fresh',
            'climate.first_floor_heat_pump': 'heat'}.items()}
        household_events.observe(state, [], rows, now)
        self.assertEqual({}, state['household_events']['pending'])
        self.assertEqual(now.timestamp(), state['household_events']['seen']['solar_recovery_since'])
