import copy
import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo
from app import service_incidents as incidents, apartment_grid
from app.report import morning_energy_lines
from app import outage_schedule, schedule_sources

NOW = datetime(2026, 10, 12, 10, 46, tzinfo=ZoneInfo('Europe/Kyiv'))
CFG = SimpleNamespace(send_time='08:00', family_quiet_start='23:00', family_quiet_end='08:01')


class UpdateTests(unittest.TestCase):
    def row(self, text, at=NOW, name='custom_components.solcast_solar.fetcher', count=1):
        return dict(timestamp=at.timestamp(), message=[text], name=name, count=count)

    def test_incident_group_persistence_failed_delivery_followup_and_new_day(self):
        state, tg = {}, Mock()
        rows=[self.row('Call status 429/Try again later, API used is 2/10'),
              self.row('API was tried 10 times, but all attempts failed',NOW+timedelta(seconds=1))]
        now=NOW+timedelta(hours=1,seconds=2)
        incidents.observe(state, rows, now)
        tg.send_message.side_effect=OSError('offline')
        with self.assertRaises(OSError): incidents.deliver(state,tg,'family',now,CFG)
        self.assertFalse(state['service_incidents']['solcast']['notified'])
        tg.send_message.side_effect=None
        self.assertTrue(incidents.deliver(state,tg,'family',now,CFG))
        state=json.loads(json.dumps(state))
        incidents.observe(state,[self.row('Call status 429/Try again later, API used is 3/10')],now)
        self.assertFalse(incidents.deliver(state,tg,'family',now,CFG))
        later=now+timedelta(days=1)
        self.assertTrue(incidents.deliver(state,tg,'family',later,CFG))
        self.assertFalse(incidents.deliver(state,tg,'family',later,CFG))
        incidents.observe(state,[],later,successful_refresh=later.timestamp())
        self.assertFalse(incidents.deliver(state,tg,'family',later,CFG))
        later+=timedelta(hours=1)
        incidents.observe(state,[],later,successful_refresh=(later-timedelta(hours=1)).timestamp())
        self.assertTrue(incidents.deliver(state,tg,'family',later,CFG))
        incidents.observe(state,[self.row('Call status 429/Try again later',later+timedelta(minutes=1))],later+timedelta(minutes=1))
        self.assertFalse(incidents.deliver(state,tg,'family',later+timedelta(minutes=1),CFG))
        self.assertTrue(incidents.deliver(state,tg,'family',later+timedelta(minutes=61),CFG))

    def test_quiet_recovered_before_delivery_is_silent(self):
        state,tg={},Mock();night=NOW.replace(hour=23)
        incidents.observe(state,[self.row('Call status 429/Try again later',night)],night)
        self.assertFalse(incidents.deliver(state,tg,'family',night,CFG))
        morning=night+timedelta(hours=10)
        incidents.observe(state,[],morning,successful_refresh=morning.timestamp())
        self.assertFalse(incidents.deliver(state,tg,'family',morning,CFG))
        tg.send_message.assert_not_called()

    def test_no_recovery_from_republished_forecast_or_missing_logs(self):
        state={};incidents.observe(state,[self.row('Call status 429/Try again later')],NOW)
        entities={'sensor.forecast':{'state':'6.2','last_updated':NOW.isoformat()}}
        self.assertIsNone(incidents.source_refresh(entities,CFG,NOW))
        incidents.observe(state,[],NOW+timedelta(hours=1))
        self.assertTrue(state['service_incidents']['solcast']['active'])

    def test_ingress_pair_one_cause_persistent_notice_without_guessing_app(self):
        state,tg={},Mock()
        rows=[self.row('Failed to call /ingress/validate_session',name='homeassistant.components.hassio'),
              self.row('Client error /ingress/validate_session 401 unexpected mimetype',name='homeassistant.components.hassio.handler')]
        incidents.observe(state,rows,NOW)
        self.assertFalse(incidents.deliver(state,tg,'family',NOW,CFG))
        later=NOW+timedelta(minutes=5)
        incidents.observe(state,[self.row('/ingress/validate_session 401',later,name='homeassistant.components.hassio')],later)
        self.assertTrue(incidents.deliver(state,tg,'family',later,CFG))
        self.assertIn('не Solcast',tg.send_message.call_args.args[1])
        self.assertEqual('unknown',state['service_incidents']['ingress']['addon'])

    def test_shortfall_uses_battery_current_not_house_current(self):
        kwargs=dict(forecast=6.2,consumption_average=13.5,soc=42,reserve_soc=40,
            battery_capacity_kwh=16,battery_voltage_v=50,battery_charge_current_a=60,
            battery_efficiency=.9,house_reference_current_a=16)
        text='\n'.join(morning_energy_lines(**kwargs))
        self.assertIn('7.3 kWh',text);self.assertIn('2.5 год',text)
        self.assertIn('60 А (~3 kW)',text);self.assertNotIn('втрат',text)
        self.assertEqual(text,'\n'.join(morning_energy_lines(**dict(kwargs,house_reference_current_a=1))))

    def test_apartment_rolling_boundary_ongoing_and_missing_onset(self):
        events=[dict(at=(NOW-timedelta(days=2)).isoformat(),online=True),
                dict(at=(NOW-timedelta(hours=26)).isoformat(),online=False),
                dict(at=(NOW-timedelta(hours=22)).isoformat(),online=True),
                dict(at=(NOW-timedelta(hours=2)).isoformat(),online=False)]
        state={'apartment_grid':{'events':events}}
        text='\n'.join(apartment_grid.daily_lines(state,NOW))
        self.assertIn('20 год',text);self.assertIn('4 год',text);self.assertIn('Xiaomi Hub',text)
        events[-1]['onset_unknown']=True
        self.assertIn('не підтверджено','\n'.join(apartment_grid.daily_lines(state,NOW)))

    def test_active_schedule_remaining_future_full_ended_hidden(self):
        rows=[dict(start=NOW.replace(hour=9,minute=0).isoformat(),end=NOW.replace(hour=12,minute=30).isoformat()),
              dict(start=NOW.replace(hour=19,minute=30).isoformat(),end=NOW.replace(hour=23,minute=0).isoformat())]
        snapshot=dict(dates=[NOW.date().isoformat()],groups={'2.2':rows},source_url='https://example.org')
        text=outage_schedule.message(snapshot,[('2.2','квартира')],NOW,remaining=True)
        self.assertIn('до планового відновлення <b>1 год 44 хв</b>',text)
        self.assertIn('3 год 30 хв',text)
        self.assertNotIn('09:00',outage_schedule.message(snapshot,[('2.2','квартира')],NOW.replace(hour=13),remaining=True))


    def test_official_slots_derive_quarters_from_half_hour_metadata(self):
        mapping={str(i+1):['slot',f'{i//2:02d}:{30*(i%2):02d}',f'{(i+1)//2:02d}:{30*((i+1)%2):02d}'] for i in range(48)}
        self.assertEqual(('1',0,30),schedule_sources.official_slots(mapping)[0])
        mapping['2'][1]='00:00'
        with self.assertRaises(ValueError):schedule_sources.official_slots(mapping)
