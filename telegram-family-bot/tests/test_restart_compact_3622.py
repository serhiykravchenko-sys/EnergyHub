import unittest
from datetime import timedelta
from types import SimpleNamespace
import test_restart_summary as fixture
from app.restart_summary import summary


class CompactRestartTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.RestartTests();self.f.setUp()
        self.cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1')
        self.state={}
        from grid_fixture_3623 import rows
        self.f.entities.update(rows(self.f.now,online=False))
        self.f.entities['sensor.powmr_10_2m_battery_soc']['state']='84'
        self.f.entities['input_number.ahm_minimum_soc']['state']='60'
        self.f.entities['sensor.energyhub_operating_mode']['state']='panic_grid_hold'
        self.f.entities['sensor.powmr_10_2m_grid_voltage']={'state':'0'}
        self.attrs=dict(source_status='fresh',checked_at=self.f.now.isoformat(),
            start=(self.f.now-timedelta(hours=1)).isoformat(),end=(self.f.now+timedelta(hours=1)).isoformat(),
            target_soc=75,phase='waiting_for_grid',control_active=True,acknowledged=False)
        self.f.entities['sensor.energyhub_outage_preparation']={'attributes':self.attrs}

    def text(self):
        return summary(self.f.client,self.f.now,self.f.session,self.cfg,self.state)

    def test_offline_restart_contains_one_soc_one_reserve_one_target_and_no_release_promise(self):
        self.state['regional_notices']={'дача':dict(places=['дача'],kind='emergency',
            schedules_invalid=True,cancelled=False,checked_at=self.f.now.isoformat())}
        text=self.text()
        self.assertEqual(1,text.count('84%'))
        self.assertEqual(1,text.count('60%'))
        self.assertEqual(1,text.count('75%'))
        self.assertEqual(1,text.count('За графіком'))
        self.assertEqual(1,text.count('екстрені'))
        self.assertIn('ДТЕК зараз недоступний',text)
        self.assertNotIn('Відключимо ДТЕК',text)
        self.assertNotIn('ДТЕК підключено',text)

    def test_unconfirmed_old_boot_or_stale_plan_omits_target(self):
        for changes in [dict(checked_at=(self.f.now-timedelta(minutes=3)).isoformat()),
                        dict(checked_at=(self.f.now-timedelta(seconds=70)).isoformat()),
                        dict(source_status='unavailable'),dict(phase='guarded')]:
            original=dict(self.attrs);self.attrs.update(changes)
            self.assertNotIn('ціль підготовки',self.text())
            self.attrs.clear();self.attrs.update(original)

    def test_stale_soc_and_grid_never_claim_actual_supply(self):
        self.f.entities['sensor.energyhub_telemetry_freshness']['state']='stale'
        text=self.text()
        self.assertNotIn('84%',text)
        self.assertIn('невідомий',text)
        self.assertIn('Доступність ДТЕК уточнюється',text)
        self.assertNotIn('ДТЕК підключено',text)

    def test_online_confirmed_preparation_and_solar_modes_are_distinct(self):
        from grid_fixture_3623 import rows
        self.f.entities.update(rows(self.f.now))
        self.attrs['acknowledged']=True
        self.assertIn('ДТЕК підключено для підготовки',self.text())
        self.attrs['control_active']=False
        self.assertIn('для збереження заряду',self.text())
        self.f.entities['sensor.energyhub_operating_mode']['state']='solar'
        self.assertIn('будинок працює без його допомоги',self.text())

    def test_next_day_date_manual_panic_and_missing_reserve_are_explicit(self):
        self.attrs['start']=(self.f.now+timedelta(days=1)).isoformat()
        self.attrs['end']=(self.f.now+timedelta(days=1,hours=4)).isoformat()
        self.assertIn('09.09',self.text())
        self.f.entities['sensor.energyhub_panic_target_source']={'state':'Manual Panic: dashboard'}
        self.assertIn('павербанк',self.text())
        self.assertNotIn('ціль підготовки',self.text())
        self.f.entities['input_number.ahm_minimum_soc']['state']='unavailable'
        self.assertIn('резерв: <b>не підтверджено',self.text())

    def test_released_early_charge_rearms_later_notification_but_stale_wait_does_not(self):
        from app.outage_schedule import rearm_waiting_preparation
        start=(self.f.now+timedelta(hours=15)).isoformat()
        end=(self.f.now+timedelta(hours=19)).isoformat()
        key=start+'/'+end+'/charging'
        state=dict(dtek_preparation_announced=[key,'other-window'],
                   precharge_soc_session=dict(key=start,completed=False))
        data=dict(phase='waiting',control_active=False,source_status='fresh',
                  start=start,end=end,checked_at=(self.f.now-timedelta(minutes=3)).isoformat())
        self.assertFalse(rearm_waiting_preparation(state,data,self.f.now))
        data['checked_at']=self.f.now.isoformat()
        self.assertTrue(rearm_waiting_preparation(state,data,self.f.now))
        self.assertEqual(['other-window'],state['dtek_preparation_announced'])
        self.assertNotIn('precharge_soc_session',state)
        self.assertFalse(rearm_waiting_preparation(state,data,self.f.now))
