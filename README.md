# EnergyHub 1.3.8 — Night Target and Heat-Pump Ownership

**Adaptive solar planning. Smart tariff use. Outage-ready reserve.**

EnergyHub is a local-first, resilience-aware Home Assistant energy controller for the PowMr 10.2M / POW-HVM10.2M hybrid inverter. It combines tomorrow's hourly solar forecast, expected household demand, battery state, a configured cheap-tariff window, and observed grid reliability to plan economical overnight charging and maintain an adaptive reserve.

**EnergyHub 1.3.8 keeps the evaluated Adaptive Hybrid target authoritative throughout the night and clearly separates family heat-pump control from EnergyHub reserve protection.**

EnergyHub 1.3.8 is the current public release. Its repository, Home Assistant
configuration, startup, MQTT, PV2/Total PV, outbound Telegram, and monitored
deployment gates passed before publication.

EnergyHub never turns the boiler or heat pumps on in 1.3.8. Automatic Smart Thermal control remains deferred.

See [Installation and Upgrade](docs/operations/INSTALLATION.md), [System Architecture](docs/design/05-System-Architecture.md), and [Developer Architecture](docs/design/10-Developer-Architecture.md).

![Adaptive Hybrid and Panic coordination](docs/Images/Infographic%235_ahm_panic_coordination.png)

## What EnergyHub does

EnergyHub:

- polls PowMr PI30MAX telemetry over local USB-RS232;
- optionally polls verified PV2 registers through bounded read-only Modbus RTU access on the same serialized connection;
- publishes Total PV only from fresh PV1 and PV2 samples acquired within 15 seconds of each other;
- publishes stable Home Assistant entities through MQTT Discovery;
- tracks grid availability over rolling 24-hour and 48-hour windows;
- derives a weighted Grid Confidence state;
- evaluates Adaptive Hybrid Mode at 23:50 from battery SOC, a selected 20–50% minimum reserve, aligned post-07 consumption, and tomorrow's hourly solar forecast;
- evaluates conservative daytime Panic reserve protection from Grid Confidence, battery SOC, and any AHM target missed at 07:00;
- executes verified inverter setting changes through one Inverter Controller;
- explains decisions and transition failures in Home Assistant;
- estimates Grid Import during intentionally grid-prioritized SUB strategies;
- stores restart-critical state atomically on local disk;
- reconstructs the operating strategy after an app restart;
- returns to Solar safely when Autopilot is disabled during an active automatic strategy.

The current release uses one configured cheap-tariff window. Future tariff planning may use multiple fixed periods or day-ahead import/export prices, but EnergyHub 1.3.8 does not claim dynamic-price or Net Billing optimization.

## Human-centered energy guidance

The homeowner selects an AHM protective reserve from 20% to 50%. EnergyHub then learns how the house behaves between 07:00 and 12:00, compares essential demand with the hourly solar forecast, and recommends the next safer or more economical reserve after three comparable completed mornings. The recommendation explains its evidence and never changes the setting automatically. Panic remains a separate emergency policy with its own Grid Confidence targets.

The optional **Telegram Family Assistant** turns the same data into a concise morning plan and sends grid-loss, recovery, Grid Confidence, reserve-advice, heat-pump ownership, and reserve-threshold updates to a private family group. Version 0.1.9 is outbound-only. Reserve warnings are sent only when a configured heat pump is actively drawing power, name the active floors and observed watts, and remain quiet through 08:01. It establishes the notification and identity boundary for future text and voice requests, but it cannot execute Home Assistant or inverter commands.

Future Telegram text/voice and Home Assistant Assist input will be translated into one structured EnergyHub request. EnergyHub—not the conversational interface—will authenticate, validate, audit, and decide whether to answer, allow, shorten, delay, or deny it.

## Supported release platform

EnergyHub 1.3.8 currently targets:

- Home Assistant OS with Supervisor/Apps;
- `aarch64` hardware, validated on Raspberry Pi 4;
- PowMr 10.2M using PI30MAX, with optional PV2 Modbus telemetry verified on the installed POW-HVM10.2M firmware;
- an FTDI USB-RS232 adapter exposed through `/dev/serial/by-id/...`;
- Mosquitto MQTT broker;
- Home Assistant as the UI, scheduling, integration, and notification layer.

The architecture is designed to become more configurable and vendor-independent in later releases, but 1.3.8 remains intentionally installation-specific.

## Operating strategies

| Strategy | Menu 01 | Menu 16 | Purpose |
|---|---|---|---|
| Solar | SBU | OSO | Default: use solar and battery first. |
| Hybrid Charging | SUB | SNU | Charge from the cheap night tariff to the configurable adaptive target. |
| Hybrid Grid Hold | SUB | OSO | Preserve the adaptive target until a guarded early-Solar release or the 07:00 handover. |
| Panic Charging | SUB | SNU | Build daytime reserve toward the conservative 20/60/80/95% target. |
| Panic Grid Hold | SUB | OSO | Preserve recovered reserve until AHM takes ownership at 23:50. |

Menu 01 is written and independently read back through QPIRI. Menu 16 has no supported read-back command on this inverter; EnergyHub stores the last ACK-confirmed value and never describes it as independently verified.

## Autopilot logic

### Solar

Solar is the default and recovery strategy:

```text
Menu 01 = SBU
Menu 16 = OSO
```

### Adaptive Hybrid Mode (AHM)

At 23:50, Home Assistant requests an AHM evaluation. EnergyHub calculates:

```text
expected post-07 consumption = today's consumption × 17 / 24
daytime deficit = max(0, expected post-07 consumption − post-07 solar)
daytime deficit SOC = deficit / (16 kWh × 90%) × 100

target SOC = min(95,
    selected minimum SOC
    + max(morning-gap SOC, daytime-deficit SOC))
```

The AHM minimum is selected in Home Assistant from 20% to 50% in 5% steps. EnergyHub learns 07:00–12:00 essential load from total-house energy minus heat-pump energy, retains 21 days, and uses a conservative per-hour 75th percentile after three complete samples per interval. It sums hourly deficits against tomorrow's solar and requires two consecutive covering hours before declaring solar takeover. Until learning is ready, the verified 300 W → 600 W ramp calculation remains authoritative.

![Adaptive Hybrid reserve and early Solar handover](docs/Images/Infographic%237_adaptive_hybrid_early_solar.png)

AHM is authoritative at 23:50 and overtakes an active Panic strategy. If projected 07:00 SOC meets target, AHM remains or restores Solar. If current SOC meets target but the overnight projection does not, it starts Hybrid Grid Hold; current SOC below target starts Hybrid Charging. At 07:00, Home Assistant requests Solar and daytime Panic inherits only an AHM target that was genuinely missed.

EnergyHub 1.3.8 persists the date of that night plan and checks its target on
every fresh telemetry cycle until a confirmed morning Solar handover. Solar
continues above target, exact target selects Hybrid Grid Hold, and a value
below target selects Hybrid Charging. If the grid is absent or SOC is stale,
the check sends no command and reevaluates later.

The prepared working-tree early-Solar increment performs one additional check
at 06:05. Only confirmed Hybrid Grid Hold is eligible. EnergyHub requires the
persisted target to be reached, fresh inverter and aligned Total Solar data,
present grid power, at least 300 W of live Total Solar, and at least 1.6 kWh in
the 06:00–07:00 Solcast interval. A failed gate makes no inverter change and
the normal 07:00 handover remains the fallback.

### Panic

Between 07:00 and 23:50, EnergyHub reevaluates automatic Panic every five minutes and after grid transitions.

- Normal Grid Confidence → protect 20% SOC.
- Unstable Grid Confidence → protect 60% SOC.
- Risk Grid Confidence → protect 80% SOC.
- Panic Grid Confidence → protect 95% SOC.

Panic does not use a solar-forecast gate. If grid is offline, it remains armed and waits. When grid returns, it charges immediately. At target it enters Panic Grid Hold rather than returning to Solar. AHM takes ownership at 23:50.

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
| `inverter_controller_state.json` | Last confirmed strategy, ACK-confirmed Menu 16, Panic target, Hybrid target, and dated night enforcement |
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
- the 23:50 Hybrid, guarded 06:05 early-Solar, and 07:00 Solar schedule;
- solar forecast input publication;
- the atomic 23:51 Daily Summary snapshot;
- the manual Panic script;
- persistent notifications;
- the EnergyHub beacon;
- household comfort controls and matching first-, second-, and third-floor auto-off timers;
- reserve-only water-boiler protection plus heat-pump manual/protected ownership and AHM-relative OFF bands based on fresh SOC, present grid, and Grid Confidence;
- dashboards and charts.

EnergyHub owns:

- telemetry processing;
- grid history and Grid Confidence;
- health aggregation;
- Hybrid and Panic decisions;
- operating-strategy execution and verification;
- persistence and restart reconstruction;
- EnergyHub MQTT state.

See [Home Assistant Configuration](docs/operations/12-HomeAssistant-Configuration.md).

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
  project, roadmap, design, feature, operations, incident, validation, and hardware docs

tools/dev/
  deployment and synchronization scripts
```

The Git repository is the development source of truth, including the selected Home Assistant configuration under `homeassistant/live/`. The live Home Assistant installation is the runtime instance; intentional UI changes are synchronized back to Git and reviewed before becoming the next baseline.

## Release status

EnergyHub 1.3.8 builds on the deployed 1.3.7 baseline with:

- Zigbee2MQTT/ZBDongle-E setup and two paired heat-pump plugs;
- matching three-floor manual controls and auto-off timers;
- dedicated Heat Pumps and Water Systems dashboards with local consumption history;
- reserve-only water-boiler and grid-confidence-aware heat-pump OFF guards;
- guarded repository-to-Home-Assistant deployment with backups and dry runs;
- incident and recovery documentation for the observed Ember failures and Tuya reauthentication;
- coordinated AHM/Panic ownership, persisted targets, morning-debt recovery, and expanded diagnostics.
- a 20–50% dashboard-selected AHM minimum reserve and independently validated 300 W → 600 W solar-ramp credit.
- learned essential morning net energy and a three-morning reserve advisor that never changes the slider automatically;
- the optional outbound-only Telegram Family Assistant for morning plans, grid events, Grid Confidence changes, and reserve advice.
- optional fixed-register, function-03 PV2 reads serialized with PI30MAX;
- PV2 voltage/power, aligned Total PV, freshness, status, and stale-safe MQTT availability;
- failure isolation that keeps PV2 observational and outside all control decisions.
- startup replacement of incompatible retained Hybrid decision reasons and a
  defensive 255-character Home Assistant state boundary.
- one guarded 06:05 release from Hybrid Grid Hold when the retained target is
  met, live aligned Total Solar is at least 300 W, and the dated 06:00-07:00
  forecast interval is at least 1.6 kWh;
- conservative no-action behavior on every missing, stale, invalid, or failed
  Early Solar gate, with the normal 07:00 handover unchanged;
- focused Early Solar diagnostics, clearer `awaiting_evaluation` wording, and
  Adaptive Hybrid Reserve dashboard presentation.
- continuous dated enforcement of the evaluated AHM target until morning
  Solar;
- trusted-grid family heat-pump ownership and AHM-relative protection when
  trust is lost;
- Telegram ownership guidance and active-heat-pump reserve warnings at
  +30/+20/+10/+0, with overnight quiet delivery.

EnergyHub 1.3.8 passes 103 add-on tests; Telegram Family Assistant 0.1.9 passes
42 tests. Both Python trees compile. The reviewed add-on, companion app, and
`automations.yaml` were synchronized to Home Assistant, `ha core check`
succeeded, EnergyHub reconstructed Solar without an inverter write, MQTT and
PV2/Total PV remained online, and the Telegram morning ownership preview was
delivered. The private monitoring window completed without a reported
regression. Paths that did not occur naturally remain covered by repository
tests rather than claimed as live transitions.

## Roadmap

- **1.0 — Autonomous Home:** released and tested as 1.0.2.
- **1.1 — Smart Plug Reserve Guard:** Zigbee2MQTT groundwork, validated smart plugs, focused dashboards, consumption history, and reserve-only OFF protection; no automatic starts.
- **1.2 — Adaptive Hybrid prototype:** developed and night-tested in the working tree; folded into the coordinated 1.3 release.
- **1.3 — Coordinated AHM & Panic:** post-07 energy planning, conservative daytime reserve targets, offline waiting, Grid Hold, and explicit 23:50 ownership transfer.
- **1.3.1 — Configurable AHM Reserve:** dashboard minimum SOC and explainable solar-ramp credit.
- **1.3.2 — Learned Morning Net Energy:** essential-load learning, aligned hourly solar deficit, and observable safe fallback.
- **1.3.3 — Projected-SOC Hybrid Gate:** remain Solar when the conservative 07:00 projection already meets the adaptive target.
- **1.3.4 — Safer Controls & Clearer Diagnostics:** confirmed reserve adjustments, concise decision summaries, and clearer fallback state.
- **1.3.5 — PV2 & Total PV:** optional read-only Modbus telemetry, freshness, failure isolation, and combined production.
- **1.3.6 — Retained-State Cleanup:** replace legacy Hybrid reason state at startup and enforce the Home Assistant state-length boundary.
- **1.3.7 — Early Solar Handover:** permit one guarded 06:05 release from Hybrid Grid Hold when reserve, live solar, forecast, grid, and telemetry gates pass.
- **1.3.8 — Night Target & Heat-Pump Ownership:** continuously enforce the dated AHM night target, leave heat pumps under family control on a trusted grid, and apply reserve-relative protection otherwise.
- **1.3.9 — SOC Anomaly Journal:** persist suspicious SOC jumps and oscillations with diagnostic context, without changing control decisions.
- **1.3.10 — Inverter Fault Diagnostics:** preserve QPIWS faults, contextual snapshots, and bounded read-only fault-code research.
- **1.3.11 — Tariff-Split Grid Import Accounting:** split estimated import into cheap and standard periods, retain daily/weekly/monthly totals, and report estimated cost without claiming billing-grade accuracy.
- **1.4 — Fault-Aware Smart Thermal & Flexible Loads:** persistent inverter-fault snapshots and overload calibration first, then Dry Run, attended Peak Load Guard, ownership, priorities, and solar-first flexible energy.
- **2.0 — Conversational EnergyHub:** Telegram-first authenticated Ukrainian/English text, followed by confirmed Ukrainian/English voice intents through the safe EnergyHub control boundary.
- **2.x — Tariff Scheduling:** multiple fixed cheap periods and later optional day-ahead import pricing.
- **3.0 — Hardware & Economic Ecosystem:** additional validated inverters and optional Net Billing/export planning.

See [Roadmap](docs/roadmap/06-Roadmap.md) and [Backlog](docs/roadmap/07-Backlog.md).

## Safety principles

- Manual control remains available.
- Autopilot is the master permission for automatic inverter strategy changes.
- EnergyHub does not automatically restart the inverter.
- Automatic recovery must remain bounded and observable.
- Menu 16 is described as ACK-confirmed, not read-back verified.
- Grid Import is informational and not billing-grade.
- Automatic Smart Thermal control must stop only loads it started; explicit reserve guards may shed manually started loads only at documented safety thresholds.

## Documentation index

- [Documentation Map](docs/README.md)
- [Installation and Upgrade](docs/operations/INSTALLATION.md)
- [Project](docs/project/01-Project.md)
- [Project Positioning](docs/project/POSITIONING.md)
- [System Architecture](docs/design/05-System-Architecture.md)
- [Roadmap](docs/roadmap/06-Roadmap.md)
- [Backlog](docs/roadmap/07-Backlog.md)
- [Decision Log](docs/design/09-Decision-Log.md)
- [Developer Architecture](docs/design/10-Developer-Architecture.md)
- [House Model](docs/design/11-House-Model.md)
- [Home Assistant Configuration](docs/operations/12-HomeAssistant-Configuration.md)
- [Recovery Strategy](docs/operations/13-Recovery-Strategy.md)
- [EnergyHub 1.x Development Plan](docs/roadmap/14-EnergyHub-1.x-Development.md)
- [Decision Engine](docs/design/DECISION_ENGINE.md)
- [Current Project State](docs/project/PROJECT_STATE.md)
- [Project History](docs/project/PROJECT_HISTORY.md)
- [PowMr Verified Commands](docs/hardware/powmr-10-2m-verified-commands.md)
- [PowMr 10.2M Modbus Telemetry](docs/hardware/powmr-10-2m-modbus-telemetry.md)
- [Release Notes 1.0.2](RELEASE_NOTES_1.0.2.md)
- [Release Notes 1.1.0](RELEASE_NOTES_1.1.0.md)
- [Release Notes 1.3.0](RELEASE_NOTES_1.3.0.md)
- [Release Notes 1.3.1](RELEASE_NOTES_1.3.1.md)
- [Release Notes 1.3.2](RELEASE_NOTES_1.3.2.md)
- [Release Notes 1.3.3](RELEASE_NOTES_1.3.3.md)
- [Release Notes 1.3.4](RELEASE_NOTES_1.3.4.md)
- [Release Notes 1.3.5](RELEASE_NOTES_1.3.5.md)
- [Release Notes 1.3.7](RELEASE_NOTES_1.3.7.md)
- [Release Notes 1.3.8](RELEASE_NOTES_1.3.8.md)
