import json
import time
from pathlib import Path

from app.utils.json_store import atomic_write_json
from app.utils.logger import log


GRID_HISTORY_FILE = Path("/data/grid_history.json")
HISTORY_WINDOW_SECONDS = 48 * 60 * 60


class GridHistoryService:
    def __init__(self):
        self.last_state = None
        self.last_change = None
        self.events = []
        self.load()

    def load(self):
        if not GRID_HISTORY_FILE.exists():
            return

        try:
            data = json.loads(GRID_HISTORY_FILE.read_text())
            self.last_state = data.get("last_state")
            self.last_change = data.get("last_change")
            self.events = data.get("events", [])
            self.cleanup()
            log(f"Grid history loaded: {len(self.events)} events")
        except Exception as e:
            log(f"Failed to load grid history: {e}")

    def save(self):
        data = {
            "last_state": self.last_state,
            "last_change": self.last_change,
            "events": self.events,
        }

        try:
            atomic_write_json(
                GRID_HISTORY_FILE,
                data,
                ensure_ascii=False,
                indent=None,
            )
        except Exception as e:
            log(f"Failed to save grid history: {e}")

    def cleanup(self):
        cutoff = time.time() - HISTORY_WINDOW_SECONDS
        self.events = [
            event for event in self.events
            if event.get("timestamp", 0) >= cutoff
        ]

    def update(self, grid_available: bool):
        now = time.time()

        if self.last_state is None:
            self.last_state = grid_available
            self.last_change = now
            self.save()
            return True

        if grid_available == self.last_state:
            return False

        duration = now - self.last_change

        self.events.append(
            {
                "from": self.last_state,
                "to": grid_available,
                "duration": duration,
                "timestamp": now,
            }
        )

        self.last_state = grid_available
        self.last_change = now

        self.cleanup()
        self.save()

        log(f"Grid state changed: {'online' if grid_available else 'offline'}")
        return True

    def outage_hours(self, hours: int):
        now = time.time()
        window_start = now - hours * 3600
        outage_seconds = 0

        for event in self.events:
            event_end = event.get("timestamp", now)
            event_start = event_end - event.get("duration", 0)

            if event.get("from") is False:
                overlap_start = max(event_start, window_start)
                overlap_end = min(event_end, now)

                if overlap_end > overlap_start:
                    outage_seconds += overlap_end - overlap_start

        if self.last_state is False and self.last_change:
            overlap_start = max(self.last_change, window_start)
            outage_seconds += max(0, now - overlap_start)

        return round(outage_seconds / 3600, 2)

    def available_hours(self, hours: int):
        return round(hours - self.outage_hours(hours), 2)

    def availability_percent(self, hours: int):
        return round((self.available_hours(hours) / hours) * 100, 1)
