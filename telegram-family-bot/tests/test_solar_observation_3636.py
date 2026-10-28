from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from app import solar_observation as solar, morning_digest
from app.restoration_messages import house_text


class SolarTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,28,10,tzinfo=timezone.utc)
        self.config=SimpleNamespace(telemetry_freshness_entity='sensor.fresh',
            ahm_minimum_soc_entity='sensor.reserve',weather_buffer_entity='sensor.buffer')

    def rows(self, value=800):
        return [dict(last_updated=(self.now-timedelta(seconds=300-i*30)).isoformat(),state=value)
                for i in range(11)]

    def test_weighted_average_constant_zero_and_varying(self):
        self.assertEqual(800,solar.average(self.rows(),self.now))
        self.assertEqual(0,solar.average(self.rows(0),self.now))
        rows=self.rows(); rows[5]['state']=1800
        self.assertEqual(900,solar.average(rows,self.now))

    def test_reject_partial_gaps_unknown_nan_and_future(self):
        for mutation in [lambda r:r[1:],lambda r:r[:3]+r[7:],
                         lambda r:r[:4]+[dict(r[4],state='unavailable')]+r[5:],
                         lambda r:r[:4]+[dict(r[4],state='nan')]+r[5:],
                         lambda r:r+[dict(last_updated=(self.now+timedelta(seconds=1)).isoformat(),state=800)]]:
            self.assertIsNone(solar.average(mutation(self.rows()),self.now))

    def test_tick_samples_unchanged_power_without_new_entity_and_restart_gap(self):
        state={}; at=self.now-timedelta(minutes=5)
        client=SimpleNamespace(state=lambda entity:dict(
            state='800' if entity==solar.ENTITY else 'fresh',last_updated=at.isoformat()))
        for i in range(11):
            at=self.now-timedelta(seconds=300-i*30)
            solar.observe(client,self.config,state,at)
        self.assertIn('0.8 kW',solar.line(state,self.now))
        solar.observe(client,self.config,state,self.now+timedelta(minutes=10))
        self.assertIn('не підтверджені',solar.line(state,self.now+timedelta(minutes=10)))

    def test_invalid_telemetry_clears_history(self):
        state={'solar_event_samples':self.rows()}
        client=SimpleNamespace(state=lambda _:dict(state='unavailable'))
        solar.observe(client,self.config,state,self.now)
        self.assertEqual([],state['solar_event_samples'])

    def test_unchanged_zero_uses_report_time_not_value_change_time(self):
        state={};at=self.now
        client=SimpleNamespace(state=lambda entity:dict(state='0' if entity==solar.ENTITY else 'fresh',
            last_updated=(self.now-timedelta(days=1)).isoformat(),last_reported=at.isoformat()))
        for i in range(11):
            at=self.now-timedelta(seconds=300-i*30)
            solar.observe(client,self.config,state,at)
        self.assertIn('<b>0 kW</b>',solar.line(state,self.now))

    def test_optional_pv_read_failure_never_blocks_grid_observation(self):
        from app.home_assistant import HomeAssistantError
        state={'solar_event_samples':self.rows()}
        def failed(_): raise HomeAssistantError('unavailable')
        solar.observe(SimpleNamespace(state=failed),self.config,state,self.now)
        self.assertEqual([],state['solar_event_samples'])

    def test_recovery_reformat_keeps_event_solar_not_delivery_reading(self):
        item={'restoration_event':dict(at=self.now.isoformat(),soc=87,
              solar_line='☀️ Генерація: <b>0.8 kW</b> · середнє за 5 хв.')}
        text=house_text(self.config,SimpleNamespace(state=lambda _:{}),{},self.now+timedelta(hours=8),item)
        self.assertIn('0.8 kW',text)


class MorningApartmentTests(unittest.TestCase):
    def test_same_style_no_hub_and_honest_unknown_onset(self):
        now=datetime.fromisoformat('2026-10-28T08:00:00+02:00')
        cfg=SimpleNamespace(timezone='Europe/Kyiv',send_time='08:00',family_quiet_start='23:00')
        state={'apartment_grid':{'events':[
            {'at':'2026-10-28T06:12:00+02:00','online':False},
            {'at':'2026-10-28T07:12:00+02:00','online':True},
            {'at':'2026-10-28T07:50:00+02:00','online':False,'onset_unknown':True}]}}
        text=morning_digest.overnight(cfg,state,now,current_strategy=[],soc=88,solar_w=0,
            grid_voltage=0,telemetry_fresh=True,inverter_mode='solar')
        self.assertIn('⚡ <b>Квартира: ДТЕК недоступний з 06:12</b>',text)
        self.assertIn('🟢 <b>Квартира: ДТЕК відновився о 07:12</b>',text)
        self.assertIn('початок невідомий',text)
        self.assertNotIn('Hub',text)
