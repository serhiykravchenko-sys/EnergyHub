# Communication Reliability

## Physical path

```text
EnergyHub add-on
→ mpp-solar subprocess
→ /dev/ttyUSB0
→ USB-RS232 adapter
→ PowMr PI30MAX
```

## Serial ownership

`PowMrLocalAdapter` uses one thread lock so telemetry, warning, settings, and write commands cannot start concurrent `mpp-solar` processes on the same serial port.

## Command timeout

Each adapter command has a 25-second subprocess timeout.

## Telemetry validation

A normalized state is valid only when required telemetry values can be interpreted. Invalid telemetry:

- is logged;
- is not published as a fresh raw state;
- advances Communication Watchdog failure state;
- marks `powmr/status` offline;
- leaves EnergyHub diagnostics available.

## Communication Watchdog

- success resets consecutive errors and timestamp;
- one or more errors before 60 seconds → recovering;
- errors with at least 60 seconds since success → offline;
- no current errors but old success timestamp → stale.

## Telemetry Freshness

Freshness is based on time since the latest valid sample:

- no valid sample → stale;
- age ≥60 seconds → stale;
- otherwise fresh.

An unchanged house load is not proof of frozen telemetry. It is published as a separate diagnostic duration.

## Inverter Health

QPIWS is read every 60 seconds. Active warning keys are published, while protocol metadata/reserved keys are ignored.

A warning-read failure produces `warning_read_failed` rather than pretending that no warnings exist.

## System Health

System Health aggregates:

- Communication Health;
- Battery Health;
- Telemetry Freshness;
- Inverter Health.

Communication offline makes System Health unavailable. Recovering/stale or component warnings produce warning.

## Availability topics

### EnergyHub process

```text
energyhub/status
```

### Raw inverter telemetry

```text
powmr/status
```

This separation is essential: diagnostic entities stay visible while raw telemetry is unavailable.

## Write reliability

### Menu 01

- up to three ACK attempts;
- QPIRI read-back verification;
- transition fails on mismatch.

### Menu 16

- up to three ACK attempts;
- persisted after ACK;
- no independent read-back available.

## Recovery

Current recovery is bounded:

- normal polling resumes after transient errors;
- partial automatic transitions attempt Solar recovery;
- safe Solar requests have queue priority;
- no automatic inverter reboot.

See [Recovery Strategy](../operations/13-Recovery-Strategy.md).

## Known hardware limits

- USB device paths may change if multiple adapters are connected;
- `mpp-solar` subprocess calls can block until timeout;
- Menu 16 cannot be queried;
- unsupported PI30MAX commands must not be treated as transient failures;
- communication recovery is not yet a full state machine.

## Planned 1.3 improvements

- error classification;
- bounded backoff;
- serial-device identity checks;
- process heartbeat;
- missed schedule recovery;
- external watchdog;
- recovery test automation.
