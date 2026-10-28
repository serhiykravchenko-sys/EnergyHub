import json
import unittest
from datetime import timedelta
from unittest.mock import patch
import test_events as fixtures
from app import restoration_messages as messages
from app.main import deliver_pending_notifications, observe_grid, observe_grid_hold

NOW=fixtures.NOW.replace(hour=19,minute=4)


class RestorationTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.EventObservationTests();fixture.setUp()
        self.config=fixture.config
        self.config.dtek_schedule_enabled=True
        self.config.dtek_dacha_group='1.1';self.config.dtek_apartment_group='2.2'
        self.client=fixtures.FakeClient({self.config.telemetry_freshness_entity:'fresh',
            self.config.operating_mode_entity:'solar',self.config.grid_voltage_entity:230,
            self.config.ahm_minimum_soc_entity:60,
            self.config.weather_buffer_entity:{'attributes':{'reserve_planning_source':'grid_confidence'}}})
        row=dict(start=NOW.replace(hour=23,minute=0).isoformat(),
                 end=(NOW+timedelta(days=1)).replace(hour=1,minute=0).isoformat())
        from grid_fixture_3623 import rows
        self.client.values.update(rows(NOW))
        self.state={'grid_restored_at':NOW.isoformat(),'dtek_raw_snapshot':dict(
            validated=True,source_status='fresh',checked_at=NOW.isoformat(),
            dates=[NOW.date().isoformat()],groups={'1.1':[row],'2.2':[row]})}

    def recovery(self):
        return dict(kind='grid_recovered',message='old',created_at=NOW.isoformat(),
            restoration_event=dict(at=NOW.isoformat(),outage_start=(NOW-timedelta(minutes=114)).isoformat(),soc=60))

    def test_agreed_house_suspended_text_has_six_lines_without_cap_or_modifier(self):
        self.state['regional_notices']={'дача':dict(kind='emergency',places=['дача'],cancelled=False,
            schedules_invalid=True,checked_at=NOW.isoformat())}
        with patch('app.source_policy.suspended',return_value=True):
            text=messages.house_text(self.config,self.client,self.state,NOW,self.recovery())
        self.assertEqual(3,len(text.splitlines()))
        for phrase in ('19:04','1 год 54 хв','60%','останні 48 год'):
            self.assertIn(phrase,text)
        for phrase in ('95%','+20','обмеження відключення','тимчасово не використовуємо'):
            self.assertNotIn(phrase,text)

    def test_apartment_has_own_duration_without_house_soc(self):
        with patch('app.source_policy.suspended',return_value=True):
            text=messages.apartment_text(self.config,self.state,NOW,NOW,NOW-timedelta(minutes=32))
        self.assertIn('Без зв’язку з Hub: <b>32 хв</b>',text)
        self.assertIn('Xiaomi Hub онлайн',text)
        self.assertNotIn('60%',text)
        self.assertNotIn('резерв',text.lower())
        unknown=messages.apartment_text(self.config,self.state,NOW,NOW,None)
        self.assertNotIn('⏱',unknown)

    def test_stale_chart_is_not_presented_and_empty_today_is_explicit(self):
        self.state['dtek_raw_snapshot']['checked_at']=(NOW-timedelta(hours=2)).isoformat()
        self.assertNotIn('23:00',messages.apartment_text(self.config,self.state,NOW,NOW,None))
        self.state['dtek_raw_snapshot'].update(checked_at=NOW.isoformat(),groups={'2.2':[]})
        self.assertIn('На сьогодні',messages.apartment_text(self.config,self.state,NOW,NOW,None))

    def test_both_directions_and_charging_coalesce_across_persisted_queue(self):
        for kind,mode in [('grid_hold_started','panic_grid_hold'),('grid_hold_released','solar'),
                          ('battery_reserve_charging','panic')]:
            with self.subTest(kind=kind):
                self.client.values[self.config.operating_mode_entity]=mode
                self.state['pending_notifications']=[dict(kind=kind,message='mode',created_at=NOW.isoformat()),self.recovery()]
                self.state=json.loads(json.dumps(self.state))
                telegram=fixtures.FakeTelegram()
                deliver_pending_notifications(self.config,telegram,self.state,NOW,client=self.client)
                self.assertEqual(1,len(telegram.messages))
                self.assertIn('ДТЕК відновився',telegram.messages[0][1])
                self.assertNotIn('Будинок працює',telegram.messages[0][1])

    def test_grid_candidate_defers_and_obsolete_mode_drops(self):
        item=dict(kind='grid_hold_started',message='mode',created_at=NOW.isoformat())
        self.client.values[self.config.operating_mode_entity]='panic_grid_hold'
        self.state['grid_candidate']=True
        self.assertEqual('defer',messages.mode_action(item,self.config,self.client,self.state,NOW))
        self.client.values[self.config.operating_mode_entity]='solar'
        self.assertEqual('drop',messages.mode_action(item,self.config,self.client,self.state,NOW))

    def test_wait_for_mode_then_refresh_restoration_at_delivery(self):
        self.state['pending_notifications']=[self.recovery()]
        self.state['operating_mode_candidate']={'mode':'solar','since':NOW.isoformat()}
        telegram=fixtures.FakeTelegram()
        deliver_pending_notifications(self.config,telegram,self.state,NOW,client=self.client)
        self.assertEqual([],telegram.messages)
        self.state['operating_mode_candidate']=None
        deliver_pending_notifications(self.config,telegram,self.state,NOW+timedelta(seconds=60),client=self.client)
        self.assertEqual(1,len(telegram.messages))
        self.assertNotIn('Будинок працює',telegram.messages[0][1])

    def test_independent_later_mode_change_still_notifies(self):
        later=NOW+timedelta(minutes=5)
        item=dict(kind='grid_hold_started',message='mode',created_at=later.isoformat())
        self.client.values[self.config.operating_mode_entity]='panic_grid_hold'
        self.assertEqual('send',messages.mode_action(item,self.config,self.client,self.state,later))

    def test_monitor_order_defers_early_mode_and_sends_only_restoration(self):
        self.state.pop('grid_restored_at')
        self.state.update(grid_online=False,outage_started_at=(NOW-timedelta(hours=1)).isoformat(),
            operating_mode_observed='solar',operating_mode_candidate={
                'mode':'panic_grid_hold','since':(NOW-timedelta(seconds=60)).isoformat()})
        self.client.values[self.config.operating_mode_entity]='panic_grid_hold'
        self.client.values[self.config.battery_soc_entity]=60
        self.client.values['binary_sensor.energyhub_grid_confirmed']=dict(state='on',attributes=dict(
            confirmation_seconds=180, checked_at=NOW.timestamp(),
            transition_pending=False, transition_at=(NOW-timedelta(seconds=180)).timestamp()))
        telegram=fixtures.FakeTelegram()
        observe_grid(self.config,self.client,self.state,NOW)
        observe_grid_hold(self.config,self.client,self.state,NOW)
        deliver_pending_notifications(self.config,telegram,self.state,NOW,client=self.client)
        self.assertEqual([],telegram.messages)
        later=NOW+timedelta(seconds=30)
        observe_grid(self.config,self.client,self.state,later)
        observe_grid_hold(self.config,self.client,self.state,later)
        deliver_pending_notifications(self.config,telegram,self.state,later,client=self.client)
        self.assertEqual(1,len(telegram.messages))
        self.assertIn('ДТЕК відновився',telegram.messages[0][1])
        self.assertNotIn('Будинок працює',telegram.messages[0][1])

    def test_stale_telemetry_omits_supply_claim_and_failed_send_keeps_queue(self):
        self.client.values[self.config.telemetry_freshness_entity]='stale'
        self.assertNotIn('Будинок працює',messages.house_text(self.config,self.client,self.state,NOW,self.recovery()))
        self.state['pending_notifications']=[self.recovery()]
        with self.assertRaises(RuntimeError):
            deliver_pending_notifications(self.config,fixtures.FakeTelegram(fail=True),self.state,NOW,client=self.client)
        self.assertEqual(1,len(self.state['pending_notifications']))
