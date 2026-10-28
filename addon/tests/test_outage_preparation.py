import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from app.services.outage_preparation import OutagePreparation,grid_headroom

NOW=datetime(2026,10,6,21,tzinfo=ZoneInfo('Europe/Kyiv'))


class OutageTests(unittest.TestCase):
    def setUp(self):
        self.plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1'))
        self.document=dict(grid_charge_current_a=60,capacity_kwh=16,house_demand_kw=3.2,forecast_max_age_hours=24,load_off_soc=40,load_restore_soc=50,schema=1,source='bezsvitla',region='kyiv_region',validated=True,
            source_status='fresh',checked_at=NOW.isoformat(),published_at=NOW.isoformat(),
            groups={'1.1':[dict(start=(NOW+timedelta(hours=2)).isoformat(),end=(NOW+timedelta(hours=6)).isoformat())]})
        self.assertTrue(self.plan.update(self.document))
        self.args=dict(now=NOW,soc=50,voltage=52,charge_a=10,solar_w=1500,load_w=1000,
                       grid_online=True,mode='solar',automatic=True,base_reserve=40,telemetry_valid=True)

    def evaluate(self,**kwargs):
        return self.plan.evaluate(**dict(self.args,**kwargs))

    def test_four_hours_targets_ninety_five_and_starts_grid_early(self):
        r=self.evaluate()
        self.assertEqual(95,r['target_soc'])
        self.assertEqual('panic',r['request'])
        self.assertTrue(r['control_active'])

    def test_verified_source_names_share_existing_controller_guards(self):
        for source in ('dtek_official','alerts_energy','pro_kyiv','schedule_sources'):
            with self.subTest(source=source):
                self.document['source']=source
                self.assertTrue(self.plan.update(self.document))
                self.assertFalse(self.evaluate(telemetry_valid=False)['control_active'])
        self.document['source']='untrusted'
        self.assertFalse(self.plan.update(self.document))

    def test_suspended_source_is_visible_without_retaining_charging_authority(self):
        self.document.update(source_status='suspended',validated=False)
        self.assertFalse(self.plan.update(self.document))
        result=self.evaluate()
        self.assertEqual('suspended',result['source_status'])
        self.assertEqual(NOW.isoformat(),result['source_checked_at'])
        self.assertFalse(result['control_active'])
        self.assertIsNone(result['target_soc'])

    def test_informational_online_emergency_does_not_disable_valid_preparation(self):
        self.document.update(emergency_notice_active=True,emergency_grid_state='online')
        self.assertTrue(self.plan.update(self.document))
        result=self.evaluate()
        self.assertTrue(result['control_active'])
        self.assertTrue(result['emergency_notice_active'])
        self.assertEqual('online',result['emergency_grid_state'])

    def test_long_outage_caps_target_and_retains_uncapped_requirement(self):
        self.document['groups']['1.1'][0]['end']=(NOW+timedelta(hours=12)).isoformat()
        self.plan.update(self.document)
        r=self.evaluate()
        self.assertEqual(95,r['target_soc'])
        self.assertGreater(r['uncapped_target_soc'],95)

    def test_strong_actual_solar_needs_complete_fresh_forecast_to_wait(self):
        self.document.update(forecast_at=NOW.isoformat(),forecast=[dict(start=(NOW+timedelta(hours=i)).isoformat(),
            end=(NOW+timedelta(hours=i+1)).isoformat(),pv_kw=8) for i in range(2)])
        self.plan.update(self.document)
        r=self.evaluate(soc=65,solar_w=8000,load_w=1000,charge_a=120)
        self.assertEqual('solar',r['phase'])
        self.assertFalse(r['control_active'])
        self.document['forecast'].pop()
        self.plan.update(self.document)
        self.assertFalse(self.evaluate(soc=65,solar_w=8000,load_w=1000,charge_a=120)['solar_forecast_complete'])

    def test_forecast_optimism_cannot_override_actual_slow_charge(self):
        self.document.update(forecast_at=NOW.isoformat(),forecast=[dict(start=NOW.isoformat(),end=(NOW+timedelta(hours=2)).isoformat(),pv_kw=20)])
        self.plan.update(self.document)
        self.assertEqual('charging',self.evaluate()['phase'])

    def test_reached_target_is_held_without_plus_ten_release(self):
        self.assertEqual('panic',self.evaluate(soc=50)['request'])
        self.assertEqual('panic_grid_hold',self.evaluate(soc=99,mode='panic',current_target=95)['request'])
        r=self.evaluate(soc=100,mode='panic_grid_hold',current_target=95)
        self.assertTrue(r['control_active'])
        self.assertIsNone(r['request'])

    def test_matching_target_alone_cannot_reconstruct_preparation_ownership(self):
        self.args['now']=NOW-timedelta(hours=2)
        self.document['checked_at']=self.args['now'].isoformat()
        self.document['published_at']=self.args['now'].isoformat()
        self.plan.update(self.document)
        r=self.evaluate(mode='panic_grid_hold',current_target=95,soc=89)
        self.assertEqual('waiting',r['phase'])
        self.assertFalse(r['control_active'])

    def test_missing_schedule_uses_normal_controller(self):
        self.plan.update(dict(schema=1,source='bezsvitla',region='kyiv_region',source_status='unavailable'))
        self.assertFalse(self.evaluate()['control_active'])

    def test_source_staleness_and_future_timestamps(self):
        for offset in (-2101,61):
            self.document['checked_at']=(NOW+timedelta(seconds=offset)).isoformat()
            self.plan.update(self.document)
            self.assertFalse(self.evaluate()['control_active'])

    def test_control_requires_automatic_and_valid_physical_evidence(self):
        for override in (dict(automatic=False),dict(telemetry_valid=False),dict(soc=float('nan')),
                         dict(voltage=0),dict(charge_a=None),dict(mode='unknown'),dict(base_reserve=None)):
            self.assertFalse(self.evaluate(**override)['control_active'],override)

    def test_grid_absence_never_requests_charge(self):
        r=self.evaluate(grid_online=False)
        self.assertEqual('waiting_for_grid',r['phase'])
        self.assertIsNone(r['request'])

    def test_no_target_when_outage_has_started(self):
        r=self.evaluate(now=NOW+timedelta(hours=2))
        self.assertFalse(r['control_active'])

    def test_other_region_or_apartment_cannot_control_house(self):
        self.document['region']='kyiv_city'
        self.assertFalse(self.plan.update(self.document))
        self.document['region']='kyiv_region'
        self.document['groups']={'2.2':self.document['groups']['1.1']}
        self.assertFalse(self.plan.update(self.document))

    def test_invalid_overlap_replaces_old_evidence(self):
        self.document['groups']['1.1']*=2
        self.assertFalse(self.plan.update(self.document))
        self.assertIsNone(self.plan.snapshot)

    def test_base_reserve_not_added_twice(self):
        r=self.evaluate(base_reserve=40)
        self.assertEqual(95,r['target_soc'])

    def test_weather_adds_twenty_to_scheduled_target_with_cap(self):
        self.document['groups']['1.1'][0]['end']=(NOW+timedelta(hours=3)).isoformat()
        self.plan.update(self.document)
        self.assertEqual(60,self.evaluate()['target_soc'])
        self.assertEqual(80,self.evaluate(weather_modifier=20,base_reserve=60)['target_soc'])
        self.assertEqual(95,self.evaluate(weather_modifier=20,base_reserve=95)['target_soc'])
        self.assertFalse(self.evaluate(weather_modifier=40)['control_active'])

    def test_weather_uses_outage_date_not_publication_or_current_date(self):
        self.document['groups']['1.1'][0]=dict(start=(NOW+timedelta(hours=5)).isoformat(),end=(NOW+timedelta(hours=6)).isoformat())
        self.plan.update(self.document)
        self.assertEqual(60,self.evaluate(weather_days=['2026-10-06'])['target_soc'])
        self.assertEqual(80,self.evaluate(weather_days=['2026-10-07'])['target_soc'])

    def test_grid_headroom_respects_combined_limit(self):
        r=self.evaluate(solar_w=10000,load_w=0,charge_a=120)
        self.assertLessEqual(r['estimated_grid_current_headroom_a'],60)
        self.assertLessEqual(r['estimated_grid_current_headroom_a']+120,120)
        self.assertEqual(50,grid_headroom(70))

    def test_distant_outage_does_not_hold_full_battery_all_day(self):
        self.document['groups']['1.1'][0]=dict(start=(NOW+timedelta(hours=18)).isoformat(),end=(NOW+timedelta(hours=22)).isoformat())
        self.plan.update(self.document)
        self.assertFalse(self.evaluate(soc=100)['control_active'])

    def test_next_cut_is_planned_independently_of_later_cut(self):
        self.document['groups']['1.1'].append(dict(start=(NOW+timedelta(hours=7)).isoformat(),end=(NOW+timedelta(hours=11)).isoformat()))
        self.plan.update(self.document)
        r=self.evaluate()
        self.assertEqual(95,r['target_soc'])
        self.assertAlmostEqual(12.8,r['energy_kwh'])
        self.assertEqual((NOW+timedelta(hours=6)).isoformat(),r['end'])

    def test_long_grid_gap_keeps_sessions_separate(self):
        self.document['groups']['1.1'].append(dict(start=(NOW+timedelta(hours=12)).isoformat(),end=(NOW+timedelta(hours=16)).isoformat()))
        self.plan.update(self.document)
        self.assertEqual(95,self.evaluate()['target_soc'])

    def test_disabled_by_default(self):
        plan=OutagePreparation({})
        self.assertFalse(plan.evaluate(**self.args)['control_active'])

    def test_heating_selection_rates_and_stale_selection(self):
        self.document.update(heating_checked_at=NOW.isoformat(),heating_policy='Off')
        self.plan.update(self.document)
        self.assertEqual(95,self.evaluate()['target_soc'])  # One configured total demand
        self.document['heating_policy']='Smart'
        self.plan.update(self.document)
        self.assertEqual(95,self.evaluate()['target_soc'])
        self.document.update(heating_policy='Off',heating_checked_at=(NOW-timedelta(minutes=3)).isoformat())
        self.plan.update(self.document)
        self.assertEqual(20,self.evaluate()['soc_per_outage_hour'])

    def test_legacy_kw_option_does_not_change_new_formula(self):
        plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1',outage_demand_kw=0.1))
        plan.update(self.document)
        self.assertEqual(95,plan.evaluate(**self.args)['target_soc'])

    def test_forecast_solar_reduces_grid_time_without_night_pv(self):
        self.document['groups']['1.1'][0]=dict(start=(NOW+timedelta(hours=5)).isoformat(),end=(NOW+timedelta(hours=9)).isoformat())
        self.document.update(forecast_at=NOW.isoformat(),forecast=[dict(start=(NOW+timedelta(hours=i)).isoformat(),
            end=(NOW+timedelta(hours=i+1)).isoformat(),pv_kw=0 if i==0 else 5) for i in range(5)])
        self.plan.update(self.document)
        r=self.evaluate(solar_w=0,charge_a=0,load_w=1000)
        self.assertGreater(r['forecast_net_solar_kwh'],0)
        self.assertLess(r['required_grid_kwh'],7.2)
        self.assertFalse(r['control_active'])
        self.document.pop('forecast')
        self.plan.update(self.document)
        no_solar=self.evaluate(solar_w=0,charge_a=0)
        self.assertGreater(no_solar['estimated_grid_minutes'],r['estimated_grid_minutes'])

    def test_actual_underperformance_advances_grid_start(self):
        self.document.update(forecast_at=NOW.isoformat(),forecast=[dict(start=(NOW+timedelta(hours=i)).isoformat(),
            end=(NOW+timedelta(hours=i+1)).isoformat(),pv_kw=8) for i in range(2)])
        self.plan.update(self.document)
        strong=self.evaluate(solar_w=8000,charge_a=120)
        weak=self.evaluate(solar_w=1000,charge_a=0)
        self.assertLess(weak['planned_grid_start'],strong['planned_grid_start'])
        self.assertEqual('charging',weak['phase'])

    def test_grid_budget_uses_combined_headroom(self):
        self.document.update(forecast_at=NOW.isoformat(),forecast=[dict(start=(NOW+timedelta(hours=i)).isoformat(),
            end=(NOW+timedelta(hours=i+1)).isoformat(),pv_kw=12) for i in range(2)])
        self.plan.update(self.document)
        self.plan.planning_demand=3.2
        budget=self.plan._forecast_budget(self.document,NOW,NOW+timedelta(hours=1),52,3.2,12000,120)
        for _,_,solar_kw,grid_kw in budget:
            self.assertLessEqual(solar_kw+grid_kw,120*52/1000+1e-9)

if __name__=='__main__':unittest.main()
