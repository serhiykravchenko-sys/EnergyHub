import unittest
import tempfile
from pathlib import Path
from datetime import timedelta
import test_outage_preparation as fixture
from app.services.house_demand import HouseDemand
from app.services.outage_preparation import OutagePreparation


class ObservedBridgeTests(unittest.TestCase):
    setUp = fixture.OutageTests.setUp
    evaluate = fixture.OutageTests.evaluate

    def seed(self, watts=500):
        t=fixture.NOW.timestamp()
        self.document.update(hp_running=True,hp_state='heat',hp_state_since=(fixture.NOW-timedelta(hours=4)).isoformat(),heating_policy='Smart',heating_checked_at=fixture.NOW.isoformat(),house_demand_kw=watts/1000,grid_charge_current_a=40,
                             forecast_at=fixture.NOW.isoformat())
        self.document['forecast']=[dict(start=(fixture.NOW+timedelta(hours=i)).isoformat(),
            end=(fixture.NOW+timedelta(hours=i+1)).isoformat(),pv_kw=0 if i<1 else 4)
            for i in range(-1,8)]
        self.plan.update(self.document)

    def test_skip_charge_and_release_independent_of_grid_but_not_authority(self):
        self.seed()
        for online in (True,False,None):
            result=self.evaluate(soc=60,load_w=500,solar_w=0,grid_online=online,mode='panic_grid_hold')
            self.assertTrue(result['solar_bridge_safe'])
            self.assertEqual('solar',result['request'])
            self.assertGreater(result['predicted_minimum_soc'],45)
        self.assertIsNone(self.evaluate(automatic=False)['request'])

    def test_early_deficit_cannot_be_repaid_by_later_sun(self):
        self.seed(1600)
        result=self.evaluate(soc=50,load_w=1600,solar_w=0)
        self.assertFalse(result['solar_bridge_safe'])
        self.assertNotEqual('solar',result['request'])

    def test_stale_forecast_and_missing_load_history_do_not_enable_bridge(self):
        self.seed()
        self.document['forecast_at']=(fixture.NOW-timedelta(hours=25)).isoformat()
        self.plan.update(self.document)
        self.assertFalse(self.evaluate(load_w=500)['solar_bridge_safe'])
        self.seed()
        self.assertTrue(self.evaluate(soc=80)['solar_bridge_safe'])  # History no longer selects demand

    def test_full_battery_zero_charge_does_not_zero_future_solar(self):
        self.seed()
        result=self.evaluate(soc=100,load_w=500,solar_w=0,charge_a=0)
        self.assertTrue(result['solar_bridge_safe'])
        self.assertGreater(result['outage_credited_solar_kwh'],0)

    def test_shared_current_change_and_invalid_value_preserve_owned_hold(self):
        self.seed()
        result=self.evaluate()
        self.assertEqual(40,result['grid_charge_current_a'])
        self.document['grid_charge_current_a']=0
        self.plan.active_context=dict(schema=1,start=self.document['groups']['1.1'][0]['start'],target_soc=80)
        self.plan.update(self.document)
        result=self.evaluate(mode='panic_grid_hold',current_target=80)
        self.assertTrue(result['control_active'])
        self.assertEqual('guarded',result['phase'])
        self.assertIsNone(result['request'])

    def test_history_reconstructs_and_gap_invalidates(self):
        self.seed()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'load.json'
            history=HouseDemand(path);history.rows=[[fixture.NOW.timestamp()-i*60,500] for i in range(180,-1,-1)]
            now=fixture.NOW+timedelta(seconds=30)
            self.assertAlmostEqual(.6,history.observe(now,500,True))
            restored=HouseDemand(path)
            self.assertAlmostEqual(.6,restored.observe(now,500,True))
            self.assertIsNone(restored.observe(now+timedelta(minutes=3),500,True))

    def test_hp_start_includes_incremental_demand_and_never_crosses_floor(self):
        self.seed()
        self.document.update(hp_state='off',hp_running=False)
        for row in self.document['forecast']:row['pv_kw']=8
        self.plan.update(self.document)
        result=self.evaluate(soc=46,load_w=500,solar_w=8000)
        self.assertTrue(result['hp_start_permitted'])
        self.assertAlmostEqual(.5,result['house_planning_demand_kw'])
        self.assertFalse(self.evaluate(soc=45,load_w=500,solar_w=8000)['hp_start_permitted'])
        self.assertFalse(self.evaluate(soc=46,load_w=500,solar_w=8000,base_reserve=50)['hp_start_permitted'])
        self.document.update(hp_state='heat',hp_running=True,hp_state_since=fixture.NOW.isoformat())
        self.plan.update(self.document)
        self.assertAlmostEqual(.5,self.evaluate(load_w=500)['house_planning_demand_kw'])
