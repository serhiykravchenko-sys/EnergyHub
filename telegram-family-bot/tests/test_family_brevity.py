import copy
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from zoneinfo import ZoneInfo

from app.main import observe_battery_reserve, deliver_pending_notifications, observe_peak_load_guard
from app.events import manual_reserve_advice, peak_load_guard_message, soc_anomaly_message
from app.report import build_report

NOW = datetime(2026,9,7,13,3,tzinfo=ZoneInfo('Europe/Kyiv'))


class Client:
    def __init__(self):
        self.attributes = dict(advice_only=True, dry_run=True, recommended_soc=20,
            applied_minimum_soc=20, daily_plan_fresh=True,
            weather_source_status='fresh', grid_confidence='normal', evidence_issues=[])
    def state(self, entity):
        return dict(attributes=self.attributes)


class BrevityTests(TestCase):
    def test_missing_load_data_message_is_short_and_names_owned_devices(self):
        message = peak_load_guard_message(dict(type="control_attention",affected_loads=[dict(key="heat_pump_floor_1")],reason="restoration_telemetry_missing"))
        self.assertIn("1-го поверху",message)
        self.assertIn("непідтверджену",message)

    def test_restore_rules_in_shed_message(self):
        self.assertEqual('',peak_load_guard_message(dict(type='load_shed',reason='overload',mode='automatic',affected_loads=[{'key':'water_boiler'}])))

    def setUp(self):
        self.config=SimpleNamespace(weather_buffer_entity='reserve', timezone='Europe/Kyiv',
                                    destination_chat_id='test',peak_load_guard_event_entity='peak')
        self.client=Client()
        self.state={}
        observe_battery_reserve(self.config,self.client,self.state,NOW)

    def poll(self):
        observe_battery_reserve(self.config,self.client,self.state,NOW)

    def test_unchanged_equal_or_stale_never_notifies(self):
        self.poll()
        self.client.attributes['evidence_issues']=['stale']
        self.poll()
        self.client.attributes['recommended_soc']=40
        self.poll()
        self.assertEqual([], self.state['pending_notifications'])

    def test_new_valid_different_target_once_across_restart(self):
        self.client.attributes['recommended_soc']=40
        self.poll()
        self.state=copy.deepcopy(self.state)
        self.poll()
        self.assertEqual(1,len(self.state['pending_notifications']))
        self.assertLessEqual(len(self.state['pending_notifications'][0]['message'].splitlines()),2)

    def test_manual_override_does_not_repeat_same_advice(self):
        self.client.attributes['recommended_soc']=40
        self.poll()
        self.client.attributes['applied_minimum_soc']=60
        self.poll()
        self.assertEqual(1,len(self.state['pending_notifications']))

    def test_queued_advice_dropped_if_family_applied_target(self):
        self.client.attributes['recommended_soc']=40
        self.poll()
        self.client.attributes['applied_minimum_soc']=40
        calls=[]
        telegram=SimpleNamespace(send_message=lambda *args:calls.append(args))
        deliver_pending_notifications(self.config,telegram,self.state,NOW,self.client)
        self.assertEqual([],calls)
        self.assertEqual([],self.state['pending_notifications'])

    def test_no_fabricated_recommendation_with_incomplete_data(self):
        self.client.attributes['evidence_issues']=['missing_days']
        message=manual_reserve_advice(self.client.attributes)
        self.assertIn('недостатньо даних',message)
        self.assertEqual(1,message.count('20%'))

    def test_queued_advice_uses_current_family_setting(self):
        self.client.attributes['recommended_soc'] = 40
        self.poll()
        self.client.attributes['applied_minimum_soc'] = 60
        calls = []
        telegram = SimpleNamespace(send_message=lambda *args: calls.append(args))
        deliver_pending_notifications(self.config, telegram, self.state, NOW, self.client)
        self.assertIn('60%', calls[0][1])
        self.assertNotIn('20%', calls[0][1])
        self.assertEqual(2, len(calls[0][1].splitlines()))


    def test_automatic_requires_confirmed_applied_change(self):
        self.client.attributes.update(management_mode='automatic',applied_minimum_soc=40,
            previous_applied_soc=20,applied_change_id='change1',applied_change_confirmed=False)
        self.poll()
        self.assertEqual([],self.state['pending_notifications'])
        self.client.attributes['applied_change_confirmed']=True
        self.poll()
        self.poll()
        self.assertEqual(1,len(self.state['pending_notifications']))
        self.assertIn('Мін. заряд: <b>20% → 40%</b>',self.state['pending_notifications'][0]['message'])

    def test_morning_precise_without_invented_energy_history(self):
        message=build_report(weather_lines=[],solar_forecast=None,solar_window=None,
            threshold_w=300,consumption=5,snapshot={'soc':45,'selected_minimum_soc':20},
            night_import=3,ahm_minimum_soc=20,weather_buffer=self.client.attributes)
        self.assertNotIn('23:00–07:00',message)
        self.assertNotIn('Заряд о 07:00',message)
        self.assertIn('Мін. заряд батареї: <b>20%</b>',message)
        self.assertNotIn('SOC',message)
        self.assertNotIn('з 07:00',message)

    def test_live_messages_only_claim_confirmed_actions(self):
        self.assertEqual('',peak_load_guard_message(dict(type='load_shed',reason='overload',mode='automatic',affected_loads=[{'key':'water_boiler'}])))

    def test_no_raw_telemetry_in_anomaly(self):
        text=soc_anomaly_message(dict(timestamp=NOW.isoformat(),previous_soc=83,
            current_soc=100,elapsed_seconds=11,battery_voltage_v=54,house_load_w=500),NOW.tzinfo)
        self.assertIn('83% → 100%',text)
        for term in ['SOC','54','500','телеметрія','PV']:
            self.assertNotIn(term,text)

    def test_warning_mode_is_short_without_trial_or_switching_claims(self):
        self.assertEqual('',peak_load_guard_message(dict(type='load_shed',reason='overload',mode='automatic',affected_loads=[{'key':'water_boiler'}])))


    def test_retired_plug_notices_are_dropped_but_hp_warning_delivered(self):
        self.state['pending_notifications'] = [dict(kind='peak_load_guard_shed_recommended', message='old'),
            dict(kind='peak_load_guard_restore_recommended', message='old restore'),
            dict(kind='peak_load_guard_load_warning', message='retired overload'),
            dict(kind='peak_load_guard_hp1_battery_warning', producer='hp1_battery', message='new warning')]
        calls=[]
        deliver_pending_notifications(self.config,
            SimpleNamespace(send_message=lambda *args:calls.append(args)), self.state, NOW, self.client)
        self.assertEqual([('test','new warning')], calls)
