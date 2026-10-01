"""Battery-load policy, independent of charging targets and grid confidence.

The shared load controller owns commands/acknowledgements. This policy owns only
the discharge episode and one-time soft shedding. Never infer grid presence from
a reliability label. Unknown evidence must be rejected by the caller.
"""
from dataclasses import dataclass, field
from math import isfinite

LOADS = ('water_pump', 'water_boiler', 'heat_pump_floor_1',
         'heat_pump_floor_2', 'heat_pump_floor_3')


def number(value):
    return type(value) in (int, float) and isfinite(value)


@dataclass
class BatteryLoadPolicy:
    active: bool = False
    attempted: set = field(default_factory=set)
    locked: bool = False
    warned: bool = False

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

    @staticmethod
    def thresholds(hard_floor=None):
        """Fixed household-protection thresholds, independent of Battery Reserve."""
        return 50, 40, 60

    def evaluate(self, *, soc, grid_present, grid_recovered=False, hard_floor=20,
                 occupied_heating=False):
        if not number(soc) or not 0 <= soc <= 100 or type(grid_present) is not bool:
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
                        (occupied_heating and not grid_present and soc >= 50)),
                    active=self.active, locked=self.locked, warning=warning,
                    soft=soft, critical=critical, recovery=recovery)

    def attempted_stop(self, key):
        if key not in LOADS:
            raise ValueError('Microwave is not a battery-protection participant')
        self.attempted.add(key)
