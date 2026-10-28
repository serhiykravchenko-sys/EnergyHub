"""Time-weighted rolling-hour house load for pre-outage charging only."""
from collections import deque
from math import isfinite


class PreparationDemand:
    def __init__(self):
        self.rows = deque(maxlen=125)

    def observe(self, now, watts, valid):
        tick = now.timestamp()
        if (not valid or isinstance(watts, bool) or not isinstance(watts, (int, float))
                or not isfinite(watts) or not 0 <= watts <= 30000):
            self.rows.clear()
            return None
        if self.rows and (tick < self.rows[-1][0] or tick-self.rows[-1][0] > 90):
            self.rows.clear()
        if not self.rows or tick-self.rows[-1][0] >= 30:
            self.rows.append((tick, watts))
        start = tick-3600
        while len(self.rows) > 1 and self.rows[1][0] <= start:
            self.rows.popleft()
        if not self.rows or self.rows[0][0] > start:
            return None
        rows = list(self.rows)
        if rows[-1][0] < tick:
            rows.append((tick, watts))
        energy_ws = 0.0
        for (a, power), (b, _) in zip(rows, rows[1:]):
            if not 0 < b-a <= 90:
                return None
            energy_ws += (b-max(start, a))*power
        return energy_ws/3600/1000
