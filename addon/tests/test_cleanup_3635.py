import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.peak_load_control import PeakLoadGuardController, ORDER, LEGACY_LOAD_KEYS
from app.mqtt.publisher import publish_daily_summary


class CleanupTests(unittest.TestCase):
    def test_one_hp_snapshot_and_old_six_participant_snapshot_are_accepted(self):
        guard=PeakLoadGuardController(lambda _:None,path=None)
        for second,keys in enumerate([LEGACY_LOAD_KEYS,ORDER],1):
            payload=dict(control_schema=6,observed_at=f'2026-10-26T12:00:0{second}+00:00',
                         bridge_session='boot',hp1_battery_control_ready=True,
                         loads=[dict(key=k,state='off') for k in keys])
            self.assertTrue(guard.update_load_snapshot(payload))
            self.assertEqual({'heat_pump_floor_1'},set(guard.loads))
        self.assertFalse(guard.update_load_snapshot(dict(payload,observed_at='2026-10-26T12:00:03+00:00',loads=[])))

    def test_legacy_journal_keeps_hp_ownership_without_any_start_command(self):
        sent=[]
        owner=dict(original={'state':'on','settings':{}},context_id='old',intent_revision=1,
                   confirmed_off_at='2026-10-26T12:00:00+00:00',reason='battery')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'journal.json'
            path.write_text(json.dumps(dict(schema=1,stream_id='prior',sequence=1,events=[],pending=None,
                cycle=dict(cycle_id='cycle',owned={'heat_pump_floor_1':owner,'water_boiler':dict(owner,reason='overload')},
                           blocked={},shed=[],restored=[],settle_until=0),
                hp1_battery=dict(active=True,attempted=['heat_pump_floor_1'],locked=True,warned=True))))
            guard=PeakLoadGuardController(sent.append,path=path)
            self.assertIsNone(guard.fault)
            self.assertEqual({'heat_pump_floor_1'},set(guard.cycle['owned']))
            self.assertFalse(sent)

    def test_non_hp_devices_still_fail_command_boundary(self):
        guard=PeakLoadGuardController(lambda _:None,path=None)
        for key in LEGACY_LOAD_KEYS:
            if key!='heat_pump_floor_1':
                with self.assertRaises(ValueError):
                    guard._command(key,'shed',datetime.now(timezone.utc),reason='battery')

    def test_old_bridge_mixed_manual_intent_keeps_only_hp1_evidence(self):
        guard=PeakLoadGuardController(lambda _:None,path=None)
        self.assertTrue(guard.update_intent(dict(context_id='family',keys=list(LEGACY_LOAD_KEYS))))
        self.assertEqual(['heat_pump_floor_1'],guard.intents[-1]['keys'])
        self.assertFalse(guard.update_intent(dict(context_id='family',keys=['water_boiler'])))

    def test_daily_forecast_history_is_bounded_and_contains_no_arbitrary_fields(self):
        client=Mock()
        rows={f'2026-{1+i//28:02d}-{1+i%28:02d}':dict(solar_forecast_kwh=5,solar_actual_kwh=6,
                 battery_full=False,private='not exported') for i in range(90)}
        summary=SimpleNamespace(last_snapshot={'date':'2026-10-25'},history=rows,mqtt_values=lambda:{})
        publish_daily_summary(client,summary)
        attributes=json.loads(client.publish.call_args_list[0].args[1])
        self.assertEqual(70,len(attributes['history']))
        self.assertNotIn('private',json.dumps(attributes))
