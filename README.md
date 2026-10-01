# EnergyHub — Solar Economy, Battery Reserve and a Connected Home

**Make the most of solar energy while keeping battery reserve for power outages.**

EnergyHub combines solar-generation forecasts, weather warnings, household
consumption and observed grid reliability to decide when to use, preserve or
replenish the battery. It coordinates selected appliances and heating,
protects against inverter overload, and explains important decisions through
Home Assistant dashboards and optional Telegram reports.

The goal is **economy when conditions allow, preparedness when conditions
demand it**. EnergyHub connects the energy system with supported smart-home
devices so the house can respond together.

## What you get today

| Capability | What it means at home |
| --- | --- |
| Forecast-aware Battery Reserve | Prepare for low solar generation, weather risks and unreliable grid supply instead of choosing a battery minimum blindly. Keep manual control or enable guarded automatic recommendations. |
| Solar, battery and grid coordination | Use solar and battery first, replenish the applied reserve when needed, and hold that reserve with the grid available. |
| Overload and outage-load protection | Pause selected appliances one at a time when inverter load is too high or an outage is draining the battery; restore only when the required checks pass. |
| Smart Heating | Coordinate one supported heat pump with solar, battery and load conditions while preserving the family's temperature, fan settings and manual OFF choice. |
| Telegram briefings and alerts | Receive the morning outlook, power-loss/recovery notices and important actions in an existing messenger, without another dedicated monitoring app. Home Assistant remains the setup and dashboard platform. |
| Diagnostics and tariff visibility | See PV1/PV2/Total PV, grid history, SOC anomalies, inverter faults and estimated night/normal grid-import costs. |

The current platform is a local Home Assistant controller developed and tested
on a **PowMr 10.2M / POW-HVM10.2M reference installation**. Other inverter models
and household devices require their own validated adapters and configuration.

## Release and validation

This release pairs **EnergyHub 2.4.12** with
**Telegram Family Assistant 2.4.15**. It was deployed and started on
2026-09-29. On 2026-10-01 the homeowner reported the agreed 24-hour observation
period passed with normal operation and no new Home Assistant Core or
Supervisor errors. Supplied startup evidence confirmed MQTT, PV2,
Solar reconstruction without inverter writes, and a real grid outage.

Routine monitoring does not establish
every rare fault or hardware-recovery scenario. Smart Heating still needs
extended cold-weather observations, and each new installation must validate
its own devices before enabling automatic control.

See [EnergyHub release notes](RELEASE_NOTES_2.4.12.md),
[Family Assistant release notes](RELEASE_NOTES_FAMILY_2.4.15.md), and
[release validation](docs/validation/RELEASE_2.4.12.md).

## How the current control works

- **One Battery Reserve, all day:** the family selects 20–95% in five-point
  steps. Manual mode preserves that choice. Automatic mode applies only an
  available, complete, recently reevaluated recommendation.
- **Reserve recommendation:** a 20% policy base plus a solar-deficit allowance,
  observed grid-reliability allowance, qualifying official weather warning,
  and enabled Smart Heating allowance, capped at 95%. The 23:52 preliminary
  forecast and 05:00 revision refresh forecast evidence; they do not create
  separate night and day control owners.
- **Inverter strategy:** Solar First uses SBU/OSO. With grid available, SOC
  below the applied reserve requests SUB/SNU charging; at the reserve it holds
  with SUB/OSO. Solar resumes at reserve +10 points, except the 95% cap remains
  held until the reserve decreases. With grid absent, the controller waits.
- **Overload protection:** 85% load or a valid recent overload warning triggers
  sequential shedding toward 75%. Recovery requires load below 50% for five
  minutes, headroom, retained ownership and acknowledgement. A dashboard
  switch selects automatic control or warnings only.
- **Outage battery protection:** actual grid absence drives a 50% SOC warning,
  flexible-load pause at 40%, and guarded restoration at 60% or verified grid
  recovery. An owned Smart Heating pause can restore in Eco at 50%.
- **Smart Heating:** native Heat/OFF on the supported first-floor climate,
  Quiet from 23:00–08:00, Eco without grid, and optional solar-conditioned
  operation. Family temperature, fan and Super choices are preserved. Other
  heat pumps remain family/timer loads except under protection.

Protection depends on fresh telemetry and an allowlisted Home Assistant
bridge. Commands expire, require acknowledgement and are checked against
observed state. Manual intervention releases load ownership. An uncertain
inverter transition is recorded before hardware writes; persistence or
recovery failure requires attended verification and produces an explanation.

The tariff feature separates **estimated** grid import into one configured
night window and normal periods. Battery Reserve may require grid charging
outside cheap hours. Deadline-aware cheap-slot scheduling, dynamic prices and
export optimization are future work; measured savings are not claimed.

See the [Battery Reserve contract](docs/design/BATTERY_RESERVE_CURRENT.md),
[Smart Heating policy](docs/design/SMART_HEATING_2.4.md), and
[load-control contract](docs/design/PEAK_LOAD_CONTROL.md) for exact gates.

## Understand the system in pictures

These version-neutral diagrams describe the current architecture and policy.
Each has an editable SVG source in the [diagram index](docs/Images/README.md).

![EnergyHub system architecture](docs/Images/system-architecture-current.png)

![Control ownership and safety boundaries](docs/Images/control-boundaries-current.png)

![Continuous Battery Reserve](docs/Images/battery-reserve-current.png)

![Smart Heating and load protection](docs/Images/smart-heating-load-protection.png)

![Telemetry, memory and recovery](docs/Images/telemetry-resilience-current.png)

## Installation and supported platform

Start with [Installation and Upgrade](docs/operations/INSTALLATION.md).
The reference platform uses:

- Home Assistant OS with Supervisor/Apps on Raspberry Pi 4 (aarch64);
- the verified PowMr PI30MAX inverter and persistent FTDI USB–RS232 path;
- Mosquitto and the Home Assistant MQTT integration;
- optional read-only PV2 Modbus registers 4563–4564 on the verified firmware;
- separately configured Home Assistant devices, helpers and automation bridge;
- optional Solcast forecast data and Telegram Family Assistant.

The app can publish inverter telemetry without enabling household load control.
Load protection and Smart Heating need a reviewed HA bridge and verified device
mapping. Reference HA configuration is an integration example, not a complete
replacement for another home's configuration.

Menu 01 is independently read back through QPIRI. Menu 16 is ACK-confirmed;
there is no supported independent readback on the reference inverter.
PV2 runs through the same serialized connection with bounded read-only access.

EnergyHub's control runs locally. Forecasts, official warnings and Telegram
delivery use external services; their availability is separate from local
inverter communication. The Telegram companion currently sends reports and
alerts and supplies normalized weather evidence. It does not accept commands.

## Where we are going

| Planned direction | Homeowner benefit |
| --- | --- |
| **3.x — Indoor sensors, BMS and flexible heating** | Understand indoor conditions and battery evidence, receive more useful health alerts, and choose family-controlled or scheduled heating policies. |
| **4.x — AI companion and Mission Control** | Ask why EnergyHub acted, discuss settings, and request approved timers or schedules in Ukrainian or English through Telegram; voice follows validated text. |
| **5.x — Smart EV charging** | Request enough charge by departure, using solar and approved cheap electricity while protecting the house battery and inverter capacity. |
| **6.x — Tariff and optional export management** | Plan around multiple cheap periods and later dynamic prices; where compatible hardware and local contracts allow it, evaluate using, storing or exporting energy to help reduce the monthly bill. |
| **Later — More homes and inverter adapters** | Bring the same ideas to individually validated equipment without assuming every installation behaves identically. |

These are plans, not shipped features. AI interfaces will request authenticated,
expiring EnergyHub intents; the deterministic controller will remain responsible
for validating device actions. EV/export features require compatible hardware
and, for export, applicable local rules and contracts.

See the [Roadmap](docs/roadmap/06-Roadmap.md) and
[positioning](docs/project/POSITIONING.md).

## Documentation and development

- [Documentation map](docs/README.md)
- [System architecture](docs/design/05-System-Architecture.md)
- [Developer architecture](docs/design/10-Developer-Architecture.md)
- [Verified PowMr commands](docs/hardware/powmr-10-2m-verified-commands.md)
- [Verified PV2 telemetry](docs/hardware/powmr-10-2m-modbus-telemetry.md)
- [Telegram Family Assistant](telegram-family-bot/README.md)
- [Changelog](CHANGELOG.md)

Both app Docker builds run their unit suites. Repository tests cover simulated
hardware, persistence, telemetry and command failures; live observations are
recorded separately. The separate Telegram Threat Monitor project is not part
of EnergyHub.
