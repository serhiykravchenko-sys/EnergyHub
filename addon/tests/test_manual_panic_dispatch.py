"""Exercise the real request dispatcher without inverter I/O."""
import ast
import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def function(name, context):
    tree=ast.parse((Path(__file__).parents[1]/'app/main.py').read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    class Localize(ast.NodeTransformer):
        def visit_Nonlocal(self,node):
            return None
    node=Localize().visit(node)
    module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    exec(compile(module,'main-dispatch','exec'),context)
    return context[name]


class DispatchTests(unittest.TestCase):
    def context(self,active=True):
        controller=SimpleNamespace(manual_panic_active=active,mode='panic_grid_hold',last_error=None)
        def owner(value):
            controller.manual_panic_active=value
            return True
        controller.set_manual_panic=Mock(side_effect=owner)
        controller.set_panic_target_soc=Mock(return_value=True)
        controller.restore_solar=Mock(return_value=True)
        controller.enter_panic=Mock(return_value=True)
        controller.enter_panic_grid_hold=Mock(return_value=True)
        context=dict(queue=queue,mode_requests=queue.Queue(maxsize=1),mode_request_lock=threading.Lock(),
            autopilot=SimpleNamespace(is_enabled=lambda:True),inverter_controller=controller,
            log=Mock(),publish_controller_state=Mock(),PANIC_DEFAULT_TARGET_SOC=95)
        return context,controller

    def test_manual_queue_intent_cannot_be_replaced_by_automatic(self):
        context,_=self.context()
        request=function('queue_mode_request',context)
        request('panic',origin='manual')
        self.assertFalse(request('solar'))
        self.assertEqual('manual',context['mode_requests'].get()['origin'])

    def test_uncertain_strategy_safe_recovery_retains_priority(self):
        context,_=self.context()
        request=function('queue_mode_request',context)
        request('panic',origin='manual')
        request('safe_solar')
        self.assertFalse(request('panic',origin='manual'))
        self.assertEqual('safe_solar',context['mode_requests'].get()['mode'])

    def test_automatic_solar_cannot_cancel_manual_panic(self):
        context,controller=self.context()
        context['mode_requests'].put(dict(mode='solar',origin='automatic'))
        function('process_mode_request',context)()
        controller.restore_solar.assert_not_called()
        self.assertTrue(controller.manual_panic_active)

    def test_auto_charging_request_cannot_lower_manual_target(self):
        context,controller=self.context()
        context['mode_requests'].put(dict(mode='panic',target_soc=40,origin='automatic'))
        function('process_mode_request',context)()
        controller.set_panic_target_soc.assert_called_once_with(95)

    def test_manual_cancellation_requires_confirmed_solar(self):
        for success in (False,True):
            context,controller=self.context()
            controller.restore_solar.return_value=success
            context['mode_requests'].put(dict(mode='solar',origin='manual'))
            function('process_mode_request',context)()
            self.assertEqual(not success,controller.manual_panic_active)
