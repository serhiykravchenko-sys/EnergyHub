from datetime import datetime
from unittest import TestCase
from zoneinfo import ZoneInfo

from app.log_digest import digest_lines, system_digest_lines


NOW = datetime(2026, 9, 20, 8, 0, tzinfo=ZoneInfo("Europe/Kyiv"))


class LogDigestTests(TestCase):
    def test_clean_log_is_explicit(self):
        self.assertIn("поточного сеансу попереджень немає", digest_lines("", NOW)[0])

    def test_deduplicates_and_counts_recent_entries(self):
        line = (
            "2026-09-20 07:30:00.000 WARNING (MainThread) "
            "[homeassistant.components.mqtt] stale payload"
        )
        result = digest_lines(f"{line}\n{line}", NOW)
        self.assertIn("Попередження: 2", result[1])
        self.assertTrue(any("×2" in item for item in result))

    def test_ignores_entries_older_than_24_hours(self):
        old = (
            "2026-09-18 07:30:00.000 ERROR (MainThread) "
            "[homeassistant.config] old error"
        )
        self.assertIn("не знайдено", digest_lines(old, NOW)[0])

    def test_combines_core_and_supervisor_and_strips_ansi(self):
        core = ("2026-09-20 07:30:00 WARNING (MainThread) "
                "[homeassistant.config] bad config")
        supervisor = ("\x1b[33m2026-09-20 07:40:00 WARNING (MainThread) "
                      "[supervisor.apps.options] obsolete option\x1b[0m")
        result = system_digest_lines(core, supervisor, NOW)
        self.assertTrue(any("Core ·" in line for line in result))
        self.assertTrue(any("Supervisor ·" in line for line in result))

    def test_combined_clean_log_is_compact(self):
        self.assertEqual(1, len(system_digest_lines("", "", NOW)))
        self.assertIn("Core і Supervisor", system_digest_lines("", "", NOW)[0])

    def test_unavailable_log_is_not_called_clean(self):
        result = system_digest_lines("", None, NOW)
        self.assertEqual(1, len(result))
        self.assertIn("✅ Core:", result[0])
        self.assertNotIn("Supervisor", result[0])
        self.assertEqual([], system_digest_lines(None, None, NOW))

    def test_unknown_nonempty_core_format_is_not_called_clean(self):
        result = system_digest_lines("unexpected log format", None, NOW)
        self.assertIn("формат", result[0])
        self.assertNotIn("✅", result[0])
