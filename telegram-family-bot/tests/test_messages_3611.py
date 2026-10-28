import unittest
from datetime import timedelta
from app import outage_schedule as dtek
from app.report import build_report, overnight_family_event_lines
from app.events import outage_message, recovery_message
import test_outage_reminders as fixtures
NOW=fixtures.NOW


class MessageTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.ReminderTests();f.setUp()
        self.cfg,self.state,self.rows,self.client=f.cfg,f.state,f.rows,f.client

    def test_actual_charging_requires_mode_ack_and_positive_current(self):
        data=self.rows[dtek.STATUS_ENTITY]['attributes']
        self.rows[dtek.STATUS_ENTITY]['state']='charging'
        data.update(phase='charging',acknowledged=True,observed_charge_a=0)
        self.assertEqual('',dtek.preparation_line(self.client,NOW))
        data['observed_charge_a']=10
        text=dtek.preparation_line(self.client,NOW)
        self.assertIn('78% → 95%',text)
        self.assertIn('Заряджаємо перед відключенням',text)

    def test_grid_returns_early_current_window_not_next_outage(self):
        doc=self.state['dtek_snapshot']
        doc['dates']=[NOW.date().isoformat()]
        doc['groups']['1.1']=[dict(start=(NOW-timedelta(hours=1)).isoformat(),end=(NOW+timedelta(hours=1)).isoformat())]
        text=dtek.context(self.state,NOW,True,'1.1')
        self.assertIn('Можливе повторне відключення',text)
        self.assertNotIn('більше не заплановано',text)
        self.assertIn('до <b>15:00</b>',text)
        doc['groups']['1.1'].append(dict(start=NOW.replace(hour=23).isoformat(),end=(NOW+timedelta(days=1)).replace(hour=1).isoformat()))
        self.assertIn('Можливе повторне відключення',dtek.context(self.state,NOW,True,'1.1'))

    def test_recovery_plan_retains_live_window_instead_of_announcing_done(self):
        doc=self.state['dtek_snapshot']
        doc['groups']['1.1']=[dict(start=(NOW-timedelta(hours=1)).isoformat(),end=(NOW+timedelta(hours=1)).isoformat())]
        text=dtek.recovery_plan(self.cfg,self.client,self.state,NOW)
        self.assertIn('13:00–15:00',text)
        self.assertIn('до кінця планового відключення',text)
        self.assertNotIn('більше не заплановано',text)

    def test_live_window_charge_notice_uses_end_not_past_start(self):
        row=self.rows[dtek.STATUS_ENTITY]
        row['state']='charging'
        row['attributes'].update(start=(NOW-timedelta(hours=1)).isoformat(),end=(NOW+timedelta(hours=1)).isoformat(),
            phase='charging',acknowledged=True,observed_charge_a=10)
        text=dtek.preparation_line(self.client,NOW)
        self.assertIn('до 15:00',text)
        self.assertIn('до 15:00</b>',text)
        self.assertNotIn('до відключення о',text)
        row['attributes']['observed_charge_a']=0
        self.assertEqual('',dtek.preparation_line(self.client,NOW))

    def test_one_actual_night_loss_without_duplicate_reserve_warning(self):
        events=[dict(kind='grid_lost',created_at=NOW.isoformat(),message=outage_message(NOW,44)),
                dict(kind='reserve_0',created_at=NOW.isoformat(),message='ДТЕК недоступний. Заряд 44%')]
        self.assertEqual(1,len(overnight_family_event_lines(events)))

    def test_status_contains_co_after_soc_and_no_control_footer(self):
        text=build_report(weather_lines=[],solar_forecast=None,solar_window=None,threshold_w=300,
                          consumption=None,snapshot={},night_import=None,current_soc=44,
                          current_strategy_lines=['🏠 Показники на 08:00'],co2_lines=['🌿 CO₂: 510 ppm'])
        self.assertLess(text.index('44%'),text.index('510 ppm'))
        self.assertNotIn('Керування',text)

    def test_loss_and_restore_are_concise_but_times_and_duration_retained(self):
        loss=outage_message(NOW,89)
        restore=recovery_message(NOW+timedelta(minutes=34),NOW,88)
        self.assertEqual(2,len(loss.splitlines()))
        self.assertIn('14:00',loss)
        self.assertIn('34 хв',restore)
        self.assertIn('88%',restore)
