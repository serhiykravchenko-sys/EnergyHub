import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from app import grid_use


class GridUseTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 3, 23, 59, tzinfo=timezone.utc)
        self.state = {}
        self.values = [12.0, 20.0]
        self.client = SimpleNamespace(state=lambda key: {
            'state': self.values[grid_use.COUNTERS.index(key)],
            'attributes': {'unit_of_measurement': 'kWh'},
            'last_reported': self.now.isoformat()})

    def tick(self, seconds=30, fresh=True, grid=True):
        self.now += timedelta(seconds=seconds)
        grid_use.observe(self.state, self.client, self.now, fresh=fresh, grid_online=grid)

    def test_midnight_restart_and_reentry_keep_original_baseline(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        start = self.state['grid_use_episode']['started_at']
        self.values = [12.3, 20.1]
        self.tick()
        self.state = copy.deepcopy(self.state)
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.values = [12.5, 20.4]
        self.tick()
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertEqual(start, episode['started_at'])
        self.assertTrue(episode['complete'])
        self.assertIn('≈ 0,90 кВт·год', '\n'.join(lines))
        self.assertIn('23:59', '\n'.join(lines))
        self.assertNotIn('grid_use_episode', self.state)

    def test_startup_mid_episode_never_invents_historical_start(self):
        grid_use.begin(self.state, self.client, self.now)
        self.values = [13, 21]
        self.tick()
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertFalse(episode['complete'])
        self.assertIn('Початок використання ДТЕК невідомий', '\n'.join(lines))
        self.assertIn('Імпорт за весь період невідомий', '\n'.join(lines))

    def test_gap_stale_reset_and_interruption_are_not_full_energy(self):
        for case in ('gap', 'stale', 'reset'):
            with self.subTest(case=case):
                self.state = {}
                self.values = [12, 20]
                grid_use.begin(self.state, self.client, self.now, started_at=self.now)
                if case == 'reset':
                    self.values = [0, 20]
                self.tick(seconds=91 if case == 'gap' else 30, fresh=case != 'stale')
                lines, episode = grid_use.finish(self.state, self.now)
                self.assertFalse(episode['complete'])
                self.assertNotIn('імпортовано ≈', '\n'.join(lines))

    def test_known_grid_outage_marks_elapsed_interval(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.tick(grid=False)
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertTrue(episode['interrupted'])
        self.assertNotIn('із перебоями', '\n'.join(lines))

    def test_telemetry_loss_does_not_claim_grid_outage(self):
        for pause in (False, True):
            with self.subTest(pause=pause):
                self.state = {}
                grid_use.begin(self.state, self.client, self.now, started_at=self.now)
                if pause:
                    grid_use.pause(self.state)
                else:
                    self.tick(fresh=False, grid=False)
                lines, episode = grid_use.finish(self.state, self.now)
                self.assertFalse(episode['complete'])
                self.assertIn('неповні дані', '\n'.join(lines))
                self.assertNotIn('перебоями мережі', '\n'.join(lines))

    def test_legacy_interruption_is_not_proof_of_grid_outage(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        episode = self.state['grid_use_episode']
        episode.pop('grid_outage')
        episode.pop('data_gap')
        episode.update(interrupted=True, complete=False)
        lines, _ = grid_use.finish(self.state, self.now)
        self.assertIn('неповні дані', '\n'.join(lines))
        self.assertNotIn('перебоями мережі', '\n'.join(lines))

    def test_invalid_or_stale_counter_does_not_validate(self):
        for value in ('nan', 'inf', '-1', 'unavailable'):
            self.values[0] = value
            self.assertIsNone(grid_use.totals(self.client, self.now))
        self.values = [12, 20]
        self.assertEqual([12, 20], grid_use.totals(self.client, self.now+timedelta(hours=12)))

    def test_summary_is_frozen_for_delivery_retry(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.values = [13, 20]
        self.tick()
        lines, episode = grid_use.finish(self.state, self.now)
        snapshot = copy.deepcopy(lines)
        self.values = [99, 99]
        self.tick()
        self.assertEqual(snapshot, lines)
        self.assertEqual(1, episode['kwh'])

    def test_malformed_persisted_counter_does_not_produce_energy(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.state['grid_use_episode']['kwh'] = 'nan'
        self.tick()
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertTrue(episode['complete'])
        self.assertEqual(0, episode['kwh'])

    def history(self, start, end, entities):
        groups = []
        for entity in entities:
            rows = []
            steps = int((end-start).total_seconds() // 60)
            for step in range(steps+1):
                stamp = start + timedelta(seconds=60*step)
                value = 'fresh' if entity == 'sensor.freshness' else str(12+step*.1 if entity == grid_use.COUNTERS[0] else 20)
                # HA can omit unchanged reports for the inactive tariff.
                if entity == grid_use.COUNTERS[1] and step:
                    continue
                rows.append(dict(entity_id=entity, state=value,
                                 last_updated=stamp.isoformat(),
                                 attributes={'unit_of_measurement': 'kWh'}))
            groups.append(rows)
        return groups

    def test_monitoring_restart_recovers_shared_counter_delta(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        grid_use.pause(self.state)
        self.state = copy.deepcopy(self.state)
        self.client.import_history = self.history
        self.now += timedelta(minutes=5)
        self.values = [12.5, 20]
        grid_use.observe(self.state, self.client, self.now, fresh=True,
                         grid_online=True, freshness_entity='sensor.freshness')
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertTrue(episode['complete'])
        self.assertIn('імпортовано ≈ 0,50', '\n'.join(lines))
        self.assertNotIn('прогалини', '\n'.join(lines))

    def test_missing_history_keeps_counter_estimate_explicitly_incomplete(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.values = [12.5, 20]
        self.tick(seconds=300)
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertFalse(episode['complete'])
        self.assertIn('≈ 0,50 кВт·год — неповна оцінка', '\n'.join(lines))

    def test_producer_gap_never_becomes_complete_after_recovery(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.tick(fresh=False)
        self.client.import_history = self.history
        self.values = [12.5, 20]
        self.tick()
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertFalse(episode['complete'])
        self.assertIn('неповна оцінка', '\n'.join(lines))

    def test_hidden_counter_reset_or_producer_staleness_rejects_history(self):
        start = self.now
        end = start+timedelta(minutes=5)
        for case in ('reset', 'stale', 'sparse', 'missing'):
            rows = self.history(start, end, (*grid_use.COUNTERS, 'sensor.freshness'))
            if case == 'reset':
                rows[0][2]['state'] = '0'
            elif case == 'stale':
                rows[2][2]['state'] = 'stale'
            elif case == 'sparse':
                rows[0] = [rows[0][0], rows[0][-1]]
            else:
                rows.pop()
            self.client.import_history = lambda *args: rows
            self.assertEqual(case == 'sparse', grid_use.history_continuous(self.client, start, end, 'sensor.freshness'), case)

    def test_history_fetch_is_bounded_and_read_only(self):
        from app.home_assistant import HomeAssistantClient
        client = HomeAssistantClient(token='test')
        paths = []
        client._request = lambda path: paths.append(path) or []
        self.assertEqual([], client.import_history(self.now, self.now+timedelta(hours=8), grid_use.COUNTERS))
        self.assertIn('filter_entity_id=', paths[0])
        self.assertIn('/history/period/', paths[0])
        self.assertIsNone(client.import_history(self.now, self.now+timedelta(hours=49), grid_use.COUNTERS))
        self.assertEqual(1, len(paths))

    def test_hidden_reset_does_not_display_a_counter_delta(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        def reset_history(start, end, entities):
            rows = self.history(start, end, entities)
            rows[0][2]['state'] = '0'
            return rows
        self.client.import_history = reset_history
        self.now += timedelta(minutes=5)
        self.values = [12.5, 20]
        grid_use.observe(self.state, self.client, self.now, fresh=True,
                         grid_online=True, freshness_entity='sensor.freshness')
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertTrue(episode['counter_reset'])
        self.assertIn('Імпорт за весь період невідомий', '\n'.join(lines))

    def test_history_failure_is_incomplete_and_not_retried_each_poll(self):
        from app.home_assistant import HomeAssistantError
        calls = []
        def fail(*args):
            calls.append(args)
            raise HomeAssistantError('unavailable')
        self.client.import_history = fail
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        grid_use.pause(self.state)
        for _ in range(3):
            self.now += timedelta(seconds=30)
            grid_use.observe(self.state, self.client, self.now, fresh=True,
                             grid_online=True, freshness_entity='sensor.freshness')
        self.assertEqual(1, len(calls))
        self.assertFalse(self.state['grid_use_episode']['complete'])

    def test_legacy_episode_without_baseline_is_not_reconstructed(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.state['grid_use_episode'].pop('baseline_counters')
        self.values = [13, 20]
        self.tick(seconds=300)
        lines, _ = grid_use.finish(self.state, self.now)
        self.assertIn('Імпорт за весь період невідомий', '\n'.join(lines))

    def test_known_start_missing_baseline_recovers_change_only_history(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now,
                       baseline={'counters': None, 'sampled_at': self.now.isoformat()})
        self.client.import_history = self.history
        self.now += timedelta(minutes=5)
        self.values = [12.5, 20]
        grid_use.observe(self.state, self.client, self.now, fresh=True, grid_online=True,
                         freshness_entity='sensor.freshness')
        lines, episode = grid_use.finish(self.state, self.now)
        self.assertTrue(episode['complete'])
        self.assertEqual([12, 20], episode['baseline_counters'])
        self.assertIn('≈ 0,50', ' '.join(lines))

    def test_post_start_history_cannot_invent_start_counters(self):
        start, end = self.now, self.now+timedelta(minutes=5)
        rows = self.history(start, end, (*grid_use.COUNTERS, 'sensor.freshness'))
        rows[0].pop(0)
        self.client.import_history = lambda *args: rows
        self.assertFalse(grid_use.history_continuous(self.client, start, end, 'sensor.freshness'))

    def test_unknown_grid_with_fresh_counters_does_not_record_outage(self):
        grid_use.begin(self.state, self.client, self.now, started_at=self.now)
        self.tick(grid=None)
        self.assertFalse(self.state['grid_use_episode']['grid_outage'])
