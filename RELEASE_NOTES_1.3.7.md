# EnergyHub 1.3.7 — Early Solar Handover

EnergyHub 1.3.7 adds a small seasonal optimization without changing the
23:50 Adaptive Hybrid calculation. When Hybrid Grid Hold is preserving an
already-reached reserve, EnergyHub may return to Solar once at 06:05 instead
of always waiting until 07:00.

## What changed

- Home Assistant sends the dated Solcast 06:00-07:00 forecast interval at
  06:05.
- EnergyHub independently checks the local time window, request date,
  Autopilot, current strategy, retained target, SOC, grid, telemetry freshness,
  live aligned Total Solar, and forecast energy.
- Solar is requested only from confirmed Hybrid Grid Hold when SOC is at or
  above its target, live Total Solar is at least 300 W, and the forecast
  interval is at least 1.6 kWh.
- Five MQTT diagnostics expose the outcome and evidence on the dashboard.
- The startup night-plan state is presented as `awaiting_evaluation`, with a
  clearer reason and retained-target context.
- Homeowner-facing dashboard wording uses **Adaptive Hybrid Reserve**.
- Home Assistant invalidates an in-progress AHM morning observation after a
  Core restart and publishes it only when the 07:00 initialization completed
  with valid SOC. This prevents partial mornings from training the advisor.

## Conservative boundaries

- Hybrid Charging is never released by this check.
- Missing, stale, invalid, insufficient, or contradictory input causes no
  inverter command.
- The existing Inverter Controller performs and acknowledges the transition.
- A failed transition is reported and does not masquerade as Solar.
- The normal 07:00 Solar handover remains the fallback.
- This release does not start a boiler or heat pump.

## Deployment scope

This is not an add-on-only behavior change. Complete deployment requires the
reviewed `addon/` tree plus the selected Home Assistant automation, helper,
and dashboard files. Updating only the add-on will publish the new entities
but will not schedule the 06:05 forecast request.

Repository preparation does not mean the release is deployed, started,
live-validated, privately pushed, or publicly released.
