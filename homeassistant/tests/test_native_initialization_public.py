import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
class NativeInitializationTests(unittest.TestCase):
    def setUp(self):
        self.rows=yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        self.rows+=yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))['automation']
        self.configured={str(r['id']) for r in self.rows}

    def test_installation_preserves_all_three_initialization_guards(self):
        rule=next(r for r in self.rows if r['id']=='energyhub_initialize_installation')
        self.assertEqual(3,len(rule['actions']))
        self.assertEqual('energyhub_planning_settings_initialized',rule['actions'][0]['if'][0]['entity_id'].split('.')[1])
        self.assertEqual('energyhub_330_initialized',rule['actions'][1]['if'][0]['entity_id'].split('.')[1])
        self.assertIn('== 0',rule['actions'][2]['if'][0]['value_template'])
        self.assertEqual([600,400],[a['data']['value'] for a in rule['actions'][2]['then']])

    def test_retired_helper_writers_and_non_hp_intents_are_absent(self):
        text=(ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8')
        config=(ROOT/'homeassistant/live/config/configuration.yaml').read_text(encoding='utf-8')
        self.assertNotIn('input_number.daily_solar_surplus_estimated',text)
        self.assertNotIn('1783102330433',self.configured)
        for key in ['water_pump','water_boiler','heat_pump_floor_2','heat_pump_floor_3','microwave']:
            self.assertNotIn('energyhub_intent_'+key,config)
        self.assertIn('energyhub_intent_heat_pump_floor_1',config)

    def test_battery_and_hp_control_sequences_are_preserved(self):
        by_id={str(r['id']):r for r in self.rows}
        self.assertEqual('restart',by_id['energyhub_battery_discharge_protection']['mode'])
        self.assertEqual('00:02:00',by_id['energyhub_fridge_battery_protection']['actions'][0]['timeout'])
        self.assertIn('input_boolean.energyhub_hp1_manual_hold',str(by_id['energyhub_smart_heating_first_floor']))
