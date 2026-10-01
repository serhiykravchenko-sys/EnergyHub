from unittest import TestCase
from types import SimpleNamespace
from tests.test_reserve_hardening import NOW, Client
from app.main import observe_battery_reserve
from app.events import manual_reserve_advice


class ManualReserveTests(TestCase):
    def test_no_target_or_restore_instruction(self):
        reserve = dict(advice_only=True, applied_minimum_soc=60, recommended_soc=40,
                       weather_modifier_percent=20, reason_codes=['uhmc_weather_risk'])
        message = manual_reserve_advice(reserve)
        self.assertIn('60%', message)
        self.assertNotIn('80%', message)
        self.assertNotIn('→', message)
        self.assertIn('недостатньо даних', message)
        self.assertNotIn('+20', message)

    def test_manual_changes_notify_once_without_repeating(self):
        config = SimpleNamespace(weather_buffer_entity='reserve')
        client = Client(dict(advice_only=True, management_mode='manual',
                             applied_minimum_soc=20, weather_modifier_percent=20))
        state = {}
        observe_battery_reserve(config, client, state, NOW)
        client.attributes['applied_minimum_soc'] = 60
        self.assertTrue(observe_battery_reserve(config, client, state, NOW))
        client.attributes['weather_modifier_percent'] = 0
        self.assertFalse(observe_battery_reserve(config, client, state, NOW))
        self.assertEqual(1, len(state['pending_notifications']))
        self.assertIn('20% → 60%', state['pending_notifications'][0]['message'])
