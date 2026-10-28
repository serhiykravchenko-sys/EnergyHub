import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from app.config import load_config
from app.message_schedule import quiet_phase
from app.main import due_for_report, deliver_pending_notifications
from app import data_incidents


class MessageScheduleTests(TestCase):
    def at(self, clock):
        return datetime.fromisoformat('2026-10-06T'+clock+':00+03:00')

    def test_custom_overnight_window_and_boundaries(self):
        config=SimpleNamespace(send_time='07:30',family_quiet_start='22:00',family_quiet_end='09:00')
        for clock in ('22:00','23:59','00:00','07:29','08:59'):
            self.assertEqual('overnight',quiet_phase(self.at(clock),config))
        for clock in ('07:30','07:31'):
            self.assertEqual('morning_buffer',quiet_phase(self.at(clock),config))
        for clock in ('09:00','21:59'):
            self.assertIsNone(quiet_phase(self.at(clock),config))

    def test_day_window_and_equal_times_disable_quiet(self):
        config=SimpleNamespace(send_time='08:00',family_quiet_start='13:00',family_quiet_end='15:00')
        self.assertIsNone(quiet_phase(self.at('12:59'),config))
        self.assertEqual('overnight',quiet_phase(self.at('13:00'),config))
        self.assertIsNone(quiet_phase(self.at('15:00'),config))
        config.family_quiet_end='13:00'
        self.assertIsNone(quiet_phase(self.at('13:00'),config))

    def test_settings_defaults_custom_times_and_validation(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'options.json'
            path.write_text('{}',encoding='utf-8')
            config=load_config(path)
            self.assertEqual(('08:00','23:00','08:01'),(config.send_time,config.family_quiet_start,config.family_quiet_end))
            path.write_text(json.dumps(dict(send_time='07:30',family_quiet_start='22:15',family_quiet_end='09:00')),encoding='utf-8')
            config=load_config(path)
            self.assertTrue(due_for_report(config,{},self.at('07:30')))
            self.assertEqual('morning_buffer',quiet_phase(self.at('07:30'),config))
            path.write_text(json.dumps(dict(family_quiet_start='24:00')),encoding='utf-8')
            with self.assertRaises(ValueError):load_config(path)

    def test_custom_window_archives_routine_family_message_but_not_personal(self):
        config=SimpleNamespace(send_time='08:00',family_quiet_start='21:00',family_quiet_end='09:00',
                               destination_chat_id='family',technical_chat_id='owner')
        now=self.at('21:30')
        routine=dict(kind='grid_online',message='routine',created_at=now.isoformat())
        personal=dict(kind='technical_test',message='diagnostic',created_at=now.isoformat())
        state=dict(pending_notifications=[routine,personal])
        tg=Mock()
        self.assertTrue(deliver_pending_notifications(config,tg,state,now))
        tg.send_message.assert_called_once_with('owner','diagnostic')
        self.assertEqual([routine],state['overnight_family_events'])

    def test_incident_family_fallback_obeys_quiet_but_personal_does_not(self):
        config=SimpleNamespace(send_time='08:00',family_quiet_start='21:00',family_quiet_end='09:00',
                               destination_chat_id='family',technical_chat_id='')
        now=self.at('21:30')
        stamp=now.timestamp()
        state=dict(data_incidents={'ha':dict(last_seen=stamp,warned=False,bad_since=stamp-600,
                                             recovered_since=None)})
        tg=Mock()
        self.assertFalse(data_incidents.deliver(state,tg,config,now,Mock()))
        tg.send_message.assert_not_called()
        config.technical_chat_id='owner'
        self.assertTrue(data_incidents.deliver(state,tg,config,now,Mock()))
        self.assertEqual('owner',tg.send_message.call_args.args[0])
