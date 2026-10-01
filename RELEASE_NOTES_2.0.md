# EnergyHub 2.0 — Load Protection Foundation

EnergyHub 2.0 begins the new feature line with an observer-only Peak Load
Guard. It watches the inverter's native Load %, active power, apparent power,
and native overload warning, then explains what it would do. It never switches
a smart plug in this release.

## Dry Run policy

- Start a recommendation cycle at 85% native inverter load or on a newly
  observed native overload warning.
- Recommend participating loads sequentially in this order: water pump, water
  boiler, second-floor heat pump, first-floor heat pump, third-floor heat pump,
  microwave.
- Continue until the observed participant power could move the triggering load
  toward 75%. An ON device with 0 W remains in the ordered recommendation but
  contributes no estimated reduction.
- At 60%, recommend restoring only the states recorded at the start of the
  cycle, in the same order.
- Produce no recommendation when inverter telemetry or the Home Assistant
  participant snapshot is stale.

## User-visible behavior

Mission Control shows the Dry Run state, thresholds, participant order, live
plug state/power, current recommendation, and restoration condition. Telegram
Family Assistant 2.0.0 sends Ukrainian explanations for recommendation and
recovery events and explicitly says EnergyHub changed nothing.

## Safety boundary

The 85/75/60 values are a visible Dry Run policy chosen for observation, not a
certified inverter limit. Automatic switching remains outside 2.0. Before a
later release can control plugs, recorded 1.3.10+ faults and warning episodes
must support the thresholds, and attended tests must validate command
acknowledgement, actual power reduction, ownership, minimum ON/OFF time,
compressor cooldown, partial failure, restart reconstruction, and conservative
restoration.

This preparation does not commit, push, deploy, restart Home Assistant, or
publish a release.
