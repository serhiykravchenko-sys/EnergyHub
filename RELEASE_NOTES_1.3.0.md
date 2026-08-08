# EnergyHub 1.3.0 — Coordinated Adaptive Hybrid and Panic

EnergyHub 1.3.0 coordinates planned cheap-night charging with conservative daytime grid-outage recovery.

## Adaptive Hybrid Mode

At 23:50, AHM combines:

- current battery SOC and a conservative 15% overnight allowance;
- the morning gap to the first forecast hour at or above 300 W;
- today's consumption projected onto the aligned 07:00–24:00 interval;
- tomorrow's hourly Solcast production over the same interval;
- a 20% protected reserve, 10% uncertainty margin, 16 kWh battery capacity, and 90% conservative efficiency.

The target is capped at 95%. AHM explicitly takes ownership from any active daytime Panic strategy and chooses Solar, Hybrid Charging, or Hybrid Grid Hold.

## Conservative daytime Panic

From 07:00 until 23:50, Panic uses simple Grid Confidence targets:

| Grid Confidence | Target SOC |
|---|---:|
| normal | 20% |
| unstable | 60% |
| risk | 80% |
| panic | 95% |

If AHM missed its target at 07:00 because grid was unavailable, Panic temporarily inherits that charging debt when it is higher than the Grid Confidence target.

Panic can remain armed while grid is offline. When grid returns it charges immediately, then switches to Panic Grid Hold instead of returning to Solar. AHM ends daytime ownership at 23:50.

## Home Assistant

- Added AHM post-07 consumption, solar, deficit, and SOC diagnostics.
- Added Panic phase, target, target source, Grid Confidence target, and inherited AHM target diagnostics.
- Extended temporary heat-pump manual permission to confirmed grid-backed Panic without enabling automatic heat-pump starts.
- Corrected the Energy Balance Grid Import source.
- Standardized daily chart dates as `dd.MM` and restored pastel chart styling.
- Corrected invalid Home Assistant state-class metadata on snapshot-style energy entities.

## Upgrade and validation

This release changes the add-on runtime and Home Assistant configuration. Build and restart the add-on, deploy the selected Home Assistant YAML/storage files while Core is stopped, run `ha core check`, start Core, and inspect the new MQTT entities and decision dashboard before relying on automatic operation.

EnergyHub still does not automatically start the boiler or any heat pump. Grid Import remains an informational estimate rather than a billing-grade meter.
