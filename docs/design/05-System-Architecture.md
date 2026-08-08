# EnergyHub System Architecture

## Overview

EnergyHub connects the physical energy system, Home Assistant, MQTT, decision services, and persistent state.

![EnergyHub technical overview](../Images/Infographic%E2%84%962_details.png)

The infographic is an implementation-level map of the current 1.0 release candidate. It should be read together with [Developer Architecture](10-Developer-Architecture.md) for file-by-file responsibilities and extension guidance.

## External systems

### PowMr 10.2M inverter

- local USB-RS232;
- PI30MAX protocol;
- `mpp-solar` command-line adapter;
- default telemetry poll every 10 seconds;
- QPIWS and QPIRI reads every 60 seconds;
- one serial lock prevents concurrent `mpp-solar` processes.

### Home Assistant

- owns the user experience, schedules, helpers, scripts, notifications, and selected household automations;
- publishes control and forecast inputs through MQTT;
- consumes EnergyHub MQTT Discovery and state.

### Mosquitto MQTT

MQTT is the integration bus between EnergyHub and Home Assistant.

### Solcast

Home Assistant publishes live Today and Tomorrow forecasts to EnergyHub. Scheduled daily values are also included in the atomic Daily Summary snapshot.

## Core layers

### 1. Adapter layer

`app/adapters/powmr.py` converts local command execution into four adapter operations:

- read telemetry;
- read warnings;
- read settings;
- write output/charger source priority.

The adapter does not decide strategies.

### 2. Telemetry and state

`TelemetryService`:

- validates required telemetry fields;
- publishes raw inverter sensors;
- creates a normalized `InverterState`;
- persists the latest valid raw snapshot at most once per minute.

`GridMonitor` derives current grid availability from normalized inverter state.

### 3. Health and reliability

Services:

- `CommunicationWatchdog`;
- `HealthMonitor`;
- `BatteryHealthMonitor`;
- `TelemetryFreshnessMonitor`;
- `InverterHealthMonitor`;
- `SystemHealthMonitor`.

System Health aggregates communication, battery, freshness, and inverter-warning state.

### 4. Knowledge and history

- `GridHistoryService` stores 48 hours of grid transition events.
- `GridStabilityEngine` derives Grid Confidence.
- `GridImportService` estimates current and daily grid import.
- `DailySummaryService` stores one coherent daily energy snapshot and later reconciles the final midnight Grid Import value.

### 5. Decision layer

- `HybridDecisionEngine` calculates the adaptive night target and chooses
  Solar, Hybrid Charging, or Hybrid Grid Hold.
- `PanicDecisionEngine` decides whether daytime reserve protection is required.
- `AutopilotState` is the master permission gate.

Decision services return requests and reasons. They do not write inverter settings.

### 6. Orchestration

`main.py`:

- constructs services;
- connects MQTT;
- receives HA inputs;
- owns the lock-protected one-item mode queue;
- executes the runtime loop;
- triggers periodic reads and decisions;
- monitors strategy targets;
- coordinates persistence reconciliation;
- publishes confirmed transition events.

### 7. Execution

`InverterController`:

- maps strategies to Menu 01 and Menu 16;
- writes with bounded retries;
- verifies Menu 01 through QPIRI;
- remembers ACK-confirmed Menu 16;
- persists confirmed context;
- reconstructs strategy after restart;
- performs bounded Solar recovery after partial failure.

### 8. Publishing

`app/mqtt/publisher.py` owns:

- MQTT client construction and last will;
- Discovery payloads;
- stable default entity IDs;
- state topics;
- notification event publication.

## Data flow

### Telemetry

```text
PowMr QPIGS
→ PowMr adapter
→ TelemetryService
→ normalized InverterState
→ health/history/import/decision services
→ MQTT state
→ Home Assistant
```

### Home Assistant inputs

```text
Home Assistant helper / schedule / Solcast sensor
→ energyhub/input/ha/#
→ MQTT callback
→ stored input or queued request
→ main runtime loop
```

### Strategy execution

```text
Decision result or manual request
→ lock-protected mode queue
→ main.py
→ InverterController
→ POPxx / PCPxx
→ ACK + Menu 01 QPIRI verification
→ confirmed mode
→ MQTT state and notification event
```

## Operating strategies

| Mode | Menu 01 | Menu 16 | Exit |
|---|---|---|---|
| Solar | SBU | OSO | default |
| Hybrid Charging | SUB | SNU | adaptive SOC target, currently 30-95% |
| Hybrid Grid Hold | SUB | OSO | 07:00 Solar request |
| Panic Charging | SUB | SNU | SOC reaches the 20/60/80/95% effective target |
| Panic Grid Hold | SUB | OSO | AHM takeover at 23:50 |

## Autopilot behavior

Autopilot is stored in Home Assistant and mirrored to EnergyHub via retained MQTT input.

When Autopilot becomes disabled:

- if the current strategy is active, unknown, inconsistent, transitioning, or failed, one `safe_solar` request is queued;
- that request cannot be overwritten by an ordinary request;
- after Solar recovery, EnergyHub performs no further automatic strategy changes.

## Forecast ownership

Two forecast paths are intentionally separate:

### Live decision inputs

- `solar_forecast_today_live`;
- `solar_forecast_tomorrow_live`.

They update whenever Solcast changes and provide Panic inputs plus contextual
forecast totals. Adaptive Hybrid receives a separate retained plan derived by
Home Assistant from tomorrow's detailed hourly Solcast forecast.

### Daily Summary inputs

Scheduled retained inputs and the 23:51 atomic JSON payload provide a coherent historical snapshot. Individual retained input updates never create a Daily Summary snapshot.

## Grid Confidence

```text
weighted availability = (availability 24h + availability 48h) / 2
```

Thresholds:

- normal: ≥ 90%;
- unstable: ≥ 60%;
- risk: ≥ 30%;
- panic: < 30%.

## Grid Import architecture

Accounting is active only for confirmed SUB-based modes:

- Hybrid Charging;
- Hybrid Grid Hold;
- Panic Charging;
- Panic Grid Hold.

The service stores separate house and battery contributions. At midnight it:

1. closes the previous date;
2. queues a persistent finalization record;
3. resets the new day;
4. asks Daily Summary to update the previous date;
5. acknowledges the queue item only after a valid reconciliation result.

This hand-off survives an add-on restart.

## Availability architecture

### `energyhub/status`

Used by EnergyHub intelligence and diagnostic sensors.

### `powmr/status`

Used by raw inverter telemetry. It becomes offline when a valid inverter response is unavailable.

Raw sensors require both topics online. EnergyHub diagnostic sensors require only the process topic.

## Persistence

All current service JSON writes use the shared atomic writer.

| File | Save behavior |
|---|---|
| controller state | immediately on confirmed/remembered strategy changes |
| grid history | immediately on grid transition |
| daily summary | on snapshot/finalization |
| grid import | immediately at important boundaries, otherwise at most once per minute |
| raw telemetry snapshot | at most once per minute |

## Restart reconstruction

The current inverter exposes Menu 01 through QPIRI but not Menu 16.

EnergyHub reconstructs from:

```text
actual Menu 01
+ persisted ACK-confirmed Menu 16
+ persisted confirmed mode
+ persisted Panic target
+ persisted AHM target and dated morning debt
```

Recognized combinations:

- SBU + OSO → Solar;
- SUB + OSO + valid Hybrid context → Hybrid Grid Hold;
- SUB + OSO + valid Panic context → Panic Grid Hold;
- SUB + SNU + persisted Panic target/context → Panic;
- SUB + SNU + Hybrid context → Hybrid Charging.

Ambiguous or inconsistent state is not silently treated as correct. With Autopilot enabled, one safe Solar recovery is queued.

## Current hardware boundary

Known limitations:

- PV2 telemetry is unavailable through the verified protocol path;
- output 2 and lifetime energy counters are unavailable;
- Menu 16 cannot be read back;
- direct reliable grid import power is unavailable;
- Grid Import is estimated;
- the current adapter supports one PowMr model/protocol path.

## Future architecture

- **1.1:** add Zigbee2MQTT-backed smart-plug monitoring, focused dashboards, manual auto-off controls, and Home Assistant reserve-only OFF guards. Zigbee2MQTT owns coordinator/device communication; Home Assistant owns user controls and the narrow reserve automations; the EnergyHub inverter runtime remains unchanged.
- **1.2:** move strategy values into validated configuration.
- **1.3:** formalize recovery ownership and external watchdog behavior.
- **1.4:** add secure remote operations and Telegram.
- **1.5:** introduce a capability-based Smart Thermal controller for tested automatic multi-load operation.
- **2.x:** separate policy from vendor adapters more completely.
