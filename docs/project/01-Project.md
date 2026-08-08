# EnergyHub Project

## What is EnergyHub?

EnergyHub is a local Home Assistant add-on and decision system for residential solar, battery, grid, and flexible-load management.

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
- forecast-aware strategy decisions;
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

EnergyHub 1.0 controls one PowMr inverter and integrates one Home Assistant installation. It supports four strategy states:

- Solar;
- Hybrid Charging;
- Hybrid Grid Hold;
- Panic.

The former Away Mode prototype has been removed. EnergyHub 1.1 adds reserve-only smart-plug OFF protection but never starts a thermal load. Automatic **Smart Thermal Energy** remains deferred to 1.5 and will not be tied only to occupancy.

## Current status

Status as of 2026-08-06:

- EnergyHub 1.0.2 tagged, released, and tested;
- 1.0 functional audit and selected Medium corrections complete;
- real 23:50, midnight, rebuild, and host-restart validation complete;
- 1.0.2 is the compatibility baseline for 1.x;
- Zigbee2MQTT and two paired heat-pump plugs validated for manual monitoring/control;
- dedicated Heat Pumps and Water Systems dashboards deployed and observed;
- matching three-floor auto-off controls and local consumption history added;
- reserve-only boiler and heat-pump OFF guards prepared for final supervised 1.1.0 validation;
- automatic Smart Thermal starts remain deferred to 1.5.

## Product pillars

1. **Autonomy** — normal decisions happen without manual inverter configuration.
2. **Safety** — writes are bounded, verified where possible, and recoverable.
3. **Explainability** — decisions and failures have visible reasons.
4. **Local first** — core operation does not depend on a cloud control service.
5. **Progressive capability** — vendor independence and broader HEMS functionality are directions, not false current claims.
6. **Human outcomes** — strategy names and dashboards describe what the house is doing.

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
