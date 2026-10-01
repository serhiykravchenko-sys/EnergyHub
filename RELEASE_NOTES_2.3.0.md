# EnergyHub 2.3.0 / Telegram Family Assistant 2.3.0

Prepared 2026-09-12 as a private candidate. Not committed, pushed, deployed, or
published at preparation time.

## Battery Reserve

- Calculation: `min(95, 20 base + forecast allowance + grid allowance + weather allowance)`.
- Forecast deficit adds 20 percentage points using one to three valid completed
  consumption days.
- Grid Confidence adds 0/20/40/60 percentage points for
  Normal/Unstable/Risk/Critical.
- A qualifying UHMC level II/III warning adds 20 percentage points only while
  Grid Confidence is Normal, avoiding duplicate risk allowances.
- Manual mode preserves the selected reserve and EnergyHub recommends only.
- Automatic mode applies a fresh, complete recommendation through a guarded
  Home Assistant automation. Incomplete or stale evidence pauses application.
- Daytime Grid Hold uses the applied reserve and returns to Solar at reserve
  plus 10 percentage points. The 95% cap remains held until the reserve falls.

## Discharge protection

- Independent of Battery Reserve and active only with verified grid absence.
- One family warning at 50%.
- At 40%, disconnect water pump, boiler and three heat pumps; microwave remains
  available. The first-floor heat pump uses native climate OFF.
- Restore EnergyHub-owned states at 60% or after verified grid recovery, subject
  to existing load margin, sequencing, minimum-off-time, ownership and fresh
  telemetry checks.

## Compatibility and deployment

- Existing entity IDs are retained, including historical AHM/Panic internal IDs.
- The load-control bridge moves from schema 4 to schema 5; mixed versions fail
  closed.
- This release changes both add-ons, `configuration.yaml`, `automations.yaml`,
  and the dashboard, so Home Assistant Core stop/check/start is required for the
  reviewed YAML/storage deployment.
