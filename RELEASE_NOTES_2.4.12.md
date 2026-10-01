# EnergyHub 2.4.12 — monitored 2.x release

Prepared and deployed on 2026-09-29 with Family Assistant 2.4.15. The homeowner reported the agreed
24-hour monitoring period passed on 2026-10-01 with normal operation and no
new Home Assistant Core/Supervisor errors. This public bundle closes the 2.x release cycle.
See [release validation](docs/validation/RELEASE_2.4.12.md) for observed checks
and remaining hardware-validation limits.

## The 2.x release for homeowners

EnergyHub coordinates solar use, forecast-aware battery reserve, selected
appliances and heating. It uses weather and observed grid reliability to
prepare for outages, protects against inverter overload, and explains important
actions in Home Assistant and Telegram. Family members retain temperature
choices and manual OFF authority. Estimated night/normal grid-import accounting
provides tariff visibility; dynamic tariff planning, EV charging and export
control are future features.

## Corrections

- Home Assistant renders optional numeric MQTT states as `None` when the
  retained source payload is `unknown`, addressing observed Core log errors
  for PV2 sample age and daily solar diagnostics.
- A burst of more than 128 HA external intents no longer latches the Peak Load
  Guard into a permanent `external_intent_overflow` fault. If queue pressure
  evicts an intent for a pending or owned load, that load is quarantined or
  released from EnergyHub ownership, so a family OFF cannot become an
  automatic restore. Other loads remain eligible for protection.
- Malformed persisted Battery Reserve state starts without a recommendation
  instead of crashing the add-on.
- A timeout/error publishes inverter availability `offline` before secondary
  diagnostic work. A failed single safe-Solar recovery is explicitly logged;
  **it is not automatically retried or claimed successful**. The unconfirmed
  mode requires attended inspection, and Family Assistant 2.4.15 reports it.
- The inverter records an uncertain transition before each hardware write.
  An ACKed Menu 16 value or final mode is not claimed confirmed if its state
  cannot be saved. A restart with an unfinished transition refuses to infer
  the old Grid Hold state and suspends automatic Solar recovery pending
  attended verification. Any controller-state save failure also blocks further
  automatic inverter writes in that process. On the Linux add-on host, a failed
  directory sync is treated as a failed save rather than silently accepted.
- If queue pressure evicts a family OFF intent while a restore is pending,
  EnergyHub releases that load's ownership before clearing the pending command.
  A still-fresh HA snapshot from before the family request cannot trigger a
  second restore request, including after journal reload.
- The HA Smart Heating correction preserves the family's temperature, fan and
  Super settings. It clears temporary auto-resume once Heat is confirmed and
  recognizes user OFF requests addressed through `service_data`.
- Automatic protective plug OFF pauses a selected auto-off timer without
  erasing the chosen hours. On a later ON, the full selected duration starts
  again; this is not preservation of the original wall-clock deadline. The
  three timer automations queue their own OFF and reset events so expiry can
  finish clearing the selected hours.
- A missing plug or power entity no longer aborts the entire six-load HA
  snapshot; its timestamp/context evidence remains absent and that load
  cannot pass the normal freshness/control gates.
- The current Smart Heating/load-protection SVG and PNG reflect family-owned
  temperature and fan settings and protective timer behavior.

## Limits and validation required

- Repository tests are not Home Assistant or inverter tests. Confirm MQTT
  numeric states and logs, manual/remote OFF, timer pause and restoration,
  restart behavior, and failed-recovery alert routing in attended tests.
- There is no automatic retry of an unconfirmed inverter transition. Automatic
  reserve control can remain suspended until a person verifies recovery.
- Context ownership across a Home Assistant restart and the complete QPIWS
  response shape still need separate evidence; do not re-baseline ownership
  from a restarted context alone.
- New installations should keep Smart Heating and automatic load actions OFF
  until their own bridge/device checks pass. Extended cold-weather Smart Heating
  observations and rare failed-recovery paths remain open on the reference
  installation; routine monitoring is not evidence of every negative case.
