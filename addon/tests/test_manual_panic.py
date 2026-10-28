import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from app.services.inverter_controller import InverterController
from app.services.panic_decision import PanicDecisionEngine

class ManualPanicTests(unittest.TestCase):
    def test_restart_target_cannot_be_lowered_and_explicit_cancel(self):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'controller.json')
            controller=InverterController(Mock(),state_path=path)
            self.assertTrue(controller.set_manual_panic(True))
            controller.set_panic_target_soc(40)
            restored=InverterController(Mock(),state_path=path)
            self.assertTrue(restored.manual_panic_active)
            self.assertEqual(95,restored.panic_target_soc)
            restored.set_manual_panic(False)
            restored.set_panic_target_soc(40)
            self.assertFalse(InverterController(Mock(),state_path=path).manual_panic_active)
            self.assertEqual(40,restored.panic_target_soc)

    def test_manual_target_ignores_reserve_confidence_and_never_releases(self):
        for soc in (50,95,100):
            engine=PanicDecisionEngine()
            result=engine.evaluate(autopilot_enabled=True,operating_mode='panic_grid_hold',
                grid_confidence='unknown',battery_soc=soc,grid_available=True,
                manual_reserve_soc=None,manual_panic_active=True)
            self.assertEqual(95,result['target_soc'])
            self.assertNotEqual('solar',result.get('request'))
            self.assertIsNone(engine.release_soc)

    def test_manual_panic_retains_stale_soc_and_autopilot_guards(self):
        for enabled,soc in ((True,None),(False,50)):
            result=PanicDecisionEngine().evaluate(autopilot_enabled=enabled,operating_mode='panic',
                grid_confidence='normal',battery_soc=soc,grid_available=True,
                manual_reserve_soc=20,manual_panic_active=True)
            self.assertIsNone(result.get('request'))
