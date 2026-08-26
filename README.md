# EnergyHub 1.3.14 — Grid-Available Reserve Guard

**Adaptive solar planning. Smart tariff use. Outage-ready reserve.**

EnergyHub is a local-first, resilience-aware Home Assistant energy controller for the PowMr 10.2M / POW-HVM10.2M hybrid inverter. It combines tomorrow's hourly solar forecast, expected household demand, battery state, a configured cheap-tariff window, and observed grid reliability to plan economical overnight charging and maintain an adaptive reserve.

**EnergyHub coordinates hourly solar planning, tariff-aware grid use, and an
outage-ready battery reserve—then shows why each decision was made.**

EnergyHub 1.3.14 is the current public 1.x closure release. Its
Normal 20% reserve floor requests Grid Hold only when the grid is physically
present, then releases Solar at 30%. It has passed repository, guarded Home
Assistant, startup, dashboard, and monitoring gates.

EnergyHub never turns the boiler or heat pumps on in 1.3.14. Automatic Smart
Thermal control remains deferred.

See [Installation and Upgrade](docs/operations/INSTALLATION.md), [System Architecture](docs/design/05-System-Architecture.md), and [Developer Architecture](docs/design/10-Developer-Architecture.md).

![Adaptive Hybrid and Panic coordination](docs/Images/Infographic%235_ahm_panic_coordination_v2.png)

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
- records bounded, restart-aware SOC anomaly evidence without changing any
  decision or telemetry-acceptance path;
- returns to Solar safely when Autopilot is disabled during an active automatic strategy.

The current release uses one configured cheap-tariff window and separates
estimated Grid Import into night and normal periods. Future tariff planning may
use multiple fixed periods or day-ahead import/export prices, but EnergyHub
1.3.14 does not claim dynamic-price or Net Billing optimization.

## Human-centered energy guidance

The homeowner selects an AHM protective reserve from 20% to 50%. EnergyHub then learns how the house behaves between 07:00 and 12:00, compares essential demand with the hourly solar forecast, and recommends the next safer or more economical reserve after three comparable completed mornings. The recommendation explains its evidence and never changes the setting automatically. Panic remains the separate daytime reserve owner with its own Grid Confidence targets.

The optional **Telegram Family Assistant 1.3.14** turns the same data into a
concise morning plan and sends grid-loss, recovery, Grid Confidence,
reserve-advice, heat-pump ownership, tariff, inverter-message, and
reserve-threshold updates to a private family group. It is outbound-only. It
also checks configured environmental sensors and can warn about a configured
doorbell battery. It establishes the notification and identity boundary for
future text and voice requests, but it cannot execute Home Assistant or
inverter commands.

The 3.0 roadmap introduces **safe conversational Mission Control**: Telegram
first, messenger-neutral by design, Ukrainian/English text before confirmed
voice. Every request will become one authenticated, expiring EnergyHub intent.
EnergyHub—not the conversational interface—will validate, audit, and decide
whether to answer, allow, shorten, delay, or deny it. No messenger or AI may
send raw inverter commands.

## Supported release platform

EnergyHub 1.3.14 currently targets:

- Home Assistant OS with Supervisor/Apps;
- `aarch64` hardware, validated on Raspberry Pi 4;
- PowMr 10.2M using PI30MAX, with optional PV2 Modbus telemetry verified on the installed POW-HVM10.2M firmware;
- an FTDI USB-RS232 adapter exposed through `/dev/serial/by-id/...`;
- Mosquitto MQTT broker;
- Home Assistant as the UI, scheduling, integration, and notification layer.

The architecture is designed to become more configurable and vendor-independent
in later releases, but 1.3.14 remains intentionally installation-specific.

## Operating strategies

| Strategy | Menu 01 | Menu 16 | Purpose |
|---|---|---|---|
| Solar | SBU | OSO | Default: use solar and battery first. |
| Hybrid Charging | SUB | SNU | Charge from the cheap night tariff to the configurable adaptive target. |
| Hybrid Grid Hold | SUB | OSO | Preserve the adaptive target until guarded early Solar or the 07:00 Panic handoff. |
| Panic Charging | SUB | SNU | Build daytime reserve toward the conservative 20/60/80/95% target. |
| Panic Grid Hold | SUB | OSO | Preserve reserve; Normal releases Solar at 30%, other confidence levels hold until AHM. |

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

AHM is authoritative at 23:50 and overtakes an active Panic strategy. If
projected 07:00 SOC meets target, AHM remains or restores Solar. If current SOC
meets target but the overnight projection does not, it starts Hybrid Grid Hold;
current SOC below target starts Hybrid Charging. At 07:00, Home Assistant
requests a Panic evaluation instead of Solar. Confirmed Hybrid Charging or
Grid Hold can transfer ownership to the matching Panic state without another
inverter write, and daytime Panic inherits only an AHM target that was
genuinely missed.

EnergyHub 1.3.8 persists the date of that night plan and checks its target on
every fresh telemetry cycle until a confirmed morning Solar handover. Solar
continues above target, exact target selects Hybrid Grid Hold, and a value
below target selects Hybrid Charging. If the grid is absent or SOC is stale,
the check sends no command and reevaluates later.

EnergyHub performs one guarded early-Solar check at 06:05. Only confirmed
Hybrid Grid Hold is eligible. EnergyHub requires the
persisted target to be reached, fresh inverter and aligned Total Solar data,
present grid power, at least 300 W of live Total Solar, and at least 1.6 kWh in
the 06:00–07:00 Solcast interval. A failed gate makes no inverter change and
the normal 07:00 Panic ownership handoff remains the fallback.

### Panic

Between 07:00 and 23:50, EnergyHub reevaluates automatic Panic every five minutes and after grid transitions.

- Normal Grid Confidence → protect 20% SOC.
- Unstable Grid Confidence → protect 60% SOC.
- Risk Grid Confidence → protect 80% SOC.
- Panic Grid Confidence → protect 95% SOC.

Panic does not use a solar-forecast gate. With Normal Grid Confidence, present
grid, and no active AHM debt, Solar reaching 20% or below enters Panic Grid
Hold; values below 20% use Panic Charging until the floor is recovered. Grid
Hold then waits for solar-only charging to raise SOC to 30% before releasing
Solar. The 10-point band prevents mode oscillation. If the physical grid is
absent at the 20% floor, EnergyHub remains Solar and waits for grid return.
Unstable, Risk, and Panic confidence retain their 60/80/95% targets and hold
recovered reserve until AHM takes ownership at 23:50.

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

EnergyHub 1.3.11 additionally classifies every new estimated increment by the
Home Assistant host's local `Europe/Kyiv` calendar time:

- night tariff — `00:00–07:00` and `23:00–24:00`;
- normal tariff — `07:00–23:00`.

Dedicated sensors expose today, completed yesterday, current month, and
monotonic night/normal totals for Home Assistant long-term statistics. Initial
cost estimates use 2.50 UAH/kWh at night and 5.00 UAH/kWh during the normal
period. The bounded daily tariff ledger and active-day accumulators use atomic
persistence. An upgrade from schema v2 preserves the existing total but starts
the tariff split at deployment rather than guessing how earlier energy should
be classified.

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
- persistent named QPIWS incidents with five minutes of bounded pre-incident
  context and the latest three incidents exposed to Home Assistant;
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
- the 23:50 Hybrid, guarded 06:05 early-Solar, and 07:00 Panic-handoff schedule;
- solar forecast input publication;
- the atomic 23:51 Daily Summary snapshot;
- the manual Panic script;
- persistent notifications;
- the EnergyHub beacon;
- household comfort controls and matching first-, second-, and third-floor auto-off timers;
- trusted-grid manual permission for the water boiler and heat pumps, with reserve-only OFF guards returning when trust is lost;
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

EnergyHub 1.3.14 was deployed and started on 2026-08-24, passed the
guarded Home Assistant configuration check and startup validation, and
completed the agreed monitoring window through 2026-08-26 without a reported
release blocker. It is the final planned feature release in the 1.x line.

Current repository evidence:

- 155 EnergyHub tests passed;
- 67 Telegram Family Assistant tests passed;
- Python compilation, tracked Home Assistant storage JSON parsing, and
  `git diff --check` passed;
- the physical-grid floor correction has focused regression coverage;
- the updated AHM/Panic infographic is version-neutral and reflects the
  07:00 ownership handoff and Normal 20%/30% cycle.

Repository evidence does not replace live Home Assistant and inverter
validation. Live startup evidence confirmed MQTT, PV1/PV2/Total PV, persisted
state, Solar reconstruction without inverter writes, online health, the
dashboard, Telegram 1.3.14 startup/preview, and no pending Home Assistant
Repairs. The physical unavailable-grid floor transition was not forced during
monitoring; focused regression coverage remains the evidence for that rare
path.

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
- **1.3.9 — SOC Anomaly Journal:** persist suspicious SOC jumps and oscillations with diagnostic context without changing control decisions; the companion 0.2.0 report adds seven-sensor health and optional doorbell-battery warnings.
- **1.3.10 — Inverter Fault Diagnostics:** preserve QPIWS faults, contextual snapshots, and bounded read-only fault-code research.
- **1.3.11 — Tariff-Split Grid Import Accounting:** split estimated import into cheap and standard periods, retain daily/weekly/monthly totals, and report estimated cost without claiming billing-grade accuracy.
- **1.3.12 — Meaningful Inverter Messages:** retain expected PV-loss evidence while excluding routine PV-only events from dashboard incident positions.
- **1.3.13 — Normal-Grid Reserve Hysteresis:** transfer AHM to Panic at 07:00, hold 20%, release Solar at 30%, and leave boiler/heat-pump plugs untouched while grid trust is valid.
- **1.3.14 — Grid-Available Reserve Guard:** wait without a transition when the
  Normal 20% floor is reached during a physical grid outage, then reevaluate
  immediately after grid return.
- **2.0 — Fault-Aware Smart Thermal & Flexible Loads:** persistent inverter-fault snapshots and bounded recovery research first, then overload calibration, Dry Run, attended Peak Load Guard, ownership, priorities, and solar-first flexible energy.
- **3.0 — Conversational EnergyHub:** Telegram-first authenticated Ukrainian/English text, followed by confirmed Ukrainian/English voice intents through the safe EnergyHub control boundary.
- **4.0 — Tariff Scheduling:** multiple fixed cheap periods and later optional day-ahead import pricing.
- **5.0 — Hardware & Economic Ecosystem:** additional validated inverters and optional Net Billing/export planning.

See the public [Roadmap](docs/roadmap/06-Roadmap.md). Detailed household
planning and the engineering backlog remain private development records.

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
- [Decision Log](docs/design/09-Decision-Log.md)
- [Developer Architecture](docs/design/10-Developer-Architecture.md)
- [House Model](docs/design/11-House-Model.md)
- [Home Assistant Configuration](docs/operations/12-HomeAssistant-Configuration.md)
- [Recovery Strategy](docs/operations/13-Recovery-Strategy.md)
- [Decision Engine](docs/design/DECISION_ENGINE.md)
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
- [Release Notes 1.3.6](RELEASE_NOTES_1.3.6.md)
- [Release Notes 1.3.7](RELEASE_NOTES_1.3.7.md)
- [Release Notes 1.3.8](RELEASE_NOTES_1.3.8.md)
- [Release Notes 1.3.9](RELEASE_NOTES_1.3.9.md)
- [Release Notes 1.3.10](RELEASE_NOTES_1.3.10.md)
- [Release Notes 1.3.11](RELEASE_NOTES_1.3.11.md)
- [Release Notes 1.3.12](RELEASE_NOTES_1.3.12.md)
- [Release Notes 1.3.13](RELEASE_NOTES_1.3.13.md)
- [Release Notes 1.3.14](RELEASE_NOTES_1.3.14.md)
