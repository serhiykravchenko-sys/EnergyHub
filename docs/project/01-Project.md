# EnergyHub Project

## What is EnergyHub?

**Adaptive solar planning. Smart tariff use. Outage-ready reserve.**

EnergyHub is a local-first, resilience-aware Home Assistant energy controller for residential solar, battery, grid, and flexible-load management. The current validated hardware target is the PowMr 10.2M / POW-HVM10.2M hybrid inverter.

The current installation uses:

- PowMr 10.2M inverter;
- PI30MAX protocol over USB-RS232;
- 16 kWh LiFePO4 battery;
- Home Assistant OS on Raspberry Pi;
- Mosquitto MQTT;
- Solcast forecasts;
- Home Assistant helpers, automations, scripts, dashboards, and smart plugs.

## Why it exists

The inverter exposes settings and telemetry, but it does not understand household intent. EnergyHub adds:

- historical grid reliability;
- hourly forecast-aware strategy decisions;
- economical use of a configured cheap-tariff window;
- emergency reserve protection;
- persistent operating context;
- explainable Home Assistant status;
- a path toward smart thermal and other flexible loads.

## Users

### Homeowners and families

They need simple answers:

- What mode is active?
- Is the grid available?
- Is the battery reserve healthy?
- Why did EnergyHub charge from the grid?
- Is an action required?

### Developers and advanced users

They need:

- raw telemetry;
- decision inputs and reasons;
- controller state;
- transition logs;
- health and persistence details;
- reproducible MQTT entity IDs;
- versioned configuration.

### Installers and integrators

Future releases should allow strategy configuration without modifying Python code and should separate hardware capabilities from policy parameters.

## Current product scope

EnergyHub 1.3 controls one PowMr inverter and integrates one Home Assistant installation. Its coordinated strategy states are:

- Solar;
- Hybrid Charging;
- Hybrid Grid Hold;
- Panic Charging;
- Panic Grid Hold.

Adaptive Hybrid owns the overnight plan and calculates a configurable target from the selected 20–50% minimum SOC, an effective forecast-ramp-aware morning gap, and the aligned post-07:00 consumption/solar balance. Conservative Panic owns daytime reserve protection and uses the higher of the applicable Grid Confidence target or a genuinely missed morning target.

The former Away Mode prototype has been removed. EnergyHub includes reserve-only smart-plug OFF protection but never starts a thermal load in 1.3. Automatic **Smart Thermal Energy** and EV charging remain future milestones.

## Current status

Status as of 2026-08-26:

- EnergyHub 1.0.2 tagged, released, and tested;
- EnergyHub 1.3.0 released and validated; the coordinated 1.3.1–1.3.14 line
  added configurable/learned reserve planning, PV2/Total PV, early Solar,
  persistent diagnostics, tariff accounting, and Normal-grid reserve
  hysteresis; 1.3.14 is the monitored closure release selected for public
  promotion;
- Adaptive Hybrid and Conservative Panic coordinated with explicit 07:00 and 23:50 ownership handoffs;
- hourly post-07:00 forecast alignment, adaptive target persistence, offline Panic waiting, and Panic Grid Hold implemented;
- Zigbee2MQTT and two paired heat-pump plugs validated for manual monitoring/control;
- dedicated Heat Pumps and Water Systems dashboards deployed and observed;
- matching three-floor auto-off controls and local consumption history added;
- reserve-only boiler and heat-pump OFF guards implemented without automatic starts;
- automatic Smart Thermal starts remain deferred to 2.0.

## Product pillars

1. **Autonomy** — normal decisions happen without manual inverter configuration.
2. **Safety** — writes are bounded, verified where possible, and recoverable.
3. **Explainability** — decisions and failures have visible reasons.
4. **Local first** — core operation does not depend on a cloud control service.
5. **Progressive capability** — vendor independence and broader HEMS functionality are directions, not false current claims.
6. **Human outcomes** — strategy names and dashboards describe what the house is doing.
7. **Resilience-constrained economy** — tariff and export opportunities must remain inside protected-reserve and hardware-safety boundaries.

## Non-goals for 1.0

EnergyHub 1.0 is not:

- billing-grade metering;
- a universal inverter driver;
- an automatic inverter reboot system;
- a full economic optimizer;
- a complete thermal controller;
- an external multi-user product with finished onboarding.

## Long-term goal

EnergyHub should evolve from one-house automation into a capability-based Home Energy Management System that can coordinate generation, storage, tariffs, comfort, and flexible loads without losing local control or explainability.

See [Project Positioning](POSITIONING.md) for the current public message, evidence requirements, and claims that remain future work.
