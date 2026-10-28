"""Offline virtual-clock executor for the prepared HA script action subset.

Runs the actual YAML/templates. It is not a Home Assistant runtime validator.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT/'homeassistant/live/config/packages/energyhub_native_overload.yaml'


class Halt(Exception):
    pass


class Runner:
    def __init__(self):
        self.package = yaml.safe_load(PACKAGE.read_text(encoding='utf-8'))
        self.state = {'automation.energyhub_battery_discharge_protection': 'on', 'input_select.energyhub_overload_phase': 'idle',
                      'input_boolean.energyhub_load_control_armed': 'on',
                      'input_boolean.energyhub_battery_plugs_blocked': 'off',
                      'sensor.powmr_10_2m_load': '90', 'sensor.energyhub_telemetry_freshness':'fresh',
                      'binary_sensor.energyhub_grid_confirmed':'on', 'sensor.powmr_10_2m_grid_voltage':'230',
                      'sensor.powmr_10_2m_battery_soc':'80'}
        self.tasks = {}
        self.commands = []
        self.messages = []
        self.now = 0
        self.env = NativeEnvironment()
        self.env.filters['from_json'] = lambda value, default=None: self.parse(value, default)
        self.env.filters['to_json'] = json.dumps
        self.env.globals.update(states=lambda entity: self.state.get(entity, 'unknown'),
            is_state=lambda entity, value: self.state.get(entity) == value,
            is_number=self.numeric, state_attr=lambda entity, attr: entity,
            expand=lambda entities: [SimpleNamespace(state=self.state.get(e)) for e in entities])
        for entity in self.package['input_text']:
            self.state['input_text.'+entity] = '{}'
        self.plugs = self.package['script']['energyhub_overload_restore']['variables']['plugs']
        for entity in self.plugs.values():
            self.state[entity] = 'on'

    @staticmethod
    def parse(value, default=None):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def numeric(value):
        try:
            import math
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    def render(self, value, context):
        if isinstance(value, str) and ('{{' in value or '{%' in value):
            return self.env.from_string(value).render(**context)
        if isinstance(value, dict):
            return {k: self.render(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [self.render(v, context) for v in value]
        return value

    def conditions(self, rows, context):
        def check(row):
            if row['condition'] == 'state':
                return self.state.get(row['entity_id']) == row['state']
            return bool(self.render(row['value_template'], context))
        return all(check(row) for row in rows)

    def sequence(self, rows, context):
        for row in rows:
            if 'condition' in row:
                if not self.conditions([row], context):
                    raise Halt()
            elif 'variables' in row:
                for key, value in row['variables'].items():
                    context[key] = self.render(value, context)
            elif 'choose' in row:
                for branch in row['choose']:
                    if self.conditions(branch['conditions'], context):
                        yield from self.sequence(branch['sequence'], context)
                        break
            elif 'stop' in row:
                raise Halt()
            elif 'if' in row:
                yield from self.sequence(row.get('then', []) if self.conditions(row['if'], context) else row.get('else', []), context)
            elif 'repeat' in row:
                repeat = row['repeat']
                if 'while' in repeat:
                    while self.conditions(repeat['while'], context):
                        yield from self.sequence(repeat['sequence'], context)
                else:
                    for index, item in enumerate(repeat['for_each']):
                        nested = dict(context, repeat=SimpleNamespace(item=item, index=index+1))
                        yield from self.sequence(repeat['sequence'], nested)
            elif 'wait_template' in row:
                if 'timeout' in row:
                    wait=SimpleNamespace(completed=False)
                    context['wait']=wait
                    raw=self.render(row['timeout'],context)
                    timeout=sum(float(v)*m for v,m in zip(str(raw).split(':'),(3600,60,1))) if ':' in str(raw) else float(raw)
                    yield ('trigger',row['wait_template'],context,self.now+timeout,wait)
                    if not wait.completed and row.get('continue_on_timeout', True) is False:
                        raise Halt()
                else:
                    while not self.render(row['wait_template'], context):
                        yield ('template', row['wait_template'], context)
            elif 'wait_for_trigger' in row:
                timeout = float(self.render(row['timeout'], context))
                wait = SimpleNamespace(completed=False)
                context['wait'] = wait
                yield ('trigger', row['wait_for_trigger'][0]['value_template'], context, self.now+timeout, wait)
            elif 'delay' in row:
                seconds = row['delay'].get('seconds', 0)
                yield ('delay', self.now+seconds)
            elif 'action' in row:
                service = row['action']
                entity = self.render(row.get('target', {}).get('entity_id'), context)
                data = self.render(row.get('data', {}), context)
                if service == 'input_text.set_value':
                    value = data['value']
                    self.state[entity] = value if isinstance(value, str) else json.dumps(value)
                elif service == 'input_select.select_option':
                    self.state[entity] = data['option']
                elif service.startswith('input_boolean.'):
                    self.state[entity] = 'on' if service.endswith('turn_on') else 'off'
                elif service.startswith('switch.'):
                    for target in entity if isinstance(entity, list) else [entity]:
                        self.commands.append((self.now, service, target))
                        self.state[target] = 'on' if service.endswith('turn_on') else 'off'
                elif service == 'notify.send_message':
                    self.messages.append(data['message'])
                elif service == 'script.turn_on':
                    self.start(entity)
                elif service == 'script.turn_off':
                    self.tasks.pop(entity, None)
                    self.state[entity] = 'off'
                elif service.startswith('script.'):
                    script = self.package['script'][service.removeprefix('script.')]
                    yield from self.sequence(script['sequence'], dict(context, **script.get('variables', {})))
                else:
                    raise AssertionError(service)
            else:
                raise AssertionError(row)

    def start(self, entity):
        if entity in self.tasks:
            return
        script = self.package['script'][entity.removeprefix('script.')]
        self.state[entity] = 'on'
        self.tasks[entity] = [self.sequence(script['sequence'], dict(script.get('variables', {}))), None]

    def pump(self):
        for _ in range(100):
            progress = False
            for entity, task in list(self.tasks.items()):
                if self.tasks.get(entity) is not task:
                    continue
                waiting = task[1]
                ready = waiting is None
                if waiting:
                    if waiting[0] == 'delay':
                        ready = self.now >= waiting[1]
                    else:
                        hit = bool(self.render(waiting[1], waiting[2]))
                        ready = hit or (waiting[0] == 'trigger' and self.now >= waiting[3])
                        if waiting[0] == 'trigger':
                            waiting[4].completed = hit
                if not ready:
                    continue
                try:
                    task[1] = next(task[0])
                except (StopIteration, Halt):
                    if self.tasks.get(entity) is task:
                        self.tasks.pop(entity)
                        self.state[entity] = 'off'
                progress = True
            if not progress:
                return
        raise AssertionError('Virtual script loop did not yield')

    def advance(self, seconds):
        for _ in range(seconds):
            self.now += 1
            self.pump()

    def shutdown(self):
        self.start('script.energyhub_overload_shutdown')
        self.pump()

    def load(self, value):
        self.state['sensor.powmr_10_2m_load'] = str(value)
        phase = self.state['input_select.energyhub_overload_phase']
        if self.numeric(value) and (float(value)>85 or (phase == 'restoring' and float(value)>=80)):
            self.shutdown()
        self.pump()

    def restart(self):
        for entity in list(self.tasks):
            self.state[entity] = 'off'
        self.tasks.clear()
        if self.state['input_select.energyhub_overload_phase'] != 'idle':
            self.start('script.energyhub_overload_restore')
        self.pump()
