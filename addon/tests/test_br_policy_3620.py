"""Agreed schedule/fallback reserve formulas and shared preparation baseline."""
import unittest
from datetime import timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from tests import test_normal_base_369 as base_fixture
from tests.test_weather_buffer import NOW, daily, samples, weather, warning
import test_outage_preparation as fixture
from app.services.panic_decision import PanicDecisionEngine


def document(emergency=False, **changes):
    row=dict(schema=1,region='kyiv_region',source='pro_kyiv',source_status='fresh',
             validated=True,checked_at=NOW.isoformat(),dates=[NOW.date().isoformat()],
             emergency_notice_active=emergency)
    row['emergency_notice_confirmed_clear']=not emergency
    row.update(changes)
    return row


class ReservePolicy3620Tests(unittest.TestCase):
    def test_schedule_matrix_excludes_confidence_and_forecast(self):
        for minimum in (20,35,60,95):
            for emergency in (False,True):
                for bad_weather in (False,True):
                    with self.subTest(minimum=minimum,emergency=emergency,weather=bad_weather):
                        service=base_fixture.NormalBaseTests().service()
                        service.set_normal_base(minimum)
                        service.update(dict(daily(solar=1,mode='Automatic'),forecast_plan_stage='morning'),samples(10,10,10))
                        service.update_grid_confidence('panic',NOW)
                        service.update_weather(weather(*([warning()] if bad_weather else [])))
                        service.update_schedule(document(emergency))
                        attrs=service.status_attributes()
                        self.assertEqual(min(95,minimum+20+20*emergency+20*bad_weather),attrs['recommended_soc'])
                        self.assertEqual('dtek_schedule',attrs['reserve_planning_source'])
                        self.assertEqual(0,attrs['generation_modifier_percent'])
                        self.assertEqual(0,attrs['grid_modifier_percent'])

    def test_no_schedule_matrix_and_emergency_once(self):
        for level,offset in [('normal',0),('unstable',20),('risk',40),('panic',60)]:
            service=base_fixture.NormalBaseTests().service()
            service.update(dict(daily(solar=1,mode='Automatic'),forecast_plan_stage='morning'),samples(10,10,10))
            service.update_grid_confidence(level,NOW)
            for _ in range(3):
                service.update_schedule(document(True,validated=False,source_status='suspended',dates=[]))
            self.assertEqual(min(95,20+offset+20),service.status_attributes()['recommended_soc'])

    def test_usable_schedule_does_not_clear_persisted_emergency(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'reserve.json'
            service=base_fixture.NormalBaseTests().service(path)
            service.update_schedule(document(True))
            self.assertEqual(60,service.status_attributes()['recommended_soc'])
            restored=base_fixture.NormalBaseTests().service(path)
            restored.update_schedule(document(True))
            self.assertEqual(60,restored.status_attributes()['recommended_soc'])
            restored.update_schedule(document(False))
            self.assertEqual(40,restored.status_attributes()['recommended_soc'])

    def test_missing_notice_is_not_cancellation(self):
        service=base_fixture.NormalBaseTests().service()
        service.update_schedule(document(True))
        service.update_schedule(document(False,emergency_notice_confirmed_clear=False))
        self.assertEqual(60,service.status_attributes()['recommended_soc'])

    def test_missing_tomorrow_does_not_change_today_even_in_emergency(self):
        service=base_fixture.NormalBaseTests().service()
        service.update_schedule(document(True,day_errors={(NOW.date()+timedelta(days=1)).isoformat():'Unconfirmed'}))
        self.assertEqual(60,service.status_attributes()['recommended_soc'])

    def test_confirmed_empty_today_is_a_schedule_not_missing_data(self):
        service=base_fixture.NormalBaseTests().service()
        service.update_grid_confidence('panic',NOW)
        service.update_schedule(document(False,intervals=[]))
        self.assertEqual('dtek_schedule',service.status_attributes()['reserve_planning_source'])
        self.assertEqual(40,service.status_attributes()['recommended_soc'])

    def test_preparation_does_not_add_allowances_twice(self):
        f=fixture.OutageTests();f.setUp()
        f.document['groups']['1.1'][0]['end']=(fixture.NOW+timedelta(hours=3)).isoformat()
        f.plan.update(f.document)
        # Applied BR80 already contains minimum20 + schedule20 + weather20 + emergency20.
        result=f.evaluate(base_reserve=80,weather_modifier=20)
        self.assertEqual(100,result['uncapped_target_soc'])
        self.assertEqual(95,result['target_soc'])
        self.assertTrue(result['coverage_capacity_insufficient'])
        result=f.evaluate(base_reserve=60)
        self.assertEqual(80,result['target_soc'])

    def test_scaled_battery_and_ha_current_remain_authoritative(self):
        f=fixture.OutageTests();f.setUp()
        f.document.update(capacity_kwh=32,grid_charge_current_a=30)
        f.document['groups']['1.1'][0]['end']=(fixture.NOW+timedelta(hours=3)).isoformat()
        f.plan.update(f.document)
        result=f.evaluate(base_reserve=60,soc=40)
        self.assertEqual(70,result['target_soc'])
        self.assertEqual(30,result['grid_charge_current_a'])

    def test_pending_ha_reserve_cannot_release_hold_using_old_floor(self):
        engine=PanicDecisionEngine()
        args=dict(autopilot_enabled=True,operating_mode='panic_grid_hold',grid_confidence='unstable',
                  battery_soc=70,grid_available=True,manual_reserve_soc=40)
        result=engine.evaluate(**args,reserve_application_pending=True)
        self.assertIsNone(result['request'])
        self.assertEqual('awaiting_reserve_application',result['status'])
        self.assertEqual('solar',engine.evaluate(**args)['request'])
        manual=engine.evaluate(**args,reserve_application_pending=True,manual_panic_active=True)
        self.assertEqual(95,manual['target_soc'])
        self.assertNotEqual('awaiting_reserve_application',manual['status'])


if __name__=='__main__':
    unittest.main()
