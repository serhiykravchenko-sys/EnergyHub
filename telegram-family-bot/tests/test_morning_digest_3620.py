"""Report boundaries, factual summaries and persisted two-message delivery."""
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch, mock_open
from zoneinfo import ZoneInfo
from app import morning_digest, co_morning
from app.main import prepare_morning_report_outbox, archive_overnight_family_event
from app.main import create_reports
from app.config import load_config
from pathlib import Path
from app.report import build_report, morning_energy_lines

NOW = datetime(2026, 10, 17, 8, tzinfo=ZoneInfo('Europe/Kyiv'))
CONFIG = SimpleNamespace(timezone='Europe/Kyiv', send_time='08:00', family_quiet_start='23:00',
                         destination_chat_id='family', technical_chat_id='private',
                         dtek_schedule_enabled=True, dtek_dacha_group='1.1', dtek_apartment_group='2.2')


def digest(state=None, now=NOW, **kwargs):
    values = dict(current_strategy=['♨️ Smart'], soc=84, solar_w=0, grid_voltage=0,
                  telemetry_fresh=True, inverter_mode='solar')
    values.update(kwargs)
    return morning_digest.overnight(CONFIG, state or {}, now, **values)


class MorningDigestTests(unittest.TestCase):
    def test_night_window_filters_old_and_late_events(self):
        events = [dict(kind='grid_lost', created_at=at, message=label) for at, label in [
            ('2026-10-16T22:59:00+03:00', 'OLD'), ('2026-10-16T23:00:00+03:00', 'START'),
            ('2026-10-17T08:00:00+03:00', 'END'), ('2026-10-17T08:01:00+03:00', 'LATE')]]
        text = digest({'overnight_family_events': events}, now=NOW+timedelta(hours=1))
        self.assertIn('23:00–08:00', text)
        self.assertIn('START', text)
        self.assertIn('END', text)
        self.assertNotIn('OLD', text)
        self.assertNotIn('LATE', text)
        self.assertIn('Стан на 09:00', text)

    def test_apartment_is_in_night_summary_without_daily_statistics(self):
        text = digest({'apartment_grid': {'events': [dict(at='2026-10-17T00:59:00+03:00', online=True)]}})
        self.assertIn('Квартира', text)
        self.assertIn('00:59', text)
        self.assertNotIn('Xiaomi Hub', text)
        self.assertIn('🟢 <b>Квартира: ДТЕК відновився о 00:59</b>', text)
        self.assertNotIn('24 год', text)

    def test_flapping_is_condensed(self):
        events = [dict(kind='grid_lost' if i%2 else 'grid_recovered',
                       created_at=(NOW-timedelta(hours=2, minutes=i)).isoformat(), message='RAW FLAP')
                  for i in range(6)]
        text = digest({'overnight_family_events': events})
        self.assertIn('6 змін за ніч', text)
        self.assertNotIn('RAW FLAP', text)

    def test_unknown_telemetry_does_not_show_old_soc_as_current(self):
        text = digest(telemetry_fresh=False)
        self.assertNotIn('84%', text)
        self.assertNotIn('0 kW', text)
        self.assertIn('не підтверджені', text)
        self.assertNotIn('змін не зафіксовано', text)

    def test_charge_readiness_and_shedding_are_retained(self):
        state = {}
        for kind, label in [('dtek_preparation', 'CHARGING'), ('dtek_precharge_complete', 'READY'),
                            ('peak_load_guard_load_shed', 'LOAD OFF')]:
            archive_overnight_family_event(state, dict(kind=kind, message=label,
                created_at='2026-10-17T04:00:00+03:00'))
        text = digest(state)
        self.assertIn('LOAD OFF', text)
        self.assertNotIn('CHARGING', text)
        self.assertNotIn('READY', text)

    def test_outbox_orders_two_family_messages_and_survives_restart(self):
        state = {}
        with patch('app.main.create_reports', return_value=('TECH', ['NIGHT', 'DAY'])) as compose:
            self.assertTrue(prepare_morning_report_outbox(CONFIG, None, state, NOW))
            self.assertEqual(['TECH','NIGHT','DAY'], state['morning_report_outbox']['messages'])
            self.assertEqual(['private','family','family'], state['morning_report_outbox']['destinations'])
            state['morning_report_outbox']['next_message_index'] = 2
            restarted = deepcopy(state)
            self.assertFalse(prepare_morning_report_outbox(CONFIG, None, restarted, NOW+timedelta(minutes=5)))
            self.assertEqual(['DAY'], restarted['morning_report_outbox']['messages'][restarted['morning_report_outbox']['next_message_index']:])
            compose.assert_called_once()

    def test_upgrade_preserves_old_inflight_outbox(self):
        old = dict(date='2026-10-17', message='OLD REPORT', messages=['OLD REPORT'], next_message_index=0)
        state = dict(morning_report_outbox=deepcopy(old))
        with patch('app.main.create_reports') as compose:
            self.assertFalse(prepare_morning_report_outbox(CONFIG, None, state, NOW))
            compose.assert_not_called()
        self.assertEqual(old, state['morning_report_outbox'])

    def test_daily_compact_omits_averages_reliability_and_repeated_status(self):
        text = build_report(weather_lines=[], solar_forecast=5.5, solar_window='09:00–16:00',
            threshold_w=300, consumption=12.6, snapshot={}, night_import=None, compact=True,
            consumption_average=13.1, consumption_sample_count=3, grid_status_lines=['GRID STATS'],
            solar_heating_lines=['EMERGENCY', 'SCHEDULE'], co2_lines=['CO2'], report_date=NOW.date())
        self.assertNotIn('середнє', text)
        self.assertNotIn('GRID STATS', text)
        self.assertLess(text.index('Споживання'), text.index('SCHEDULE'))
        self.assertIn('17.10', text)

    def test_estimated_grid_need_uses_minutes_and_current_setting(self):
        text = '\n'.join(morning_energy_lines(forecast=5.5, consumption_average=13.2,
            soc=84, reserve_soc=40, battery_capacity_kwh=16, battery_voltage_v=50,
            battery_charge_current_a=30, battery_efficiency=.9, house_reference_current_a=30, compact=True))
        self.assertIn('Орієнтовна потреба', text)
        self.assertIn('5 год 30 хв', text)
        self.assertIn('30 А', text)

    def test_emergency_is_repeated_even_without_new_notification(self):
        notice = dict(kind='emergency', cancelled=False, places=['дача','квартира'], checked_at=NOW.isoformat())
        state = dict(pro_notice=notice, regional_notices={'дача': notice, 'квартира': notice})
        text = '\n'.join(morning_digest.schedule(CONFIG,state,NOW))
        self.assertIn('Дача', text)
        self.assertIn('Квартира', text)
        self.assertIn('екстрені', text)
        self.assertIn('поза графіком', text)
        self.assertIn('ще не підтверджено', text)

    def test_co_keeps_dated_zero_and_only_low_battery(self):
        config = SimpleNamespace(co_alarms=[SimpleNamespace(entity='binary_sensor.test_carbon_monoxide',label='<First>')])
        rows = {'binary_sensor.test_carbon_monoxide': {'state':'off', 'last_updated':NOW.isoformat()},
                'sensor.test_co': {'state':'0', 'last_updated':(NOW-timedelta(hours=11)).isoformat()},
                'sensor.test_battery': {'state':'100', 'last_updated':NOW.isoformat()}}
        client = SimpleNamespace(state=lambda key: rows.get(key))
        text = '\n'.join(co_morning.lines(config,client,NOW,compact=True))
        self.assertIn('<b>0 ppm</b>', text)
        self.assertIn('показник у HA від', text)
        self.assertNotIn('в нормі', text)
        self.assertNotIn('100%', text)
        rows['sensor.test_battery']['state']='15'
        self.assertIn('15%', '\n'.join(co_morning.lines(config,client,NOW,compact=True)))

    def test_composed_report_is_two_distinct_family_messages(self):
        with patch.object(Path, 'open', mock_open(read_data='{"dtek_schedule_enabled": true}')):
            config = load_config(Path('unused.json'))
        values = {config.battery_soc_entity: '84', config.telemetry_freshness_entity: 'fresh',
                  config.grid_voltage_entity: '0', config.operating_mode_entity: 'solar',
                  config.yesterday_consumption_entity: '12.6',
                  'sensor.energyhub_solar_power_15m_average': '0',
                  'input_select.energyhub_climate_policy': 'Smart'}
        def row(key):
            if key == config.weather_buffer_entity:
                return dict(state='60', attributes=dict(date=NOW.date().isoformat(),
                    consumption_average_kwh=13.1,consumption_sample_count=3))
            if key == config.solar_forecast_entity:
                return dict(state='5.5', attributes={})
            return dict(state=values[key], attributes={}) if key in values else None
        client = SimpleNamespace(state=row, error_log=lambda: '')
        notice = dict(kind='emergency', cancelled=False, places=['дача','квартира'], checked_at=NOW.isoformat())
        state = dict(pro_notice=notice,regional_notices={'дача':notice,'квартира':notice},
            overnight_family_events=[dict(kind='grid_lost',created_at='2026-10-17T06:08:00+03:00',
                                         message='ДТЕК зник о 06:08')])
        with patch('app.main.fetch_weather',return_value=['🌧 Дощ, +11…+15 °C']), \
             patch('app.main.technical_summary.archive'):
            _, messages = create_reports(config,client,state,NOW)
        self.assertEqual(2,len(messages))
        night, day = messages
        self.assertIn('06:08',night)
        self.assertIn('84%',night)
        self.assertNotIn('Дощ',night)
        self.assertIn('Дощ',day)
        self.assertIn('екстрені',day)
        self.assertNotIn('12.6',night)
        self.assertNotIn('13.1',night)
        self.assertIn('12.6',day)
        self.assertIn('13.1',day)
        self.assertNotIn('06:08',day)
        self.assertIn('середнє за',day)
        self.assertEqual(1,day.count('Споживання та генерація'))
        self.assertNotIn('корисна генерація',day)
        self.assertNotIn('ДТЕК за 24',day)
        self.assertTrue(all(len(text) < 4096 for text in messages))

    def test_stale_emergency_remains_labelled_as_last_confirmed(self):
        notice = dict(kind='emergency',cancelled=False,places=['дача'],checked_at=(NOW-timedelta(hours=1)).isoformat())
        text = '\n'.join(morning_digest.schedule(CONFIG,dict(pro_notice=notice),NOW))
        self.assertIn('Останній підтверджений статус',text)

    def test_co_expired_reading_is_not_silently_zero(self):
        config = SimpleNamespace(co_alarms=[SimpleNamespace(entity='binary_sensor.test_carbon_monoxide',label='CO')])
        at = (NOW-timedelta(hours=25)).isoformat()
        client = SimpleNamespace(state=lambda key: dict(state='0',last_updated=at))
        text = '\n'.join(co_morning.lines(config,client,NOW,compact=True))
        self.assertIn('показник у HA від',text)
        self.assertIn('0 ppm',text)

    def test_day_schedule_omits_finished_windows(self):
        state = dict(dtek_raw_snapshot=dict(validated=True,source_status='fresh',source='pro_kyiv',
            checked_at=NOW.isoformat(),dates=['2026-10-17'],groups={
                '1.1':[dict(start='2026-10-17T00:00:00+03:00',end='2026-10-17T01:00:00+03:00'),
                       dict(start='2026-10-17T15:00:00+03:00',end='2026-10-17T19:00:00+03:00')],
                '2.2':[]}))
        text='\n'.join(morning_digest.schedule(CONFIG,state,NOW))
        self.assertNotIn('00:00–01:00',text)
        self.assertIn('15:00–19:00',text)
        self.assertIn('Джерело — Pro Kyiv',text)

    def test_custom_local_window_and_utc_event_are_respected(self):
        config = SimpleNamespace(timezone='Europe/Kyiv',send_time='07:30',family_quiet_start='22:00')
        start,end=morning_digest.night_window(config,NOW)
        self.assertEqual((22,7,30),(start.hour,end.hour,end.minute))
        state=dict(overnight_family_events=[dict(kind='grid_lost',created_at='2026-10-16T20:00:00+00:00',message='UTC EVENT')])
        text = morning_digest.overnight(config,state,NOW,current_strategy=[],soc=None,solar_w=None,
            grid_voltage=None,telemetry_fresh=False,inverter_mode='solar')
        self.assertIn('UTC EVENT',text)
        self.assertIn('22:00–07:30',text)

    def test_cached_co_alarm_is_dated_not_silenced(self):
        config=SimpleNamespace(co_alarms=[SimpleNamespace(entity='binary_sensor.test_carbon_monoxide',label='Test')])
        client=SimpleNamespace(state=lambda key: None)
        state=dict(co_last_valid={'binary_sensor.test_carbon_monoxide':dict(state='on',at=(NOW-timedelta(hours=2)).isoformat()),
                                  'sensor.test_co':dict(state=25,at=(NOW-timedelta(hours=2)).isoformat())})
        text='\n'.join(co_morning.lines(config,client,NOW,state,compact=True))
        self.assertIn('25 ppm',text)
        self.assertIn('остання передана тривога',text)
        self.assertIn('17.10 06:00',text)


if __name__ == '__main__':
    unittest.main()
