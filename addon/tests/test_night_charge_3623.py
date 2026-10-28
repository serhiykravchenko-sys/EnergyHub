import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo
from app.services.night_charge import NightCharge, choose_owner

NOW = datetime(2026, 10, 19, 23, 50, tzinfo=ZoneInfo('Europe/Kyiv'))


class NightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'night.json'
        self.plan = NightCharge(self.path)
        self.set_forecast(NOW)

    def set_forecast(self, now, solar=5):
        start = datetime.combine(self.plan.window(now)[1].date(), datetime.min.time(), now.tzinfo)
        self.plan.update(dict(planning_checked_at=now.isoformat(), forecast_at=now.isoformat(),
            forecast_max_age_hours=24, night_forecasts={start.date().isoformat():solar}, forecast=[dict(start=(start+timedelta(hours=h)).isoformat(),
                end=(start+timedelta(hours=h+1)).isoformat(), pv_kw=solar/24) for h in range(24)]))

    def evaluate(self, now=NOW, **changes):
        args=dict(now=now, soc=70, reserve=40, capacity=16,
            samples=[dict(date=(now.date()-timedelta(days=d)).isoformat(), kwh=13, complete=True) for d in (1,2,3)],
            grid_online=True, automatic=True, telemetry_valid=True, mode='solar', current_target=40)
        args.update(changes)
        return self.plan.evaluate(**args)

    def test_budget_and_cap_cases(self):
        for solar, target in ((15,40),(9,65),(5,90),(2,95)):
            self.plan = NightCharge(self.path.with_name(str(solar)+'.json'))
            self.set_forecast(NOW, solar)
            result=self.evaluate(soc=40)
            self.assertEqual(target,result['target_soc'])
            self.assertEqual('not_needed' if solar==15 else 'charging',result['phase'])

    def test_above_target_holds_without_extra_recharge_setpoint(self):
        result=self.evaluate(soc=91)
        self.assertEqual('holding',result['phase'])
        self.assertEqual(90,result['target_soc'])
        self.assertEqual('panic_grid_hold',result['request'])

    def test_reassessment_increases_target_and_does_not_double_count_night(self):
        self.evaluate()
        now=NOW+timedelta(hours=5,minutes=10)
        self.set_forecast(now,2)
        result=self.evaluate(now,soc=90)
        self.assertEqual(95,result['target_soc'])
        self.assertEqual('correction',result['stage'])
        self.assertEqual(0,self.plan.saved['missing_nights'])

    def test_lower_target_does_not_recharge_back_to_initial_soc(self):
        self.evaluate()
        now=NOW+timedelta(hours=5,minutes=10)
        self.set_forecast(now,9)
        result=self.evaluate(now,soc=90)
        self.assertEqual(65,result['target_soc'])
        self.assertEqual('holding',result['phase'])

    def test_failed_reassessment_keeps_existing_decision(self):
        self.evaluate()
        result=self.evaluate(NOW+timedelta(hours=5,minutes=10))
        self.assertEqual(90,result['target_soc'])
        self.assertEqual(0,self.plan.saved['missing_nights'])

    def test_exact_expiry_and_restart_outcome(self):
        self.evaluate()
        now=NOW+timedelta(hours=7,minutes=10)
        result=self.evaluate(now,soc=82)
        self.assertFalse(result['control_active'])
        self.assertEqual(82,result['completed']['end_soc'])
        self.assertEqual(90,result['completed']['target_soc'])
        self.plan=NightCharge(self.path)
        self.assertEqual(82,self.evaluate(now,soc=83)['completed']['end_soc'])

    def test_missing_first_two_then_third_skip(self):
        self.evaluate()
        for d in (1,2,3):
            now=NOW+timedelta(days=d)
            result=self.evaluate(now)
            self.assertEqual('fallback' if d<3 else 'unavailable',result['source'])
            self.assertEqual(d,self.plan.saved['missing_nights'])
            self.assertEqual('charging' if d<3 else 'skipped',result['phase'])
        self.set_forecast(now)
        result=self.evaluate(now+timedelta(hours=5,minutes=10))
        # Source timestamp remains within age but transport stale: still skip.
        self.assertEqual('skipped',result['phase'])

    def test_missing_history_not_zero_deficit(self):
        result=self.evaluate(samples=[])
        self.assertEqual('skipped',result['phase'])
        self.assertIsNone(result['target_soc'])

    def test_missing_target_date_or_invalid_daily_total_rejected(self):
        for value in (None, -1, float('nan'), True):
            self.plan=NightCharge(self.path.with_name(str(value)+'.json'))
            self.set_forecast(NOW)
            self.plan.document['night_forecasts']={'2026-10-20':value}
            self.assertEqual('skipped',self.evaluate()['phase'])

    def test_grid_offline_unknown_and_return(self):
        for grid in (False,None):
            result=self.evaluate(grid_online=grid)
            self.assertEqual('waiting_for_grid',result['phase'])
            self.assertIsNone(result['request'])
        self.assertEqual('panic',self.evaluate()['request'])

    def test_manual_stale_invalid_and_unsupported_mode_never_write(self):
        for changes in (dict(automatic=False),dict(telemetry_valid=False),dict(capacity=None),
                        dict(mode='transition_failed'),dict(soc=float('nan'))):
            self.assertIsNone(self.evaluate(**changes)['request'])

    def test_failed_persistence_does_not_acquire(self):
        with patch('app.services.night_charge.atomic_write_json',side_effect=OSError):
            result=self.evaluate()
        self.assertFalse(result['control_active'])
        self.assertIsNone(result['request'])

    def test_failed_target_update_retains_durable_owner(self):
        self.evaluate()
        with patch('app.services.night_charge.atomic_write_json',side_effect=OSError):
            result=self.evaluate(reserve=60,mode='panic',current_target=90)
        self.assertTrue(result['control_active'])
        self.assertEqual(90,result['target_soc'])
        self.assertIsNone(result['request'])
        self.assertEqual(self.plan.saved['current']['end'],result['end'])

    def test_acquired_owner_survives_grid_loss_but_manual_release_wins(self):
        self.evaluate()
        result=self.evaluate(grid_online=False,mode='panic',current_target=90)
        self.assertTrue(result['control_active'])
        self.assertIsNone(result['request'])
        result=self.evaluate(automatic=False,ownership_allowed=False,mode='panic',current_target=90)
        self.assertFalse(result['control_active'])

    def test_correction_to_zero_does_not_discharge_existing_charge(self):
        self.evaluate()
        now=NOW+timedelta(hours=5,minutes=10)
        self.set_forecast(now,20)
        result=self.evaluate(now,soc=90,mode='panic_grid_hold',current_target=90)
        self.assertTrue(result['control_active'])
        self.assertEqual('holding',result['phase'])
        self.assertEqual(40,result['target_soc'])

    def test_restart_no_double_missing_increment(self):
        self.evaluate()
        self.plan=NightCharge(self.path)
        self.assertEqual(90,self.evaluate()['target_soc'])
        self.assertEqual(0,self.plan.saved['missing_nights'])

    def test_due_schedule_wins_but_future_plan_does_not(self):
        night=self.evaluate()
        due=dict(control_active=True,target_soc=95)
        self.assertIs(due,choose_owner(due,night))
        due['control_active']=False
        self.assertIs(night,choose_owner(due,night))

    def test_earlier_deadline_keeps_schedule_owner_at_07(self):
        self.evaluate()
        due=dict(control_active=True,target_soc=95)
        expired=self.evaluate(NOW+timedelta(hours=7,minutes=10))
        self.assertIs(due,choose_owner(due,expired))

    def test_window_before_start_inactive(self):
        self.assertEqual('inactive',self.evaluate(NOW-timedelta(seconds=1))['phase'])

    def test_dynamic_reserve_and_capacity_are_used(self):
        self.assertEqual(65,self.evaluate(capacity=32,soc=40)['target_soc'])
        self.assertEqual(95,self.evaluate(reserve=60)['target_soc'])

    def test_zero_deficit_fallback_remains_no_charge(self):
        self.set_forecast(NOW,20)
        self.assertEqual('not_needed',self.evaluate()['phase'])
        self.assertEqual('not_needed',self.evaluate(NOW+timedelta(days=1))['phase'])

    def test_daily_total_does_not_require_an_hourly_demand_model(self):
        self.plan.document['forecast'] = []
        self.plan.document['night_forecasts'] = {'2026-10-20': 5}
        self.assertEqual(90,self.evaluate()['target_soc'])

    def test_incomplete_history_and_stale_forecast_skip(self):
        self.plan.document['forecast_at'] = (NOW-timedelta(hours=25)).isoformat()
        self.assertEqual('skipped',self.evaluate()['phase'])

    def test_malformed_saved_state_cannot_manufacture_ownership(self):
        self.path.write_text('{"schema":1,"current":[],"missing_nights":"broken"}')
        self.plan=NightCharge(self.path)
        self.assertEqual('skipped',self.evaluate()['phase'])

    def test_stale_daily_forecast_does_not_hide_current_weather_risk(self):
        from app.services.weather_buffer import WeatherBufferDryRun
        from test_weather_buffer import warning
        clock=[NOW]
        service=WeatherBufferDryRun(path=None,clock=lambda:clock[0])
        self.assertTrue(service.update(dict(date=NOW.date().isoformat(),observed_at=NOW.isoformat(),
                            mode='Automatic',applied_minimum_soc=20,solar_forecast_kwh=5),[]))
        clock[0]+=timedelta(days=1)
        at=clock[0]
        event=warning(until=at.replace(hour=23,minute=59).isoformat())
        event.update(published_at=at.isoformat(),valid_from=at.isoformat())
        service.update_weather(dict(observed_at=at.isoformat(),source_status='fresh',warnings=[event]))
        self.assertEqual(20,service.status_attributes()['weather_modifier_percent'])
