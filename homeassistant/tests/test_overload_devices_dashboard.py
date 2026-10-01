import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from jinja2 import Environment
from test_presentation import contents


class OverloadDevicesTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2]
        data = json.loads((root/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        source = next(x for x in contents(data) if '| Device · switching order |' in x)
        self.template = Environment().from_string(source)
        self.now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
        self.attrs = dict(load_snapshot_at=self.now.isoformat(), participants=[])

    def render(self):
        def stamp(value, default=0):
            try:
                return (value if isinstance(value, datetime) else datetime.fromisoformat(value)).timestamp()
            except (ValueError, TypeError):
                return default
        return self.template.render(now=lambda:self.now, as_timestamp=stamp,
                                    state_attr=lambda entity,key:self.attrs.get(key))

    def test_six_in_order_and_native_measurement(self):
        output = self.render()
        names = ['Water pump', 'Water boiler', 'First-floor heat pump · native',
                 'Second-floor heat pump', 'Third-floor heat pump', 'Microwave']
        self.assertEqual(sorted(output.index(x) for x in names), [output.index(x) for x in names])
        self.assertEqual(6, output.count('Unknown / —'))
        self.assertNotIn('0 W', output)
        self.assertIn('smart plug stays powered', output)
        table = output[output.index('| Device · switching order |'):].split('\n\n')[0]
        self.assertEqual(8, len(table.splitlines()))

    def test_native_not_ready_distinct_from_power(self):
        self.attrs['participants'] = [dict(key='heat_pump_floor_1', state='on', power_w=1020,
            power_observed_at=self.now.isoformat(), control_ready=False, context_id='a', intent_revision=1)]
        output = self.render()
        self.assertIn('On / 1020 W | Native checks pending', output)
        self.attrs['participants'][0]['control_ready'] = True
        self.assertIn('On / 1020 W | Ready', self.render())

    def test_stale_snapshot_keeps_last_power_visible_and_marks_checks(self):
        self.attrs['load_snapshot_at'] = '2026-09-08T11:58:00+00:00'
        self.attrs['participants'] = [dict(key='water_pump', state='on', power_w=1000,
            power_observed_at=self.now.isoformat(), control_ready=True)]
        output = self.render()
        self.assertIn('On / 1000 W', output)
        self.assertIn('Snapshot stale', output)

    def test_old_unchanged_power_does_not_claim_online_device_is_stale(self):
        self.attrs['participants'] = [dict(
            key='heat_pump_floor_2', state='on', power_w=1,
            power_observed_at='2026-09-08T09:00:00+00:00',
            availability='online', control_ready=True,
            context_id='a', intent_revision=1,
        )]
        output = self.render()
        self.assertIn('On / 1 W | Ready · power unchanged', output)
        self.assertNotIn('Power stale', output)

    def test_zigbee_availability_is_explicit_and_fails_closed(self):
        base = dict(key='heat_pump_floor_2', state='on', power_w=1,
            power_observed_at=self.now.isoformat(), control_ready=False,
            context_id='a', intent_revision=1)
        self.attrs['participants'] = [dict(base, availability='unknown')]
        self.assertIn('Availability unknown', self.render())
        self.attrs['participants'] = [dict(base, availability='offline')]
        self.assertIn('Device offline', self.render())
