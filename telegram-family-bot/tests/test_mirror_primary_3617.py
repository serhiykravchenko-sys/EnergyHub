import unittest
from unittest.mock import patch
import test_schedule_sources as fixture
from app import schedule_sources as sources


class MirrorTests(unittest.TestCase):
    def test_retired_official_setting_cannot_enable_official_requests(self):
        bodies={sources.URLS['pro_kyiv']:fixture.pro(),sources.URLS['alerts_energy']:fixture.alerts()}
        with patch.object(sources,'fetch',side_effect=lambda url,deadline:bodies[url]) as fetch:
            result=sources.read_snapshot(fixture.NOW,official_trial=True)
        self.assertEqual('pro_kyiv',result['source'])
        self.assertEqual(set(bodies),{c.args[0] for c in fetch.call_args_list})
        self.assertNotIn('dtek_official',result['source_failures'])
        self.assertNotIn('official_trial',result)

    def test_primary_failure_uses_alerts_and_records_only_active_source_failures(self):
        with patch.object(sources,'fetch',side_effect=lambda url,deadline:
                          fixture.alerts() if url==sources.URLS['alerts_energy'] else 'blocked'):
            result=sources.read_snapshot(fixture.NOW)
        self.assertEqual('alerts_energy',result['source'])
        self.assertEqual({'pro_kyiv'},set(result['source_failures']))

    def test_official_url_is_not_an_allowed_transport(self):
        with self.assertRaises(ValueError):
            sources.fetch(sources.URLS['dtek_official'],0)

    def test_retired_diagnostics_do_not_create_false_recovery_or_stale_warning(self):
        state=dict(schedule_source_failures={'dtek_official':'access_challenge','pro_kyiv':'offline'},
                   pending_notifications=[dict(kind='technical_dtek_sources',message='Офіційний сайт ДТЕК blocked'),
                                          dict(kind='grid_lost',message='grid offline')])
        sources.retire_official_state(state)
        self.assertEqual({'pro_kyiv':'offline'},state['schedule_source_failures'])
        self.assertEqual(['grid_lost'],[item['kind'] for item in state['pending_notifications']])
