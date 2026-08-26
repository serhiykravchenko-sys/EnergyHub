# EnergyHub Developer Architecture

## Purpose

This document maps the current implementation to runtime responsibilities. It is intended for developers who need to modify, test, or reconstruct EnergyHub.

![Technical architecture](../Images/Infographic%E2%84%962_details.png)

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
    pv2_telemetry.py
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
- one `threading.Lock` shared by PI30MAX command execution and direct Modbus;
- one fixed read-only Modbus operation for slave 5, function 03, registers
  4563-4564 at 2400 baud/8N1;
- strict response address, function, byte-count, CRC, byte-order, and range
  validation;
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
| `solar_forecast_today_live` | yes | live contextual forecast |
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
| optional PV2 Modbus | configured, default 30 seconds; bounded failure backoff |
| QPIWS warnings | 60 seconds |
| QPIRI settings | 60 seconds |
| automatic Panic evaluation | 5 minutes, plus grid/mode reevaluation events |
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

After a valid PI30MAX sample, `PV2TelemetryService` may schedule one serialized
PV2 read. Successful samples publish PV2 and an aligned Total PV. Failures are
caught inside the service, marked stale, and backed off without entering the
PI30MAX watchdog failure path. An unsupported-register exception suppresses
further Modbus attempts until process restart. Retained PV2 measurements are
masked by dedicated availability after failure, expiry, or restart.

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

### SOC Anomaly Journal

`SocAnomalyJournal` compares consecutive valid SOC samples and records an
event when the absolute change is at least five percentage points within five
minutes. Its `/data/soc_anomaly_journal.json` file retains the latest 100
events plus a lifetime count and the latest valid baseline. Each event carries
battery voltage and charge/discharge current, PV1/fresh PV2/aligned Total PV,
load, grid availability and voltage, mode, freshness, process uptime, SOC
region, and startup/communication-recovery flags.

The journal publishes only `sensor.energyhub_soc_anomaly_event_count` and
`sensor.energyhub_soc_anomaly_latest` diagnostics. It is not consulted by the
telemetry parser, controller, Hybrid/Panic services, smart-load policy, System
Health, or Telegram delivery. Load/save failures are logged and isolated.

### Telemetry Freshness

- no valid telemetry → stale;
- last valid telemetry age at least 60 seconds → stale;
- otherwise fresh.

Unchanged load duration is published separately.

### Inverter Health

QPIWS values equal to `1` are treated as active warnings, excluding command metadata and reserved fields.

The verified adapter normally returns the complete named QPIWS map. EnergyHub
does not currently attach a completeness marker to that response, so a
partial-but-nonempty map would be interpreted as a real active-set transition.
No control decision depends on this diagnostic path. Firmware/adapter evidence
is required before introducing a different completeness rule.

EnergyHub 1.3.10 treats each change of the active named QPIWS set as a
diagnostic transition. It persists at most 100 incidents, closes an incident
when the active set changes or clears, and attaches a 30-sample/five-minute
in-memory pre-event telemetry ring. Current and latest-three MQTT entities are
retained for Home Assistant and the Family Assistant. QPIWS clearance alone is
not evidence of an inverter restart.

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

#### Panic Grid Hold

Preserve the Panic target/context, keep/verify SUB, and ACK-confirm OSO. Resume Panic Charging if SOC falls below target.

## Decision engines

### Hybrid

Pure input/output service. See [Decision Engine](DECISION_ENGINE.md).
The companion night-enforcement evaluator reuses the persisted target and
dated ownership context; it does not recalculate the target or write hardware.

### Panic

Pure input/output service with 07:00–23:50 time-window checks. It maps Grid Confidence to 20/60/80/95% and optionally inherits a persisted AHM morning debt. It does not gate recovery on live PV or forecast sufficiency.

## Target monitoring

The main loop monitors confirmed modes:

- Hybrid Charging + SOC ≥ adaptive target → enter Hybrid Grid Hold;
- active dated AHM plan + Solar + SOC = target → enter Hybrid Grid Hold;
- active dated AHM plan + Solar/Grid Hold + SOC < target → enter or resume
  Hybrid Charging when fresh telemetry and grid are available;
- Panic Charging + SOC ≥ target → enter Panic Grid Hold;
- Panic Grid Hold + SOC < target → resume Panic Charging;
- AHM at 23:50 overtakes either Panic mode.

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

An invalid finalization remains queued for retry. An `updated` or `unchanged`
result is acknowledged normally. A `missing` Daily Summary snapshot is also
acknowledged and removed from the queue because the scheduled historical
snapshot cannot appear later; the completed value remains available in Grid
Import history and the log records the missing reconciliation. This is a
deliberate bounded-retry policy, not loss of the underlying Grid Import total.

Intervals longer than 60 seconds are not integrated as house energy, preventing a long blocked loop from creating a false jump.

## Entity stability

MQTT Discovery includes:

- stable `unique_id`;
- explicit `default_entity_id` for fresh HA installations;
- process or combined availability as appropriate.

Existing HA registry IDs are not automatically renamed by `default_entity_id`; migrations must preserve unique ID and rename through Home Assistant.

## Known technical debt

- `main.py` is large;
- release test coverage remains concentrated in standard-library unit suites;
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
