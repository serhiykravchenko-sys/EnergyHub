from __future__ import annotations

import unittest
from datetime import date, datetime, time
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from app.calendar_service import (
    CalendarError,
    calendar_digest_lines,
    fetch_ical,
    normalize_events,
    parse_ical_events,
)


TZ = ZoneInfo("Europe/Kyiv")
TODAY = date(2026, 8, 26)


class CalendarServiceTests(unittest.TestCase):
    def test_today_events_keep_exact_titles_and_omit_tomorrow(self):
        events = normalize_events([
            {"summary": "Тренування", "start": "2026-08-26T15:00:00+03:00", "end": "2026-08-26T16:00:00+03:00"},
            {"summary": "Asya Nazarenko Happy Birthday!", "start": "2026-08-26", "end": "2026-08-27"},
            {"summary": "Тест день народження", "start": "2026-08-27", "end": "2026-08-28"},
        ], TZ)

        lines = calendar_digest_lines(events, TODAY, TZ)

        self.assertIn("📅 <b>Сьогодні</b>", lines)
        self.assertIn("Asya Nazarenko Happy Birthday!", lines)
        self.assertIn("15:00 — Тренування", lines)
        self.assertNotIn("Тест день народження", lines)
        self.assertNotIn("Увесь день", "\n".join(lines))

    def test_name_only_timed_event_keeps_time_prefix(self):
        events = normalize_events([{
            "summary": "Іван",
            "start": "2026-08-26T10:00:00+03:00",
            "end": "2026-08-26T11:00:00+03:00",
        }], TZ)
        self.assertIn("10:00 — Іван", calendar_digest_lines(events, TODAY, TZ))

    def test_name_only_all_day_event_is_reproduced_without_inference(self):
        events = normalize_events([{
            "summary": "Іван Петренко",
            "start": "2026-08-26",
            "end": "2026-08-27",
        }], TZ)
        lines = calendar_digest_lines(events, TODAY, TZ)
        self.assertIn("Іван Петренко", lines)
        self.assertNotIn("день народження", "\n".join(lines).lower())

    def test_regular_tomorrow_event_is_not_shown(self):
        events = normalize_events([{
            "summary": "Купити продукти",
            "start": "2026-08-27T10:00:00+03:00",
            "end": "2026-08-27T11:00:00+03:00",
        }], TZ)
        self.assertEqual([], calendar_digest_lines(events, TODAY, TZ))

    def test_html_is_escaped(self):
        events = normalize_events([{
            "summary": "Басейн <діти>",
            "start": "2026-08-26T10:00:00+03:00",
            "end": "2026-08-26T11:00:00+03:00",
        }], TZ)
        self.assertIn("10:00 — Басейн &lt;діти&gt;", calendar_digest_lines(events, TODAY, TZ))

    def test_recurring_ical_events_are_expanded_for_requested_window(self):
        payload = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//EnergyHub test//EN\r
BEGIN:VEVENT\r
UID:birthday-1\r
DTSTART;VALUE=DATE:20200826\r
DTEND;VALUE=DATE:20200827\r
RRULE:FREQ=YEARLY\r
SUMMARY:Dasha\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:training-1\r
DTSTART;TZID=Europe/Kyiv:20260826T150000\r
DTEND;TZID=Europe/Kyiv:20260826T160000\r
SUMMARY:Training\r
END:VEVENT\r
END:VCALENDAR\r
"""
        start = datetime.combine(TODAY, time.min, TZ)
        events = parse_ical_events(payload, start, start.replace(day=28), TZ)

        lines = calendar_digest_lines(events, TODAY, TZ)
        self.assertIn("15:00 — Training", lines)
        self.assertIn("Dasha", lines)

    def test_cancelled_recurring_occurrence_is_not_returned(self):
        payload = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//EnergyHub test//EN\r
BEGIN:VEVENT\r
UID:weekly-1\r
DTSTART;TZID=Europe/Kyiv:20260819T150000\r
DTEND;TZID=Europe/Kyiv:20260819T160000\r
RRULE:FREQ=WEEKLY;COUNT=3\r
EXDATE;TZID=Europe/Kyiv:20260826T150000\r
SUMMARY:Training\r
END:VEVENT\r
END:VCALENDAR\r
"""
        start = datetime.combine(TODAY, time.min, TZ)
        events = parse_ical_events(payload, start, start.replace(day=28), TZ)
        self.assertEqual([], events)

    def test_private_url_is_not_exposed_in_http_error(self):
        secret = "https://calendar.google.com/calendar/ical/private-token/basic.ics"
        with patch(
            "app.calendar_service.urlopen",
            side_effect=HTTPError(secret, 403, "Forbidden", {}, None),
        ):
            with self.assertRaises(CalendarError) as context:
                fetch_ical(secret)
        self.assertNotIn("private-token", str(context.exception))
        self.assertIn("HTTP 403", str(context.exception))

    def test_non_https_private_url_is_rejected_without_request(self):
        with patch("app.calendar_service.urlopen") as mocked:
            with self.assertRaises(CalendarError):
                fetch_ical("http://example.test/private.ics")
        mocked.assert_not_called()

    def test_redirect_to_non_https_address_is_rejected(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = "http://example.test/private.ics"
        with patch("app.calendar_service.urlopen", return_value=response):
            with self.assertRaises(CalendarError):
                fetch_ical("https://example.test/private.ics")


if __name__ == "__main__":
    unittest.main()
