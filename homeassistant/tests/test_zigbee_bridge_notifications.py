from pathlib import Path
import unittest
import yaml

class ZigbeeNotificationsRetiredTests(unittest.TestCase):
    def test_custom_bridge_alerts_are_absent(self):
        root=Path(__file__).resolve().parents[2]
        rows=yaml.safe_load((root/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        self.assertFalse({'1786100000101','1786100000102'} & {r['id'] for r in rows})
