import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from unittest.mock import patch

from app import battery_weekly, forecast_quality, night_charge, outage_schedule

NOW = datetime(2026, 10, 26, 8, tzinfo=ZoneInfo('Europe/Kyiv'))


class ReleaseTests(unittest.TestCase):
    def test_partial_battery_coverage_preserves_independent_counters(self):
        first = dict(at='2026-10-22T12:00:00+03:00', cycles=68, jumps=32)
        last = dict(at='2026-10-25T23:59:00+02:00', cycles=71, jumps=32)
        state = {'battery_weekly': {'days': {'2026-10-22': dict(first=first, last=last, seconds=90, reset=False)}}}
        text = '\n'.join(battery_weekly.lines(state, NOW))
        self.assertIn('68 → 71 (+3)', text)
        self.assertIn('за спостереженнями: <b>0', text)
        self.assertIn('1 із 7', text)
        last['jumps'] = None
        text = '\n'.join(battery_weekly.lines(state, NOW))
        self.assertIn('68 → 71 (+3)', text)
        self.assertIn('Стрибків заряду за спостереженнями: даних недостатньо', text)

    def test_counter_reset_does_not_hide_the_other_metric(self):
        first = dict(at='2026-10-22T12:00:00+03:00', cycles=68, jumps=32)
        last = dict(at='2026-10-25T23:59:00+02:00', cycles=71, jumps=1)
        state = {'battery_weekly': {'days': {'2026-10-22': dict(first=first,last=last,seconds=100,reset=True,jumps_reset=True)}}}
        text = '\n'.join(battery_weekly.lines(state, NOW))
        self.assertIn('скинуто', text)
        self.assertIn('68 → 71 (+3)', text)

    def test_forecast_surplus_includes_full_battery_days_and_excludes_equal(self):
        days = {'2026-10-23': dict(forecast_kwh=12,consumption_kwh=10,battery_full=True,actual_kwh=9),
                '2026-10-24': dict(forecast_kwh=10,consumption_kwh=10,battery_full=False,actual_kwh=11),
                '2026-10-25': dict(forecast_kwh=2,consumption_kwh=None,battery_full=False,actual_kwh=3)}
        text = '\n'.join(forecast_quality.weekly({'forecast_quality_days': days}, NOW, {}))
        self.assertIn('вище споживання: <b>1 із 2 днів', text)
        self.assertIn('Дані за 2 із 7 днів', text)
        self.assertIn('2 дн. без 100% SOC', text)

    def test_monthly_window_uses_previous_month(self):
        now = datetime(2026, 11, 1, 8, tzinfo=NOW.tzinfo)
        days = {'2026-09-30':dict(forecast_kwh=12,consumption_kwh=2),
                '2026-10-01':dict(forecast_kwh=12,consumption_kwh=2),
                '2026-10-31':dict(forecast_kwh=4,consumption_kwh=6)}
        text = '\n'.join(forecast_quality.weekly({'forecast_quality_days':days}, now, {}))
        self.assertIn('за місяць', text)
        self.assertIn('1 із 2 днів', text)
        self.assertIn('2 із 31 днів', text)

    def test_normal_night_uses_percent_and_cap_without_observed_charge_narrative(self):
        data = dict(day=NOW.date().isoformat(),finished=True,finished_at=NOW.replace(hour=7).isoformat(),
                    end=NOW.replace(hour=7).isoformat(),source='fresh',consumption_kwh=13.6,solar_kwh=6.2,
                    deficit_kwh=7.3,reserve_soc=60,capacity_kwh=16,target_soc=95,start_soc=47,end_soc=95,
                    hold_confirmed=True,operations={'night':dict(start_soc=47,end_soc=95)})
        text = night_charge.morning(SimpleNamespace(state=lambda _:dict(attributes={'completed':data})), NOW)
        self.assertIn('45.6%', text)
        self.assertIn('Максимум', text)
        self.assertNotIn('п.п.', text)
        self.assertNotIn('47% → 95%', text)
        self.assertNotIn('підтримувався', text)

    def reminder(self, supply, target=74):
        now=NOW.replace(hour=13)
        interval=dict(start=now.replace(hour=14).isoformat(),end=now.replace(hour=16).isoformat())
        cfg=SimpleNamespace(dtek_schedule_enabled=True,battery_soc_entity='soc',telemetry_freshness_entity='fresh',grid_voltage_entity='grid')
        plan=dict(**interval,checked_at=now.isoformat(),target_soc=target,estimated_grid_minutes=113,
                  phase='charging',acknowledged=True,observed_charge_a=20)
        values={'soc':dict(state='56'),'fresh':dict(state='fresh'),'grid':dict(state='0'),
                outage_schedule.STATUS_ENTITY:dict(state='charging',attributes=plan)}
        state={'dtek_snapshot':dict(source_status='fresh',validated=True,checked_at=now.isoformat(),groups={'1.1':[interval]})}
        item=dict(**interval,place='дача',group='1.1')
        with patch('app.grid_evidence.qualified',return_value=supply):
            return outage_schedule.reminder_text(cfg,SimpleNamespace(state=values.get),state,now,item)

    def test_offline_reminder_never_claims_charging_or_absolute_finish(self):
        text=self.reminder(False)
        self.assertIn('ДТЕК зараз недоступний', text)
        self.assertIn('після відновлення', text)
        self.assertIn('1 год 53 хв', text)
        self.assertNotIn('14:53', text)
        self.assertNotIn('може не вистачити', text)
        self.assertNotIn('дозаряджаємо', text)

    def test_unconfirmed_target_has_no_ready_claim_or_eta(self):
        text=self.reminder(False,None)
        self.assertIn('ціль дозаряджання уточнюється', text)
        self.assertNotIn('1 год 53 хв', text)

    def test_unknown_supply_does_not_become_confirmed_outage(self):
        text=self.reminder(None)
        self.assertIn('Живлення ДТЕК не підтверджено', text)
        self.assertNotIn('ДТЕК зараз недоступний', text)

    def test_hp_warning_explains_the_configured_floor(self):
        from app.events import peak_load_guard_message
        text=peak_load_guard_message(dict(type='hp1_battery_warning',battery_soc=49,battery_off_soc=40))
        self.assertIn('49%',text);self.assertIn('при 40%',text)
        self.assertNotIn('окрема політика',text)

    def test_forecast_history_backfill_uses_recorder_dates(self):
        midnight=NOW.replace(hour=0)
        day=midnight-timedelta(days=1)
        attributes=dict(date=day.date().isoformat(),forecast_kwh=12,actual_kwh=5,battery_full=False,
                        history=[dict(date=day.date().isoformat(),forecast_kwh=12,actual_kwh=5,battery_full=False)])
        def statistics(start,end,ids):
            self.assertIn('sensor.powmr_10_2m_daily_house_consumption',ids)
            return {ids[0]:[dict(start=day.timestamp(),end=midnight.timestamp(),change=10)]}
        client=SimpleNamespace(state=lambda _:dict(attributes=attributes),daily_energy_statistics=statistics)
        observation=forecast_quality.collect(client,NOW)
        self.assertEqual(10,observation['consumption_kwh'])
        text='\n'.join(forecast_quality.weekly({},NOW,observation))
        self.assertIn('1 із 1 днів',text)
