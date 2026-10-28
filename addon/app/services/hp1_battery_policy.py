"""First-floor HP battery policy retained until its separate native migration.

The shared load controller owns commands/acknowledgements. This policy owns only
the discharge episode and one-time soft shedding. Never infer grid presence from
a reliability label. Unknown evidence must be rejected by the caller.
"""
from dataclasses import dataclass, field
from math import isfinite

LOADS = ('heat_pump_floor_1',)


def number(value):
    return type(value) in (int, float) and isfinite(value)


@dataclass
class Hp1BatteryPolicy:
    active: bool = False
    attempted: set = field(default_factory=set)
    locked: bool = False
    warned: bool = False
    off_soc: float = 40
    on_soc: float = 50

    def configure(self, settings):
        off, on = settings.get('load_off_soc'), settings.get('load_restore_soc')
        if number(off) and number(on) and 1 <= off < on <= 95:
            self.off_soc, self.on_soc = off, on
            return True
        self.off_soc = self.on_soc = None
        return False

    def export(self):
        return dict(active=self.active, attempted=sorted(self.attempted), locked=self.locked,
                    warned=self.warned)

    @classmethod
    def restore(cls, data):
        if (not isinstance(data, dict) or type(data.get('active')) is not bool
                or type(data.get('locked', False)) is not bool
                or type(data.get('warned', False)) is not bool or not isinstance(data.get('attempted'), list)
                or any(k not in LOADS for k in data['attempted'])):
            raise ValueError('Invalid battery-load episode')
        return cls(data['active'], set(data['attempted']), data.get('locked', False),
                   data.get('warned', False))

    def thresholds(self, hard_floor=None):
        """Fixed household-protection thresholds, independent of Battery Reserve."""
        return min(100, self.off_soc+10), self.off_soc, self.on_soc

    def evaluate(self, *, soc, grid_present, grid_recovered=False, hard_floor=20,
                 occupied_heating=False):
        if (self.off_soc is None or self.on_soc is None or not number(soc)
                or not 0 <= soc <= 100 or type(grid_present) is not bool):
            raise ValueError('Fresh battery and actual grid evidence required')
        soft, critical, recovery = self.thresholds()
        warning = False
        if soc >= recovery or grid_recovered:
            self.active = False
            self.attempted.clear()
            self.locked = False
            self.warned = False
        elif not grid_present and soc <= soft:
            self.active = True
            if not self.warned:
                warning = True
                self.warned = True
        if not grid_present and soc <= critical:
            self.locked = True
        stop = []
        if not grid_present and soc <= critical:
            for key in LOADS:
                stop.append(key)
        return dict(stop=stop, restore_allowed=soc >= recovery or grid_recovered,
                    hp_restore_allowed=(grid_recovered or
                        (occupied_heating and not grid_present and soc >= recovery)),
                    active=self.active, locked=self.locked, warning=warning,
                    soft=soft, critical=critical, recovery=recovery)

    def attempted_stop(self, key):
        if key not in LOADS:
            raise ValueError('Only first-floor HP remains in the legacy battery policy')
        self.attempted.add(key)
