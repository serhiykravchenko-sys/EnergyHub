"""Read-only shared solar thresholds, including the pre-helper HA baseline."""
from math import isfinite
from .report import number

START = 'input_number.energyhub_solar_start_power'
PAUSE = 'input_number.energyhub_solar_pause_power'


def thresholds(entities):
    if START not in entities and PAUSE not in entities:
        return 600, 400  # Older HA control before the coordinated package update.
    start = number((entities.get(START) or {}).get('state'))
    pause = number((entities.get(PAUSE) or {}).get('state'))
    if (start is not None and pause is not None and isfinite(start) and isfinite(pause)
            and 0 <= pause < start <= 10000):
        return start, pause
    return None
