import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from app import night_charge, solar_outlook, outage_schedule, source_policy, battery_weekly
from app import system_log_monitor, technical_summary, reserve_policy_text

NOW = datetime(2026,10,22,17,35,31,tzinfo=ZoneInfo('Europe/Kyiv'))


class RefinementTests(unittest.TestCase):
    def test_future_xiaomi_deprecation_is_maintenance_but_functional_error_stays_actionable(self):
        state={}
        row=dict(level='WARNING',count=4,name='homeassistant.const',timestamp=NOW.timestamp(),
            message=['The deprecated constant CONCENTRATION_PARTS_PER_MILLION was used from xiaomi_miot.'])
        system_log_monitor.observe(state,[row],NOW)
        self.assertFalse(state['system_log_monitor']['pending'])
        self.assertIn('Xiaomi Miot',technical_summary.build(state,NOW))
        row.update(level='ERROR')
        system_log_monitor.observe(state,[row],NOW)
        self.assertTrue(state['system_log_monitor']['pending'])
        system_log_monitor.observe(state,[],NOW)
        self.assertTrue(state['system_log_monitor']['pending'])

    def test_morning_supply_explains_only_acknowledged_preparation(self):
        from grid_fixture_3623 import qualify
        cfg=SimpleNamespace(telemetry_freshness_entity='fresh',grid_voltage_entity='grid',operating_mode_entity='mode')
        data=dict(checked_at=NOW.isoformat(),start=(NOW+timedelta(hours=3)).isoformat(),
            phase='charging',acknowledged=True,observed_charge_a=20,current_soc=79,target_soc=95)
        values={'fresh':dict(state='fresh'),'grid':dict(state='230'),'mode':dict(state='panic'),
                outage_schedule.STATUS_ENTITY:dict(state='charging',attributes=data)}
        client=qualify(SimpleNamespace(state=values.get),NOW)
        text=reserve_policy_text.supply_line(cfg,client,NOW)
        self.assertIn('79% → 95%',text)
        self.assertIn('перед відключенням',text)
        data['acknowledged']=False
        self.assertNotIn('79% → 95%',reserve_policy_text.supply_line(cfg,client,NOW))

    def test_internal_margin_shortfall_does_not_warn_about_outage_deadline(self):
        data=dict(start=NOW.replace(hour=21,minute=0,second=0).isoformat(),estimated_grid_minutes=175,
                  preparation_time_insufficient=True,forecast_net_solar_kwh=0)
        text=outage_schedule.preparation_timing(data,NOW)
        self.assertIn('20:30',text)
        self.assertNotIn('не вистачити',text)
        data['estimated_grid_minutes']=220
        self.assertIn('не вистачити',outage_schedule.preparation_timing(data,NOW))

    def test_grid_only_duration_does_not_predict_completion_before_solar_arrives(self):
        data=dict(start=NOW.replace(hour=21).isoformat(),estimated_grid_minutes=30,
                  forecast_net_solar_kwh=2,charge_deadline=NOW.replace(hour=20,minute=30,second=0).isoformat())
        self.assertIn('20:30',outage_schedule.preparation_timing(data,NOW))

    def test_night_history_preserved_and_new_forecast_requires_timestamp(self):
        now=NOW.replace(hour=8,minute=0,second=0)
        completed=dict(day=now.date().isoformat(),finished=True,source='fresh',
            end=now.replace(hour=7).isoformat(),finished_at=now.replace(hour=7,second=5).isoformat(),
            start_soc=67,end_soc=69,target_soc=50,reserve_soc=40,capacity_kwh=16,
            consumption_kwh=10.4,solar_kwh=8.9,deficit_kwh=1.5,hold_confirmed=True,
            forecast_at=(now-timedelta(hours=9)).isoformat())
        states={'sensor.energyhub_night_charge':dict(attributes=dict(completed=completed)),
                'poll':dict(state=now.replace(hour=5).isoformat())}
        client=SimpleNamespace(state=states.get);cfg=SimpleNamespace(solcast_last_success_entity='poll')
        text=night_charge.morning(client,now)
        self.assertIn('прогноз',text);self.assertIn('8.9',text)
        self.assertIn('Ціль: резерв',text);self.assertNotIn('Заряд підтримувався',text)
        self.assertEqual('Оновлений прогноз на сьогодні',solar_outlook.today_label(cfg,client,now,8.2))
        completed.pop('forecast_at')
        self.assertEqual('Прогноз на сьогодні',solar_outlook.today_label(cfg,client,now,8.2))

    def test_district_description_preserves_partial_scope_and_removes_boilerplate(self):
        text=('У частині Бучанського і Фастівського районів зникло світло через локальну аварію в мережі. '
              'Фахівці вже працюють над відновленням електропостачання.')
        cfg=SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv')
        notice=dict(kind='fault',text=text,cancelled=False)
        description=source_policy.concise_description(notice,cfg,'квартира')
        self.assertIn('без світла частина',description)
        self.assertIn('Фастівського',description)
        self.assertNotIn('Фахівці',description)
        self.assertEqual('',source_policy.concise_description(notice,cfg,'дача'))

    def test_notice_signature_upgrade_does_not_reannounce_unchanged_fault(self):
        import hashlib
        cfg=SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv',
            dtek_dacha_group='1.1',dtek_apartment_group='2.2')
        notice=source_policy.parse('У Фастівському районі зникло світло через локальну аварію в мережі.',NOW.isoformat(),NOW)
        state={};source_policy.apply(state,notice,cfg,NOW)
        record=state['pro_notice'];record.pop('signature_schema')
        record['signature']=hashlib.sha256(str([('квартира','fault',False,True)]).encode()).hexdigest()
        state['pending_notifications']=[]
        self.assertFalse(source_policy.apply(state,notice,cfg,NOW))
        self.assertFalse(state['pending_notifications'])

    def test_weekly_incomplete_is_not_zero_and_balancing_count_is_not_invented(self):
        monday=NOW.replace(day=26,hour=8)
        text='\n'.join(battery_weekly.lines({},monday))
        self.assertIn('недостатньо',text)
        self.assertNotIn('Стрибків заряду за спостереженнями: <b>0',text)
        self.assertNotIn('баланс',text)

    def test_weekly_cycle_and_jump_deltas_require_complete_coverage(self):
        now=datetime(2026,10,19,8,tzinfo=NOW.tzinfo)
        left=now.replace(hour=0)-timedelta(days=7)
        days={}
        for i in range(8):
            a=left+timedelta(days=i);b=a+timedelta(days=1,seconds=-30)
            first=dict(at=a.isoformat(),cycles=65+(3 if i==7 else 0),jumps=10)
            days[a.date().isoformat()]=dict(first=first,last=dict(first,at=b.isoformat()),seconds=86370,reset=False)
        state=dict(battery_weekly=dict(days=days))
        text='\n'.join(battery_weekly.lines(state,now))
        self.assertIn('65 → 68 (+3)',text);self.assertIn('Стрибків заряду за спостереженнями: <b>0',text)
        days[left.date().isoformat()]['reset']=True
        self.assertIn('скинуто','\n'.join(battery_weekly.lines(state,now)))

    def test_weekly_observation_does_not_turn_stale_bms_into_coverage(self):
        from app.house_monitor import DeviceTarget
        cfg=SimpleNamespace(bms_entities=tuple(DeviceTarget(k,k) for k in ['soc','current','voltage','cycles']),soc_anomaly_latest_entity='jumps')
        sample={k:dict(state=v,last_updated=NOW.isoformat()) for k,v in
                [('soc','70'),('current','-10'),('voltage','53'),('cycles','68')]}
        sample['jumps']=dict(attributes=dict(event_count=5))
        state={};battery_weekly.observe(state,cfg,sample,NOW)
        battery_weekly.observe(state,cfg,sample,NOW+timedelta(minutes=10))
        entry=state['battery_weekly']['days'][NOW.date().isoformat()]
        self.assertEqual(0,entry['seconds'])
