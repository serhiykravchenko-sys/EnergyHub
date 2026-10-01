from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.main import poll_uhmc_weather, publish_uhmc_weather_snapshot
from app.uhmc_source import SourcePost


class FakeSource:
    def __init__(self, result=None, error=None):
        self.result = result or []
        self.error = error
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self):
        self.published = []

    def publish_mqtt(self, topic, payload, retain=True):
        self.published.append((topic, payload, retain))


class UhmcAdapterTests(unittest.TestCase):
    def test_mqtt_failure_does_not_hide_source_failure(self):
        from app.uhmc_morning import morning_status, UNKNOWN
        state = {}
        client = FakeClient()
        publish_uhmc_weather_snapshot(self.config, client, FakeSource(), state, self.now)
        def fail(*args, **kwargs):
            raise RuntimeError('mqtt unavailable')
        client.publish_mqtt = fail
        with self.assertRaises(RuntimeError):
            publish_uhmc_weather_snapshot(self.config, client, FakeSource(error=RuntimeError('source offline')),
                                          state, self.now+timedelta(seconds=1))
        self.assertEqual(UNKNOWN, morning_status(state['uhmc_last_snapshot'], self.now+timedelta(seconds=1)))

    def test_morning_snapshot_persists_source_failure(self):
        from app.uhmc_morning import morning_status, CLEAR, UNKNOWN
        state = {}
        client = FakeClient()
        publish_uhmc_weather_snapshot(self.config, client, FakeSource(), state, self.now)
        state = json.loads(json.dumps(state))
        self.assertEqual(CLEAR, morning_status(state['uhmc_last_snapshot'], self.now))
        publish_uhmc_weather_snapshot(self.config, client, FakeSource(error=RuntimeError('offline')),
                                      state, self.now + timedelta(seconds=1))
        self.assertEqual(UNKNOWN, morning_status(state['uhmc_last_snapshot'], self.now + timedelta(seconds=1)))

    def test_superseded_history_survives_later_refresh(self):
        from app.weather_warning import normalize_warning
        wind = SourcePost(channel="uhmc1921", message_id=10,
            text="Попередження. 5 вересня у Києві сильний вітер. I рівень небезпечності.",
            published_at=self.now, url="https://t.me/uhmc1921/10")
        combined = SourcePost(channel="uhmc1921", message_id=11,
            text=wind.text.replace("вітер.", "вітер та гроза."),
            published_at=self.now, url="https://t.me/uhmc1921/11")
        state = {"uhmc_active_warnings": [normalize_warning(wind)]}
        client = FakeClient()
        publish_uhmc_weather_snapshot(self.config, client, FakeSource([combined]), state, self.now)
        self.assertEqual(1, len(state["uhmc_active_warnings"]))
        self.assertEqual(10, state["uhmc_superseded_warnings"][0]["message_id"])
        # State JSON round trip represents restart persistence.
        state = json.loads(json.dumps(state))
        publish_uhmc_weather_snapshot(self.config, client, FakeSource([combined]), state, self.now + timedelta(minutes=6))
        self.assertEqual(1, len(state["uhmc_superseded_warnings"]))

    def setUp(self):
        self.zone = ZoneInfo("Europe/Kyiv")
        self.now = datetime(2026, 9, 5, 10, 0, tzinfo=self.zone)
        self.config = SimpleNamespace(
            timezone="Europe/Kyiv",
            uhmc_weather_mqtt_topic="energyhub/input/weather/uhmc",
        )

    def test_publishes_fresh_evidence_and_throttles_unchanged_snapshot(self):
        source = FakeSource([
            SourcePost(
                channel="uhmc1921",
                message_id=1,
                text="Попередження. 5 вересня у Київській області гроза. II рівень небезпечності.",
                published_at=self.now,
                url="https://t.me/uhmc1921/1",
            )
        ])
        client = FakeClient()
        state = {}
        self.assertTrue(publish_uhmc_weather_snapshot(self.config, client, source, state, self.now))
        self.assertEqual(client.published[0][0], "energyhub/input/weather/uhmc")
        self.assertEqual(client.published[0][1]["source_status"], "fresh")
        self.assertFalse(
            publish_uhmc_weather_snapshot(
                self.config,
                client,
                source,
                state,
                self.now + timedelta(seconds=30),
            )
        )

    def test_source_failure_publishes_unknown_without_erasing_active_state(self):
        state = {"uhmc_active_warnings": [{"event_id": "kept"}]}
        client = FakeClient()
        source = FakeSource(error=RuntimeError("offline"))
        self.assertTrue(publish_uhmc_weather_snapshot(self.config, client, source, state, self.now))
        self.assertEqual(client.published[0][1]["source_status"], "unknown")
        self.assertEqual(state["uhmc_active_warnings"], [{"event_id": "kept"}])

    def test_hourly_poll_retries_once_then_warns_once(self):
        state = {}
        client = FakeClient()
        source = FakeSource(error=RuntimeError("offline"))
        self.assertTrue(poll_uhmc_weather(self.config, client, source, state, self.now))
        self.assertEqual(1, source.calls)
        self.assertFalse(poll_uhmc_weather(
            self.config, client, source, state, self.now + timedelta(minutes=4)
        ))
        self.assertEqual(1, source.calls)
        self.assertTrue(poll_uhmc_weather(
            self.config, client, source, state, self.now + timedelta(minutes=5)
        ))
        self.assertEqual(2, source.calls)
        self.assertEqual("uhmc_source_unavailable", state["pending_notifications"][0]["kind"])
        self.assertFalse(poll_uhmc_weather(
            self.config, client, source, state, self.now + timedelta(minutes=59)
        ))

    def test_successful_retry_clears_failure_without_warning(self):
        state = {}
        client = FakeClient()
        source = FakeSource(error=RuntimeError("offline"))
        poll_uhmc_weather(self.config, client, source, state, self.now)
        source.error = None
        poll_uhmc_weather(self.config, client, source, state, self.now + timedelta(minutes=5))
        self.assertFalse(state["uhmc_retry_pending"])
        self.assertFalse(state["uhmc_source_warning_active"])
        self.assertFalse(state.get("pending_notifications"))


if __name__ == "__main__":
    unittest.main()
