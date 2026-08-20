# Energy Hub 1.3.7

## Early Solar handover

- Adds one guarded 06:05 evaluation while confirmed Hybrid Grid Hold is
  active.
- Requires Autopilot, the current request date, local 06:00-07:00 time, fresh
  inverter telemetry, fresh aligned Total Solar, present grid power, retained
  target already met, at least 300 W live Total Solar, and at least 1.6 kWh in
  the 06:00-07:00 Solcast interval.
- Publishes check status, reason, evaluation time, live power, and forecast
  interval energy through MQTT Discovery.
- Keeps Grid Hold unchanged when any gate fails and retains 07:00 as the normal
  Solar fallback.

## Presentation

- Maps the initial internal Hybrid state to `awaiting_evaluation` for Home
  Assistant.
- Explains the next 23:50 evaluation and any retained target without exposing
  an overlong sensor state.

The Home Assistant 06:05 automation is required for the new handover. An
add-on-only update does not schedule it.
