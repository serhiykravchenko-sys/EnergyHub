"""Schema-4 battery protection replaces independent confidence/relay guards."""
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


class SmartPlugAuthorityTests(unittest.TestCase):
    def test_old_independent_reserve_writers_removed(self):
        data = yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        ids = {str(x['id']) for x in data}
        for ident in ('1786023000001', '1786023000002', '1786023000003', '1786023000004',
                      '1786023000011', '1786023000013', '1786023000014', '1786023000015', '1786023000016'):
            self.assertNotIn(ident, ids)
        executor = next(x for x in data if x['id'] == 'energyhub_load_control_executor')
        text = str(executor)
        self.assertNotIn('energyhub_grid_confidence', text)
        self.assertIn('battery_recovered', text)
        self.assertIn('climate.set_hvac_mode', text)
        self.assertNotIn('switch.first_floor_heat_pump_plug', executor['actions'][0]['variables']['mapping'].values())

    def test_dashboard_explains_actual_outage_and_owned_restoration(self):
        text = (ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8')
        self.assertNotIn('Instantaneous grid-voltage and telemetry transitions cannot', text)
        self.assertIn('actual grid outages', text)
        self.assertIn('EH-owned', text)
