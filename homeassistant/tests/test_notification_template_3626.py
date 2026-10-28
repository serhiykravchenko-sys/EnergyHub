"""HA-side template validation, separate from the messaging app runtime image."""
import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('notification_discovery',ROOT/'telegram-family-bot/app/automation_notifications.py')
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class TemplateTests(unittest.TestCase):
    def test_native_command_template_preserves_message_and_stable_invocation_id(self):
        root,configs=bridge.discovery('test-installation')
        cfg=next(c for c in configs.values() if 'command_topic' in c)
        env=Environment();env.filters['to_json']=json.dumps
        now=datetime(2026,10,22,17,35,tzinfo=timezone.utc)
        rendered=env.from_string(cfg['command_template']).render(value='Fridge "off"\n20%',now=lambda:now)
        value=json.loads(rendered)
        self.assertEqual('Fridge "off"\n20%',value['message'])
        self.assertEqual(value['created_at'],value['id'])
        self.assertEqual(now.isoformat(),value['created_at'])
        self.assertEqual(1,value['schema'])
        self.assertFalse(cfg['retain'])
        self.assertEqual(root+'/request',cfg['command_topic'])
        self.assertNotIn('chat_id',cfg['command_template'])
