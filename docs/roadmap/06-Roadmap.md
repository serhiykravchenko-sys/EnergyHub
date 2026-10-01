# EnergyHub roadmap

Plans are not shipped capabilities. Version boundaries may change as hardware,
testing and household evidence become available.

## Current 2.x closure

EnergyHub 2.4.12 / Family Assistant 2.4.15 combine a continuous battery reserve,
forecast/weather/grid inputs, guarded overload/outage load management, native
Smart Heating and outbound Telegram explanations. Routine 24-hour monitoring
passed; extended cold-weather heating observations remain necessary.
See [release evidence](../validation/RELEASE_2.4.12.md).

| Direction | Technical work | What the household gets |
| --- | --- | --- |
| 3.x — sensors and diagnostics | CO/CO2 integration, verified BMS readings, telemetry/recovery evidence; flexible heating policies | Clearer air/battery warnings and heating choices: family-managed, solar-only, and later scheduled comfort |
| 4.x — AI companion / Mission Control | System-aware explanations, Ukrainian/English chat, structured authorized intents; voice later | Ask why a decision happened, request settings or appliance timers without learning technical menus |
| 5.x — smart EV charging | Vehicle/charger integration, departure energy target, solar and approved low-cost grid charging | “Enough energy for tomorrow's trip by 08:00” within agreed limits |
| 6.x — tariff and export planning | Multiple cheap slots, dynamic prices, optional contract/hardware-specific export and Net Billing | Optimize import/export costs without sacrificing the household reserve |
| Later — wider hardware support | Verified adapters and per-installation capability checks | Reuse the policy on more compatible installations |

## Cross-cutting work

Recorded-day replay, clearer explanations, privacy-safe diagnostic bundles and
hardware-specific commissioning support every phase. An AI interface must
request validated intents, never raw inverter or relay commands. Certified
CO alarms remain independent life-safety devices; HA notifications are not a
replacement. Fault recovery starts with evidence and bounded verified actions,
not blanket automatic restarts.

Current Telegram messages are outbound-only. EV charging, AI control and
Net Billing are future work, not features of this 2.x release.
