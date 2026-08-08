# EnergyHub Development Principles

## Product before code

Every change must improve a real household outcome, reliability, explainability, maintainability, or release quality. Abstractions are not goals by themselves.

## Git is the project source of truth

The repository contains:

- add-on code;
- selected Home Assistant configuration;
- architecture and product decisions;
- deployment and synchronization tools.

The live Home Assistant installation remains the runtime source of truth. Changes made through the HA UI must be synchronized back to Git and reviewed before commit.

## Documentation follows stable behavior

Architecture and product documentation should be updated after a coherent group of code and UI changes is stable. This avoids repeatedly documenting temporary states.

Historical reviews remain historical; current-state documents must describe the current implementation.

## Small coherent commits

One commit should represent one understandable change, for example:

- fix telemetry freshness;
- make notifications transition-confirmed;
- make persistence atomic;
- redesign charts and dashboards;
- update documentation.

## Clear responsibility boundaries

### Home Assistant owns

- UI and dashboards;
- helpers;
- schedules;
- selected household automations;
- persistent notifications;
- user actions.

### EnergyHub owns

- normalized telemetry;
- historical energy knowledge;
- health and reliability state;
- decision engines;
- strategy execution;
- verification and reconstruction;
- EnergyHub MQTT state.

### `main.py` owns

- dependency construction;
- lifecycle orchestration;
- request queue coordination;
- scheduling within the runtime loop;
- service-to-service data flow.

It should not become the permanent home of every policy calculation.

## Decision services decide

Hybrid and Panic services return structured decisions. They do not call the adapter or publish Home Assistant notifications directly.

## Inverter Controller executes

Only Inverter Controller may perform strategy transitions. It owns:

- Menu 01 and Menu 16 mappings;
- bounded write retries;
- Menu 01 read-back verification;
- ACK-confirmed Menu 16 state;
- partial-failure recovery;
- confirmed operating mode;
- persisted controller context.

## Read before write

When the hardware supports it, use actual state before issuing a command. Startup reconstruction reads Menu 01 from QPIRI before deciding whether recovery is necessary.

## Verify physical state honestly

A successful write acknowledgement is not always the same as verified physical state.

- Menu 01: write, then read QPIRI and compare.
- Menu 16: accept ACK, persist the value, and label it ACK-confirmed because no supported read-back exists.

## Safe queue semantics

MQTT callbacks and the main runtime loop use different threads. Mode-request replacement must be lock-protected. A pending safe Solar recovery has priority and cannot be replaced by an ordinary request.

## Persistent state must survive power loss

JSON persistence uses:

1. a temporary file in the target directory;
2. flush;
3. file `fsync`;
4. atomic `os.replace`;
5. directory `fsync` where supported.

High-frequency diagnostic snapshots are throttled. Important transitions and day boundaries are forced immediately.

## Availability is not one concept

Raw inverter telemetry and EnergyHub intelligence have separate availability topics. Diagnostic entities must remain visible when they are needed to explain an inverter communication failure.

## Explainability and logging

Every automatic strategy decision should log:

- status;
- reason;
- selected target;
- queued request.

Every transition should log:

- requested settings;
- retries;
- verification result;
- recovery result;
- confirmed mode.

## Test on the real system

The PowMr protocol and actual inverter behavior cannot be validated only from mocks. Important commands and transitions require real hardware tests.

At the same time, pure logic and persistence should gain executable automated tests before an external 1.0 release.

## Do not refactor without a safety net

`main.py` is large and contains technical debt. A broad lifecycle extraction is deferred until tests cover queue priority, transitions, targets, restart reconstruction, and notifications.

## Technical limits and strategy settings are different

Technical limits come from hardware documentation and safe operation.

Strategy settings express household policy.

Future configuration must not present a battery current limit and a comfort preference as equivalent parameters.

## Security and release quality

Published defaults must not contain weak credentials. Dependencies should be pinned to tested versions. Installation documentation must explain secrets and local network assumptions.

## Definition of done

A change is complete when:

- code and configuration are updated;
- behavior is validated at the correct level;
- logs and failure behavior are checked;
- dashboard/entity references are updated;
- no obsolete retained state remains;
- documentation is updated when the feature set is stable;
- Git status contains no accidental runtime exports or archives.
