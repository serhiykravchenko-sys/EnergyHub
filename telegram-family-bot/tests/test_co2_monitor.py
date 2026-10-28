import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from app import co2_monitor


class Co2Tests(unittest.TestCase):
    def test_history_maximum_rejects_invalid_and_out_of_window_samples(self):
        def sample(value, hours=0, entity='sensor.co2'):
            return dict(entity_id=entity, state=str(value),
                        last_updated=(self.now-timedelta(hours=hours)).isoformat())
        history = [[sample(1100, 23), sample(800), sample(3000, 25),
                    sample(4000, -1), sample('nan'), sample(5100),
                    sample(4900, entity='sensor.other'),
                    dict(entity_id='sensor.co2', state='4000', last_updated='2026-10-04T08:00:00')]]
        self.assertEqual({'sensor.co2': 1100}, co2_monitor.history_maxima([self.target], history, self.now))
    def setUp(self):
        self.now = datetime(2026, 10, 4, 9, tzinfo=timezone.utc)
        self.state = {}
        self.target = SimpleNamespace(entity='sensor.co2', label='Room <1>', parent='')
        self.messages = []
        self.telegram = SimpleNamespace(send_message=lambda chat, text: self.messages.append(text))

    def sample(self, ppm, seconds, age=0):
        when = self.now+timedelta(seconds=seconds)
        row = {'state': str(ppm), 'last_updated': (when-timedelta(seconds=age)).isoformat()}
        co2_monitor.observe(self.state, [self.target], {'sensor.co2': row}, when)
        return when

    def hold(self, ppm, start, end):
        for seconds in range(start, end+1, 30):
            self.sample(ppm, seconds)

    def send(self, seconds, quiet=False):
        return co2_monitor.deliver(self.state, self.telegram, 'test',
            self.now+timedelta(seconds=seconds), quiet)

    def test_advisory_escalation_recovery_and_deduplication(self):
        self.hold(1200, 0, 570)
        self.assertFalse(self.send(570))
        self.sample(1200, 600)
        self.assertTrue(self.send(600))
        self.assertIn('Room &lt;1&gt;', self.messages[-1])
        self.hold(2000, 630, 810)
        self.assertTrue(self.send(810, quiet=True))
        self.assertIn('зараз', self.messages[-1])
        self.assertFalse(self.send(810))
        self.hold(999, 840, 1110)
        self.assertFalse(self.send(1110))
        self.sample(999, 1140)
        self.assertTrue(self.send(1140))
        self.assertEqual(len(self.messages), 3)

    def test_short_spike_invalid_values_and_unobserved_gap(self):
        self.hold(2000, 0, 150)
        self.sample('unavailable', 180)
        self.assertFalse(self.send(180))
        self.hold(2000, 210, 360)
        self.sample(2000, 480)
        self.assertFalse(self.send(480))
        self.sample(2000, 510, age=200)
        self.assertFalse(self.send(510))

    def test_retry_and_quiet_hours(self):
        self.hold(1300, 0, 600)
        self.assertFalse(self.send(600, quiet=True))
        failing = SimpleNamespace(send_message=lambda *args: (_ for _ in ()).throw(OSError('offline')))
        with self.assertRaises(OSError):
            co2_monitor.deliver(self.state, failing, 'test', self.now+timedelta(seconds=600))
        self.assertEqual(self.state['co2_monitor']['sensor.co2']['delivered'], 0)
        self.assertTrue(self.send(600))

    def test_parent_off_and_removed_inventory(self):
        self.target.parent = 'binary_sensor.bridge'
        self.hold(2100, 0, 600)
        self.assertFalse(self.send(600))
        co2_monitor.observe(self.state, [], {}, self.now+timedelta(seconds=630))
        self.assertEqual(self.state['co2_monitor'], {})

    def test_unsent_urgent_is_not_replayed_after_gap_with_low_current_reading(self):
        self.hold(2200, 0, 180)
        self.sample(800, 600)
        self.assertFalse(self.send(600))
        self.hold(800, 630, 900)
        self.assertFalse(self.send(900))

    def test_recovery_requires_new_full_window_after_gap(self):
        self.hold(2200, 0, 180)
        self.assertTrue(self.send(180))
        self.sample(800, 600)
        self.assertFalse(self.send(600))
        self.hold(800, 630, 900)
        self.assertTrue(self.send(900))
