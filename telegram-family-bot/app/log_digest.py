"""Small, private morning digest of Home Assistant Core warnings and errors."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
import re


ENTRY = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?) "
    r"(?P<level>WARNING|ERROR|CRITICAL) \([^)]*\) \[(?P<logger>[^]]+)\] "
    r"(?P<message>.*)$"
)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _entries(text: str, now: datetime) -> list[tuple[str, str, str]]:
    cutoff = now - timedelta(hours=24)
    entries: list[tuple[str, str, str]] = []
    for raw in str(text or "").splitlines():
        match = ENTRY.match(ANSI.sub("", raw).strip())
        if not match:
            continue
        try:
            stamp = datetime.fromisoformat(match.group("stamp")).replace(
                tzinfo=now.tzinfo
            )
        except ValueError:
            continue
        if stamp < cutoff or stamp > now + timedelta(minutes=5):
            continue
        message = re.sub(r"\s+", " ", match.group("message")).strip()
        entries.append((match.group("level"), match.group("logger"), message))
    return entries


def digest_lines(text: str, now: datetime, *, limit: int = 8) -> list[str]:
    entries = _entries(text, now)

    if not entries:
        if str(text or "").strip():
            return ["ℹ️ У доступному журналі Core не знайдено розпізнаних попереджень за 24 год; формат і повноту журналу слід перевірити."]
        return ["✅ У доступному журналі Core поточного сеансу попереджень немає"]

    counts = Counter(entries)
    severity = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2}
    ordered = sorted(counts, key=lambda item: (severity[item[0]], item[1], item[2]))
    lines = [
        f"🔴 Помилки: {sum(count for item, count in counts.items() if item[0] in {'ERROR', 'CRITICAL'})}",
        f"🟡 Попередження: {sum(count for item, count in counts.items() if item[0] == 'WARNING')}",
    ]
    for level, logger, message in ordered[:limit]:
        count = counts[(level, logger, message)]
        marker = "🔴" if level in {"ERROR", "CRITICAL"} else "🟡"
        suffix = f" ×{count}" if count > 1 else ""
        clipped = message if len(message) <= 180 else message[:177] + "…"
        lines.append(f"{marker} <code>{escape(logger)}</code>: {escape(clipped)}{suffix}")
    hidden = len(ordered) - limit
    if hidden > 0:
        lines.append(f"…ще {hidden} типів повідомлень")
    return lines


def system_digest_lines(core_text: str | None, supervisor_text: str | None, now: datetime,
                        *, limit: int = 8) -> list[str]:
    """Deduplicate actionable Core and Supervisor entries from the last 24 h."""
    entries = [("Core", *entry) for entry in _entries(core_text or "", now)]
    entries += [("Supervisor", *entry) for entry in _entries(supervisor_text or "", now)]
    if not entries:
        if any(str(text or "").strip() for text in (core_text, supervisor_text)):
            return ["ℹ️ У доступних журналах не знайдено розпізнаних попереджень за 24 год; формат і повноту журналів слід перевірити."]
        if core_text is not None and supervisor_text is not None:
            return ["✅ Core і Supervisor: у доступних журналах поточного сеансу попереджень немає"]
        available = [name for name, text in (("Core", core_text), ("Supervisor", supervisor_text))
                     if text is not None]
        return ([f"✅ {' і '.join(available)}: у доступному журналі поточного сеансу попереджень немає"]
                if available else [])
    counts = Counter(entries)
    severity = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2}
    ordered = sorted(counts, key=lambda item: (severity[item[1]], item[0], item[2], item[3]))
    lines = [
        f"🔴 Помилки: {sum(count for item, count in counts.items() if item[1] in {'ERROR', 'CRITICAL'})}",
        f"🟡 Попередження: {sum(count for item, count in counts.items() if item[1] == 'WARNING')}",
    ]
    for source, level, logger, message in ordered[:limit]:
        count = counts[(source, level, logger, message)]
        marker = "🔴" if level in {"ERROR", "CRITICAL"} else "🟡"
        suffix = f" ×{count}" if count > 1 else ""
        clipped = message if len(message) <= 160 else message[:157] + "…"
        lines.append(f"{marker} {source} · <code>{escape(logger)}</code>: {escape(clipped)}{suffix}")
    hidden = len(ordered) - limit
    if hidden > 0:
        lines.append(f"…ще {hidden} типів повідомлень")
    return lines
