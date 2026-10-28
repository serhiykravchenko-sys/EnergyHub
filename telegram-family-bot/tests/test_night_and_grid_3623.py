import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from app import night_charge, hp_daily_energy, outage_schedule
from app.grid_evidence import qualified
from app.main import deliver_pending_notifications
from grid_fixture_3623 import rows
from unittest.mock import Mock
from unittest.mock import patch
import test_outage_reminders as fixture

NOW = fixture.NOW


class NightAndGridTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(timezone='Europe/Kyiv', destination_chat_id='family',
            technical_chat_id='owner', family_quiet_start='23:00', send_time='08:00')
        self.rows = rows(NOW)
        self.client = SimpleNamespace(state=lambda e:self.rows.get(e))
        self.plan=dict(day=NOW.date().isoformat(), checked_at=NOW.isoformat(), phase='charging',
            current_soc=70, target_soc=90, deficit_kwh=8, consumption_kwh=15, solar_kwh=7,
            source='fresh', acknowledged=True, observed_charge_a=20)
        self.rows[night_charge.ENTITY]=dict(attributes=self.plan)

    def test_grid_is_independent_of_schedule_and_unknown_is_not_online(self):
        self.assertTrue(qualified(self.config,self.client,NOW))
        self.rows['binary_sensor.energyhub_grid_confirmed']['attributes']['transition_pending']=True
        self.assertIsNone(qualified(self.config,self.client,NOW))
        self.rows.pop('binary_sensor.energyhub_grid_confirmed')
        self.assertIsNone(qualified(self.config,self.client,NOW))

    def test_stale_or_contradictory_evidence_cannot_assert_supply(self):
        self.assertIsNone(qualified(self.config,self.client,NOW+timedelta(seconds=31)))
        self.rows['sensor.powmr_10_2m_grid_voltage']['state']='0'
        self.assertIsNone(qualified(self.config,self.client,NOW))

    def test_night_decisions_and_offline_plan_wording(self):
        text=night_charge.decision(self.config,self.client,NOW,self.plan)
        self.assertIn('15 kWh',text);self.assertIn('7 kWh',text)
        self.assertIn('Дозаряджаємо',text)
        self.rows.update(rows(NOW,online=False))
        text=night_charge.decision(self.config,self.client,NOW,self.plan)
        self.assertNotIn('Дозаряджаємо',text)
        self.assertIn('Очікуємо',text)

    def test_enough_charge_zero_deficit_and_fallback_are_distinct(self):
        self.plan.update(current_soc=91,planned_target_soc=90,target_soc=91)
        self.assertIn('ціль <b>90%',night_charge.decision(self.config,self.client,NOW,self.plan))
        self.plan.update(deficit_kwh=0)
        self.assertIn('покриває',night_charge.decision(self.config,self.client,NOW,self.plan))
        self.plan.update(deficit_kwh=8,source='fallback')
        self.assertIn('останній підтверджений',night_charge.decision(self.config,self.client,NOW,self.plan))
        self.plan.update(phase='skipped')
        self.assertNotIn('покриває',night_charge.decision(self.config,self.client,NOW,self.plan))

    def test_reassessment_without_changed_decision_does_not_spam(self):
        state={}
        self.assertTrue(night_charge.observe(self.config,self.client,state,NOW))
        self.plan.update(stage='correction', current_soc=80)
        self.assertFalse(night_charge.observe(self.config,self.client,state,NOW))
        self.plan['target_soc']=95
        self.assertTrue(night_charge.observe(self.config,self.client,state,NOW))

    def test_actual_morning_outcome_and_day_boundary(self):
        self.plan['completed']=dict(finished=True,end=NOW.replace(hour=7,minute=0,second=0).isoformat(),finished_at=NOW.replace(hour=7,minute=0,second=5).isoformat(),day=NOW.date().isoformat(),source='fresh',deficit_kwh=8,
                                    start_soc=70,end_soc=82,target_soc=90,reserve_soc=40,consumption_kwh=13,solar_kwh=5)
        text=night_charge.morning(self.client,NOW)
        self.assertNotIn('70% → 82%',text);self.assertIn('90%',text)
        self.assertIn('не досягнуто',text)
        self.plan['completed']['day']='2020-01-01'
        self.assertIn('не підтверджено',night_charge.morning(self.client,NOW))

    def test_online_or_unknown_grid_suppresses_restoration_and_stale_soc_does_not_enable_it(self):
        f=fixture.ReminderTests();f.setUp()
        now=NOW+timedelta(hours=4,minutes=45)
        f.state['dtek_snapshot']['checked_at']=now.isoformat()
        f.rows.update(rows(now))
        self.assertFalse(outage_schedule.queue_restoration_reminders(f.cfg,f.client,f.state,now))
        f.rows['fresh']['state']='unavailable'
        f.rows.update(rows(now,online=False))
        self.assertFalse(outage_schedule.queue_restoration_reminders(f.cfg,f.client,f.state,now))

    def test_pending_connected_claim_is_dropped_after_supply_loss(self):
        f=fixture.ReminderTests();f.setUp()
        f.cfg.grid_voltage_entity='sensor.powmr_10_2m_grid_voltage'
        f.rows.update(rows(NOW,online=False))
        f.state['pending_notifications']=[dict(kind='grid_hold_started',message='connected',created_at=NOW.isoformat())]
        tg=Mock()
        deliver_pending_notifications(f.cfg,tg,f.state,NOW,f.client)
        tg.send_message.assert_not_called()

    def test_active_window_topup_and_hold_do_not_use_preparation_deadline(self):
        f=fixture.ReminderTests();f.setUp()
        row=f.rows[outage_schedule.STATUS_ENTITY]
        row['state']='charging'
        row['attributes'].update(phase='charging', start=(NOW-timedelta(hours=1)).isoformat(),
            end=(NOW+timedelta(hours=4)).isoformat(), acknowledged=True, observed_charge_a=10,
            preparation_time_insufficient=True)
        text=outage_schedule.preparation_line(f.client,NOW)
        self.assertIn('повторні',text);self.assertNotIn('недостатньо',text)
        row['state']='holding';row['attributes'].update(phase='holding',current_soc=95)
        self.assertEqual('',outage_schedule.preparation_line(f.client,NOW))


    def test_disabled_schedule_still_publishes_independent_night_inputs(self):
        self.config.dtek_schedule_enabled=False
        self.config.solar_forecast_entity='sensor.today'
        self.config.dtek_solar_forecast_tomorrow_entity='sensor.tomorrow'
        self.rows['sensor.today']={'state':'7'}
        self.rows['sensor.tomorrow']={'state':'5'}
        self.client.publish_mqtt=Mock()
        monitor=outage_schedule.ScheduleMonitor()
        self.addCleanup(monitor.executor.shutdown,wait=False)
        with patch('app.service_incidents.source_refresh',return_value=NOW.timestamp()):
            monitor.poll(self.config,self.client,{},NOW)
        payload=self.client.publish_mqtt.call_args.args[1]
        self.assertEqual('disabled',payload['source_status'])
        self.assertFalse(payload['validated'])
        self.assertEqual(NOW.isoformat(),payload['planning_checked_at'])
        self.assertEqual(5,payload['night_forecasts'][(NOW+timedelta(days=1)).date().isoformat()])

    def test_fallback_is_visible_in_morning_despite_quiet_hours(self):
        self.plan['completed']=dict(finished=True,end=NOW.replace(hour=7,minute=0,second=0).isoformat(),finished_at=NOW.replace(hour=7,minute=0,second=5).isoformat(),day=NOW.date().isoformat(),source='fallback',deficit_kwh=8,
            start_soc=70,end_soc=90,target_soc=90)
        self.assertIn('останній підтверджений',night_charge.morning(self.client,NOW))
