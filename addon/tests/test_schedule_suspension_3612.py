import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tests import test_normal_base_369 as base_tests
from tests.test_weather_buffer import NOW, daily, samples
from app.services.weather_buffer import WeatherBufferDryRun


def envelope(**changes):
    value = dict(schema=1, region='kyiv_region', source='pro_kyiv',
                 source_status='suspended', validated=False,
                 emergency_notice_active=True, checked_at=NOW.isoformat(),
                 emergency_notice_confirmed_clear=True,
                 dates=[NOW.date().isoformat()])
    value.update(changes)
    return value


class ScheduleSuspensionTests(TestCase):
    def service(self, path=None):
        return base_tests.NormalBaseTests().service(path)

    def test_all_levels_add_twenty_once_and_cap_at_95(self):
        for level, original, target in [('normal',20,40), ('unstable',40,60),
                                         ('risk',60,80), ('panic',80,95)]:
            with self.subTest(level=level):
                service=self.service()
                service.update_grid_confidence(level,NOW)
                self.assertEqual(original,service.status_attributes()['recommended_soc'])
                for _ in range(3):
                    service.update_schedule(json.dumps(envelope()))
                    attrs=service.status_attributes()
                    self.assertEqual(target,attrs['recommended_soc'])
                    self.assertEqual(20,attrs['schedule_suspension_modifier_percent'])
                    self.assertEqual('grid_confidence',attrs['reserve_planning_source'])

    def test_editable_base_and_other_modifiers_are_preserved(self):
        service=self.service()
        service.set_normal_base(45)
        service.update_grid_confidence('unstable',NOW)
        service.update_schedule(envelope())
        self.assertEqual(85,service.status_attributes()['recommended_soc'])
        revised=daily(solar=0,mode='Automatic')
        revised['forecast_plan_stage']='morning'
        service.update(revised,samples(10,10,10))
        self.assertEqual(85,service.status_attributes()['recommended_soc'])

    def test_untrusted_or_merely_unavailable_source_cannot_activate(self):
        for change in [dict(schema=2),dict(region='other'),dict(source='unknown'),
                       dict(checked_at=(NOW-timedelta(hours=1)).isoformat()),
                       dict(source_status='unavailable'),dict(emergency_notice_active=None),
                       dict(emergency_notice_active='true')]:
            with self.subTest(change=change):
                service=self.service();service.update_schedule(envelope(**change))
                self.assertFalse(service.status_attributes()['schedule_suspension_active'])

    def test_latch_survives_missing_stale_and_changed_chart(self):
        service=self.service();service.update_schedule(envelope())
        for value in [None,'invalid',{},envelope(source_status='unknown'),
                      envelope(checked_at=(NOW-timedelta(hours=1)).isoformat()),
                      envelope(source_status='fresh',validated=True,emergency_notice_active=None)]:
            service.update_schedule(value)
            self.assertTrue(service.status_attributes()['schedule_suspension_active'])
        service.update_schedule(envelope(source_status='fresh',validated=True,
                                         emergency_notice_active=False))
        self.assertFalse(service.status_attributes()['schedule_suspension_active'])
        self.assertEqual('dtek_schedule',service.status_attributes()['reserve_planning_source'])

    def test_restart_keeps_modifier_until_confirmed_reinstatement(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'reserve.json'
            service=self.service(path);service.update_schedule(envelope())
            restored=WeatherBufferDryRun(path=path,clock=lambda:NOW)
            restored.update_schedule(None)
            self.assertTrue(restored.status_attributes()['schedule_suspension_active'])
            self.assertEqual(40,restored.status_attributes()['recommended_soc'])

    def test_failed_durable_clear_cannot_lower_reserve(self):
        service=self.service();service.update_grid_confidence('unstable',NOW)
        service.update_schedule(envelope())
        with patch.object(service,'_save',return_value=False):
            service.update_schedule(envelope(source_status='fresh',validated=True,
                                             emergency_notice_active=False))
        self.assertEqual(60,service.status_attributes()['recommended_soc'])

    def test_manual_ownership_still_blocks_automatic_control(self):
        service=self.service()
        service.update(daily(solar=30,mode='Manual'),samples(10,10,10))
        service.update_schedule(envelope())
        self.assertFalse(service.status_attributes()['automatic_control_enabled'])
        self.assertEqual('family',service.status_attributes()['reserve_owner'])
