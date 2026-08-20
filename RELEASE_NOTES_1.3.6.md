# EnergyHub 1.3.6 - Retained Hybrid State Cleanup

EnergyHub 1.3.6 is a focused compatibility correction after Home Assistant Core
2026.8.1 exposed a historical retained Hybrid decision reason that exceeded the
255-character entity-state limit.

## Fixed

- Publish the concise initial Hybrid decision state whenever EnergyHub starts.
- Retain that replacement so later Home Assistant restarts do not reload an
  incompatible pre-1.3.4 reason.
- Limit `hybrid_decision_reason` to 255 characters at the MQTT publisher.

## Behavior boundary

The warning affected only the Home Assistant presentation of Hybrid Decision
Reason. The scheduled 23:50 evaluation published the current concise reason and
correctly remained Solar because projected 07:00 SOC exceeded the AHM target.
EnergyHub 1.3.6 does not change AHM calculations, Panic, PV2, Total PV, or any
inverter command.

## Validation status

Repository regression tests cover retained startup replacement and the
publisher boundary. Supervised deployment, EnergyHub restart, retained-state
inspection, and a later Home Assistant Core restart remain required.
