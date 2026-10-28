"""Conservative observed house demand; no device commands or HP attribution."""
import json
from app.utils.json_store import atomic_write_json


class HouseDemand:
    def __init__(self, path=None):
        self.path = path
        self.rows = []
        if path:
            try:
                rows = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(rows, list):
                    self.rows = rows[-400:]
            except (OSError, ValueError):
                pass

    def observe(self, now, watts, valid):
        from app.services.outage_preparation import number
        watts = number(watts)
        tick = now.timestamp()
        parsed = [[number(r[0]),number(r[1])] for r in self.rows if isinstance(r,list) and len(r)==2]
        self.rows = [r for r in parsed if all(v is not None for v in r)
                     and tick-10890 <= r[0] <= tick and 0 <= r[1] <= 30000]
        if not valid or watts is None or not 0 <= watts <= 30000:
            return None
        if not self.rows or tick-self.rows[-1][0] >= 30:
            self.rows.append([tick, watts])
            self.rows = self.rows[-400:]
            if self.path:
                try:
                    atomic_write_json(self.path, self.rows, ensure_ascii=False, indent=1)
                except OSError:
                    pass  # Never grant history authority because persistence succeeded.
        averages = []
        for window in (1800, 10800):
            start = tick-window
            rows = [r for r in self.rows if r[0] >= start-90]
            if not rows or rows[0][0] > start or tick-rows[-1][0] > 90:
                return None
            energy = 0
            for left, right in zip(rows, rows[1:]):
                if not 0 < right[0]-left[0] <= 90:
                    return None
                energy += max(0, right[0]-max(start, left[0])) * max(left[1], right[1])
            averages.append(energy/window)
        return max(watts, *averages) / 1000 * 1.2
