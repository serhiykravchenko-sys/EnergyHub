# EnergyHub Developer Architecture

## Purpose

This document maps the current implementation to runtime responsibilities. It is intended for developers who need to modify, test, or reconstruct EnergyHub.

![Technical architecture](Images/Infographic%E2%84%962_details.png)

## Runtime entry point

`addon/app/main.py` constructs all services and owns the process lifecycle.

Main responsibilities:

- load add-on options;
- construct adapter, services, and publishers;
- configure MQTT callbacks;
- publish Discovery and initial state;
- maintain the one-item mode request queue;
- run the telemetry loop;
- schedule QPIWS/QPIRI reads;
- trigger decisions;
- monitor target SOCs;
- reconcile day finalizations;
- publish confirmed events.

## Package map

```text
app/
  adapters/
    powmr.py
  models/
    inverter_state.py
  mqtt/
    publisher.py
  services/
    autopilot.py
    battery_health.py
    daily_summary.py
    event_bus.py
    grid_history.py
    grid_import.py
    grid_monitor.py
    grid_stability.py
    health_monitor.py
    hybrid_decision.py
    inverter_controller.py
    inverter_health.py
    panic_decision.py
    system_health.py
    telemetry.py
    telemetry_freshness.py
    watchdog.py
  utils/
    json_store.py
    logger.py
  config.py
  main.py
```

## Adapter

### `PowMrLocalAdapter`

Builds commands as:

```text
mpp-solar -p <serial> -P <protocol> -c <command> -o json
```

Properties:

- 25-second subprocess timeout;
- JSON output;
- one `threading.Lock` around serial command execution;
- adapter methods return protocol-level data or ACK booleans.

## Normalized state

`InverterState` contains:

- `valid`;
- `grid_available`;
- battery SOC, voltage, current;
- PV power;
- load power;
- raw telemetry.

Grid availability is currently derived from AC input voltage greater than 180 V in normalized telemetry. The family dashboard uses the actual voltage and shows online when it is above 1 V because a stabilizer supplies approximately 220 V whenever the upstream grid exists.

## MQTT threading and queue

Paho invokes MQTT callbacks in its network thread. The main loop consumes mode requests.

The queue:

- has `maxsize=1`;
- is protected by `mode_request_lock` during read/replace/write;
- stores `mode` and optional notification context;
- gives `safe_solar` priority.

This is not a general work queue. It represents the latest allowed strategy request, except that a pending safety recovery is preserved.

## MQTT input topics

Prefix:

```text
energyhub/input/ha/#
```

Current inputs:

| Suffix | Retained | Purpose |
|---|---:|---|
| `autopilot` | yes | master permission state |
| `inverter_mode` | no | `evaluate_hybrid`, `solar`, `panic` and supported requests |
| `solar_forecast_today_live` | yes | live Panic forecast |
| `solar_forecast_tomorrow_live` | yes | live Hybrid forecast |
| `daily_house_consumption` | yes | scheduled consumption input |
| `solar_forecast_today` | yes | scheduled Daily Summary input |
| `solar_forecast_tomorrow` | yes | scheduled/fallback forecast input |
| `daily_solar_surplus_estimated` | yes | scheduled Daily Summary input |
| `daily_summary_snapshot` | yes | atomic JSON historical snapshot |

## Runtime cadence

| Task | Cadence |
|---|---|
| QPIGS telemetry | configured, default 10 seconds |
| QPIWS warnings | 60 seconds |
| QPIRI settings | 60 seconds |
| automatic Panic evaluation | 15 minutes, plus explicit reevaluation events |
| raw telemetry disk snapshot | at most 60 seconds |
| incremental Grid Import save | at most 60 seconds |
| Hybrid evaluation | HA trigger at 23:50 |
| Daily Summary atomic snapshot | HA trigger at 23:51 |
| Solar restoration | HA trigger at 07:00 |

## Startup sequence

1. Load options.
2. Load persisted Inverter Controller, Grid History, Grid Import, and Daily Summary state.
3. Connect MQTT.
4. Publish Discovery.
5. Subscribe to HA input prefix.
6. Publish EnergyHub process online and inverter telemetry offline.
7. Receive retained Autopilot and forecast inputs.
8. Read QPIGS.
9. Read QPIRI.
10. Reconstruct strategy.
11. Accept consistent state without writes, or queue one safe Solar recovery if Autopilot is enabled and reconstruction is incomplete.

Startup recovery waits for both:

- QPIRI reconstruction completion;
- retained Autopilot state reception.

## Telemetry path

`TelemetryService.create_state()` validates required data and converts values.

A valid sample:

- publishes all configured raw sensors;
- publishes `powmr/status=online`;
- updates the raw snapshot;
- feeds health, history, import, decisions, and event bus.

An invalid sample:

- increments Communication Watchdog errors;
- publishes raw inverter availability offline;
- leaves EnergyHub diagnostics available.

## Health services

### Communication Watchdog

States:

- starting;
- online;
- recovering;
- stale;
- offline.

### Battery Health

Current rules:

- missing/invalid SOC → warning;
- SOC below 15% → warning;
- absolute SOC jump of at least 2 percentage points while both readings are at or below 95% → warning.

This is a warning service, not yet a complete telemetry quarantine layer.

### Telemetry Freshness

- no valid telemetry → stale;
- last valid telemetry age at least 60 seconds → stale;
- otherwise fresh.

Unchanged load duration is published separately.

### Inverter Health

QPIWS values equal to `1` are treated as active warnings, excluding command metadata and reserved fields.

### System Health

- communication offline/unavailable → unavailable;
- starting/recovering/stale or any component warning → warning;
- otherwise normal.

## Inverter Controller

### Constants

- write attempts: 3;
- retry delay: 1 second;
- settle delay: 2 seconds;
- controller state schema: 1.

### Menu 01

`set_output_priority()`:

1. sends POP command;
2. requires ACK;
3. reads QPIRI up to the configured verification attempts;
4. compares raw `output_source_priority` with the expected value;
5. returns success only after a match.

### Menu 16

`set_charger_priority()`:

1. sends PCP command;
2. requires ACK;
3. stores `known_charger_priority`;
4. persists immediately.

There is no independent read-back.

### Strategy transitions

#### Solar

Write OSO, then SBU. Confirm only when both succeed.

#### Hybrid Charging

Write/verify SUB, then ACK-confirm SNU. On partial failure, attempt Solar recovery.

#### Hybrid Grid Hold

Keep/verify SUB, then ACK-confirm OSO. On either failure, attempt one Solar recovery and preserve combined failure detail if recovery fails.

#### Panic

Persist target, write/verify SUB, ACK-confirm SNU. On partial failure, attempt Solar recovery.

## Decision engines

### Hybrid

Pure input/output service. See [Decision Engine](DECISION_ENGINE.md).

### Panic

Pure input/output service with time-window checks. The current service does not receive live PV power.

## Target monitoring

The main loop monitors confirmed modes:

- Hybrid Charging + SOC ≥ 80 → enter Grid Hold;
- Panic + SOC ≥ target → restore Solar;
- successful Panic exit requests an immediate reevaluation.

## Notifications

Decision context is attached to the queued request. After transition processing:

- success → event type `automatic_mode_activation`;
- failure → event type `automatic_mode_activation_failed`, including current mode and error.

No activation event is published at decision time.

## Persistence internals

`atomic_write_json()` creates a temporary file beside the target, flushes and fsyncs it, replaces the target atomically, then fsyncs the directory where supported.

This reduces corruption risk after sudden power loss.

## Daily Summary internals

The service accepts individual numeric inputs but does not snapshot on them.

The atomic JSON snapshot requires:

- current date;
- source timestamp;
- daily house consumption;
- forecast today;
- estimated solar surplus.

A duplicate source timestamp is idempotently accepted.

## Grid Import internals

Schema version: 2.

Tracked fields:

- house energy;
- battery energy;
- current power;
- yesterday total;
- SUB interval start/max SOC;
- already-accounted battery contribution;
- pending day finalizations.

Intervals longer than 60 seconds are not integrated as house energy, preventing a long blocked loop from creating a false jump.

## Entity stability

MQTT Discovery includes:

- stable `unique_id`;
- explicit `default_entity_id` for fresh HA installations;
- process or combined availability as appropriate.

Existing HA registry IDs are not automatically renamed by `default_entity_id`; migrations must preserve unique ID and rename through Home Assistant.

## Known technical debt

- `main.py` is large;
- no executable test suite;
- dependencies are unpinned;
- graceful shutdown is implicit;
- constants are duplicated across services;
- HA owns the 07:00 schedule;
- Grid Import is approximate during daytime SUB with simultaneous PV;
- configuration is not yet user-editable.

## Safe refactoring order

1. Add pure service tests.
2. Add controller tests with a fake adapter.
3. Add queue/notification integration tests.
4. Extract lifecycle coordinators one responsibility at a time.
5. Preserve MQTT contracts and persisted schemas.
