"""Retired first-floor relay control must not return through another path."""
import json
import unittest
from pathlib import Path
import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT=Path(__file__).resolve().parents[2]
RELAY='switch.first_floor_heat_pump_plug'
POWER='sensor.first_floor_heat_pump_plug_power'
ENERGY='sensor.first_floor_heat_pump_plug_energy'


class MeteringOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.automations=yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        cls.by_id={str(row['id']):row for row in cls.automations}
        cls.package=yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))

    def test_relay_is_absent_from_production_and_configuration(self):
        files=[]
        for directory in ('addon/app','telegram-family-bot/app','homeassistant/live/config'):
            files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in {'.py','.yaml','.json'})
        for p in files:
            with self.subTest(path=p.relative_to(ROOT)):
                self.assertNotIn(RELAY,p.read_text(encoding='utf-8'))

    def test_no_recovery_or_timer_component_helpers_or_automation_remain(self):
        self.assertNotIn('energyhub_recovery',self.package)
        for name in ('energyhub_hp1_recovery_enabled','energyhub_hp1_meter_trusted'):
            self.assertNotIn(name,self.package.get('input_boolean',{}))
        for ident in ('energyhub_heat_pump_manual_state_memory','energyhub_heat_pump_grid_recovery_timer',
                      'energyhub_heat_pump_restart_restore','1784300000101'):
            self.assertNotIn(ident,self.by_id)
        for filename in ('__init__.py','engine.py','manifest.json','services.yaml'):
            self.assertFalse((ROOT/'homeassistant/live/config/custom_components/energyhub_recovery'/filename).exists())
        for filename,ident in [('input_number','input_number_floor1_heat_pump_timer_hours'),
                               ('timer','floor_1_heat_pump_auto_off')]:
            data=json.loads((ROOT/'homeassistant/live/storage'/filename).read_text(encoding='utf-8'))
            self.assertNotIn(ident,{r['id'] for r in data['data']['items']})

    def test_climate_readiness_does_not_require_relay_or_recovery_status(self):
        smart=self.by_id['energyhub_smart_heating_first_floor']
        source=smart['actions'][1]['variables']['hp_available']
        value=NativeEnvironment().from_string(source).render(
            states=lambda e:'heat' if e=='climate.first_floor_heat_pump' else 'unavailable',
            is_state=lambda *args:False, family_mode='heat')
        self.assertEqual('true',str(value).strip().lower())
        self.assertNotIn('energyhub_hp1_recovery',str(smart))

    def test_overload_still_uses_climate_entity_and_retains_metering(self):
        executor=self.by_id['energyhub_load_control_executor']
        self.assertEqual('climate.first_floor_heat_pump',executor['actions'][0]['variables']['mapping']['heat_pump_floor_1'])
        snapshot=str(self.by_id['energyhub_load_control_snapshot'])
        self.assertIn(POWER,snapshot)
        self.assertNotIn(RELAY,snapshot)
        self.assertNotIn('energyhub_hp1_recovery',str(executor))

    def test_dashboard_retains_only_first_floor_metering_entities(self):
        text=(ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8')
        for entity in (POWER,ENERGY):self.assertIn(entity,text)
        for entity in (RELAY,'sensor.energyhub_hp1_recovery','energyhub_hp1_recovery_enabled'):
            self.assertNotIn(entity,text)
        configuration=(ROOT/'homeassistant/live/config/configuration.yaml').read_text(encoding='utf-8')
        self.assertIn('source: '+ENERGY,configuration)
        self.assertNotIn('Turns Off At',configuration)

    def test_temperature_units_come_from_retained_network_metadata(self):
        package=(ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8')
        self.assertIn("state_attr('sensor.energyhub_hp1_connection', 'ha_temperature_unit')",package)
        network=(ROOT/'homeassistant/live/config/custom_components/energyhub_network/__init__.py').read_text(encoding='utf-8')
        self.assertIn("'ha_temperature_unit':",network)
        self.assertIn('hass.config.units.temperature_unit',network)
        self.assertNotIn('plug_state',network)
        self.assertNotIn('recovery_enabled',network)
