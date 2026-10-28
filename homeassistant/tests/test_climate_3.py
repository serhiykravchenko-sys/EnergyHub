"""Render the actual HA policy for boundaries, cooling and invalid inputs."""
import json
import ast
import re
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from jinja2.nativetypes import NativeEnvironment
import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT/'homeassistant/live/config/packages/energyhub_3.yaml'


class ClimateTests(unittest.TestCase):
    def test_night_manual_release_keeps_user_guard_without_retired_recovery(self):
        def check_unique(node):
            if isinstance(node, yaml.MappingNode):
                keys = [key.value for key, _ in node.value]
                self.assertEqual(len(keys), len(set(keys)), 'Duplicate YAML mapping key')
                for _, value in node.value:
                    check_unique(value)
            elif isinstance(node, yaml.SequenceNode):
                for value in node.value:
                    check_unique(value)
        check_unique(yaml.compose(PACKAGE.read_text(encoding='utf-8')))
        data = yaml.safe_load(PACKAGE.read_text(encoding='utf-8'))
        automation = next(row for row in data['automation']
                          if row['id'] == 'energyhub_3_night_manual_temperature')
        self.assertEqual(1, len(automation['conditions']))
        self.assertNotIn('energyhub_hp1_recovery', str(automation))
        template = automation['conditions'][0]['value_template']
        env = NativeEnvironment()
        for domain, service, target, user, expected in [
                ('climate', 'set_temperature', 'climate.first_floor_heat_pump', 'owner', True),
                ('climate', 'set_temperature', 'climate.first_floor_heat_pump', None, False),
                ('light', 'turn_on', 'light.beacon', 'owner', False),
                ('climate', 'set_temperature', 'climate.other', 'owner', False)]:
            trigger = SimpleNamespace(event=SimpleNamespace(
                context=SimpleNamespace(user_id=user),
                data={'domain': domain, 'service': service, 'target': {'entity_id': target}}))
            self.assertEqual(expected, env.from_string(template).render(trigger=trigger))

    def setUp(self):
        self.data = yaml.safe_load(PACKAGE.read_text(encoding='utf-8'))
        self.sensors = {row['unique_id']: row for row in next(row['sensor'] for row in self.data['template'] if 'sensor' in row)}
        self.env = NativeEnvironment()
        self.env.globals['states'] = lambda entity: 'unknown'
        self.env.filters['regex_match'] = lambda value, pattern: bool(re.match(pattern, str(value)))
        self.env.filters['to_json'] = json.dumps
        self.env.filters['from_json'] = lambda value, default={}: json.loads(value) if value.startswith('{') else default
        self.states = {
            'input_select.energyhub_climate_policy': 'Smart',
            'input_select.energyhub_climate_operation': 'Scheduled',
            'input_boolean.energyhub_climate_solar_window_enabled': 'on',
            'input_boolean.energyhub_climate_smart_window_enabled': 'on',
            'input_datetime.energyhub_climate_solar_start': '09:00:00',
            'input_datetime.energyhub_climate_solar_end': '17:00:00',
            'input_datetime.energyhub_climate_smart_start': '19:00:00',
            'input_datetime.energyhub_climate_smart_end': '00:00:00',
        }

    def render(self, name, hour, minute=0, template_field='state', **extra):
        now = datetime(2026, 10, 3, hour, minute, tzinfo=timezone.utc)
        result = self.env.from_string(self.sensors[name][template_field]).render(
            states=lambda entity: self.states.get(entity, 'unknown'),
            is_state=lambda entity, value: self.states.get(entity) == value,
            now=lambda: now, timedelta=timedelta,
            today_at=lambda value: now.replace(hour=int(value[:2]), minute=int(value[3:5]), second=int(value[6:8])), **extra)
        if isinstance(result, str):
            try:
                return ast.literal_eval(result.strip())
            except (ValueError, SyntaxError):
                return result.strip()
        return result

    def test_daily_windows_boundaries_and_continuous(self):
        for hour, minute, expected in [(8,59,'Off'), (9,0,'Solar-only'), (16,59,'Solar-only'),
                (17,0,'Off'), (19,0,'Smart'), (23,59,'Smart'), (0,0,'Off')]:
            self.assertEqual(expected, self.render('energyhub_climate_requested_policy', hour, minute))
        self.states['input_select.energyhub_climate_operation'] = 'Continuous'
        self.assertEqual('Smart', self.render('energyhub_climate_requested_policy', 3))
        self.states['input_select.energyhub_climate_policy'] = 'Off'
        self.assertEqual('Off', self.render('energyhub_climate_requested_policy', 19))
        self.states['input_select.energyhub_climate_operation'] = 'Scheduled'
        self.states['input_select.energyhub_climate_policy'] = 'Solar-only'
        self.assertEqual('Off', self.render('energyhub_climate_requested_policy', 19))
        self.assertEqual('Solar-only', self.render('energyhub_climate_requested_policy', 9))

    def test_overlap_and_invalid_window_fail_conservatively(self):
        self.states['input_datetime.energyhub_climate_smart_start'] = '16:00:00'
        self.assertEqual('Smart', self.render('energyhub_climate_requested_policy', 16))
        self.states['input_datetime.energyhub_climate_smart_end'] = '16:00:00'
        self.assertEqual('Solar-only', self.render('energyhub_climate_requested_policy', 16))
        self.states['input_datetime.energyhub_climate_solar_end'] = 'unavailable'
        self.assertEqual('Off', self.render('energyhub_climate_requested_policy', 16))
        self.states['input_select.energyhub_climate_policy'] = 'unavailable'
        self.assertEqual('Off', self.render('energyhub_climate_requested_policy', 19))

    def test_quiet_crosses_midnight_only_for_smart_heat(self):
        rows = yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))
        policy = next(row for row in rows if row['id'] == 'energyhub_smart_heating_first_floor')
        template = self.env.from_string(policy['actions'][1]['variables']['quiet_hours'])
        self.states.update({'input_boolean.energyhub_climate_quiet_enabled': 'on',
                           'input_datetime.energyhub_climate_quiet_start': '23:00:00',
                           'input_datetime.energyhub_climate_quiet_end': '06:00:00'})
        def quiet(hour, mode='heat', solar='off'):
            self.states['input_boolean.energyhub_solar_only_heating'] = solar
            result = template.render(states=lambda entity: self.states.get(entity, 'unknown'),
                is_state=lambda entity, value: self.states.get(entity) == value, family_mode=mode,
                now=lambda: datetime(2026,10,3,hour,tzinfo=timezone.utc))
            return result.strip() == 'True' if isinstance(result, str) else result
        for hour in (23,0,5):
            self.assertTrue(quiet(hour))
        for hour in (6,22):
            self.assertFalse(quiet(hour))
        self.assertTrue(quiet(23, 'cool'))
        self.assertFalse(quiet(23, solar='on'))
        self.assertNotIn('set_temperature', str(policy))

    def test_dashboard_views_and_policy_ownership(self):
        data = json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        paths = [v['path'] for v in data['data']['config']['views']]
        self.assertEqual(len(paths), len(set(paths)))
        for path in ('climate-policy', 'air-quality', 'reference', 'network'):
            self.assertIn(path, paths)
        automation = next(row for row in self.data['automation'] if row['id'] == 'energyhub_3_apply_climate_schedule')
        off = automation['actions'][2]['choose'][0]['sequence']
        self.assertEqual('input_number.increment', off[0]['then'][0]['action'])
        self.assertEqual('input_number.energyhub_intent_heat_pump_floor_1', off[0]['then'][0]['target']['entity_id'])
        self.assertEqual('input_boolean.turn_off', off[1]['action'])
        self.assertIn('input_boolean.energyhub_hp1_auto_resume', off[1]['target']['entity_id'])
        family = next(row for row in self.data['automation'] if row['id'] == 'energyhub_3_family_off_overrides_schedule')
        self.assertIn('manual_request', str(family))

    def test_all_package_templates_compile(self):
        def walk(value):
            if isinstance(value, dict):
                for child in value.values(): walk(child)
            elif isinstance(value, list):
                for child in value: walk(child)
            elif isinstance(value, str) and ('{{' in value or '{%' in value):
                self.env.from_string(value)
        walk(self.data)

    def test_native_profile_requests_are_bounded_and_ack_suppresses_writes(self):
        sequence = self.data['script']['energyhub_apply_hp_profile']['sequence']
        condition = self.env.from_string(sequence[2]['value_template'])
        def permits(previous, actual='off', tick=1000):
            value = condition.render(entity='switch.hp_quiet', desired='on', previous=dict(w='night',**previous),
                                     tick=tick, now=lambda: datetime.fromtimestamp(tick, timezone.utc), overrides={}, profile='quiet', quiet_budget={}, window='night', states=lambda entity: actual, is_state=lambda entity,value: value == 'off')
            return value.strip() == 'True' if isinstance(value, str) else value
        self.assertTrue(permits({}))
        self.assertFalse(permits({'t':'on', 'at':950, 'n':1}))
        self.assertTrue(permits({'t':'on', 'at':800, 'n':2}))
        self.assertFalse(permits({'t':'on', 'at':800, 'n':3}))
        self.assertFalse(permits({}, actual='on'))
        self.assertTrue(permits({'t':'off','at':999,'n':3}))

    def test_explicit_user_off_can_cancel_policy_without_recovery_state(self):
        row = next(row for row in self.data['automation'] if row['id'] == 'energyhub_3_family_off_overrides_schedule')
        template = self.env.from_string(row['conditions'][0]['value_template'])
        trigger = SimpleNamespace(id='manual_request', event=SimpleNamespace(
            context=SimpleNamespace(user_id='owner'),
            data=dict(domain='climate',service='turn_off',service_data=dict(entity_id='climate.first_floor_heat_pump'))))
        for phase, expected in [('unavailable',True),('unknown',True)]:
            result=template.render(trigger=trigger, states=lambda entity:phase,
                is_state=lambda entity,value:phase==value)
            self.assertEqual(expected,result.strip()=='True' if isinstance(result,str) else result)

    def night_decision(self, memory=None, current=22, reduction=3, window=True,
                       policy='Smart', mode='heat', minimum=16, features=1, tick=1000, profile_ready=True):
        row = next(row for row in self.data['automation'] if row['id'] == 'energyhub_3_night_temperature')
        result = self.env.from_string(row['actions'][1]['variables']['decision']).render(
            memory=memory or {}, current=current, minimum=minimum, maximum=30, profile_ready=profile_ready,
            offset=-reduction if reduction is not None else None, step=1, unit="°C", in_window=window,
            eligible=window and policy == 'Smart' and mode == 'heat' and reduction is not None and 0 < reduction <= 4,
            hp='climate.hp', states=lambda entity: mode if entity == 'climate.hp' else 'unknown',
            is_state=lambda *args: False, now=lambda: datetime.fromtimestamp(tick, timezone.utc),
            state_attr=lambda entity, attribute: features if attribute == 'supported_features' else None)
        return ast.literal_eval(result.strip()) if isinstance(result, str) else result

    def test_night_reduction_is_not_repeated_and_survives_restart(self):
        first = self.night_decision()
        self.assertEqual(19, first['target'])
        self.assertEqual({'base': 22, 'expected': 19, 'pending_until': 1180,
                          'mode': 'heat', 'unit': '°C'}, first['memory'])
        restarted = self.night_decision(memory=first['memory'], current=19)
        self.assertNotIn('target', restarted)
        settled = self.night_decision(memory=restarted['memory'], current=19, tick=1120)
        self.assertEqual('reduced', settled['event'])
        changed_delta = self.night_decision(memory=settled['memory'], current=19, reduction=4, tick=1125)
        self.assertEqual(18, changed_delta['target'])

    def test_night_manual_target_wins_until_window_ends(self):
        changed = self.night_decision(memory={'base': 22, 'expected': 19}, current=21)
        changed = self.night_decision(memory=changed['memory'], current=21, tick=1120)
        self.assertEqual({'memory': {'blocked': True}}, changed)
        self.assertNotIn('target', self.night_decision(memory=changed['memory'], current=21))
        ended = self.night_decision(memory=changed['memory'], current=21, window=False)
        self.assertEqual({'memory': {}}, ended)

    def test_night_restores_owned_target_and_acknowledges_restore(self):
        for options in ({'window': False}, {'policy': 'Solar-only'}, {'reduction': 0}):
            restored = self.night_decision(memory={'base': 22, 'expected': 19}, current=19, **options)
            self.assertEqual(22, restored['target'])
            acknowledged = self.night_decision(memory=restored['memory'], current=22, **options)
            self.assertNotIn('target', acknowledged)

    def test_night_off_unavailable_cooling_and_limits(self):
        memory = {'base': 22, 'expected': 19}
        self.assertEqual({'memory': {}}, self.night_decision(memory=memory, current=19, mode='off', window=False))
        self.assertEqual({'memory': memory}, self.night_decision(memory=memory, current=19, mode='unavailable', window=False))
        for options in ({'mode': 'cool'}, {'policy': 'Off'}, {'policy': 'Solar-only'},
                        {'reduction': 0}, {'current': None}, {'minimum': None}, {'features': 0}):
            self.assertNotIn('target', self.night_decision(**options))
        self.assertEqual(16, self.night_decision(current=18, reduction=4)['target'])
        # A failed write does not repeatedly issue commands or invent acknowledgement.
        pending = {'base': 22, 'expected': 19, 'pending_until': 1180}
        self.assertEqual(22, self.night_decision(memory=pending, current=22)['memory']['base'])
        self.assertNotIn('target', self.night_decision(memory=pending, current=22, tick=1200))

    def test_shared_night_window_and_dashboard_explanation(self):
        row = next(row for row in self.data['automation'] if row['id'] == 'energyhub_3_night_temperature')
        template = self.env.from_string(row['actions'][0]['variables']['in_window'])
        values = {'input_boolean.energyhub_climate_quiet_enabled': 'on',
                  'input_datetime.energyhub_climate_quiet_start': '23:00:00',
                  'input_datetime.energyhub_climate_quiet_end': '06:00:00'}
        def active(hour):
            result = template.render(states=lambda e: values.get(e), is_state=lambda e,v: values.get(e)==v,
                                     now=lambda: datetime(2026,10,4,hour))
            return result.strip() == 'True' if isinstance(result,str) else result
        for hour in (23,0,5): self.assertTrue(active(hour))
        for hour in (6,22): self.assertFalse(active(hour))
        values['input_datetime.energyhub_climate_quiet_end'] = 'unavailable'
        self.assertFalse(active(23))
        values['input_datetime.energyhub_climate_quiet_end'] = '23:00:00'
        self.assertFalse(active(23))
        dashboard = (ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8')
        self.assertIn('input_number.energyhub_climate_heat_offset', dashboard)
        self.assertIn('0°C', dashboard)

    def test_continuous_solar_request_persists_overnight_and_smart_replaces_it(self):
        self.states['input_select.energyhub_climate_operation'] = 'Continuous'
        self.states['input_select.energyhub_climate_policy'] = 'Solar-only'
        self.states['input_boolean.energyhub_climate_solar_window_enabled'] = 'off'
        for hour in (9, 17, 23, 0, 6):
            self.assertEqual('Solar-only', self.render('energyhub_climate_requested_policy', hour))
        self.states['input_select.energyhub_climate_policy'] = 'Smart'
        self.assertEqual('Smart', self.render('energyhub_climate_requested_policy', 9))

    def test_schedule_fields_are_optional_in_dashboard(self):
        data = json.loads((ROOT/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        view = next(v for v in data['data']['config']['views'] if v['path'] == 'climate-policy')
        windows = [section['cards'][0] for section in view['sections']
                   if section['cards'][0].get('card', {}).get('title') in {'Сонячне вікно', 'Smart вікно'}]
        self.assertEqual(2, len(windows))
        self.assertTrue(all(card['conditions'] == [dict(entity='input_select.energyhub_climate_operation', state='Scheduled')]
                            for card in windows))

    def test_native_app_off_is_distinguished_from_owned_pause(self):
        family = next(row for row in self.data['automation'] if row['id'] == 'energyhub_3_family_off_overrides_schedule')
        template = self.env.from_string(family['conditions'][0]['value_template'])
        trigger = SimpleNamespace(id='manual_state', from_state=SimpleNamespace(state='cool'),
            to_state=SimpleNamespace(context=SimpleNamespace(user_id=None, parent_id=None)))
        def allowed(resume=False, owned=False):
            result = template.render(trigger=trigger,
                state_attr=lambda entity,key: {'owned': {'heat_pump_floor_1': {}}} if key=='cycle' and owned else {},
                is_state=lambda entity,value: resume and entity.endswith('auto_resume'))
            return result.strip()=='True' if isinstance(result,str) else result
        self.assertTrue(allowed())
        self.assertFalse(allowed(resume=True))
        self.assertFalse(allowed(owned=True))
        trigger.from_state.state='unavailable'
        self.assertFalse(allowed())

    def test_owned_pause_beats_inherited_user_context(self):
        family = next(row for row in self.data['automation'] if row['id'] == 'energyhub_3_family_off_overrides_schedule')
        template = self.env.from_string(family['conditions'][0]['value_template'])
        trigger = SimpleNamespace(id='manual_state', from_state=SimpleNamespace(state='heat'),
            to_state=SimpleNamespace(context=SimpleNamespace(user_id='old-context', parent_id=None)))
        for marker in ('auto_resume', 'battery_paused'):
            result=template.render(trigger=trigger,state_attr=lambda *a:{},
                is_state=lambda entity,value: entity.endswith(marker))
            self.assertFalse(result.strip()=='True' if isinstance(result,str) else result)
