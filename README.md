# EnergyHub 1.1 — Smart Plug Reserve Guard

EnergyHub is a local-first Home Assistant app that turns a PowMr 10.2M inverter, a 16 kWh battery, solar forecasts, grid history, and Home Assistant inputs into an explainable household energy strategy.

**EnergyHub 1.1.0 adds monitored smart loads and reserve-only OFF protection while preserving the released and tested EnergyHub 1.0.2 inverter runtime.**

Feature development, the functional audit, dependency pinning, credential hardening, executable release tests, persistent USB serial access, packaging validation, and live restart testing have been completed.

EnergyHub never turns the boiler or heat pumps on in 1.1.0. Automatic Smart Thermal control remains deferred.

See [Installation and Upgrade](docs/INSTALLATION.md), [System Architecture](docs/05-System-Architecture.md), and [Developer Architecture](docs/10-Developer-Architecture.md).

## What EnergyHub does

EnergyHub:

- polls PowMr PI30MAX telemetry over local USB-RS232;
- publishes stable Home Assistant entities through MQTT Discovery;
- tracks grid availability over rolling 24-hour and 48-hour windows;
- derives a weighted Grid Confidence state;
- evaluates a nightly Hybrid strategy from battery SOC, current consumption, and tomorrow's solar forecast;
- evaluates daytime Panic reserve protection from Grid Confidence, battery SOC, and forecast sufficiency;
- executes verified inverter setting changes through one Inverter Controller;
- explains decisions and transition failures in Home Assistant;
- estimates Grid Import during intentionally grid-prioritized SUB strategies;
- stores restart-critical state atomically on local disk;
- reconstructs the operating strategy after an app restart;
- returns to Solar safely when Autopilot is disabled during an active automatic strategy.

## Supported release platform

EnergyHub 1.1.0 currently targets:

- Home Assistant OS with Supervisor/Apps;
- `aarch64` hardware, validated on Raspberry Pi 4;
- PowMr 10.2M using PI30MAX;
- an FTDI USB-RS232 adapter exposed through `/dev/serial/by-id/...`;
- Mosquitto MQTT broker;
- Home Assistant as the UI, scheduling, integration, and notification layer.

The architecture is designed to become more configurable and vendor-independent in later releases, but 1.1.0 remains intentionally installation-specific.

## Operating strategies

| Strategy | Menu 01 | Menu 16 | Purpose |
|---|---|---|---|
| Solar | SBU | OSO | Default: use solar and battery first. |
| Hybrid Charging | SUB | SNU | Charge from the cheap night tariff to 80% SOC. |
| Hybrid Grid Hold | SUB | OSO | Preserve the charged battery and keep the house on night grid power until 07:00. |
| Panic | SUB | SNU | Build daytime emergency reserve to 80% or 95%, depending on Grid Confidence. |

Menu 01 is written and independently read back through QPIRI. Menu 16 has no supported read-back command on this inverter; EnergyHub stores the last ACK-confirmed value and never describes it as independently verified.

## Autopilot logic

### Solar

Solar is the default and recovery strategy:

```text
Menu 01 = SBU
Menu 16 = OSO
```

### Hybrid

At 23:50, Home Assistant requests a Hybrid evaluation. EnergyHub compares tomorrow's live solar forecast with:

```text
required energy
= today's house consumption
+ energy required to fill the 16 kWh battery from current SOC to 100%
```

If the forecast is insufficient, EnergyHub enters Hybrid Charging. At 80% SOC it enters Hybrid Grid Hold. Home Assistant requests Solar again at 07:00 when Autopilot is enabled.

### Panic

Between 12:00 and 23:50, EnergyHub reevaluates automatic Panic every 15 minutes while Solar is active.

- Unstable grid: SOC below 50% and forecast below yesterday's consumption plus 20% → charge to 80%.
- Risk or panic grid: SOC below 80% and forecast below yesterday's consumption plus 20% → charge to 95%.
- Normal grid: no automatic Panic.

A separate live-PV threshold is not part of the current Panic implementation.

Manual Panic uses a 95% target and requires Autopilot to be enabled. When Autopilot is off, Home Assistant shows a clear notification rather than silently ignoring the request.

## Decision and execution boundary

```text
Home Assistant schedules and supplies inputs
                ↓ MQTT
Decision services select a requested strategy
                ↓
main.py queues and orchestrates the request
                ↓
InverterController writes and confirms settings
                ↓
MQTT state + notification event
                ↓
Home Assistant dashboards and notifications
```

Decision services do not write hardware. The Inverter Controller is the only owner of strategy transitions.

## Grid intelligence

EnergyHub stores grid up/down transitions for 48 hours and calculates:

- available hours in the last 24 and 48 hours;
- outage hours in the last 24 hours;
- availability percentage in the last 24 hours;
- weighted Grid Confidence from 24-hour and 48-hour availability.

| Weighted availability | Grid Confidence |
|---|---|
| 90% or more | normal |
| 60–89.9% | unstable |
| 30–59.9% | risk |
| below 30% | panic |

## Grid Import accounting

The inverter does not expose a reliable billing-grade import counter. EnergyHub therefore estimates import during intentionally grid-prioritized SUB strategies:

```text
estimated import
= integrated house output power during SUB
+ positive battery SOC gain × 16 kWh
```

Current entities:

- `sensor.energyhub_grid_import_power_estimated` — current grid-supplied house power estimate;
- `sensor.energyhub_daily_grid_import_estimated` — current-day accumulated estimate;
- `sensor.energyhub_grid_import_yesterday_estimated` — completed previous day;
- `sensor.energyhub_daily_summary_grid_import` — finalized Daily Summary value for charts.

The result is informational and not billing-grade. Daytime simultaneous PV may affect accuracy and remains a 1.1 refinement area.

## Health and availability

EnergyHub separates two availability layers:

- `energyhub/status` — the EnergyHub process and diagnostic intelligence;
- `powmr/status` — valid raw inverter telemetry.

Current health services:

- Communication Watchdog;
- Battery Health;
- Telemetry Freshness;
- Inverter Health from QPIWS;
- System Health aggregation.

Telemetry Freshness depends on the age of valid telemetry. An unchanged house load is retained as diagnostic information but does not create a false warning.

## Persistence and restart reconstruction

The following files are stored under the app `/data` directory:

| File | Purpose |
|---|---|
| `grid_history.json` | Rolling grid transition history |
| `grid_import.json` | Current-day import, previous day, SUB interval, pending finalizations |
| `daily_summary.json` | Daily snapshots and finalized values |
| `inverter_controller_state.json` | Last confirmed strategy, ACK-confirmed Menu 16, Panic target |
| `energy_hub_powmr_last.json` | Latest valid raw telemetry snapshot |

Writes use temporary files, `fsync`, and atomic replacement. Incremental telemetry and Grid Import persistence are throttled to reduce storage writes; important transitions are persisted immediately.

At startup, EnergyHub combines:

- actual Menu 01 read from QPIRI;
- persisted ACK-confirmed Menu 16;
- persisted strategy context and Panic target.

If reconstruction is consistent, no inverter write occurs. If it is incomplete and Autopilot is enabled, EnergyHub queues one prioritized safe Solar recovery.

## Home Assistant integration

Home Assistant owns:

- the Autopilot helper;
- the 23:50 Hybrid and 07:00 Solar schedule;
- solar forecast input publication;
- the atomic 23:51 Daily Summary snapshot;
- the manual Panic script;
- persistent notifications;
- the EnergyHub beacon;
- household comfort controls and matching first-, second-, and third-floor auto-off timers;
- reserve-only water-boiler and heat-pump OFF protection based on fresh SOC and Grid Confidence;
- dashboards and charts.

EnergyHub owns:

- telemetry processing;
- grid history and Grid Confidence;
- health aggregation;
- Hybrid and Panic decisions;
- operating-strategy execution and verification;
- persistence and restart reconstruction;
- EnergyHub MQTT state.

See [Home Assistant Configuration](docs/12-HomeAssistant-Configuration.md).

## Development and release validation

The Docker image build runs executable standard-library unit tests:

```text
python3 -m unittest discover -s tests -v
```

The inherited 1.0.2 add-on release gate validates:

- Hybrid decision branches;
- Panic thresholds and evaluation window;
- Grid Confidence boundaries;
- telemetry freshness;
- restart strategy reconstruction;
- verified inverter transition sequencing;
- safe Solar recovery after a partial transition failure.

Live validation completed on 2026-08-01 included a full Home Assistant host restart with both the inverter FTDI adapter and a SONOFF Zigbee coordinator connected. EnergyHub resumed through the persistent FTDI `by-id` path and reconstructed Solar without unnecessary inverter writes.

EnergyHub 1.1.0 additionally requires Home Assistant `ha core check`, dashboard/entity inspection, and supervised reserve-guard validation because the new smart-plug logic is Home Assistant configuration rather than inverter-runtime Python.

## Project structure

```text
addon/
  app/             EnergyHub runtime
  tests/           executable release tests
  config.yaml      Home Assistant app manifest and defaults
  Dockerfile       image build and test gate
  DOCS.md          app-store documentation
  CHANGELOG.md     app-specific release notes
  requirements.txt pinned Python dependencies
  run.sh           container entry point

homeassistant/
  live/config/     selected synchronized YAML
  live/storage/    selected synchronized Home Assistant objects

docs/
  product, architecture, installation, decision, recovery, and hardware docs

tools/dev/
  deployment and synchronization scripts
```

The Git repository is the development source of truth, including the selected Home Assistant configuration under `homeassistant/live/`. The live Home Assistant installation is the runtime instance; intentional UI changes are synchronized back to Git and reviewed before becoming the next baseline.

## Release status

The tested EnergyHub 1.0.2 baseline remains unchanged. EnergyHub 1.1.0 adds:

- Zigbee2MQTT/ZBDongle-E setup and two paired heat-pump plugs;
- matching three-floor manual controls and auto-off timers;
- dedicated Heat Pumps and Water Systems dashboards with local consumption history;
- reserve-only water-boiler and grid-confidence-aware heat-pump OFF guards;
- guarded repository-to-Home-Assistant deployment with backups and dry runs;
- incident and recovery documentation for the observed Ember failures and Tuya reauthentication.

The stable 1.0.2 public baseline remains untouched until the 1.1.0 working tree passes final supervised Home Assistant validation and is explicitly committed.

## Roadmap

- **1.0 — Autonomous Home:** released and tested as 1.0.2.
- **1.1 — Smart Plug Reserve Guard:** Zigbee2MQTT groundwork, validated smart plugs, focused dashboards, consumption history, and reserve-only OFF protection; no automatic starts.
- **1.2 — Configurable EnergyHub:** strategy parameters, profiles, and safe hardware-aware bounds.
- **1.3 — Recovery & Resilience:** bounded recovery for MQTT, network, serial, `mpp-solar`, and Home Assistant outages.
- **1.4 — Remote Access & Telegram:** secure remote access, status, alerts, and commands.
- **1.5 — Smart Thermal Energy:** introduce tested automatic heating and cooling using surplus solar or cheap-tariff electricity, independent of occupancy.
- **2.x — Energy Optimization:** broader economic and multi-vendor optimization.
- **3.x — Full HEMS:** whole-home energy management.

See [Roadmap](docs/06-Roadmap.md) and [Backlog](docs/07-Backlog.md).

## Safety principles

- Manual control remains available.
- Autopilot is the master permission for automatic inverter strategy changes.
- EnergyHub does not automatically restart the inverter.
- Automatic recovery must remain bounded and observable.
- Menu 16 is described as ACK-confirmed, not read-back verified.
- Grid Import is informational and not billing-grade.
- Automatic Smart Thermal control must stop only loads it started; explicit reserve guards may shed manually started loads only at documented safety thresholds.

## Documentation index

- [Installation and Upgrade](docs/INSTALLATION.md)
- [Project](docs/01-Project.md)
- [System Architecture](docs/05-System-Architecture.md)
- [Roadmap](docs/06-Roadmap.md)
- [Backlog](docs/07-Backlog.md)
- [Decision Log](docs/09-Decision-Log.md)
- [Developer Architecture](docs/10-Developer-Architecture.md)
- [House Model](docs/11-House-Model.md)
- [Home Assistant Configuration](docs/12-HomeAssistant-Configuration.md)
- [Recovery Strategy](docs/13-Recovery-Strategy.md)
- [EnergyHub 1.x Development Plan](docs/14-EnergyHub-1.x-Development.md)
- [Decision Engine](docs/DECISION_ENGINE.md)
- [Current Project State](docs/PROJECT_STATE.md)
- [Project History](docs/PROJECT_HISTORY.md)
- [PowMr Verified Commands](docs/hardware/powmr-10-2m-verified-commands.md)
- [Release Notes 1.0.2](RELEASE_NOTES_1.0.2.md)
- [Release Notes 1.1.0](RELEASE_NOTES_1.1.0.md)
