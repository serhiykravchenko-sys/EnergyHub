import unittest
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from app import source_policy, outage_schedule, soc_interval, hp_daily_energy
from test_schedule_sources import NOW, CFG


class BrMessageTests(unittest.TestCase):
    def setUp(self):
        self.notice=dict(kind='emergency',cancelled=False,schedules_invalid=True,
            revision=NOW.isoformat(),checked_at=NOW.isoformat(),text='Запроваджені екстрені відключення в Обухівському та Фастівському районах.')
        self.start=NOW+timedelta(hours=4)
        self.end=self.start+timedelta(hours=4)
        self.interval=dict(start=self.start.isoformat(),end=self.end.isoformat())
        self.document=dict(schema=1,source='pro_kyiv',region='kyiv_region',validated=True,
            source_status='fresh',checked_at=NOW.isoformat(),published_at=NOW.isoformat(),
            dates=[NOW.date().isoformat()],groups={'1.1':[self.interval],'2.2':[self.interval]})
        self.state=dict(pro_policy_enabled=True,dtek_snapshot=self.document,dtek_raw_snapshot=self.document)
        source_policy.apply(self.state,self.notice,CFG,NOW,self.document)

    def test_emergency_retains_timetable_and_bonus_through_restart(self):
        state=deepcopy(self.state)
        snapshot=source_policy.authority(self.document,state,NOW)
        self.assertTrue(snapshot['validated'])
        self.assertEqual('fresh',snapshot['source_status'])
        self.assertTrue(snapshot['emergency_notice_active'])
        self.assertFalse(source_policy.schedule_blocked(state,'дача',snapshot))
        self.assertTrue(source_policy.suspended(state,'дача'))  # Regional risk persists.

    def test_invalid_document_is_never_promoted_by_emergency(self):
        for status in ('unavailable','stale','starting'):
            snapshot=source_policy.authority(dict(self.document,validated=False,source_status=status),self.state,NOW)
            self.assertFalse(snapshot['validated'])
            self.assertTrue(snapshot['emergency_notice_active'])

    def test_absent_notice_is_not_confirmed_emergency_cancellation(self):
        snapshot=source_policy.authority(self.document,{},NOW)
        self.assertFalse(snapshot['emergency_notice_confirmed_clear'])
        record=dict(self.notice,cancelled=True,schedules_invalid=False,places=['дача'])
        snapshot=source_policy.authority(self.document,dict(pro_notice=record),NOW)
        self.assertTrue(snapshot['emergency_notice_confirmed_clear'])

    def test_charging_contains_soc_time_emergency_and_energy(self):
        config=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_dacha_district='Obukhiv')
        data=dict(self.interval,checked_at=NOW.isoformat(),phase='charging',current_soc=60,target_soc=95,
            capacity_kwh=16,acknowledged=True,observed_charge_a=20,estimated_grid_minutes=210,
            solar_forecast_complete=True,forecast_net_solar_kwh=2,required_grid_kwh=3.6)
        from grid_fixture_3623 import qualify
        client=qualify(SimpleNamespace(state=lambda entity:dict(state='charging',attributes=data)), NOW)
        text=outage_schedule.preparation_for_state(config,client,self.state,NOW)
        self.assertIn('Потреба заряду батареї',text)
        self.assertIn('60% → 95%',text)
        self.assertIn('Обухівському',text)
        self.assertIn('екстрені',text)
        self.assertIn('≈2.0 kWh',text)
        self.assertIn('≈3.6 kWh',text)
        data['preparation_time_insufficient']=True
        # A safety-margin flag alone is not a missed-outage prediction.
        self.assertNotIn('часу може не вистачити',outage_schedule.preparation_for_state(config,client,self.state,NOW))
        data.update(estimated_grid_minutes=300, forecast_net_solar_kwh=0)
        self.assertIn('часу може не вистачити',outage_schedule.preparation_for_state(config,client,self.state,NOW))

    def test_release_requires_fresh_confirmed_mode_and_available_grid(self):
        config=SimpleNamespace(grid_voltage_entity='grid',telemetry_freshness_entity='fresh',operating_mode_entity='mode')
        data=dict(self.interval,phase='solar',coverage_release=True,solar_bridge_safe=True,
                  checked_at=NOW.isoformat(),current_soc=95,ordinary_reserve_soc=60)
        rows={outage_schedule.STATUS_ENTITY:dict(attributes=data),'grid':dict(state='230'),
              'fresh':dict(state='fresh'),'mode':dict(state='panic_grid_hold')}
        client=SimpleNamespace(state=lambda entity:rows.get(entity))
        self.assertEqual('',outage_schedule.coverage_release_text(config,client,self.state,NOW))
        rows['mode']['state']='solar'
        text=outage_schedule.coverage_release_text(config,client,self.state,NOW)
        self.assertIn('Сонця та заряду',text)
        self.assertIn('95%',text)
        self.assertIn('60%',text)
        rows['grid']['state']='0'
        self.assertEqual('',outage_schedule.coverage_release_text(config,client,self.state,NOW))
        rows['grid']['state']='230'
        self.assertEqual('',outage_schedule.coverage_release_text(config,client,self.state,NOW+timedelta(minutes=3)))

    def test_ready_notice_states_hold_near_target_and_rate_once(self):
        state={}
        mode={'state':'panic'}
        client=SimpleNamespace(state=lambda entity:mode)
        data=dict(self.interval,checked_at=NOW.isoformat(),current_soc=60,target_soc=95,
            phase='charging',acknowledged=True,observed_charge_a=30)
        self.assertIsNone(soc_interval.preparation_notice(state,client,NOW,data))
        at=NOW+timedelta(hours=2)
        # Supply intermediate samples so the net SOC jump is not a discontinuity.
        soc_interval.sample(state['precharge_soc_session'],at-timedelta(seconds=60),94)
        data.update(checked_at=at.isoformat(),current_soc=95,phase='holding',acknowledged_target_soc=95)
        mode['state']='panic_grid_hold'
        text=soc_interval.preparation_notice(state,client,at,data)
        self.assertIn('60% → 95%',text)
        self.assertIn('швидкість заряджання',text)
        self.assertIn('близько 95%',text)
        self.assertIsNone(soc_interval.preparation_notice(state,client,at,data))



if __name__=='__main__':
    unittest.main()
