from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from zoneinfo import ZoneInfo

from app.main import observe_peak_load_guard, observe_battery_reserve
from app.report import build_report
from app.uhmc_source import SourcePost, TelegramPreviewParser
from app.weather_warning import build_warning_snapshot, normalize_warning


NOW = datetime(2026, 9, 6, 10, tzinfo=ZoneInfo("Europe/Kyiv"))


class Client:
    def __init__(self, attributes):
        self.attributes = attributes

    def state(self, entity):
        return {"state": "normal", "attributes": self.attributes}


def event(sequence, kind):
    return {"event_id": f"peak-load-{sequence}", "sequence": sequence,
            "stream_id": "stream-a", "cycle_id": "cycle-a", "type": kind,
            "load_percent": 90, "mode": "warnings_only",
            "thresholds": {"shed_percent": 85, "relief_percent": 75, "restore_percent": 60}}


class EventDeliveryTests(TestCase):
    def test_poll_drains_all_events_and_legacy_migration_does_not_replay(self):
        events = [event(1, "load_warning"), event(2, "load_warning_cleared"),
                  event(3, "load_warning"), event(4, "load_warning_cleared")]
        client = Client({"event": events[-1], "events": events})
        state = {"peak_load_guard_last_event_id": "peak-load-2"}
        config = SimpleNamespace(peak_load_guard_event_entity="guard")
        self.assertTrue(observe_peak_load_guard(config, client, state, NOW))
        self.assertEqual(["peak_load_guard_load_warning", "peak_load_guard_load_warning_cleared"],
                         [item["kind"] for item in state["pending_notifications"]])
        self.assertFalse(observe_peak_load_guard(config, client, state, NOW))
        self.assertEqual(2, len(state["pending_notifications"]))

    def test_new_stream_reuses_sequence_without_losing_event(self):
        config = SimpleNamespace(peak_load_guard_event_entity="guard")
        state = {}
        first = event(1, "load_warning")
        client = Client({"event": first})
        observe_peak_load_guard(config, client, state, NOW)
        client.attributes = {"event": dict(first, stream_id="stream-b")}
        self.assertTrue(observe_peak_load_guard(config, client, state, NOW))

    def test_reserve_quiet_hours_and_target_deduplication(self):
        config = SimpleNamespace(weather_buffer_entity="reserve")
        client = Client({"dry_run": True, "recommended_soc": 20,
            "applied_minimum_soc": 20, "daily_plan_fresh": True,
            "weather_source_status": "fresh", "grid_confidence": "normal"})
        state = {}
        self.assertTrue(observe_battery_reserve(config, client, state, NOW))
        client.attributes["recommended_soc"] = 40
        observe_battery_reserve(config, client, state, NOW.replace(hour=5))
        self.assertFalse(state.get("pending_notifications"))
        client.attributes["recommended_soc"] = 60
        observe_battery_reserve(config, client, state, NOW)
        self.assertEqual(1, len(state["pending_notifications"]))
        self.assertFalse(observe_battery_reserve(config, client, state, NOW))

    def test_one_reserve_advice_in_morning(self):
        message = build_report(weather_lines=[], solar_forecast=None, solar_window=None,
            threshold_w=300, consumption=5, snapshot={}, night_import=None,
            ahm_minimum_soc=20,
            weather_buffer={"dry_run": True, "baseline_soc": 20, "recommended_soc": 40,
                            "weather_modifier_percent": 20, "evidence_issues": ["forecast_unknown"]})
        self.assertIn("недостатньо даних", message)
        self.assertNotIn("10%", message)
        self.assertIn("Керування мін. зарядом: ручне", message)
        self.assertNotIn("40%", message)


class WarningSafetyTests(TestCase):
    def post(self, text, number=1):
        return SourcePost("uhmc1921", number, text, NOW, f"https://t.me/uhmc1921/{number}")

    def test_other_regions_severity_not_assigned_to_kyiv(self):
        post = self.post("Попередження: у Київській області туман, I рівень; у Львівській області сильний вітер, II рівень.")
        self.assertIsNone(normalize_warning(post))
        self.assertEqual("unknown", build_warning_snapshot([post], NOW)["source_status"])

    def test_no_precipitation_is_not_a_cancellation(self):
        active = self.post("Попередження для Києва: сильний вітер, II рівень небезпечності.")
        previous = build_warning_snapshot([active], NOW)["warnings"]
        ordinary = self.post("У Києві опадів не очікується.", 2)
        self.assertEqual(1, len(build_warning_snapshot([ordinary], NOW, previous)["warnings"]))

    def test_hazard_specific_cancellation_keeps_unrelated_warning(self):
        wind = self.post("Попередження для Києва: сильний вітер, II рівень небезпечності.")
        ice = self.post("Попередження для Києва: ожеледиця, II рівень небезпечності.", 2)
        previous = build_warning_snapshot([wind, ice], NOW)["warnings"]
        cancel = self.post("Для Києва попередження про сильний вітер скасовано.", 3)
        warnings = build_warning_snapshot([cancel], NOW, previous)["warnings"]
        self.assertEqual(["ice"], warnings[0]["hazards"])
        self.assertEqual(1, len(warnings))

    def test_parser_does_not_invent_publication_time(self):
        parser = TelegramPreviewParser("uhmc1921")
        parser.feed('<div class="tgme_widget_message" data-post="uhmc1921/1"><div class="tgme_widget_message_text">Warning</div></div>')
        parser.close()
        self.assertEqual([], parser.posts)
