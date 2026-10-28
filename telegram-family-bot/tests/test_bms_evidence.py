from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.bms_evidence import BmsEvidence, parse_mapping, MAX_EVENTS, MAX_SAMPLES


class EvidenceTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'evidence.json'
        self.journal = BmsEvidence(self.path)
        self.now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        self.mapping = {key: 'sensor.'+key for key in ('soc', 'current', 'voltage', 'cells')}

    def observe(self, second, soc=66, current=100, event=None, reported=None):
        when = self.now + timedelta(seconds=second)
        at = (self.now + timedelta(seconds=second if reported is None else reported)).isoformat()
        rows = {self.mapping[k]: {'state': str(v), 'last_reported': at, 'attributes': {}}
                for k, v in dict(soc=soc, current=current, voltage=52, cells=.004).items()}
        rows['sensor.cells']['attributes'] = {'cell_voltages': [3.3]*16, 'private_token': 'never-store'}
        if event:
            rows['sensor.event'] = {'attributes': {'latest_event': event}}
        return self.journal.observe(rows, self.mapping, 'sensor.event', when)

    def test_bms_and_inverter_jumps_capture_once_with_pre_post_cells(self):
        self.observe(0)
        event = {'timestamp': (self.now+timedelta(seconds=30)).isoformat(), 'previous_soc': 66, 'current_soc': 100}
        self.assertTrue(self.observe(30, soc=100, event=event))
        self.assertFalse(self.observe(60, soc=100, event=event))
        self.assertEqual(2, len(self.journal.data['events']))
        for second in range(90, 931, 30):
            self.observe(second, soc=100, event=event)
        for item in self.journal.data['events']:
            self.assertTrue(item['complete'])
            self.assertEqual(self.now.isoformat(), item['samples'][0]['timestamp'])
            self.assertEqual(16, len(item['samples'][0]['readings']['cells']['cell_voltages']))
        self.assertNotIn('never-store', self.path.read_text())

    def test_current_integration_duplicates_gaps_and_restart(self):
        self.observe(0)
        self.observe(30)
        totals = self.journal.data['totals']
        self.assertAlmostEqual(100/120, totals['charge_ah'])
        self.assertAlmostEqual(52*100/120, totals['charge_wh'])
        self.observe(60, reported=30)
        self.assertEqual(30, totals['observed_seconds'])
        self.observe(150)
        self.assertEqual(30, totals['observed_seconds'])
        self.assertEqual(1, totals['gaps'])
        self.journal = BmsEvidence(self.path)
        self.observe(180)
        self.assertEqual(30, self.journal.data['totals']['observed_seconds'])
        self.assertEqual(2, self.journal.data['totals']['gaps'])

    def test_sign_crossing_keeps_charge_and_discharge_separate(self):
        self.observe(0, current=100)
        self.observe(30, current=-100)
        totals = self.journal.data['totals']
        self.assertAlmostEqual(100/480, totals['charge_ah'])
        self.assertAlmostEqual(100/480, totals['discharge_ah'])

    def test_invalid_or_stale_data_never_integrates_or_triggers_jump(self):
        self.observe(0)
        self.observe(300, soc=100, reported=30)
        self.assertFalse(self.journal.data['events'])
        self.assertEqual(0, self.journal.data['totals']['observed_seconds'])
        self.observe(330, current='nan')
        self.assertIsNone(self.journal.data['baseline'])
        self.assertNotIn('NaN', self.path.read_text())

    def test_capture_survives_restart_without_retriggering_event(self):
        self.observe(0)
        event = {'timestamp': (self.now+timedelta(seconds=30)).isoformat()}
        self.observe(30, soc=100, event=event)
        self.journal = BmsEvidence(self.path)
        self.assertFalse(self.observe(60, soc=100, event=event))
        self.assertEqual(2, len(self.journal.data['events']))
        self.observe(930, soc=100)
        self.assertTrue(all(row['complete'] for row in self.journal.data['events']))

    def test_storage_is_bounded_and_corruption_preserved(self):
        for second in range(0, 2100, 30):
            self.observe(second, soc=50 if second % 60 else 100)
        self.assertLessEqual(len(self.journal.data['samples']), MAX_SAMPLES)
        self.assertLessEqual(len(self.journal.data['events']), MAX_EVENTS)
        self.path.write_text('{bad')
        with self.assertRaises(ValueError):
            BmsEvidence(self.path)
        self.assertEqual('{bad', self.path.read_text())

    def test_completed_archive_is_restored_and_not_rewritten(self):
        self.observe(0)
        self.observe(30, soc=100)
        self.observe(930, soc=100)
        archive = next(self.journal.archive_directory.glob('*.json'))
        original = archive.read_bytes()
        modified = archive.stat().st_mtime_ns
        index = json.loads(self.path.read_text())
        self.assertIn('archive', index['events'][0])
        self.journal = BmsEvidence(self.path)
        self.assertEqual(16, len(self.journal.data['events'][0]['samples'][0]['readings']['cells']['cell_voltages']))
        self.observe(960, soc=100)
        self.assertEqual(original, archive.read_bytes())
        self.assertEqual(modified, archive.stat().st_mtime_ns)

    def test_archive_failure_keeps_previous_index_and_is_retryable(self):
        self.observe(0)
        self.observe(30, soc=100)
        original = self.path.read_bytes()
        with patch.object(self.journal, '_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.observe(930, soc=100)
        self.assertEqual(original, self.path.read_bytes())
        self.observe(960, soc=100)
        self.assertTrue(BmsEvidence(self.path).data['events'][0]['complete'])

    def test_mapping_validation(self):
        self.assertEqual(3, len(parse_mapping('soc|sensor.a;current|sensor.b;voltage|sensor.c')))
        for mapping in ('capacity|sensor.a', 'soc|sensor.a;soc|sensor.b', 'unsupported|sensor.x'):
            with self.assertRaises(ValueError):
                parse_mapping(mapping)

    def test_unchanged_current_integrates_only_real_sibling_report_times(self):
        readings={
            'current':dict(value=-10,reported_at=(self.now-timedelta(hours=1)).isoformat()),
            'voltage':dict(value=52,reported_at=self.now.isoformat())}
        self.journal._integrate({'readings':readings},self.now.timestamp())
        readings['voltage']['reported_at']=(self.now+timedelta(seconds=30)).isoformat()
        self.journal._integrate({'readings':readings},self.now.timestamp()+30)
        self.assertAlmostEqual(10/120,self.journal.data['totals']['discharge_ah'])
        self.journal._integrate({'readings':readings},self.now.timestamp()+60)
        self.assertEqual(30,self.journal.data['totals']['observed_seconds'])
        self.journal._integrate({'readings':readings},self.now.timestamp()+121)
        self.assertIsNone(self.journal.data['baseline'])
        self.assertEqual(1,self.journal.data['totals']['gaps'])

    def test_unchanged_soc_baseline_survives_while_packet_siblings_update(self):
        def observe(second,soc,soc_time):
            now=self.now+timedelta(seconds=second)
            rows={self.mapping[k]:dict(state=str(v),last_updated=now.isoformat(),attributes={})
                  for k,v in dict(soc=soc,current=10,voltage=52,cells=.003).items()}
            rows['sensor.soc']['last_updated']=(self.now+timedelta(seconds=soc_time)).isoformat()
            return self.journal.observe(rows,self.mapping,'sensor.event',now)
        for second in (0,60,120,180,240,300,360):
            self.assertFalse(observe(second,66,0))
        self.assertTrue(observe(390,100,390))
        self.assertEqual('bms',self.journal.data['events'][0]['source'])

    def test_snapshot_pipeline_preserves_availability_when_evidence_disk_fails(self):
        from app.main import observe_monitoring
        from app.house_monitor import parse_targets
        config = SimpleNamespace(house_monitor_enabled=True,
            monitored_devices=parse_targets('Heat pump|climate.hp'), smart_plugs=(), environment_sensors=(),
            bms_entities=parse_mapping('soc|sensor.soc;current|sensor.current;voltage|sensor.voltage'),
            telemetry_freshness_entity='sensor.fresh', battery_soc_entity='sensor.inverter_soc',
            grid_voltage_entity='sensor.grid', solar_forecast_entity='sensor.forecast',
            weather_buffer_entity='sensor.reserve', soc_anomaly_latest_entity='sensor.event')
        client = SimpleNamespace(states=lambda: [{'entity_id': 'climate.hp', 'state': 'unavailable'}])
        state = {}
        with patch.object(self.journal, 'save', side_effect=OSError('disk unavailable')):
            observe_monitoring(config, client, state, self.now, self.journal)
        self.assertTrue(state['bms_evidence_status']['error'])
        self.assertIn('device:climate.hp', state['data_incidents'])
        self.assertNotIn('load_water_pump', state['data_incidents'])

    def test_soc_notification_reports_only_confirmed_saved_capture(self):
        from app.main import observe_soc_anomaly
        event = {'timestamp': self.now.isoformat(), 'previous_soc': 66, 'current_soc': 100, 'elapsed_seconds': 11}
        config = SimpleNamespace(soc_anomaly_latest_entity='event', timezone='UTC', bms_entities=(True,))
        client = SimpleNamespace(state=lambda key: {'attributes': {'latest_event': event}})
        for confirmed in (True, False):
            state = {'soc_anomaly_initialized': True, 'soc_anomaly_last_event_id': 'old',
                     'bms_evidence_status': {'event_ids': ['inverter:'+event['timestamp']] if confirmed else []}}
            observe_soc_anomaly(config, client, state, self.now)
            text = state['pending_notifications'][0]['message']
            self.assertIn('Дані BMS збережено' if confirmed else 'не підтверджено', text)
