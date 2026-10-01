from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Calendar


MAX_ICAL_BYTES = 5 * 1024 * 1024


class CalendarError(RuntimeError):
    """A safe calendar error that never contains the private feed URL."""


@dataclass(frozen=True)
class CalendarEvent:
    summary: str
    start: date | datetime
    end: date | datetime | None
    all_day: bool


def _parse_event_boundary(value: object, timezone: ZoneInfo) -> date | datetime | None:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone)
        return parsed.astimezone(timezone)
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def normalize_events(
    raw_events: list[dict[str, Any]],
    timezone: ZoneInfo,
) -> list[CalendarEvent]:
    normalized: list[CalendarEvent] = []
    for raw in raw_events:
        summary = str(raw.get("summary") or "").strip()
        start = _parse_event_boundary(raw.get("start"), timezone)
        if not summary or start is None:
            continue
        normalized.append(
            CalendarEvent(
                summary=summary,
                start=start,
                end=_parse_event_boundary(raw.get("end"), timezone),
                all_day=isinstance(start, date)
                and not isinstance(start, datetime),
            )
        )
    return sorted(
        normalized,
        key=lambda event: (
            datetime.combine(event.start, time.min, timezone)
            if event.all_day
            else event.start
        ),
    )


def _occurs_on(event: CalendarEvent, target: date, timezone: ZoneInfo) -> bool:
    if event.all_day:
        end = (
            event.end
            if isinstance(event.end, date)
            and not isinstance(event.end, datetime)
            else event.start + timedelta(days=1)
        )
        return event.start <= target < end
    start = event.start.astimezone(timezone)
    end = event.end.astimezone(timezone) if isinstance(event.end, datetime) else start
    target_start = datetime.combine(target, time.min, timezone)
    target_end = target_start + timedelta(days=1)
    return start < target_end and end > target_start


def _today_line(event: CalendarEvent, timezone: ZoneInfo) -> str:
    title = escape(event.summary)
    if event.all_day:
        return title
    return f"{event.start.astimezone(timezone).strftime('%H:%M')} — {title}"


def calendar_digest_lines(
    events: list[CalendarEvent],
    today: date,
    timezone: ZoneInfo,
) -> list[str]:
    today_events = [event for event in events if _occurs_on(event, today, timezone)]
    if not today_events:
        return []
    return [
        "📅 <b>Сьогодні</b>",
        *(_today_line(event, timezone) for event in today_events),
    ]


def fetch_ical(url: str, timeout: int = 20) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CalendarError("private iCal address must be a valid HTTPS URL")
    request = Request(
        url,
        headers={
            "Accept": "text/calendar",
            "User-Agent": "Telegram-Family-Assistant",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if urlparse(response.geturl()).scheme != "https":
                raise CalendarError("private iCal feed redirected to a non-HTTPS address")
            payload = response.read(MAX_ICAL_BYTES + 1)
    except CalendarError:
        raise
    except HTTPError as exc:
        raise CalendarError(f"private iCal feed returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise CalendarError("private iCal feed could not be reached") from None
    if len(payload) > MAX_ICAL_BYTES:
        raise CalendarError("private iCal feed exceeds the 5 MiB safety limit")
    return payload


def parse_ical_events(
    payload: bytes,
    start: datetime,
    end: datetime,
    timezone: ZoneInfo,
) -> list[CalendarEvent]:
    try:
        calendar = Calendar.from_ical(payload)
        components = recurring_ical_events.of(calendar).between(start, end)
    except Exception as exc:
        raise CalendarError(f"private iCal feed could not be parsed ({type(exc).__name__})") from None

    raw_events: list[dict[str, Any]] = []
    for component in components:
        try:
            event_start = component.decoded("dtstart")
        except (KeyError, ValueError, TypeError):
            continue
        event_end: date | datetime | None = None
        try:
            event_end = component.decoded("dtend")
        except (KeyError, ValueError, TypeError):
            try:
                duration = component.decoded("duration")
                event_end = event_start + duration
            except (KeyError, ValueError, TypeError):
                pass
        raw_events.append(
            {
                "summary": str(component.get("summary") or "").strip(),
                "start": event_start,
                "end": event_end,
            }
        )
    return normalize_events(raw_events, timezone)


class CalendarService:
    def __init__(self, private_ical_url: str, timezone: ZoneInfo, timeout: int = 20):
        self.private_ical_url = private_ical_url
        self.timezone = timezone
        self.timeout = timeout

    def digest_lines(self, today: date) -> list[str]:
        start = datetime.combine(today, time.min, self.timezone)
        end = start + timedelta(days=1)
        payload = fetch_ical(self.private_ical_url, self.timeout)
        events = parse_ical_events(payload, start, end, self.timezone)
        return calendar_digest_lines(events, today, self.timezone)
