"""Offline bridge structure/template checks; not a Home Assistant runtime test."""
import ast
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[2]


class BridgeTests(unittest.TestCase):
    def test_restart_preserves_requested_setting_but_rotates_session(self):
        actions = self.by_id['energyhub_load_bridge_start']['actions']
        self.assertEqual(['input_text.set_value'], [x['action'] for x in actions])
        source = (ROOT/'homeassistant/live/config/configuration.yaml').read_text(encoding='utf-8')
        helper = source.split('  energyhub_load_control_armed:',1)[1].split('\ninput_number:',1)[0]
        self.assertNotIn('initial:',helper)
        executor = str(self.by_id['energyhub_load_control_executor'])
        for gate in ('bridge_session', 'telemetry_freshness', 'expected_context', 'expected_revision'):
            self.assertIn(gate,executor)

    def test_dashboard_removes_only_emergency_button(self):
        data = json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        serialized = json.dumps(data)
        self.assertNotIn('script.energyhub_start_panic', serialized)
        for value in ('input_boolean.energyhub_autopilot', 'input_boolean.energyhub_load_control_armed',
                      'input_select.energyhub_climate_policy',
                      'input_select.energyhub_climate_operation',
                      'ACTIVE RESERVE', 'Increase 5%', 'Decrease 5%'):
            self.assertIn(value, serialized)

    @classmethod
    def setUpClass(cls):
        cls.automations = yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        cls.by_id = {str(a['id']): a for a in cls.automations}
        package = yaml.safe_load((ROOT/'homeassistant/live/config/packages/energyhub_3.yaml').read_text(encoding='utf-8'))
        cls.automations += package['automation']
        cls.by_id.update({r['id']: r for r in package['automation']})
        cls.env = NativeEnvironment()
        cls.env.tests['search'] = lambda value, pattern: bool(re.search(pattern, value))
        cls.env.filters['tojson'] = json.dumps
        cls.env.filters['to_json'] = json.dumps
        cls.env.filters['from_json'] = lambda value, default={}: json.loads(value) if isinstance(value,str) and value.startswith('{') else default

    def test_unique_ids_and_dashboard_json(self):
        self.assertEqual(len(self.by_id), len(self.automations))
        json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))

    def test_zigbee_availability_uses_existing_switch_entities(self):
        configuration = (ROOT/'homeassistant/live/config/configuration.yaml').read_text(encoding='utf-8')
        automation = str(self.by_id['energyhub_load_control_snapshot'])
        self.assertNotIn('energyhub_first_floor_heat_pump_plug_online', configuration)
        self.assertNotIn('energyhub_second_floor_heat_pump_plug_online', configuration)
        self.assertNotIn('binary_sensor.energyhub_first_floor_heat_pump_plug_online', automation)
        self.assertNotIn('binary_sensor.energyhub_second_floor_heat_pump_plug_online', automation)
        self.assertNotIn('switch.first_floor_heat_pump_plug', automation)
        self.assertNotIn('switch.second_floor_heat_pump_plug', automation)

    def test_every_new_template_compiles(self):
        def walk(value):
            if isinstance(value, dict):
                for v in value.values(): walk(v)
            elif isinstance(value, list):
                for v in value: walk(v)
            elif isinstance(value, str) and ('{{' in value or '{%' in value):
                self.env.from_string(value)
        for key, value in self.by_id.items():
            if key.startswith((
                'energyhub_load_',
                'energyhub_smart_heating_',
                'energyhub_heat_pump_',
            )):
                walk(value)

    def test_service_target_mapping_and_same_state_requests(self):
        variables = self.by_id['energyhub_load_control_external_intents']['actions'][0]['variables']
        self.assertIn("data.get('target'", variables['targets'])
        self.assertIn("service_data.get('entity_id'", variables['targets'])
        template = self.env.from_string(variables['keys'])
        mapping = variables['mapping']
        def render(**kwargs):
            value = template.render(**kwargs)
            return ast.literal_eval(value.strip()) if isinstance(value, str) else value
        self.assertEqual([], render(mapping=mapping,
            target_list=['switch.water_boiler_plug_switch']))
        self.assertEqual(['heat_pump_floor_1'], render(mapping=mapping,
            target_list=['switch.first_floor_heat_pump_eco']))
        self.assertEqual([], render(mapping=mapping, target_list=['switch.unrelated']))
        self.assertEqual([], render(mapping=mapping, target_list=[]))

    def test_executor_is_allowlisted_expiring_and_not_retained(self):
        executor = self.by_id['energyhub_load_control_executor']
        variables = executor['actions'][0]['variables']
        self.assertEqual({'heat_pump_floor_1'}, set(variables['mapping']))
        # First-floor relay is intentionally absent from the command allow-list.
        self.assertNotIn('switch.first_floor_heat_pump_plug', variables['mapping'].values())
        guard = executor['actions'][1]['value_template']
        for field in ('expires_at', 'issued_at', 'expected_context', 'expected_revision',
                      'expected_settings', 'bridge_session',
                      'last_reported'):
            self.assertIn(field, guard)
        self.assertFalse(executor['actions'][-1]['data']['retain'])

    def test_restore_headroom_is_checked_again_at_execution(self):
        gate = self.env.from_string(self.by_id['energyhub_load_control_executor']['actions'][2]['value_template'])
        context = dict(cmd=dict(action='restore',key='heat_pump_floor_1',reason='battery'),load_pct=49,load_w=100,hp1_battery_recovered=True)
        self.assertTrue(gate.render(**context))
        context['load_pct']=50
        self.assertFalse(gate.render(**context))

    def test_no_arm_on_startup(self):
        actions = self.by_id['energyhub_load_bridge_start']['actions']
        self.assertNotIn('input_boolean.turn_on', [x['action'] for x in actions])
        self.assertNotIn('input_boolean.turn_off', [x['action'] for x in actions])

    def test_retired_battery_commands_fail_the_executor_boundary(self):
        source = self.by_id['energyhub_load_control_executor']['actions'][1]['value_template']
        self.assertIn('cmd.get("reason") == "battery"',source)
        self.assertIn('cmd.get("key") == "heat_pump_floor_1"',source)

    def test_no_restart_allowance_gates_or_dashboard_inputs(self):
        executor = str(self.by_id['energyhub_load_control_executor'])
        self.assertNotIn('restore_budget_w', executor)
        self.assertNotIn('energyhub_restart_', executor)
        self.assertIn("cmd.get('control_schema') == 6", " ".join(self.by_id['energyhub_load_control_executor']['actions'][1]['value_template'].split()))
        dashboard = (ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8')
        self.assertNotIn('input_number.energyhub_restart_', dashboard)
        self.assertIn('below 50% for five minutes', dashboard.lower())

    def test_bridge_contract_version_prevents_old_retained_arming(self):
        payload = self.by_id['energyhub_load_control_snapshot']['actions'][1]['data']['payload']
        self.assertIn("'control_schema': 6", payload)
        self.assertNotIn('restore_budget_w', payload)
        self.assertNotIn('energyhub_restart_', payload)
        self.assertIn("'automatic_requested'", payload)
        self.assertNotIn("'battery_control_ready'", payload)
        self.assertEqual(1, payload.count("'state_observed_at'"))

    def test_missing_participant_does_not_abort_whole_snapshot(self):
        payload = self.by_id['energyhub_load_control_snapshot']['actions'][1]['data']['payload']

        class MissingStates:
            def __call__(self, _entity):
                return 'unknown'

            def __getitem__(self, entity):
                raise KeyError(entity)

        rendered = self.env.from_string(payload).render(
            states=MissingStates(), state_attr=lambda *_args: None,
            is_state=lambda *_args: False, now=lambda: datetime(2026, 9, 29, tzinfo=timezone.utc),
            bridge_ready=False,
        )
        snapshot = json.loads(rendered)
        self.assertEqual(1, len(snapshot['loads']))
        self.assertFalse(snapshot['armed'])
        self.assertTrue(all(row['state_observed_at'] is None and row['context_id'] is None
                            and row['power_observed_at'] is None for row in snapshot['loads']))

    def test_smart_heating_is_native_first_floor_only_and_protection_aware(self):
        policy = self.by_id['energyhub_smart_heating_first_floor']
        text = str(policy)
        self.assertIn('climate.first_floor_heat_pump', text)
        self.assertIn('sensor.energyhub_peak_load_guard', text)
        self.assertIn('input_boolean.energyhub_smart_heating', text)
        self.assertIn('input_boolean.energyhub_solar_only_heating', text)
        self.assertNotIn('switch.second_floor_heat_pump_plug', text)
        self.assertNotIn('switch.third_floor_heat_pump_plug_switch', text)

    def test_manual_off_blocks_unowned_smart_heating_restart(self):
        policy = self.by_id['energyhub_smart_heating_first_floor']
        self.assertEqual('smart_enabled', policy['triggers'][2]['id'])
        branches = policy['actions'][2]['choose']
        manual = self.env.from_string(branches[3]['conditions'])
        is_state = lambda entity, state: (entity, state) == (
            'climate.first_floor_heat_pump', 'off')
        self.assertTrue(manual.render(is_state=is_state))
        self.assertFalse(manual.render(is_state=lambda *args: True))
        self.assertIn('energyhub_hp1_auto_resume', str(branches[3]))
        self.assertIn('input_number.energyhub_load_off_soc', str(branches[4]))
        self.assertIn('solar_only and not solar_allowed', str(branches[6]))
        manual_off = self.by_id['energyhub_3_family_off_overrides_schedule']
        self.assertIn('context.user_id is not none', str(manual_off))
        self.assertIn('energyhub_hp1_auto_resume', str(manual_off))

    def test_smart_heating_preserves_family_setpoint_and_fan(self):
        policy = self.by_id['energyhub_smart_heating_first_floor']
        actions = str(policy['actions'])
        self.assertNotIn('climate.set_temperature', actions)
        self.assertNotIn('climate.set_fan_mode', actions)
        self.assertNotIn('switch.first_floor_heat_pump_super', actions)
        self.assertIn('input_boolean.energyhub_hp1_auto_resume',
                      str(policy['actions'][2]['default']))

    def test_manual_off_service_request_accepts_service_data_target(self):
        manual_off = self.by_id['energyhub_3_family_off_overrides_schedule']
        template = self.env.from_string(manual_off['conditions'][0]['value_template'])
        for placement in ('target', 'service_data'):
            with self.subTest(placement=placement):
                data = {'domain': 'climate', 'service': 'set_hvac_mode',
                        'service_data': {'hvac_mode': 'off'}}
                data.setdefault(placement, {})['entity_id'] = (
                    'climate.first_floor_heat_pump')
                trigger = SimpleNamespace(id='manual_request', event=SimpleNamespace(
                    data=data, context=SimpleNamespace(user_id='family')))
                self.assertTrue(template.render(trigger=trigger, is_state=lambda *args: False))


    def test_heating_protection_blocks_other_owned_loads_and_high_load(self):
        source = self.by_id['energyhub_smart_heating_first_floor']['actions'][1]['variables']['protected']
        template = self.env.from_string(source)
        observed = datetime(2026, 9, 26, tzinfo=timezone.utc)
        context = dict(
            now=lambda: observed,
            as_timestamp=lambda value, default=0: observed.timestamp() if value else default,
            states=lambda entity: 'normal',
            state_attr=lambda entity, key: observed.isoformat() if key == 'load_snapshot_at' else None,
            cycle={'owned': {'water_pump': {}}}, pending={}, load_pct=20,
        )
        self.assertTrue(template.render(**context))
        context['cycle'] = {}
        self.assertFalse(template.render(**context))
        context['load_pct'] = 80
        self.assertTrue(template.render(**context))

    def test_solar_only_uses_distinct_start_and_continue_thresholds(self):
        source = self.by_id['energyhub_smart_heating_first_floor']['actions'][1]['variables']['solar_allowed']
        template = self.env.from_string(source)
        heating = False
        context = dict(
            fresh=True, pv=500, soc=70, reserve=20, solar_thresholds_valid=True, solar_start_w=600, solar_pause_w=400,
            states=lambda entity: ('heat' if heating else 'off') if entity.startswith('climate.') else 'solar',
            is_state=lambda entity, state: (
                (entity == 'sun.sun' and state == 'above_horizon')
                or (entity == 'climate.first_floor_heat_pump'
                    and state == 'heat' and heating)
            ),
        )
        self.assertFalse(template.render(**context))
        context['pv'] = 600
        self.assertTrue(template.render(**context))
        context['pv'] = 500
        heating = True
        self.assertTrue(template.render(**context))
        context['pv'] = 399
        self.assertFalse(template.render(**context))



    def test_reserve_apply_rejects_unavailable_and_old_evidence(self):
        source = self.by_id['energyhub_battery_reserve_automatic_apply']['conditions'][1]['value_template']
        template = self.env.from_string(source)
        observed = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
        attrs = dict(recommended_soc=20, automatic_control_available=True,
                     daily_plan_fresh=True, recommendation_status='ready',
                     date='2026-09-26', forecast_plan_stage='refresh',
                     control_evidence_at=observed.isoformat())
        context = dict(now=lambda: observed, today_at=lambda *args: observed,
                       as_timestamp=lambda value, default=0: datetime.fromisoformat(value).timestamp() if value else default,
                       timedelta=__import__('datetime').timedelta,
                       state_attr=lambda entity, key: attrs.get(key),
                       states=lambda entity: '60' if entity.startswith('input_number.') else 'ready')
        self.assertEqual('True', str(template.render(**context)).strip())
        context['states'] = lambda entity: '60' if entity.startswith('input_number.') else 'unavailable'
        self.assertEqual('False', str(template.render(**context)).strip())
        context['states'] = lambda entity: '60' if entity.startswith('input_number.') else 'ready'
        attrs['control_evidence_at'] = '2026-09-20T12:00:00+00:00'
        self.assertEqual('False', str(template.render(**context)).strip())

    def test_warning_only_overload_is_consistent_at_executor(self):
        gate = self.by_id['energyhub_load_control_executor']['actions'][1]['value_template']
        self.assertIn('cmd.get("reason") == "battery"',gate)
        self.assertIn('cmd.get("key") == "heat_pump_floor_1"',gate)

    def test_smart_heating_quiet_hours_and_beacon_pulse_are_explicit(self):
        smart_heating = self.by_id['energyhub_smart_heating_first_floor']
        policy = str(smart_heating)
        self.assertIn('input_boolean.energyhub_climate_quiet_enabled', policy)
        self.assertIn("family_mode in ['heat', 'cool']", policy)
        self.assertIn('input_number.energyhub_load_off_soc', policy)
        self.assertIn('input_number.energyhub_load_restore_soc', policy)
        self.assertIn('input_boolean.energyhub_hp1_battery_paused', policy)
        self.assertIn("'Eco' if eco_needed", policy)
        self.assertNotIn('Turbo', policy)
        self.assertIn('script.energyhub_apply_hp_profile', policy)
        time_trigger = next(
            trigger for trigger in smart_heating['triggers']
            if trigger['trigger'] == 'time'
        )
        self.assertEqual(['input_datetime.energyhub_climate_quiet_start',
                          'input_datetime.energyhub_climate_quiet_end'], time_trigger['at'])
        pulse = self.by_id['energyhub_smart_heating_beacon_pulse']
        self.assertEqual('/1', pulse['triggers'][0]['minutes'])
        self.assertEqual('timer.start', pulse['actions'][0]['action'])
        self.assertEqual(
            'timer.energyhub_smart_heating_beacon_pulse',
            pulse['actions'][0]['target']['entity_id'],
        )
        self.assertEqual('00:00:05', pulse['actions'][0]['data']['duration'])

        configuration = (
            ROOT/'homeassistant/live/config/configuration.yaml'
        ).read_text(encoding='utf-8')
        timer = configuration.split(
            '  energyhub_smart_heating_beacon_pulse:', 1
        )[1].split('\nsensor:', 1)[0]
        self.assertIn('duration: "00:00:02"', timer)

    def test_beacon_has_solid_white_fail_safe_and_no_dark_blink(self):
        beacon = str(self.by_id['1781793005552'])
        self.assertIn('[255, 255, 255]', beacon)
        self.assertIn('[220, 20, 30]', beacon)
        self.assertIn('[90, 0, 25]', beacon)
        self.assertIn('[20, 50, 80, 50]', beacon)
        self.assertIn('timer.energyhub_smart_heating_beacon_pulse', beacon)
        self.assertIn('input_boolean.energyhub_solar_only_heating', beacon)
        self.assertIn('[255, 220, 0]', beacon)

    def test_mode_failure_notification_condition_is_structurally_valid(self):
        notification = self.by_id['1783953087633']
        self.assertEqual('template', notification['conditions'][0]['condition'])
        self.assertIn('automatic_mode_activation_failed', notification['conditions'][0]['value_template'])
        self.assertEqual('persistent_notification.create', notification['actions'][1]['action'])

    def test_single_visible_overload_switch_separate_from_battery(self):
        dashboard = json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        matches = []
        def walk(node):
            if isinstance(node, dict):
                if node.get('entity') == 'input_boolean.energyhub_load_control_armed': matches.append(node)
                for child in node.values(): walk(child)
            elif isinstance(node, list):
                for child in node: walk(child)
        walk(dashboard)
        self.assertEqual(1, len(matches))
        self.assertEqual('Inverter Overload Guard', matches[0]['name'])
        self.assertEqual('toggle', matches[0]['tap_action']['action'])


    def test_solar_telemetry_gap_preserves_running_state_for_at_most_sixty_seconds(self):
        policy = self.by_id['energyhub_smart_heating_first_floor']
        stop = self.env.from_string(policy['actions'][2]['choose'][6]['conditions'])
        context = dict(solar_only=True, solar_allowed=False, fresh=False,
                       input_loss_age=13, soc=None, reserve=20, hp_age=600,
                       solar_inputs_ready=False,
                       states=lambda entity: 'unknown', is_state=lambda *args: False)
        self.assertFalse(stop.render(**context))
        context['input_loss_age'] = 60
        self.assertTrue(stop.render(**context))
        context['input_loss_age'] = 13
        context['is_state'] = lambda entity, value: value == 'below_horizon'
        self.assertTrue(stop.render(**context))
        context.update(fresh=True, soc=19, is_state=lambda *args: False)
        self.assertTrue(stop.render(**context))
        blocked = self.env.from_string(policy['actions'][2]['choose'][7]['conditions'])
        self.assertTrue(blocked.render(hp_available=True, protected=False, fresh=False, solar_only=True, solar_inputs_ready=False))

    def test_startup_unknown_mode_does_not_override_gap_grace_or_allow_start(self):
        policy = self.by_id['energyhub_smart_heating_first_floor']
        stop = self.env.from_string(policy['actions'][2]['choose'][6]['conditions'])
        blocked = self.env.from_string(policy['actions'][2]['choose'][7]['conditions'])
        context = dict(solar_only=True, solar_allowed=False, fresh=True,
            solar_inputs_ready=False, input_loss_age=1, soc=99, reserve=20,
            hp_age=600, states=lambda entity: 'unknown', is_state=lambda *args: False)
        self.assertFalse(stop.render(**context))
        self.assertTrue(blocked.render(hp_available=True, protected=False, night_stop=False, **context))
        context['input_loss_age'] = 60
        self.assertTrue(stop.render(**context))
        context.update(input_loss_age=1, solar_inputs_ready=True, states=lambda entity: 'hybrid_grid_hold')
        self.assertTrue(stop.render(**context))


if __name__ == '__main__':
    unittest.main()
