"""Saved-state recovery avoids duplicate ON requests and success claims."""
import unittest
from native_overload_fixture import Runner

class NoopTests(unittest.TestCase):
    def setUp(self):
        self.r=Runner();self.r.state['sensor.powmr_10_2m_load']='20'
    def run_script(self,name):
        self.r.start('script.'+name);self.r.pump()
    def test_repeated_recovery_does_not_command_or_notify_all_on(self):
        for _ in range(20):self.run_script('energyhub_battery_restore_saved')
        self.assertFalse(self.r.commands);self.assertFalse(self.r.messages)
    def test_repeated_low_soc_does_not_command_or_notify_all_off(self):
        for entity in self.r.plugs.values():self.r.state[entity]='off'
        for _ in range(20):self.run_script('energyhub_battery_save_and_stop')
        self.assertFalse(self.r.commands);self.assertFalse(self.r.messages)
    def test_mixed_states_restore_only_originally_on(self):
        boiler=self.r.plugs['water_boiler'];self.r.state[boiler]='off'
        self.run_script('energyhub_battery_save_and_stop')
        self.r.state['input_boolean.energyhub_battery_plugs_blocked']='off'
        self.run_script('energyhub_battery_restore_saved')
        ons={e for _,action,e in self.r.commands if action=='switch.turn_on'}
        self.assertEqual(set(self.r.plugs.values())-{boiler,self.r.plugs['microwave']},ons)
    def test_unavailable_is_not_guessed_as_on(self):
        import json
        for entity in self.r.plugs.values():self.r.state[entity]='unavailable'
        self.run_script('energyhub_battery_save_and_stop')
        saved=json.loads(self.r.state['input_text.energyhub_battery_plug_saved'])
        self.assertFalse(any(saved.values()))
    def test_messages_describe_requests(self):
        self.run_script('energyhub_battery_save_and_stop')
        self.assertIn('Надіслано команду',self.r.messages[0])
