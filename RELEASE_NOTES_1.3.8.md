# EnergyHub 1.3.8 — Night Target and Heat-Pump Ownership

EnergyHub 1.3.8 keeps the Adaptive Hybrid target authoritative throughout the
night and makes heat-pump ownership understandable to the family.

## Adaptive Hybrid night enforcement

The 23:50 AHM evaluation now persists the date through which its target is
active. Until the confirmed morning Solar handover:

- SOC above target remains Solar;
- SOC exactly at target enters Hybrid Grid Hold;
- SOC below target enters or resumes Hybrid Charging;
- reaching the target uses the existing Hybrid Grid Hold transition;
- an absent grid or stale SOC causes no inverter command.

A failed transition is not retried on every telemetry poll. The unchanged
request is latched until the condition clears or grid availability changes.

The check runs with each fresh local telemetry cycle. It does not introduce a
new public operating mode and does not change daytime Panic ownership.

## Heat-pump ownership

When Grid Confidence is Normal, the grid is present, and telemetry is fresh,
the family controls the heat pumps normally while EnergyHub monitors reserve.

When that trust gate is not met, the selected AHM minimum defines the policy:

- minimum +30 percentage points: request all running participating heat pumps
  OFF once; manual override remains possible;
- minimum +20: latch mandatory OFF and reject later ON requests;
- minimum +40: clear the lockout without starting a heat pump.

EnergyHub never starts a heat pump automatically.

## Telegram Family Assistant 0.1.9

The Ukrainian morning report states either `РУЧНЕ КЕРУВАННЯ` or
`ЗАХИСТ ENERGYHUB`. Persisted downward-crossing warnings follow the selected
AHM minimum at +30, +20, +10, and +0 percentage points. A two-point recovery
margin prevents repeated warnings around the same boundary.

Reserve warnings are relevant to active thermal use: at least one configured
heat pump must be drawing more than the configurable activity threshold (50 W
by default). The message names every active floor and its observed power.
Reserve delivery is quiet from midnight through 08:01; any still-relevant
queued warning is refreshed before later delivery.

Telegram remains outbound-only and has no control authority.
