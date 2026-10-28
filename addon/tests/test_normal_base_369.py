import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from tests.test_weather_buffer import NOW, daily, samples, weather, RecordingClient
from app.services.weather_buffer import WeatherBufferDryRun
from app.mqtt.publisher import publish_weather_buffer, publish_weather_buffer_discovery

class NormalBaseTests(TestCase):
    def service(self,path=None):
        service=WeatherBufferDryRun(path=path,clock=lambda:NOW)
        service.update(daily(solar=30,mode='Automatic'),samples(10,10,10))
        service.update_weather(weather())
        service.update_grid_confidence('normal',NOW)
        return service

    def test_default_and_all_levels_follow_editable_base(self):
        service=self.service()
        self.assertEqual(20,service.policy_base_soc)
        self.assertTrue(service.set_normal_base('30'))
        for level,target in [('normal',30),('unstable',50),('risk',70),('panic',90)]:
            service.update_grid_confidence(level,NOW)
            self.assertEqual(target,service.status_attributes()['recommended_soc'])
        self.assertEqual({'normal':30,'unstable':50,'risk':70,'panic':90},service.status_attributes()['grid_base_reserves'])

    def test_invalid_and_retained_commands_preserve_setting(self):
        service=self.service();service.set_normal_base(35)
        for value in [0,15,19,21,22.5,96,100,'nan','inf','invalid',True,None]:
            with self.subTest(value=value):
                self.assertFalse(service.set_normal_base(value))
                self.assertEqual(35,service.policy_base_soc)
        self.assertFalse(service.set_normal_base(40,retained=True))
        self.assertEqual(35,service.policy_base_soc)

    def test_ceiling_and_minimum(self):
        service=self.service()
        service.set_normal_base(80)
        self.assertEqual({'normal':80,'unstable':95,'risk':95,'panic':95},service.status_attributes()['grid_base_reserves'])
        service.update_grid_confidence('panic',NOW)
        self.assertEqual(95,service.status_attributes()['recommended_soc'])
        self.assertTrue(service.set_normal_base(20))
        self.assertTrue(service.set_normal_base(95))

    def test_persists_without_daily_inputs_and_recovers_on_restart(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'reserve.json'
            service=WeatherBufferDryRun(path=path,clock=lambda:NOW)
            self.assertTrue(service.set_normal_base(35))
            restored=WeatherBufferDryRun(path=path,clock=lambda:NOW)
            self.assertEqual(35,restored.policy_base_soc)
            self.assertEqual(35,restored.status_attributes()['policy_base_soc'])

    def test_legacy_or_invalid_saved_setting_uses_twenty(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'reserve.json'
            for value in [None,15,22,'nan',True]:
                record=dict(schema_version=2,decision=None,daily_input=None)
                if value is not None:record['policy_base_soc']=value
                path.write_text(json.dumps(record),encoding='utf-8')
                service=WeatherBufferDryRun(path=path,clock=lambda:NOW)
                self.assertEqual(20,service.policy_base_soc)

    def test_failed_persistence_rolls_back_setting_and_recommendation(self):
        with TemporaryDirectory() as directory:
            service=self.service(Path(directory)/'reserve.json')
            old=dict(service.status_attributes())
            with patch('app.services.weather_buffer.atomic_write_json',side_effect=OSError('read only')):
                self.assertFalse(service.set_normal_base(40))
            self.assertEqual(20,service.policy_base_soc)
            self.assertEqual(old,service.status_attributes())

    def test_setting_does_not_take_manual_control_ownership(self):
        service=self.service()
        service.update(daily(solar=30,mode='Manual'),samples(10,10,10))
        self.assertTrue(service.set_normal_base(30))
        attrs=service.status_attributes()
        self.assertEqual('family',attrs['reserve_owner'])
        self.assertFalse(attrs['automatic_control_enabled'])
        self.assertEqual(30,attrs['recommended_soc'])

    def test_schedule_base_respects_selected_floor(self):
        service=self.service();service.set_normal_base(60)
        service.update_schedule(dict(source='pro_kyiv',region='kyiv_region',source_status='fresh',validated=True,
                                     checked_at=NOW.isoformat(),dates=[NOW.date().isoformat()]))
        self.assertEqual('dtek_schedule',service.status_attributes()['reserve_planning_source'])
        self.assertEqual(80,service.status_attributes()['recommended_soc'])

    def test_discovery_state_and_reconnect_publish_confirmed_value(self):
        service=self.service();service.set_normal_base(35)
        client=RecordingClient();publish_weather_buffer_discovery(client);publish_weather_buffer(client,service)
        config=json.loads(next(payload for topic,payload,retain in client.messages if topic=='homeassistant/number/energyhub_normal_reserve/config'))
        self.assertEqual((20,95,5),(config['min'],config['max'],config['step']))
        self.assertFalse(config['optimistic']);self.assertFalse(config['retain'])
        self.assertIn(('energyhub/reserve/normal_base/state','35.0',True),client.messages)
        client.messages.clear();publish_weather_buffer(client,service)
        self.assertIn(('energyhub/reserve/normal_base/state','35.0',True),client.messages)
