from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.uhmc_source import SourcePost
from app.weather_warning import build_warning_snapshot, normalize_warning


NOW = datetime(2026, 9, 5, 7, 0, tzinfo=timezone.utc)


def post(text: str, message_id: int = 1, published_at: datetime = NOW) -> SourcePost:
    return SourcePost(
        channel="uhmc1921",
        message_id=message_id,
        text=text,
        published_at=published_at,
        url=f"https://t.me/uhmc1921/{message_id}",
    )


class WeatherWarningTests(unittest.TestCase):
    def test_new_combined_warning_replaces_wind_and_keeps_evidence(self):
        wind = post("Попередження. 5 вересня у Києві сильний вітер. I рівень небезпечності.", 10)
        combined = post("Попередження. 5 вересня у Києві сильний вітер та гроза. I рівень небезпечності.", 11)
        snapshot = build_warning_snapshot([combined, wind], NOW)
        self.assertEqual([11], [item["message_id"] for item in snapshot["warnings"]])
        self.assertEqual([10], [item["message_id"] for item in snapshot["superseded_warnings"]])
        self.assertFalse(snapshot["superseded_warnings"][0]["active"])
        restored = build_warning_snapshot([wind], NOW, snapshot["warnings"])
        self.assertEqual(snapshot["warnings"], restored["warnings"])

    def test_unrelated_hazards_and_different_days_remain_separate(self):
        wind = post("Попередження. 5 вересня у Києві сильний вітер. I рівень небезпечності.", 10)
        for text in ("Попередження. 5 вересня у Києві гроза. I рівень небезпечності.",
                     "Попередження. 6 вересня у Києві сильний вітер та гроза. I рівень небезпечності."):
            self.assertEqual(2, len(build_warning_snapshot([wind, post(text, 11)], NOW)["warnings"]))

    def test_lower_severity_or_shorter_validity_does_not_erase_risk(self):
        wind = post("Попередження. 5–6 вересня у Києві сильний вітер. II рівень небезпечності.", 10)
        for text in ("Попередження. 5–6 вересня у Києві сильний вітер та гроза. I рівень небезпечності.",
                     "Попередження. 5 вересня у Києві сильний вітер та гроза. II рівень небезпечності."):
            self.assertEqual(2, len(build_warning_snapshot([wind, post(text, 11)], NOW)["warnings"]))

    def test_equal_hazards_higher_severity_replaces_old(self):
        first = post("Попередження. 5 вересня у Києві сильний вітер. I рівень небезпечності.", 10)
        later = post(first.text.replace("I рівень", "II рівень"), 11)
        self.assertEqual([11], [item["message_id"] for item in build_warning_snapshot([first, later], NOW)["warnings"]])

    def test_superseded_warning_does_not_reappear_after_cancellation(self):
        first = post("Попередження. 5 вересня у Києві сильний вітер. I рівень небезпечності.", 10)
        later = post(first.text.replace("вітер.", "вітер та гроза."), 11)
        cancellation = post("У Києві попередження скасовано.", 12)
        snapshot = build_warning_snapshot([first, later], NOW)
        self.assertEqual([], build_warning_snapshot([first, later, cancellation], NOW, snapshot["warnings"])["warnings"])

    def test_level_one_thunderstorm_is_normalized_but_not_promoted(self):
        warning = normalize_warning(
            post("Попередження. 5 вересня у Київській області грози. I рівень небезпечності.")
        )
        self.assertIsNotNone(warning)
        self.assertEqual(warning["severity"], 1)
        self.assertEqual(warning["hazards"], ["thunderstorm"])

    def test_level_two_road_ice_is_grid_relevant(self):
        warning = normalize_warning(
            post("Попередження. 5 вересня у Києві та Київській області ожеледиця. II рівень небезпечності.")
        )
        self.assertEqual(warning["severity"], 2)
        self.assertIn("ice", warning["hazards"])
        self.assertTrue(warning["region_match"])
        self.assertTrue(warning["grid_relevant"])

    def test_fog_heat_and_other_region_are_excluded(self):
        self.assertIsNone(normalize_warning(post("Попередження. У Київській області туман. II рівень небезпечності.")))
        self.assertIsNone(normalize_warning(post("Попередження. У Києві спека. II рівень небезпечності.")))
        self.assertIsNone(normalize_warning(post("Попередження. У Львівській області гроза. II рівень небезпечності.")))

    def test_missing_validity_uses_twelve_hour_ttl(self):
        warning = normalize_warning(
            post("Попередження для Києва: сильний вітер. II рівень небезпечності.")
        )
        start = datetime.fromisoformat(warning["valid_from"])
        end = datetime.fromisoformat(warning["valid_until"])
        self.assertEqual(end - start, timedelta(hours=12))

    def test_supplied_multi_day_validity_is_preserved(self):
        warning = normalize_warning(
            post("Попередження. 5–6 вересня у Київській області сильний вітер. II рівень небезпечності.")
        )
        start = datetime.fromisoformat(warning["valid_from"])
        end = datetime.fromisoformat(warning["valid_until"])
        self.assertGreater(end - start, timedelta(hours=47))

    def test_separate_dates_extend_warning_through_last_mentioned_day(self):
        warning = normalize_warning(post(
            "Попередження по Київщині. До кінця доби 21 вересня, "
            "вночі та вранці 22 вересня значні дощі. I рівень небезпечності.",
            published_at=datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc),
        ))
        end = datetime.fromisoformat(warning["valid_until"]).astimezone(
            ZoneInfo("Europe/Kyiv")
        )
        self.assertEqual((22, 23), (end.day, end.hour))

    def test_duplicate_is_collapsed_and_cancellation_clears(self):
        first = post("Попередження. 5 вересня у Київській області гроза. II рівень небезпечності.", 10)
        duplicate = post(first.text, 11, NOW + timedelta(minutes=10))
        snapshot = build_warning_snapshot([first, duplicate], NOW)
        self.assertEqual(len(snapshot["warnings"]), 1)
        cancellation = post("Для Київської області попередження скасовано.", 12)
        cleared = build_warning_snapshot([cancellation], NOW, snapshot["warnings"])
        self.assertEqual(cleared["warnings"], [])

    def test_active_warning_survives_preview_pagination_and_restart(self):
        warning = normalize_warning(
            post("Попередження. 5 вересня у Київській області сильний вітер. III рівень небезпечності.", 20)
        )
        snapshot = build_warning_snapshot([], NOW + timedelta(hours=1), [warning])
        self.assertEqual([warning["event_id"]], [item["event_id"] for item in snapshot["warnings"]])
        expired = build_warning_snapshot([], NOW + timedelta(days=2), snapshot["warnings"])
        self.assertEqual(expired["warnings"], [])

    def test_edited_post_replaces_previous_revision(self):
        original = post("Попередження. 5 вересня у Київській області гроза. II рівень небезпечності.", 30)
        first = build_warning_snapshot([original], NOW)
        edited = post("Попередження. 5 вересня у Київській області сильний вітер. III рівень небезпечності.", 30)
        second = build_warning_snapshot([edited], NOW, first["warnings"])
        self.assertEqual(len(second["warnings"]), 1)
        self.assertEqual(second["warnings"][0]["severity"], 3)
        self.assertEqual(second["warnings"][0]["hazards"], ["strong_wind"])
        self.assertNotEqual(first["warnings"][0]["event_id"], second["warnings"][0]["event_id"])


if __name__ == "__main__":
    unittest.main()
