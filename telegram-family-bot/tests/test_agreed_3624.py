import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from app import hp_daily_energy, co_cache, co_morning, solar_outlook
from app.main import retire_zigbee_diagnostics
from app import outage_schedule
from app.main import deliver_pending_notifications
import test_outage_reminders as reminder_fixture

NOW=datetime(2026,10,20,8,tzinfo=ZoneInfo('Europe/Kyiv'))


class ReportTests(unittest.TestCase):
    def test_queued_window_hold_entry_is_silent(self):
        f=reminder_fixture.ReminderTests();f.setUp()
        now=reminder_fixture.NOW
        row=f.rows[outage_schedule.STATUS_ENTITY]
        row['state']='holding'
        row['attributes'].update(phase='holding',acknowledged=True,current_soc=95,target_soc=95,
            start=(now-timedelta(minutes=1)).isoformat(),end=(now+timedelta(hours=2)).isoformat(),window_active=True)
        self.assertEqual('',outage_schedule.preparation_line(f.client,now))
        state=dict(f.state, pending_notifications=[dict(kind='dtek_preparation',message='obsolete hold notice',
            created_at=now.isoformat(),start=row['attributes']['start'])])
        state['dtek_snapshot']['groups']['1.1']=[dict(start=row['attributes']['start'],end=row['attributes']['end'])]
        sent=[]
        telegram=SimpleNamespace(send_message=lambda *args:sent.append(args))
        deliver_pending_notifications(f.cfg,telegram,state,now,client=f.client)
        self.assertEqual([],sent)
        self.assertEqual([],state['pending_notifications'])






    def test_co_old_zero_retains_real_timestamp_and_unknown_state(self):
        at=NOW-timedelta(days=4)
        target=SimpleNamespace(entity='binary_sensor.basement_co_carbon_monoxide',label='Basement CO')
        cfg=SimpleNamespace(co_alarms=[target])
        rows={'sensor.basement_co_co':dict(state='0',last_updated=at.isoformat()),
              target.entity:dict(state='off',last_updated=at.isoformat())}
        state={};co_cache.observe(state,[target],rows,NOW)
        rows['sensor.basement_co_co']['state']='unavailable';rows[target.entity]['state']='unavailable'
        client=SimpleNamespace(state=lambda e:rows.get(e))
        text='\n'.join(co_morning.lines(cfg,client,NOW,state,compact=True))
        self.assertIn('0 ppm',text);self.assertIn('16.10',text)
        self.assertIn('поточний стан недоступний',text);self.assertNotIn('в нормі',text)

    def test_retired_diagnostics_are_removed_without_touching_other_sources(self):
        state=dict(plug_power_monitor={'pending':'obsolete'},plug_discovered=[1],
            data_incidents={'zigbee':{},'device:switch.hp':{},'inverter':{'active':True}},
            data_incident_history=[{'key':'zigbee'},{'key':'ha'}])
        retire_zigbee_diagnostics(state)
        self.assertNotIn('plug_power_monitor',state)
        self.assertEqual({'inverter':{'active':True}},state['data_incidents'])
        self.assertEqual([{'key':'ha'}],state['data_incident_history'])

    def test_outlook_dates_and_fresh_source(self):
        cfg=SimpleNamespace(dtek_solar_forecast_tomorrow_entity='tomorrow',solar_forecast_day3_entity='later')
        rows={'tomorrow':dict(state='9.9',attributes={'unit_of_measurement':'kWh','dayname':'Wednesday'}),
              'later':dict(state='15',attributes={'unit_of_measurement':'kWh','dayname':'Thursday'}),
              'sensor.solcast_pv_forecast_api_last_polled':dict(state=NOW.isoformat())}
        client=SimpleNamespace(state=lambda e:rows.get(e))
        text=solar_outlook.lines(cfg,client,NOW)[0]
        self.assertIn('9.9 kWh',text);self.assertIn('15 kWh',text)
        rows['later']['attributes']['dayname']='Wednesday'
        self.assertIn('післязавтра не підтверджено',solar_outlook.lines(cfg,client,NOW)[0])
        rows['sensor.solcast_pv_forecast_api_last_polled']['state']=(NOW-timedelta(days=2)).isoformat()
        self.assertNotIn('kWh',solar_outlook.lines(cfg,client,NOW)[0])
        from app.home_assistant import HomeAssistantError
        def failed(_):
            raise HomeAssistantError('Source unavailable')
        self.assertNotIn('kWh',solar_outlook.lines(cfg,SimpleNamespace(state=failed),NOW)[0])
