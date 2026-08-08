# EnergyHub Manifesto

EnergyHub exists to make a home energy system calmer, safer, and easier to live with.

## The problem

A modern solar home contains an inverter, battery, grid connection, forecasts, tariffs, smart plugs, climate equipment, and many separate applications. Each component exposes data, but the homeowner still has to decide:

- whether the battery should be preserved;
- whether cheap grid electricity should be used tonight;
- whether unstable grid conditions justify building reserve now;
- whether surplus energy can be converted into useful comfort;
- whether the system is healthy or merely silent.

Raw telemetry is not autonomy.

## Our belief

The home should manage ordinary energy decisions by itself while remaining understandable and reversible.

```text
Observe → remember → decide → act → verify → explain
```

## Our promise

EnergyHub should:

- reduce the number of decisions a person must make;
- keep the family informed without demanding constant attention;
- prefer safe, bounded actions over clever but fragile automation;
- make every important automatic decision explainable;
- preserve manual control;
- remain local-first;
- treat hardware truth as more important than software assumptions.

## Autonomous Home

An autonomous home is not one that performs the most automations. It is one that quietly makes the correct routine decisions and asks for attention only when needed.

For EnergyHub 1.0 this means:

- Solar as the normal state;
- cheap-tariff charging only when tomorrow may require it;
- daytime reserve protection when grid conditions deteriorate;
- clear status, reasons, and failure notifications;
- safe reconstruction after restart.

Future Smart Thermal Energy extends the same idea to comfort: use surplus solar or cheap-tariff electricity for heating and cooling regardless of whether the house is occupied.

## Human-first principles

1. **The family sees outcomes.** Engineers may inspect every input and state, but family members should see a clear current strategy and simple controls.
2. **Automation is permissioned.** Autopilot is the explicit master permission for inverter strategy changes.
3. **Failure is visible.** A failed transition must never be reported as activated.
4. **Recovery is bounded.** EnergyHub does not endlessly retry or restart the inverter.
5. **Language is honest.** Estimated values are identified as estimates; ACK-confirmed settings are not described as independently verified.
6. **No fake controls.** A planned feature may be visible, but it must not appear to work before a real controller exists.
7. **Manual actions remain possible.** Automation should assist the homeowner, not lock them out.

## Success metric

EnergyHub succeeds when the household stops thinking about inverter menus and starts thinking in human outcomes:

- the house is protected;
- the battery is prepared;
- cheap energy is used intelligently;
- surplus energy becomes useful;
- unusual conditions are explained.

## Final thought

EnergyHub is not a dashboard around an inverter.

It is the decision layer that turns a collection of energy devices into one understandable home system.
