# EnergyHub 1.3.8

## Added

- Continuous enforcement of the dated 23:50 Adaptive Hybrid target until the
  confirmed morning Solar handover.
- Restart-safe persistence of the active night-plan date.

## Behavior

- Above target: remain Solar.
- At target: enter Hybrid Grid Hold.
- Below target: enter or resume Hybrid Charging.
- Grid absent or telemetry stale: issue no inverter command and reevaluate on
  later fresh telemetry.
- Failed transition: do not repeat the same unchanged request every telemetry
  cycle.

This release does not add a new inverter mode and does not change daytime
Panic ownership.
