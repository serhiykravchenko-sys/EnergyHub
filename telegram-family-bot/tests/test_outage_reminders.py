import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from unittest.mock import Mock
from app import outage_schedule as dtek
from app.main import deliver_pending_notifications
from app.report import overnight_family_event_lines

NOW=datetime(2026,10,7,14,tzinfo=ZoneInfo('Europe/Kyiv'))


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_apartment_group='2.2',
            battery_soc_entity='soc',telemetry_freshness_entity='fresh',destination_chat_id='family',technical_chat_id='owner',timezone='Europe/Kyiv')
        self.interval=dict(start=(NOW+timedelta(hours=1)).isoformat(),end=(NOW+timedelta(hours=5)).isoformat())
        self.state={'dtek_snapshot':dict(source_status='fresh',validated=True,checked_at=NOW.isoformat(),groups={'1.1':[self.interval],'2.2':[self.interval]})}
        self.rows={'soc':{'state':'78'},'fresh':{'state':'fresh'},dtek.STATUS_ENTITY:dict(state='waiting',attributes=dict(
            start=self.interval['start'],end=self.interval['end'],checked_at=NOW.isoformat(),target_soc=95,current_soc=78))}
        from grid_fixture_3623 import rows
        self.rows.update(rows(NOW))
        self.client=SimpleNamespace(state=lambda e:self.rows.get(e))

    def test_one_reminder_per_place_and_no_restart_replay(self):
        self.assertTrue(dtek.queue_reminders(self.cfg,self.client,self.state,NOW))
        queue=self.state['pending_notifications']
        self.assertEqual(2,len(queue))
        self.assertIn('ціль підготовки',queue[0]['message'])
        self.assertNotIn('🔋',queue[1]['message'])
        self.assertFalse(dtek.queue_reminders(self.cfg,self.client,self.state,NOW+timedelta(seconds=30)))

    def test_late_read_catches_up_once_with_actual_remaining_time(self):
        late=NOW+timedelta(minutes=20)
        self.state['dtek_snapshot']['checked_at']=late.isoformat()
        self.assertTrue(dtek.queue_reminders(self.cfg,self.client,self.state,late))
        self.assertIn('через 40 хв',self.state['pending_notifications'][0]['message'])
        self.assertFalse(dtek.queue_reminders(self.cfg,self.client,self.state,late+timedelta(seconds=30)))

    def test_source_error_and_recovery_notices_go_to_owner(self):
        self.state['pending_notifications']=[dict(kind=kind,message='technical source notice',created_at=NOW.isoformat()) for kind in ('technical_dtek_source','technical_dtek_recovered')]
        tg=Mock()
        deliver_pending_notifications(self.cfg,tg,self.state,NOW,self.client)
        self.assertEqual(2,tg.send_message.call_count)
        for call in tg.send_message.call_args_list:
            self.assertEqual('owner',call.args[0])

    def test_target_reached_is_not_autonomy_guarantee(self):
        self.rows['soc']['state']='95'
        dtek.queue_reminders(self.cfg,self.client,self.state,NOW)
        text=self.state['pending_notifications'][0]['message']
        self.assertIn('Заряд досяг цілі підготовки',text)
        self.assertNotIn('достатньо на',text)

    def test_stale_source_cancelled_interval_and_expired_reminder(self):
        dtek.queue_reminders(self.cfg,self.client,self.state,NOW)
        item=self.state['pending_notifications'][0]
        self.state['dtek_snapshot']['groups']['1.1']=[]
        self.assertEqual('',dtek.reminder_text(self.cfg,self.client,self.state,NOW,item))
        self.state['dtek_snapshot']['groups']['1.1']=[self.interval]
        self.assertEqual('',dtek.reminder_text(self.cfg,self.client,self.state,NOW+timedelta(hours=1),item))
        self.state['dtek_snapshot']['source_status']='suspended'
        self.assertEqual('',dtek.reminder_text(self.cfg,self.client,self.state,NOW,item))

    def test_unavailable_soc_still_delivers_schedule(self):
        self.rows['soc']['state']='unavailable'
        dtek.queue_reminders(self.cfg,self.client,self.state,NOW)
        self.assertIn('не підтверджено',self.state['pending_notifications'][0]['message'])

    def test_invalid_plan_timestamp_does_not_hide_valid_schedule(self):
        self.rows[dtek.STATUS_ENTITY]['attributes']['checked_at']='invalid'
        dtek.queue_reminders(self.cfg,self.client,self.state,NOW)
        self.assertEqual(2,len(self.state['pending_notifications']))
        self.assertIn('ціль підготовки не підтверджено',self.state['pending_notifications'][0]['message'])

    def test_cancelled_source_cannot_authorize_old_charging_notice(self):
        self.rows[dtek.STATUS_ENTITY].update(state='charging')
        self.rows[dtek.STATUS_ENTITY]['attributes'].update(phase='charging',acknowledged=True,observed_charge_a=10)
        self.assertTrue(dtek.preparation_for_state(self.cfg,self.client,self.state,NOW))
        self.state['dtek_snapshot']['groups']['1.1']=[]
        self.assertEqual('',dtek.preparation_for_state(self.cfg,self.client,self.state,NOW))

    def test_old_pending_preparation_is_not_reused_for_new_outage(self):
        self.rows[dtek.STATUS_ENTITY].update(state='charging')
        self.rows[dtek.STATUS_ENTITY]['attributes'].update(phase='charging',acknowledged=True,observed_charge_a=10)
        self.state['pending_notifications']=[dict(kind='dtek_preparation',
            start=(NOW+timedelta(minutes=30)).isoformat(),created_at=NOW.isoformat(),message='obsolete')]
        tg=Mock()
        deliver_pending_notifications(self.cfg,tg,self.state,NOW,self.client)
        tg.send_message.assert_not_called()
        self.assertFalse(self.state['pending_notifications'])

    def test_charging_notice_remains_separate_from_prospective_reminder(self):
        self.rows['sensor.powmr_10_2m_grid_voltage']={'state':'230'}
        self.rows[dtek.STATUS_ENTITY].update(state='charging')
        self.rows[dtek.STATUS_ENTITY]['attributes'].update(phase='charging',acknowledged=True,observed_charge_a=10)
        self.state['pending_notifications']=[dict(kind='dtek_preparation',start=self.interval['start'],message='old')]
        dtek.queue_reminders(self.cfg,self.client,self.state,NOW)
        queue=self.state['pending_notifications']
        self.assertEqual(3,len(queue))
        self.assertEqual('dtek_preparation',queue[0]['kind'])
        self.assertIn('дозаряджаємо від ДТЕК до',dtek.reminder_text(self.cfg,self.client,self.state,NOW,queue[1]))

    def test_solar_and_holding_do_not_generate_charging_notices(self):
        for phase in ('solar','holding'):
            self.rows[dtek.STATUS_ENTITY].update(state=phase)
            self.rows[dtek.STATUS_ENTITY]['attributes'].update(phase=phase,acknowledged=True,observed_charge_a=10)
            self.assertEqual('',dtek.preparation_line(self.client,NOW))

    def test_quiet_reminder_is_not_sent_or_replayed_in_morning(self):
        night=NOW.replace(hour=23)
        self.interval.update(start=(night+timedelta(hours=1)).isoformat(),end=(night+timedelta(hours=5)).isoformat())
        self.state['dtek_snapshot']['checked_at']=night.isoformat()
        dtek.queue_reminders(self.cfg,self.client,self.state,night)
        tg=Mock()
        deliver_pending_notifications(self.cfg,tg,self.state,night,self.client)
        tg.send_message.assert_not_called()
        self.assertFalse(self.state['pending_notifications'])
        self.assertFalse(self.state.get('overnight_family_events'))

    def test_old_repeat_topups_collapse_but_new_episode_is_retained(self):
        def event(kind,minute,**extra):
            return dict(kind=kind,created_at=(NOW+timedelta(minutes=minute)).isoformat(),reserve_soc=40,**extra)
        events=[event('grid_hold_started',0,soc=40)]+[event('battery_reserve_charging',m) for m in (5,10,20)]
        self.assertEqual(1,len(overnight_family_event_lines(events)))
        events += [event('grid_hold_released',30,release_soc=50),event('battery_reserve_charging',40)]
        self.assertEqual(3,len(overnight_family_event_lines(events)))


    def test_ready_does_not_replay_queued_charging_start(self):
        self.rows[dtek.STATUS_ENTITY].update(state='holding')
        self.rows[dtek.STATUS_ENTITY]['attributes'].update(phase='holding',acknowledged=True,current_soc=96)
        self.state['pending_notifications']=[dict(kind='dtek_preparation',message='old charging',created_at=NOW.isoformat(),start=self.interval['start'])]
        tg=Mock()
        deliver_pending_notifications(self.cfg,tg,self.state,NOW,self.client)
        tg.send_message.assert_not_called()
        self.assertEqual([],self.state['pending_notifications'])

    def test_reminder_distinguishes_solar_and_insufficient_time(self):
        attrs=self.rows[dtek.STATUS_ENTITY]['attributes']
        attrs.update(phase='solar',solar_forecast_complete=True)
        dtek.queue_reminders(self.cfg,self.client,self.state,NOW)
        item=self.state['pending_notifications'][0]
        self.assertIn('Очікуємо поповнення',dtek.reminder_text(self.cfg,self.client,self.state,NOW,item))
        attrs['preparation_time_insufficient']=True
        self.assertNotIn('може не вистачити',dtek.reminder_text(self.cfg,self.client,self.state,NOW,item))
        attrs.update(estimated_grid_minutes=600,forecast_net_solar_kwh=0)
        self.assertIn('може не вистачити',dtek.reminder_text(self.cfg,self.client,self.state,NOW,item))

if __name__=='__main__':unittest.main()
