import unittest
from app.events import peak_load_guard_message


class BatteryMessageTests(unittest.TestCase):
    def test_battery_stop_is_not_called_inverter_overload(self):
        message = peak_load_guard_message(dict(type='load_shed', mode='automatic', reason='battery',
            battery_soc=49, affected_loads=[dict(key='water_pump')], load_percent=12))
        self.assertIn('49%', message)
        self.assertIn('заряд', message)
        self.assertNotIn('Захист інвертора', message)
        self.assertNotIn('SOC', message)
