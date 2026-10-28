import json
import unittest
from pathlib import Path
import yaml
from jinja2 import Environment
from test_presentation import contents

ROOT=Path(__file__).resolve().parents[2]


class NotificationStatusTests(unittest.TestCase):
    def test_offline_grid_hold_card_never_claims_available_supply(self):
        dashboard=json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        template=Environment().from_string(next(c for c in contents(dashboard) if '**Резерв батареї:**' in c))
        values={'sensor.energyhub_operating_mode':'panic_grid_hold',
                'binary_sensor.energyhub_grid_confirmed':'off', 'input_number.ahm_minimum_soc':'40'}
        text=template.render(states=lambda e:values.get(e,'unknown'),
            is_state=lambda e,v:True, state_attr=lambda e,k:95 if k=='target_soc' else None)
        self.assertIn('**Резерв батареї:** 40%',text)
        self.assertIn('**Ціль підготовки:** 95%',text)
        self.assertIn('Живлення від ДТЕК зараз не підтверджене',text)
