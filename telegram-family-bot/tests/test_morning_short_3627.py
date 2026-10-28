import unittest
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from app import morning_energy, night_charge, forecast_quality, co_morning
from app.main import observe_reserve_warnings, observe_peak_load_guard

NOW = datetime(2026, 10, 23, 8, tzinfo=timezone.utc)


class ShortMorningTests(unittest.TestCase):
    def test_energy_is_one_section_and_latest_forecast_keeps_night_provenance(self):
        rows = morning_energy.lines(consumption=15.8, average=12.1, sample_count=3, forecast=3.9, forecast_label='LATEST', hp_lines=['HP'], night_summary='NIGHT', completed=dict(solar_kwh=4.5), day='2026-10-23')
        text = '\n'.join(rows)
        for value in ('15.8','12.1','HP'): self.assertIn(value,text)
        for value in ('3.9','4.5','NIGHT','LATEST'): self.assertNotIn(value,text)

    def test_missing_forecast_or_usage_is_not_zero(self):
        text = '\n'.join(morning_energy.lines(consumption=None, average=None, sample_count=0, forecast=None, forecast_label='', hp_lines=[], night_summary=''))
        self.assertIn('Споживання не підтверджено',text)
        self.assertNotIn('0 kWh',text)

    def test_night_soc_change_is_not_labelled_measured_grid_energy(self):
        data = dict(day=NOW.date().isoformat(), finished=True, source='fresh', end=NOW.replace(hour=7).isoformat(), finished_at=NOW.replace(hour=7, second=1).isoformat(), start_soc=82, end_soc=94, target_soc=91, reserve_soc=40, consumption_kwh=12.1, solar_kwh=3.9, deficit_kwh=8.2)
        client = SimpleNamespace(state=lambda _: dict(attributes=dict(completed=data)))
        text = night_charge.morning(client,NOW)
        self.assertIn('дефіцит',text)
        self.assertIn('Ціль:',text)
        self.assertNotIn('82% → 94%',text)

    def test_retired_queue_drops_without_reissuing_policy_warning(self):
        state = dict(reserve_warning_offsets=[10], pending_notifications=[
            dict(kind='reserve_10', message='old'), dict(kind='dtek_reminder', message='keep')])
        state['peak_load_attention_pending'] = {
            'old-battery':dict(reasons=['battery_load_unavailable']),
            'overload':dict(reasons=['command_outcome_unconfirmed'])}
        client = SimpleNamespace(state=lambda _: None)
        self.assertTrue(observe_reserve_warnings(None, client, state, NOW))
        self.assertEqual(['dtek_reminder'], [x['kind'] for x in state['pending_notifications']])
        self.assertNotIn('reserve_warning_offsets', state)
        self.assertEqual(set(),set(state['peak_load_attention_pending']))
        self.assertFalse(observe_reserve_warnings(None, client, state, NOW))

    def test_weekly_forecast_uses_only_eligible_days_and_discloses_coverage(self):
        state = {}
        for i in range(4):
            now = NOW+timedelta(days=i)
            row = dict(date=(now.date()-timedelta(days=1)).isoformat(),
                       battery_full=(i==0), forecast_kwh=5, actual_kwh=6)
            result = forecast_quality.weekly(state, now, row)
            if now.weekday() != 0:
                self.assertEqual([], result)
        self.assertIn('3 дн. без 100% SOC', result[0])
        self.assertIn('+20.0%', result[0])

    def test_stale_or_unavailable_co_does_not_collapse_into_normal_line(self):
        rows = {'binary_sensor.test_carbon_monoxide':dict(state='off', last_updated=NOW.isoformat()),
                'sensor.test_co':dict(state='0', last_updated=(NOW-timedelta(hours=25)).isoformat())}
        cfg = SimpleNamespace(co_alarms=[SimpleNamespace(entity='binary_sensor.test_carbon_monoxide',label='Test')])
        text = '\n'.join(co_morning.lines(cfg, SimpleNamespace(state=rows.get), NOW, compact=True))
        self.assertIn('застарілий', text)
        self.assertIn('показник у HA від', text)
