import unittest
from datetime import timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
import test_outage_preparation as fixture
from app.services.outage_preparation import OutagePreparation
from app.services.battery_discharge_window import BatteryDischargeWindow
from app.services.panic_decision import PanicDecisionEngine


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.OutageTests();self.f.setUp()
        self.f.document['groups']['1.1']=[dict(start=(fixture.NOW+timedelta(hours=15)).isoformat(),
                                              end=(fixture.NOW+timedelta(hours=19)).isoformat())]
        self.f.document['grid_charge_current_a']=30
        self.f.plan.update(self.f.document)
        self.f.args.update(soc=60,base_reserve=60,solar_w=0,charge_a=0,voltage=53)

    def trend(self):
        for second in range(-3600,1,30):
            self.f.plan.discharge_window.observe(fixture.NOW+timedelta(seconds=second),
                voltage=50,discharge_a=20,charge_a=0,valid=True,mode='solar')

    def legacy(self):
        row=self.f.document['groups']['1.1'][0]
        self.f.plan.active_context=dict(schema=1,**row,target_soc=95)

    def test_reserve_boundary_waits_for_morning_and_ordinary_control_holds(self):
        self.trend()
        result=self.f.evaluate()
        self.assertFalse(result['control_active'])
        self.assertEqual('waiting',result['phase'])
        self.assertGreater(result['planned_grid_start'],(fixture.NOW+timedelta(hours=9)).isoformat())
        self.assertEqual(0,result['predicted_waiting_discharge_kwh'])
        decision=PanicDecisionEngine().evaluate(autopilot_enabled=True,operating_mode='solar',
            grid_confidence='unstable',battery_soc=60,grid_available=True,manual_reserve_soc=60)
        self.assertEqual('panic_grid_hold',decision['request'])
        self.assertEqual(60,decision['target_soc'])

    def test_above_reserve_and_below_reserve_never_credit_overnight_depletion_below_floor(self):
        self.trend()
        for soc,loss in [(61,.16),(65,.8),(59,0)]:
            result=self.f.evaluate(soc=soc)
            self.assertFalse(result['control_active'])
            self.assertAlmostEqual(loss,result['predicted_waiting_discharge_kwh'])

    def test_legacy_early_owner_returns_to_ordinary_reserve_and_stays_released_after_restart(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'intent.json';self.f.plan.path=path
            self.legacy()
            result=self.f.evaluate(mode='panic',soc=63,current_target=95)
            self.assertTrue(result['legacy_ownership_released'])
            self.assertFalse(result['control_active'])
            decision=PanicDecisionEngine().evaluate(autopilot_enabled=True,operating_mode='panic',
                grid_confidence='unstable',battery_soc=63,grid_available=True,manual_reserve_soc=60)
            self.assertEqual('panic_grid_hold',decision['request'])
            self.assertEqual(60,decision['target_soc'])
            self.f.plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1'),path)
            self.f.plan.update(self.f.document)
            again=self.f.evaluate(mode='panic_grid_hold',soc=63,current_target=60)
            self.assertFalse(again['control_active'])
            self.assertNotIn('legacy_ownership_released',again)

    def test_legacy_offline_stale_manual_or_persistence_failure_cannot_hand_back(self):
        for changes in [dict(grid_online=False),dict(grid_online=None),dict(telemetry_valid=False)]:
            self.legacy()
            result=self.f.evaluate(mode='panic',**changes)
            self.assertTrue(result['control_active'])
            self.assertIsNone(result['request'])
        self.legacy()
        self.assertFalse(self.f.evaluate(mode='panic',automatic=False,ownership_allowed=False)['control_active'])
        self.legacy()
        with patch.object(self.f.plan,'_remember',return_value=False):
            result=self.f.evaluate(mode='panic')
        self.assertEqual('guarded',result['phase'])
        self.assertTrue(result['control_active'])
        self.assertIsNone(result['request'])

    def test_actual_deadline_acquires_durable_ownership_and_retains_it(self):
        with TemporaryDirectory() as directory:
            self.f.plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1'),Path(directory)/'intent.json')
            self.f.plan.update(self.f.document)
            # Refresh source authority before evaluating a later time.
            self.f.document['checked_at']=(fixture.NOW+timedelta(hours=12)).isoformat()
            self.f.plan.update(self.f.document)
            first=self.f.evaluate(now=fixture.NOW+timedelta(hours=12))
            self.assertTrue(first['control_active'])
            self.assertTrue(self.f.plan.active_context['charging_started_at'])
            self.f.plan=OutagePreparation(dict(outage_preparation_enabled=True,outage_group='1.1'),Path(directory)/'intent.json')
            self.f.plan.update(self.f.document)
            again=self.f.evaluate(now=fixture.NOW+timedelta(hours=12,minutes=1),mode='panic',soc=90,current_target=95)
            self.assertTrue(again['control_active'])
            self.assertNotIn('legacy_ownership_released',again)
            with patch.object(self.f.plan,'_remember',wraps=self.f.plan._remember) as remember:
                self.f.evaluate(now=fixture.NOW+timedelta(hours=12,minutes=2),mode='panic',soc=90,current_target=95,grid_online=False)
                self.f.evaluate(now=fixture.NOW+timedelta(hours=12,minutes=2),mode='panic',soc=90,current_target=95,grid_online=False)
            remember.assert_not_called()

    def test_window_reset_after_grid_support_keeps_waiting_until_genuine_deadline(self):
        self.trend();self.f.evaluate()
        self.f.plan.discharge_window=BatteryDischargeWindow()
        result=self.f.evaluate(mode='panic_grid_hold',current_target=60)
        self.assertFalse(result['control_active'])
        self.assertIsNone(result['observed_net_discharge_kw'])

    def test_legacy_current_window_retains_ownership(self):
        self.legacy()
        later=fixture.NOW+timedelta(hours=16)
        self.f.document['checked_at']=later.isoformat()
        self.f.plan.update(self.f.document)
        result=self.f.evaluate(now=later,mode='panic',soc=50)
        self.assertTrue(result['control_active'])
        self.assertNotIn('legacy_ownership_released',result)

    def test_solar_coverage_does_not_authorize_future_charge_after_reserve_support(self):
        self.f.document.update(heating_policy='Off',heating_checked_at=fixture.NOW.isoformat(),
            forecast_at=fixture.NOW.isoformat(),forecast=[dict(start=(fixture.NOW+timedelta(hours=i)).isoformat(),
            end=(fixture.NOW+timedelta(hours=i+1)).isoformat(),pv_kw=12) for i in range(20)])
        self.f.plan.update(self.f.document)
        safe=self.f.evaluate(soc=84,solar_w=12000)
        self.assertTrue(safe['solar_bridge_safe'])
        self.assertTrue(self.f.plan.active_context['ownership_released'])
        self.f.document['forecast']=[]
        self.f.plan.update(self.f.document)
        result=self.f.evaluate(mode='panic_grid_hold',current_target=60)
        self.assertFalse(result['control_active'])
