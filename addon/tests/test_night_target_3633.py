import unittest
from datetime import timedelta
from app.services.night_charge import NightCharge, choose_owner
import test_night_charge_3623 as fixture


class NightTargetTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.NightTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_grid_return_does_not_recharge_to_initial_soc(self):
        self.f.set_forecast(fixture.NOW,9)
        self.f.evaluate(soc=73,grid_online=False)
        now=fixture.NOW+timedelta(minutes=20)
        self.f.set_forecast(now,9)
        result=self.f.evaluate(now=now,soc=66)
        self.assertEqual(65,result['target_soc']);self.assertEqual('holding',result['phase'])

    def test_old_retained_hold_soc_is_replaced_by_calculated_target(self):
        self.f.evaluate(soc=91)
        data=self.f.plan.saved;data['current']['hold_soc']=95;self.f.plan._save(data)
        self.f.plan=NightCharge(self.f.path)
        self.f.set_forecast(fixture.NOW+timedelta(seconds=2),5)
        result=self.f.evaluate(now=fixture.NOW+timedelta(seconds=2),soc=92)
        self.assertEqual(90,result['target_soc']);self.assertEqual('holding',result['phase'])

    def test_operations_require_selected_acknowledged_charging_and_grid(self):
        self.f.evaluate()
        now=fixture.NOW+timedelta(seconds=2)
        night=dict(phase='charging',target_soc=90,acknowledged=False)
        self.f.plan.record_operation(now=now,soc=70,preparation={},night=night,owner=night,charge_a=20,grid_online=True)
        self.assertFalse(self.f.plan.saved['current'].get('operations'))
        night['acknowledged']=True
        self.f.plan.record_operation(now=now,soc=70,preparation={},night=night,owner=night,charge_a=20,grid_online=True)
        self.assertEqual(70,self.f.plan.saved['current']['operations']['night']['start_soc'])
        self.f.plan=NightCharge(self.f.path)
        self.assertIn('night',self.f.plan.saved['current']['operations'])

    def test_scheduled_higher_target_can_take_over_without_relabeling_night(self):
        night=dict(control_active=True,target_soc=65)
        scheduled=dict(control_active=True,target_soc=90)
        self.assertIs(scheduled,choose_owner(scheduled,night))
