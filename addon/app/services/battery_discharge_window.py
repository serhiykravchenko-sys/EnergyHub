"""Time-weighted net battery flow during autonomous Solar operation."""
from collections import deque
from math import isfinite


class BatteryDischargeWindow:
    WINDOW_SECONDS = 3600
    MAX_GAP_SECONDS = 90

    def __init__(self):
        self.samples = deque()

    def observe(self, now, *, voltage, discharge_a, charge_a, valid, mode):
        # Grid-support/charging modes cannot measure autonomous consumption.
        values = (voltage, discharge_a, charge_a)
        if (not valid or mode != 'solar'
                or any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not isfinite(x) for x in values)
                or not 40 <= voltage <= 65 or not 0 <= discharge_a <= 300
                or not 0 <= charge_a <= 200):
            self.samples.clear()
            return
        if self.samples:
            gap = (now-self.samples[-1][0]).total_seconds()
            if gap == 0:
                return
            if not 0 < gap <= self.MAX_GAP_SECONDS:
                self.samples.clear()
        self.samples.append((now, voltage*(discharge_a-charge_a)/1000))
        cutoff = now.timestamp()-self.WINDOW_SECONDS
        # Retain one point before the boundary for exact interpolation.
        while len(self.samples) > 2 and self.samples[1][0].timestamp() <= cutoff:
            self.samples.popleft()

    def average_kw(self, now):
        if (len(self.samples) < 2
                or not 0 <= (now-self.samples[-1][0]).total_seconds() <= self.MAX_GAP_SECONDS
                or (now-self.samples[0][0]).total_seconds() < self.WINDOW_SECONDS):
            return None
        cutoff = now.timestamp()-self.WINDOW_SECONDS
        energy = duration = 0.0
        for (a, left), (b, right) in zip(self.samples, list(self.samples)[1:]):
            start, stop = max(cutoff, a.timestamp()), b.timestamp()
            seconds = stop-start
            if seconds <= 0:
                continue
            edge = left+(right-left)*(start-a.timestamp())/(b-a).total_seconds()
            energy += (edge+right)/2*seconds
            duration += seconds
        return energy/duration if duration >= self.WINDOW_SECONDS-1 else None


def checked_start(*, now, completion, planned_start, gap_kwh, solar_kwh,
                  rows, discharge_kw, soc, reserve, capacity):
    """Advance, never postpone, the configured-demand charging deadline."""
    from datetime import timedelta
    if discharge_kw is None or discharge_kw <= 0 or completion <= now:
        return planned_start, 0.0

    # Ordinary reserve control supplies the house once BR is reached. Charging
    # for a future outage must not own the strategy merely to protect that floor.
    usable=max(0,(soc-reserve)*capacity/100)

    def waiting_loss(candidate):
        return min(usable,discharge_kw*max(0,(candidate-now).total_seconds()/3600))

    def feasible(candidate):
        available = sum(max(0, (b-max(a, candidate)).total_seconds()/3600)*grid
                        for a, b, _, grid in rows if b > candidate)
        return available >= max(0, gap_kwh+waiting_loss(candidate)-solar_kwh)

    low, high = now, max(now, min(completion, planned_start))
    if feasible(low):
        for _ in range(32):
            middle = low+(high-low)/2
            if feasible(middle):
                low = middle
            else:
                high = middle
        candidate = low
    else:
        candidate = now
    candidate = min(candidate, planned_start)
    candidate = max(now, candidate)
    return candidate, waiting_loss(candidate)
