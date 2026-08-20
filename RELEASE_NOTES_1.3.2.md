# EnergyHub 1.3.2 — Learned Morning Net Energy

EnergyHub 1.3.2 replaces the fixed morning-consumption estimate when sufficient local history exists.

## Learning

- Capture cumulative house and heat-pump energy at hourly boundaries from 07:00 through 12:00.
- Subtract all three heat-pump deltas from the total house delta.
- Retain 21 days and use the per-interval 75th percentile.
- Require three complete samples for every interval before activation.

## Planning

AHM compares each learned essential-load interval with the aligned Solcast hourly forecast. Solar takeover requires two consecutive hours whose forecast covers expected essential load. Accumulated hourly deficits are converted to SOC using the existing 16 kWh battery and 90% conservative efficiency model.

The selected 20–50% AHM Minimum SOC remains the residual reserve. The existing verified 300 W → 600 W model remains authoritative until learning and forecast inputs are complete.

## Monitoring

Dashboard and MQTT diagnostics expose the active model, fallback reason, samples per interval, expected morning essential load, morning solar and calculated net deficit.

EnergyHub also observes the lowest SOC during each completed 07:00–12:00 morning. At one unchanged slider value, two of three mornings within five SOC points of the reserve produce a one-step increase suggestion; a decrease requires all three mornings to remain at least 20 points above it. Other evidence keeps the setting. Changing the slider starts a new comparable three-morning window. Dashboard and Family Assistant show the same informational result; neither changes the slider or Panic targets.

An unavailable 07:00 SOC or a Home Assistant restart during the observation window invalidates that morning. Incomplete evidence is skipped rather than converted into reserve advice.

## Optional Telegram companion

Telegram Family Assistant 0.1.6 sends a concise morning weather/energy plan plus debounced grid-loss, recovery, Grid Confidence, and AHM reserve-advice notifications. It is outbound-only: it cannot execute Home Assistant or inverter commands. The companion establishes a safe notification surface for future text and voice requests, which will require a separate authenticated and auditable EnergyHub intent gateway.
