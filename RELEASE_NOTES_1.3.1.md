# EnergyHub 1.3.1 — Configurable AHM Reserve

EnergyHub 1.3.1 makes the Adaptive Hybrid minimum reserve explicit and gives a confirmed rising solar forecast one hour of morning-gap credit.

## AHM Minimum SOC

Home Assistant provides a 20–50% setting in 5% steps:

- 20% — economy;
- 30% — balanced;
- 40% — conservative;
- 50% — very conservative for highly unreliable grid conditions.

This setting belongs only to AHM. Panic retains its separate Grid Confidence targets of 20/60/80/95%.

## Confirmed solar ramp

AHM keeps the first forecast hour at or above 300 W as an audit value. If the following hourly forecast is at least 600 W, effective solar support moves one hour earlier:

```text
raw morning gap = hours from 07:00 to first 300 W forecast
ramp credit = 1 hour when next forecast is at least 600 W
effective morning gap = raw morning gap - ramp credit

target SOC = min(95,
    selected minimum SOC
    + max(effective morning SOC, daytime deficit SOC))
```

EnergyHub independently validates the two forecast power values before applying the credit. Missing or inconsistent inputs retain the uncredited morning gap; missing hourly forecast still uses the five-hour fallback.

At 23:50, SOC below the target starts Hybrid Charging. SOC already at or above the target starts Hybrid Grid Hold so the selected floor is actively protected until Solar is restored at 07:00.

## Explainability

Retained dashboard diagnostics show the selected minimum, raw and effective gaps, both forecast powers, ramp confirmation, credit, effective support time, and final calculation captured for the 23:50 decision.

## Upgrade notes

The update adds a Home Assistant `input_number` helper, automation, dashboard entities, and new MQTT Discovery sensors. Stop Home Assistant Core before deploying the helper storage and dashboard, run `ha core check`, then start Core and rebuild/start the Energy Hub app.
