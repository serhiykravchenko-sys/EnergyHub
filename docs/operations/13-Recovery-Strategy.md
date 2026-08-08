# EnergyHub Recovery Strategy

## Scope

This document distinguishes current 1.0 recovery behavior from the broader 1.3 Recovery & Resilience milestone.

## Safety rules

- Never automatically restart the inverter.
- Never retry indefinitely.
- Never report a mode as active before transition success.
- Prefer Solar as the bounded recovery strategy.
- Preserve diagnostics during inverter communication failure.
- Do not change settings automatically when Autopilot is disabled, except the one final safe Solar recovery triggered by disabling it during an active/unknown automatic state.

## Failure classes

1. MQTT connection or broker failure.
2. Serial/USB failure.
3. `mpp-solar` timeout or malformed response.
4. Invalid or stale telemetry.
5. QPIWS warning/fault.
6. Menu 01 write or verification failure.
7. Menu 16 missing ACK.
8. Partial multi-setting strategy transition.
9. Add-on restart with incomplete state.
10. Home Assistant schedule/input failure.
11. Corrupt or missing persistence.

## Current communication behavior

### MQTT

The client uses a last will on `energyhub/status`. Paho owns ordinary network reconnect behavior. A formal bounded MQTT recovery policy remains 1.3 work.

### Serial and `mpp-solar`

- one serial lock;
- subprocess timeout: 25 seconds;
- exceptions are caught by the runtime loop;
- invalid telemetry moves communication to recovering/offline;
- the next loop attempts normal polling again.

### Communication states

- starting;
- online;
- recovering after one or more errors;
- offline after at least 60 seconds without success while errors continue;
- stale when success age exceeds 60 seconds without current consecutive errors.

## Availability during failure

`powmr/status` becomes offline when raw telemetry is invalid.

`energyhub/status` remains online while the process is running, allowing diagnostic sensors to show:

- communication state;
- freshness;
- health reason;
- last known decision/controller state.

## Write recovery

### Menu 01

- up to three write attempts;
- one-second delay between retries;
- independent QPIRI verification;
- failure if expected state is not read back.

### Menu 16

- up to three write attempts;
- one-second delay;
- success requires ACK;
- accepted value is immediately persisted.

## Transition recovery

### Hybrid Charging partial failure

If SUB succeeds but SNU fails, attempt Solar recovery.

### Panic partial failure

If SUB succeeds but SNU fails, attempt Solar recovery.

### Hybrid Grid Hold failure

If SUB verification or OSO ACK fails, attempt one Solar recovery.

If recovery also fails, retain a combined error and publish `transition_failed`.

### Solar recovery failure

If either OSO or SBU fails, mode becomes `transition_failed` with detailed errors.

## Safe Solar queue priority

The queue is shared by the MQTT callback thread and main loop. A lock protects replacement. Once `safe_solar` is pending, ordinary requests are ignored until it is processed.

## Autopilot-off behavior

When Autopilot changes from on to off:

- EnergyHub queues `safe_solar` if the controller is in an active, unknown, inconsistent, transitioning, or failed state;
- Solar recovery executes even though ordinary mode requests are blocked by Autopilot off;
- after the recovery, automatic strategy changes stop.

## Restart reconstruction

### Persisted data

`inverter_controller_state.json` stores:

- schema version;
- confirmed mode;
- ACK-confirmed Menu 16;
- Panic target;
- timestamp.

### Physical data

QPIRI supplies actual Menu 01.

### Reconstruction outcome

- consistent recognized combination → accept without writes;
- unknown/inconsistent + Autopilot on → one safe Solar recovery;
- unknown/inconsistent + Autopilot off → report state, do not write.

The old clock-based HA restart restoration is removed.

## Persistence recovery

Current JSON writers are atomic. If a file is missing, the owning service initializes safe empty/default state. If a file is unreadable, the error is logged; a richer quarantine/backup policy remains future work.

## Daily boundary recovery

Grid Import stores pending completed-day finalizations. A restart between midnight closure and Daily Summary reconciliation does not lose the hand-off.

Reconciliation outcomes:

- updated;
- unchanged;
- missing snapshot;
- invalid.

Invalid remains pending. Valid non-invalid outcomes are acknowledged.

## Home Assistant dependency

Current limitations:

- Hybrid trigger comes from HA at 23:50;
- Solar restoration comes from HA at 07:00;
- Solcast and daily snapshot inputs come from HA;
- Autopilot permission comes from a retained HA helper.

An internal missed-schedule fallback belongs to 1.3 and requires timezone, duplicate-command, and delayed-start rules.

## No automatic inverter reboot

Even when communication fails, EnergyHub may retry local reads and bounded setting writes, but it does not power-cycle or restart the inverter.

## Notifications

Current automatic strategy events distinguish:

- successful activation;
- failed activation.

Future recovery notifications should avoid alert storms and should report only meaningful state changes or exhausted bounded recovery.

## 1.3 planned work

- explicit MQTT reconnect state machine;
- serial error classification;
- bounded command backoff;
- service-level recovery ownership;
- missed schedule detection;
- HA unavailable behavior;
- external heartbeat/watchdog;
- persistence backup/quarantine;
- recovery test matrix;
- graceful process shutdown.

## Recovery test matrix

Minimum cases:

- unplug/replug serial cable;
- broker restart;
- HA restart before 23:50 and 07:00;
- add-on restart in every confirmed strategy;
- Menu 01 ACK but failed read-back;
- Menu 16 no ACK;
- Grid Hold partial failure;
- corrupt each JSON file;
- restart exactly after midnight day closure;
- Autopilot disabled with a pending ordinary request;
- repeated invalid telemetry.
