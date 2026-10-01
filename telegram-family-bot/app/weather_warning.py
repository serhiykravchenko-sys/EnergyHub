from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .uhmc_source import SourcePost, content_hash


KYIV_RE = re.compile(
    r"\b(?:ки(?:ї|є)в(?:і|а|ом|у)?|київськ(?:а|ій|ої|у|ою)\s+(?:област(?:ь|і)|обл\.?))\b|\bкиївщин",
    re.IGNORECASE,
)
WARNING_RE = re.compile(
    r"попереджен|небезпечн|стихійн|рівень\s+небезпечності|рівень\s+загроз",
    re.IGNORECASE,
)
CANCEL_RE = re.compile(
    r"скасован|відбій|втратил[аои]?\s+актуальність",
    re.IGNORECASE,
)
OTHER_REGION_RE = re.compile(
    r"\b(?!київськ)\w+(?:ськ|цьк)\w*\s+област|\b(?:західних|східних|південних)\s+област",
    re.IGNORECASE,
)
MONTHS = {
    "січня": 1,
    "лютого": 2,
    "березня": 3,
    "квітня": 4,
    "травня": 5,
    "червня": 6,
    "липня": 7,
    "серпня": 8,
    "вересня": 9,
    "жовтня": 10,
    "листопада": 11,
    "грудня": 12,
}
DATE_RE = re.compile(
    r"\b([0-3]?\d)\s+(" + "|".join(MONTHS) + r")\b",
    re.IGNORECASE,
)
DATE_RANGE_RE = re.compile(
    r"\b([0-3]?\d)\s*(?:[-–—]|та)\s*([0-3]?\d)\s+("
    + "|".join(MONTHS)
    + r")\b",
    re.IGNORECASE,
)
HAZARD_PATTERNS = {
    "strong_wind": re.compile(r"сильн\w*\s+віт|порив\w*\s+віт|шквал", re.IGNORECASE),
    "thunderstorm": re.compile(r"гроз", re.IGNORECASE),
    "ice": re.compile(r"ожелед|обледен|налипан\w*\s+(?:мокр\w*\s+)?сніг", re.IGNORECASE),
    "heavy_snow": re.compile(r"сильн\w*\s+сніг|значн\w*\s+сніг|мокр\w*\s+сніг|хуртовин", re.IGNORECASE),
    "severe_precipitation": re.compile(r"сильн\w*\s+(?:дощ|опад)|значн\w*\s+(?:дощ|опад)|злива", re.IGNORECASE),
    "hail": re.compile(r"град", re.IGNORECASE),
}


def _severity(text: str) -> int | None:
    lowered = text.lower()
    if re.search(r"(?:iii|ііі|3)\s*(?:рівень|рівня)|червон", lowered):
        return 3
    if re.search(r"(?:ii|іі|2)\s*(?:рівень|рівня)|помаранч", lowered):
        return 2
    if re.search(r"(?:i|і|1)\s*(?:рівень|рівня)|жовт", lowered):
        return 1
    return None


def _validity(post: SourcePost, timezone_name: str) -> tuple[datetime, datetime]:
    local_zone = ZoneInfo(timezone_name)
    published = post.published_at.astimezone(local_zone)
    range_match = DATE_RANGE_RE.search(post.text)
    dates: list[tuple[int, int]] = []
    if range_match:
        month = MONTHS[range_match.group(3).lower()]
        dates.extend([
            (int(range_match.group(1)), month),
            (int(range_match.group(2)), month),
        ])
    for match in DATE_RE.finditer(post.text):
        dates.append((int(match.group(1)), MONTHS[match.group(2).lower()]))
    if not dates:
        return post.published_at.astimezone(timezone.utc), (
            post.published_at + timedelta(hours=12)
        ).astimezone(timezone.utc)
    parsed_dates = []
    for day, month in dates:
        year = published.year
        if month < published.month - 6:
            year += 1
        elif month > published.month + 6:
            year -= 1
        try:
            parsed_dates.append(published.date().replace(year=year, month=month, day=day))
        except ValueError:
            continue
    if not parsed_dates:
        return post.published_at.astimezone(timezone.utc), (
            post.published_at + timedelta(hours=12)
        ).astimezone(timezone.utc)
    first_date = min(parsed_dates)
    last_date = max(parsed_dates)
    start = datetime.combine(first_date, time.min, local_zone)
    end = datetime.combine(last_date, time.max, local_zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def normalize_warning(
    post: SourcePost,
    timezone_name: str = "Europe/Kyiv",
) -> dict[str, Any] | None:
    text = post.text.strip()
    if not KYIV_RE.search(text) or not WARNING_RE.search(text):
        return None
    # Do not assign another region's severity to Kyiv. Ambiguous nationwide
    # posts remain unknown evidence until a region-specific warning arrives.
    if OTHER_REGION_RE.search(text):
        return None
    levels = set(re.findall(r"(?<!\w)(iii|ііі|ii|іі|i|і|[123])\s*(?:рівень|рівня)", text.lower()))
    normalized_levels = { {"iii": 3, "ііі": 3, "ii": 2, "іі": 2,
                           "i": 1, "і": 1, "1": 1, "2": 2, "3": 3}[item] for item in levels }
    if len(normalized_levels) > 1:
        return None
    hazards = sorted(
        name for name, pattern in HAZARD_PATTERNS.items() if pattern.search(text)
    )
    severity = _severity(text)
    if not hazards or severity is None:
        return None
    valid_from, valid_until = _validity(post, timezone_name)
    return {
        "event_id": f"{post.channel}/{post.message_id}/{content_hash(post)}",
        "source": post.channel,
        "message_id": post.message_id,
        "url": post.url,
        "published_at": post.published_at.astimezone(timezone.utc).isoformat(),
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat(),
        "severity": severity,
        "severity_color": {1: "yellow", 2: "orange", 3: "red"}[severity],
        "hazards": hazards,
        "region": "Kyiv/Kyiv region",
        "region_match": True,
        "active": True,
        "grid_relevant": True,
        "summary": text[:1000],
    }


def _parse_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _still_active(warning: dict[str, Any], observed_at: datetime) -> bool:
    valid_until = _parse_time(warning.get("valid_until"))
    return bool(warning.get("active", True)) and valid_until is not None and valid_until >= observed_at


def _supersedes(new: dict[str, Any], old: dict[str, Any], now: datetime) -> bool:
    """Replace only fully covered evidence, never silently weaken a warning."""
    if not new.get("source") or new.get("source") != old.get("source"):
        return False
    if not new.get("region") or new.get("region") != old.get("region"):
        return False
    old_hazards, new_hazards = set(old.get("hazards") or []), set(new.get("hazards") or [])
    if not old_hazards or not old_hazards <= new_hazards:
        return False
    try:
        if int(new["message_id"]) <= int(old["message_id"]):
            return False
        if int(new["severity"]) < int(old["severity"]):
            return False
        # Unchanged reposts continue through the existing deduplication path.
        if new_hazards == old_hazards and new["severity"] == old["severity"]:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    new_start, new_end = _parse_time(new.get("valid_from")), _parse_time(new.get("valid_until"))
    old_start, old_end = _parse_time(old.get("valid_from")), _parse_time(old.get("valid_until"))
    if None in (new_start, new_end, old_start, old_end):
        return False
    return new_start <= max(now, old_start) <= old_end <= new_end


def build_warning_snapshot(
    posts: Iterable[SourcePost],
    observed_at: datetime,
    previous_warnings: Iterable[dict[str, Any]] = (),
    timezone_name: str = "Europe/Kyiv",
) -> dict[str, Any]:
    observed_at = observed_at.astimezone(timezone.utc)
    warnings = [
        dict(item)
        for item in previous_warnings
        if isinstance(item, dict) and _still_active(item, observed_at)
    ]
    source_status = "fresh"
    for post in sorted(posts, key=lambda item: item.message_id):
        if not KYIV_RE.search(post.text):
            continue
        if OTHER_REGION_RE.search(post.text):
            source_status = "unknown"
            continue
        cancelled_hazards = [key for key, pattern in HAZARD_PATTERNS.items() if pattern.search(post.text)]
        if CANCEL_RE.search(post.text) and WARNING_RE.search(post.text):
            warnings = [
                item
                for item in warnings
                if str(item.get("source")) != post.channel
                or int(item.get("message_id", 0) or 0) >= post.message_id
                or (cancelled_hazards and not set(cancelled_hazards).intersection(item.get("hazards", [])))
            ]
            continue
        warning = normalize_warning(post, timezone_name)
        if warning is None and WARNING_RE.search(post.text) and cancelled_hazards:
            source_status = "unknown"
        if warning is not None and _still_active(warning, observed_at):
            post_prefix = f"{post.channel}/{post.message_id}/"
            warnings = [item for item in warnings
                        if not str(item.get("event_id", "")).startswith(post_prefix)]
            warnings.append(warning)

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for warning in sorted(warnings, key=lambda item: str(item.get("published_at", ""))):
        fingerprint = (
            warning.get("source"),
            warning.get("region"),
            warning.get("severity"),
            tuple(warning.get("hazards") or ()),
            warning.get("valid_from"),
            warning.get("valid_until"),
        )
        unique.setdefault(fingerprint, warning)
    active, superseded = [], []
    candidates = list(unique.values())
    for warning in candidates:
        replacements = [item for item in candidates if _supersedes(item, warning, observed_at)]
        if replacements:
            replacement = max(replacements, key=lambda item: int(item["message_id"]))
            archived = dict(warning, active=False, superseded_by=replacement["event_id"])
            superseded.append(archived)
        else:
            active.append(warning)
    return {
        "schema": 1,
        "source": "uhmc1921",
        "source_status": source_status,
        "observed_at": observed_at.isoformat(),
        "warnings": sorted(active, key=lambda item: str(item.get("event_id", ""))),
        "superseded_warnings": superseded,
    }


def unavailable_warning_snapshot(observed_at: datetime) -> dict[str, Any]:
    return {
        "schema": 1,
        "source": "uhmc1921",
        "source_status": "unknown",
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "warnings": [],
    }
