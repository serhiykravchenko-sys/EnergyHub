import json
import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock
from app import service_incidents as incidents, soc_interval
from app.report import morning_energy_lines, build_report

NOW=datetime(2026,10,15,10,tzinfo=timezone.utc)
CFG=SimpleNamespace(family_quiet_start='23:00',family_quiet_end='08:01')


class MessagesTests(unittest.TestCase):
    def error(self,now):
        return dict(timestamp=now.timestamp(),name='custom_components.solcast_solar.fetcher',message=['429 / Try again later'])

    def test_hour_failure_delay_daily_repeats_and_success_timestamp(self):
        state,tg={},Mock()
        incidents.observe(state,[self.error(NOW)],NOW,successful_refresh=(NOW-timedelta(hours=2)).timestamp())
        self.assertFalse(incidents.deliver(state,tg,'family',NOW+timedelta(minutes=59),CFG))
        self.assertTrue(incidents.deliver(state,tg,'family',NOW+timedelta(hours=1),CFG))
        text=tg.send_message.call_args.args[1]
        self.assertIn('15.10 о 08:00',text)
        self.assertIn('toolkit.solcast.com.au',text)
        self.assertNotIn('status.solcast',text)
        for days in (1,2):
            self.assertTrue(incidents.deliver(state,tg,'family',NOW+timedelta(days=days,hours=1),CFG))
        state=json.loads(json.dumps(state))
        self.assertFalse(incidents.deliver(state,tg,'family',NOW+timedelta(days=2,hours=1),CFG))

    def test_recovery_needs_hour_and_new_failure_restarts_qualification(self):
        state,tg={},Mock()
        incidents.observe(state,[self.error(NOW)],NOW)
        incidents.deliver(state,tg,'family',NOW+timedelta(hours=1),CFG)
        recovered=NOW+timedelta(hours=2)
        incidents.observe(state,[],recovered,successful_refresh=recovered.timestamp())
        self.assertFalse(incidents.deliver(state,tg,'family',recovered,CFG))
        failure=recovered+timedelta(minutes=30)
        incidents.observe(state,[self.error(failure)],failure,successful_refresh=recovered.timestamp())
        self.assertNotIn('recovery_at',state['service_incidents']['solcast'])
        success=failure+timedelta(minutes=1)
        incidents.observe(state,[],success,successful_refresh=success.timestamp())
        incidents.observe(state,[],success+timedelta(hours=1),successful_refresh=success.timestamp())
        self.assertTrue(incidents.deliver(state,tg,'family',success+timedelta(hours=1),CFG))
        self.assertIn('знову оновлюється',tg.send_message.call_args.args[1])

    def test_quiet_and_unnotified_recovery_no_false_warning(self):
        state,tg={},Mock(); now=NOW.replace(hour=23)
        incidents.observe(state,[self.error(now)],now)
        self.assertFalse(incidents.deliver(state,tg,'family',now+timedelta(hours=1),CFG))
        success=now+timedelta(hours=2)
        incidents.observe(state,[],success,successful_refresh=success.timestamp())
        incidents.observe(state,[],success+timedelta(hours=1),successful_refresh=success.timestamp())
        self.assertFalse(incidents.deliver(state,tg,'family',NOW+timedelta(days=1),CFG))
        tg.send_message.assert_not_called()

    def test_signed_net_soc_rate_and_jump_or_gap_suppression(self):
        for delta in (-12,12):
            record=soc_interval.begin(NOW,80)
            for minute in range(1,135):
                soc_interval.sample(record,NOW+timedelta(minutes=minute),80+delta*minute/134)
            text=soc_interval.net_line(record,NOW+timedelta(minutes=134),80+delta)
            self.assertIn('5.4',text)
            self.assertIn('+' if delta>0 else '−',text)
        soc_interval.sample(record,NOW+timedelta(minutes=140),92)
        self.assertIn('за крайніми',soc_interval.net_line(record,NOW+timedelta(minutes=140),92))
        record=soc_interval.begin(NOW,72)
        soc_interval.sample(record,NOW+timedelta(minutes=1),88)
        self.assertFalse(record['valid'])

    def test_completion_requires_actual_charging_and_confirmed_hold_once(self):
        state={};mode='panic'
        client=SimpleNamespace(state=lambda _:dict(state=mode))
        data=dict(start=(NOW+timedelta(hours=2)).isoformat(),end=(NOW+timedelta(hours=4)).isoformat(),
                  checked_at=NOW.isoformat(),current_soc=72,target_soc=80,phase='charging',acknowledged=True,observed_charge_a=30)
        self.assertIsNone(soc_interval.preparation_notice(state,client,NOW,data))
        for minute in range(1,38):
            now=NOW+timedelta(minutes=minute)
            data.update(checked_at=now.isoformat(),current_soc=72+8*minute/37)
            soc_interval.preparation_notice(state,client,now,data)
        mode='panic_grid_hold';data.update(phase='holding',acknowledged_target_soc=80)
        text=soc_interval.preparation_notice(state,client,now,data)
        self.assertIn('37 хв',text);self.assertIn('≈13 %/год',text)
        self.assertIsNone(soc_interval.preparation_notice(json.loads(json.dumps(state)),client,now,data))
        self.assertIsNone(soc_interval.preparation_notice({},client,now,data))

    def test_zero_support_and_unknown_current_never_fall_back(self):
        args=dict(forecast=30,consumption_average=13.4,soc=58,reserve_soc=40,battery_capacity_kwh=16,
                  battery_voltage_v=50,battery_charge_current_a=None,battery_efficiency=.9,house_reference_current_a=16)
        text='\n'.join(morning_energy_lines(**args))
        self.assertIn('допомога ДТЕК сьогодні не потрібна',text)
        self.assertNotIn('0 год',text);self.assertNotIn('середнє',text)
        text='\n'.join(morning_energy_lines(**dict(args,forecast=6)))
        self.assertNotIn('А (~',text)

    def test_morning_energy_and_comparison_precede_schedule_without_duplicate_average(self):
        text=build_report(weather_lines=[],solar_forecast=7.5,solar_window=None,
                          threshold_w=300,consumption=11.3,snapshot={},night_import=None,
                          consumption_average=13.3,consumption_sample_count=3,
                          energy_outlook_lines=['GRID SUPPORT'],solar_heating_lines=['OUTAGE SCHEDULE'],
                          forecast_accuracy=dict(battery_full=False,actual_kwh=7,forecast_kwh=6.5,error_percent=8))
        self.assertEqual(1,text.count('середнє за'))
        self.assertLess(text.index('Споживання:'),text.index('GRID SUPPORT'))
        self.assertLess(text.index('GRID SUPPORT'),text.index('OUTAGE SCHEDULE'))
        self.assertLess(text.index('Учора батарея'),text.index('OUTAGE SCHEDULE'))
