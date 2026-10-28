"""Reporting evidence and notification-order regressions for the native migration."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo
from app import hp_daily_energy, forecast_quality, solar_outlook, night_charge, co_morning
from app.main import observe_peak_load_guard, observe_reserve_warnings, deliver_pending_notifications

NOW=datetime(2026,10,26,8,5,tzinfo=ZoneInfo('Europe/Kyiv'))


class ReleaseTests(unittest.TestCase):
    def test_planning_forecast_orders_repeated_dst_hour_by_instant(self):
        from app.outage_schedule import planning_document
        from datetime import timezone
        now=datetime(2026,10,24,11,45,tzinfo=ZoneInfo('Europe/Kyiv'))
        rows=[]
        start=now.replace(hour=0,minute=0).astimezone(timezone.utc)
        end=(now+timedelta(days=2)).replace(hour=0,minute=0).astimezone(timezone.utc)
        while start<end:
            rows.append(dict(period_start=start.astimezone(now.tzinfo).isoformat(),pv_estimate=2))
            start+=timedelta(hours=1)
        values={'today':dict(state='8.73',attributes=dict(detailedHourly=[r for r in rows if datetime.fromisoformat(r['period_start']).date()==now.date()])),
                'tomorrow':dict(state='11.5',attributes=dict(detailedHourly=[r for r in rows if datetime.fromisoformat(r['period_start']).date()!=now.date()]))}
        cfg=SimpleNamespace(solar_forecast_entity='today',dtek_solar_forecast_tomorrow_entity='tomorrow')
        with patch('app.planning_settings.read',return_value={}),patch('app.service_incidents.source_refresh',return_value=now.timestamp()):
            data=planning_document(cfg,SimpleNamespace(state=values.get),now,{})
        self.assertEqual(49,len(data['forecast']))
        starts=[datetime.fromisoformat(r['start']).timestamp() for r in data['forecast']]
        self.assertEqual(sorted(starts),starts)
        self.assertTrue(all(b-a==3600 for a,b in zip(starts,starts[1:])))

    def test_precharge_notice_explains_unavailable_solar_evidence(self):
        from app.outage_schedule import preparation_energy_details
        _,text=preparation_energy_details(dict(capacity_kwh=16,solar_forecast_complete=False,
            preparation_solar_reason='missing_current_pv'),73,95)
        self.assertIn('3.5 kWh',text)
        self.assertIn('поточної генерації',text)
        self.assertNotIn('0.0 kWh',text)

    def completed(self, **changes):
        data=dict(day=NOW.date().isoformat(),finished=True,finished_at=NOW.replace(hour=7,minute=0).isoformat(),
            end=NOW.replace(hour=7,minute=0).isoformat(),source='fresh',consumption_kwh=12.2,solar_kwh=8.6,
            deficit_kwh=3.6,reserve_soc=40,capacity_kwh=16,target_soc=62.5,start_soc=73,end_soc=87)
        data.update(changes)
        return SimpleNamespace(state=lambda _:dict(attributes=dict(completed=data)))

    def test_night_explains_deficit_and_separates_scheduled_charging(self):
        client=self.completed(operations={'scheduled':dict(start_soc=73,end_soc=90,
            outage_start=NOW.replace(hour=6,minute=0).isoformat())})
        text=night_charge.morning(client,NOW)
        for expected in ('12.2','8.6','3.6 kWh','06:00','73% → 90%','22.5%','62.5%'):self.assertIn(expected,text)
        self.assertNotIn('не знадобилося',text)

    def test_observed_night_charging_is_not_inferred_from_window_endpoints(self):
        text=night_charge.morning(self.completed(start_soc=50,operations={}),NOW)
        self.assertNotIn('50% →',text)
        text=night_charge.morning(self.completed(start_soc=50,operations={'night':dict(start_soc=50,end_soc=63)}),NOW)
        self.assertNotIn('50% → 63%',text)  # Latest compact normal case omits this narrative.

    def test_hot_water_reads_the_exact_chart_statistic_and_dst_day(self):
        cfg=SimpleNamespace(water_boiler_energy_entity='sensor.water_boiler_energy_calculated')
        def stats(start,end,entities):
            self.assertEqual(25*3600,(end-start).total_seconds())
            self.assertEqual(['sensor.water_boiler_energy_calculated'],entities)
            return {entities[0]:[dict(start=start.timestamp(),end=end.timestamp(),change=1.28)]}
        text=' '.join(hp_daily_energy.hot_water_lines(cfg,SimpleNamespace(daily_energy_statistics=stats),NOW))
        self.assertIn('Гаряча вода',text);self.assertIn('1.3 kWh',text)

    def test_missing_boiler_statistics_are_not_reported_as_zero(self):
        text=' '.join(hp_daily_energy.hot_water_lines(SimpleNamespace(),SimpleNamespace(daily_energy_statistics=lambda *_:{}),NOW))
        self.assertIn('недостатньо',text);self.assertNotIn('0 kWh',text)

    def test_compact_hp_breakdown_omits_below_point_two_but_keeps_missing(self):
        cfg=SimpleNamespace(**{f'heat_pump_floor_{i}_energy_entity':f'hp{i}' for i in (1,2,3)})
        def stats(start,end,entities):
            return {'hp1':[dict(start=start.timestamp(),end=end.timestamp(),change=0.19)],
                    'hp2':[dict(start=start.timestamp(),end=end.timestamp(),change=0.2)]}
        text=' '.join(hp_daily_energy.lines(cfg,SimpleNamespace(daily_energy_statistics=stats),NOW,compact=True))
        self.assertNotIn('1-й поверх',text);self.assertIn('2-й поверх',text);self.assertIn('3-й поверх — не підтверджено',text)

    def test_weekly_forecast_reports_daily_averages_and_coverage(self):
        days={'2026-10-24':dict(battery_full=False,forecast_kwh=5,actual_kwh=6),
              '2026-10-23':dict(battery_full=False,forecast_kwh=7,actual_kwh=8)}
        text=' '.join(forecast_quality.weekly(dict(forecast_quality_days=days),NOW,{}))
        for value in ('2 дн. без 100% SOC','прогноз 6.0','7.0 kWh/день','+16.7%'):self.assertIn(value,text)

    def test_forecast_colors_compare_same_mean_and_stale_source_is_unknown(self):
        values={'tomorrow':dict(state='12.5',attributes=dict(unit_of_measurement='kWh',dayname='Tuesday')),
                'later':dict(state='6.3',attributes=dict(unit_of_measurement='kWh',dayname='Wednesday')),
                'poll':dict(state=NOW.isoformat())}
        cfg=SimpleNamespace(dtek_solar_forecast_tomorrow_entity='tomorrow',solar_forecast_day3_entity='later',solcast_last_success_entity='poll')
        client=SimpleNamespace(state=values.get)
        text=solar_outlook.lines(cfg,client,NOW,today=9,average=12.2)[0]
        self.assertEqual(2,text.count('🔴'));self.assertEqual(1,text.count('🟢'))
        values['poll']['state']=(NOW-timedelta(days=2)).isoformat()
        text=solar_outlook.lines(cfg,client,NOW,today=9,average=12.2)[0]
        self.assertEqual(3,text.count('не підтверджено'));self.assertNotIn('🔴',text)

    def test_co_zero_always_keeps_ha_timestamp(self):
        values={'sensor.test_co':dict(state='0',last_updated=NOW.isoformat()),
                'binary_sensor.test_carbon_monoxide':dict(state='off',last_updated=NOW.isoformat())}
        cfg=SimpleNamespace(co_alarms=[SimpleNamespace(entity='binary_sensor.test_carbon_monoxide',label='Test')])
        text=' '.join(co_morning.lines(cfg,SimpleNamespace(state=values.get),NOW,compact=True))
        self.assertIn('показник у HA від',text);self.assertNotIn('в нормі',text)

    def test_hp1_events_survive_queue_cleanup_but_overload_notices_do_not(self):
        event=dict(event_id='new-hp1',type='load_shed',mode='automatic',reason='battery',
            affected_loads=[dict(key='heat_pump_floor_1')])
        client=SimpleNamespace(state=lambda _:dict(attributes=dict(events=[event])))
        cfg=SimpleNamespace(peak_load_guard_event_entity='guard');state={}
        observe_peak_load_guard(cfg,client,state,NOW)
        self.assertEqual(1,len(state['pending_notifications']))
        observe_reserve_warnings(cfg,client,state,NOW)
        self.assertEqual(1,len(state['pending_notifications']))
        state['pending_notifications'].append(dict(kind='peak_load_guard_load_shed',message='retired'))
        observe_reserve_warnings(cfg,client,state,NOW)
        self.assertEqual(1,len(state['pending_notifications']))

    def test_precharge_waits_for_grid_recovery_delivery(self):
        cfg=SimpleNamespace(timezone='Europe/Kyiv',destination_chat_id='family',technical_chat_id='tech',
            family_quiet_start='23:00',send_time='08:00')
        start=(NOW+timedelta(hours=2)).isoformat()
        status=dict(state='charging',attributes=dict(start=start))
        client=SimpleNamespace(state=lambda _:status)
        state=dict(grid_restored_at=NOW.isoformat(),pending_notifications=[
            dict(kind='dtek_preparation',message='PREP',start=start,created_at=NOW.isoformat()),
            dict(kind='grid_recovered',message='GRID',created_at=NOW.isoformat())])
        tg=Mock()
        with patch('app.grid_evidence.qualified',return_value=True),patch('app.main.outage_schedule.preparation_for_state',return_value='PREP'),patch('app.restoration_messages.house_text',return_value='GRID'),patch('app.hp_eco.acknowledge_grid'):
            deliver_pending_notifications(cfg,tg,state,NOW,client)
            self.assertEqual(['GRID'],[c.args[1] for c in tg.send_message.call_args_list])
            deliver_pending_notifications(cfg,tg,state,NOW,client)
            self.assertEqual(['GRID','PREP'],[c.args[1] for c in tg.send_message.call_args_list])
