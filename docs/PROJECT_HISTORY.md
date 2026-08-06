# EnergyHub Project History

This document records the major development eras and architectural milestones of EnergyHub.

Detailed implementation changes belong in `CHANGELOG.md`.

---

# June 2026 — Foundation

EnergyHub began as a local integration between a PowMr inverter, Raspberry Pi, Home Assistant, and MQTT.

Major milestones:

- PowMr PI30MAX communication;
- real-time inverter telemetry;
- MQTT publishing;
- MQTT Discovery;
- automatic Home Assistant entities;
- GitHub repository;
- structured project documentation.

Architectural result:

> EnergyHub became a local-first, MQTT-first energy platform rather than a collection of isolated scripts.

---

# Late June 2026 — Grid Intelligence and Health

EnergyHub expanded from telemetry into system awareness.

Major milestones:

- Grid Monitor;
- Grid History;
- 24-hour and 48-hour grid availability;
- Grid Confidence;
- Communication Watchdog;
- Communication Health state machine;
- Developer Dashboard;
- Family Dashboard;
- House Model documentation.

Architectural result:

> EnergyHub began preserving historical context and treating system health as a first-class subsystem.

---

# Late June 2026 — Home Automation and Historical Energy

EnergyHub began connecting energy telemetry with household behavior.

Major milestones:

- Daily Energy Statistics;
- 7-day historical charts;
- solar forecast integration;
- Grid Availability visualization;
- Floor 3 Heat Pump Auto-Off;
- timer helpers;
- Daily Energy Balance helper.

Architectural result:

> Dashboards and automations began consuming reusable energy knowledge rather than repeatedly calculating raw telemetry.

---

# Early July 2026 — Architecture v2

The project was reorganized around modular services and explainable decisions.

Major milestones:

- Daily Summary Engine;
- persistent daily history;
- Battery Health Monitor;
- Telemetry Freshness Monitor;
- Inverter Health Monitor;
- System Health aggregation;
- QPIWS monitoring;
- Recovery Strategy principles;
- Decision Engine design;
- Home Assistant configuration documentation.

Architectural result:

```text
Telemetry
    ↓
Reliable Facts
    ↓
Health Awareness
    ↓
Historical Knowledge
    ↓
Explainable Decisions
```

---

# July 2026 — Real Inverter Control

EnergyHub moved from monitoring and recommendations to verified control of the real inverter.

Major milestones:

- Setting 16 control confirmed:
  - `PCP01 → SNU`;
  - `PCP02 → OSO`;
  - `PCP03 → CSO`.
- Setting 01 control confirmed:
  - `POP01 → SUB`;
  - `POP02 → SBU`.
- command acknowledgement;
- QPIRI verification;
- bounded retries;
- real inverter display verification;
- safe Solar restoration.

Architectural result:

> EnergyHub gained the ability to execute operating strategies rather than only recommend them.

---

# July 2026 — Autonomous Operating Modes

EnergyHub implemented its first complete operating strategies.

## Solar

Default strategy:

```text
SBU + OSO
```

## Hybrid

Night strategy based on tomorrow's forecast, today's consumption, current SOC, and required battery refill energy.

Sequence:

```text
Hybrid Decision
    ↓
Hybrid Charging
SUB + SNU
    ↓
Battery reaches 80%
    ↓
Hybrid Grid Hold
SUB + OSO
    ↓
07:00
    ↓
Solar
```

## Panic

Protective daytime charging based on:

- Grid Confidence;
- current SOC;
- insufficient solar forecast.

Targets:

- 80% for unstable-grid conditions;
- 95% for higher-risk conditions.

## Away Mode Exploration

An initial Away Mode concept explored autonomous heat-pump control based on occupancy, temperature, Battery SOC, and available solar energy.

Real design review showed that the concept mixed several separate concerns:

- occupancy;
- comfort;
- solar-surplus use;
- battery reserve;
- cheap-tariff opportunities;
- flexible-load control.

Away Mode was therefore deferred from EnergyHub 1.0 and moved to EnergyHub 1.1 for redesign as part of a broader Smart Heating and flexible-load architecture.


Architectural result:

> EnergyHub crossed the boundary from monitoring into explainable autonomous home energy control.

---

# July 2026 — Grid Import Estimation

The PowMr inverter does not provide a reliable accumulated Grid Import counter.

EnergyHub introduced a mode-aware Grid Import Estimator.

Major milestones:

- estimated current Grid Import power;
- estimated Daily Grid Import energy;
- accounting tied to SUB operating intervals;
- house energy accumulation during SUB;
- battery energy estimation from positive SOC gain and nominal battery capacity;
- support for Hybrid Charging, Hybrid Grid Hold, and Panic;
- persistent daily state;
- schema migration after estimator redesign;
- yesterday and Daily Summary history;
- chart and dashboard integration.

Architectural result:

> EnergyHub learned to derive missing operational knowledge from telemetry and known control state.

---

# July 2026 — Home Assistant as Versioned Project State

The Home Assistant side of EnergyHub was integrated into the repository workflow.

Major milestones:

- `homeassistant/live/` for current synchronized configuration;
- `tools/dev/sync-from-ha.ps1`;
- selected Home Assistant YAML synchronization;
- selected `.storage` synchronization;
- Lovelace dashboard synchronization;
- helper and timer synchronization.

Development workflow became bidirectional:

```text
EnergyHub code
Git → Home Assistant

Home Assistant configuration
Home Assistant → Git
```

Architectural result:

> The repository now represents both the EnergyHub runtime and the reviewed Home Assistant configuration that surrounds it.

---

# Current Era — EnergyHub 1.0 Test Drive and Cleanup

EnergyHub 1.0 feature development is complete.

The project has entered a real-system test-drive and cleanup phase.

Final 1.0 milestones included:

- complete Solar, Hybrid Charging, Hybrid Grid Hold, and Panic strategies;
- Autopilot execution;
- explainable Hybrid Decision data;
- corrected Panic evaluation order;
- removal of the current-PV threshold from Panic decisions;
- automatic Hybrid and Panic notifications;
- redesigned Grid Import accounting;
- Home Assistant synchronization workflow;
- removal of obsolete manually maintained `homeassistant/legacy/` files;
- removal of the duplicate Autopilot helper;
- Decision Logic dashboard improvements.

Current priorities:

- run Autopilot under real household conditions;
- perform a full post-implementation code review;
- clean entity IDs such as `*_2`;
- remove obsolete retained MQTT Discovery entities;
- verify Grid Import midnight rollover and historical continuity;
- improve restart strategy reconstruction;
- redesign and standardize charts and dashboards;
- fix bugs discovered during the test-drive period;
- investigate persistent inverter `eeprom_fault`.

EnergyHub 1.0 success means:

> The house can operate safely and economically with minimal homeowner intervention while every important automated decision remains understandable.

---

# Next Era — EnergyHub 1.1

EnergyHub 1.1 will focus on Smart Loads and improvements discovered during the EnergyHub 1.0 test drive.

Planned direction:

- bug fixes;
- cosmetic and usability improvements;
- dashboard and chart improvements;
- Smart Heating architecture;
- Away Mode rethink;
- solar-surplus heating;
- cheap-tariff heating;
- EV charging template;
- flexible-load architecture.

Architectural goal:

> Extend autonomous energy management from the inverter and battery to useful household loads without compromising comfort, resilience, or explainability.

---

# EnergyHub 1.2 — Configurable EnergyHub

EnergyHub 1.2 will make trusted household strategy parameters configurable without editing code or YAML.

Planned examples:

- cheap electricity tariff window;
- Panic evaluation window;
- nominal battery capacity;
- grid charging current;
- Hybrid target SOC;
- Panic thresholds and targets;
- selectable Panic profiles;
- other safe Decision Engine variables.

Architectural goal:

> Separate hardware technical limits from configurable household strategy.

---

# EnergyHub 1.3 — Recovery & Resilience

EnergyHub 1.3 will focus on safe and predictable recovery from real system failures.

Planned direction:

- MQTT recovery;
- network recovery;
- serial communication recovery;
- inverter communication recovery;
- `mpp-solar` timeout handling;
- Home Assistant connectivity recovery;
- bounded retries;
- safe-state reconstruction;
- external heartbeat and watchdog strategy.

Architectural goal:

> Detect failures, recover automatically only when safe, keep recovery bounded, and preserve understandable system state.

---

# Future — EnergyHub 2.x

EnergyHub will evolve into a multi-vendor energy optimization platform.

Planned direction:

- Deye, GoodWe, Victron, and other inverter support;
- additional BMS vendors;
- dynamic electricity tariffs;
- import optimization;
- export optimization;
- Net Billing;
- battery degradation modeling.

Core question:

> Is it better to consume, store, import, or export energy now?

---

# Long-Term Vision — EnergyHub 3.x

EnergyHub will evolve into a full Home Energy Management System.

Planned ecosystem:

- solar;
- battery storage;
- weather;
- dynamic electricity markets;
- EV charging;
- heat pumps;
- water heating;
- flexible household loads;
- grid reliability;
- energy trading.

Long-term architecture:

```text
Weather
+
Solar Forecast
+
House Consumption
+
Battery State
+
Grid Reliability
+
Electricity Prices
+
EV Requirements
+
Heating Requirements
        ↓
EnergyHub
        ↓
Explainable Whole-Home Energy Strategy
```

---

# Project Evolution

```text
Monitoring
    ↓
Reliable Facts
    ↓
Health Awareness
    ↓
Historical Knowledge
    ↓
Explainable Decisions
    ↓
Validated Automation
    ↓
Autonomous Home Operation
    ↓
Smart Household Loads
    ↓
Configurable Strategy
    ↓
Recovery & Resilience
    ↓
Whole-Home Energy Optimization
```

---

# August 2026 — EnergyHub 1.0.2 Release Engineering

EnergyHub completed the transition from a real-system release candidate to its first release-ready build.

Major milestones:

- pinned tested Python dependencies;
- removed usable MQTT credentials from public defaults;
- introduced persistent FTDI serial selection through `/dev/serial/by-id`;
- enabled UART and udev access in the Home Assistant app manifest;
- corrected the runtime publisher path;
- made the startup banner use the Home Assistant build version;
- removed the obsolete raw inverter warning MQTT entity;
- added a 24-test standard-library release suite;
- made the Docker build fail when release tests fail;
- rebuilt and restarted successfully on Home Assistant OS;
- validated coexistence with a connected SONOFF Zigbee coordinator;
- confirmed Solar startup reconstruction without inverter writes;
- completed installation, upgrade, changelog, roadmap, and project-state documentation.

Release result:

```text
EnergyHub 1.0.2
→ tagged and released
→ validated on the real installation
→ stable compatibility baseline for EnergyHub 1.x
```

Architectural result:

> EnergyHub 1.0 became not only functionally complete, but reproducibly buildable, test-gated, restart-safe, and installable from documented public defaults.

---

# August 2026 — EnergyHub 1.x Development Start

EnergyHub 1.0.2 was tagged, released, and tested. Development then moved to the `SKrav69/EnergyHub` repository while the stable public distribution repository remained unchanged.

The initial 1.1 sequence was agreed as:

1. align the 1.x development documentation;
2. configure Zigbee2MQTT with the SONOFF ZBDongle-E;
3. pair and validate two Zigbee smart plugs;
4. build a bounded Smart Thermal Load Controller prototype.

During implementation, issue 4 was deliberately narrowed to dashboards, timers, consumption history, and reserve-only OFF guards. Automatic starts and Smart Thermal ownership moved to 1.5. The final 1.1 scope preserves the proven inverter strategies and never turns a protected thermal load on.

The first two Zigbee smart plugs were paired for the first- and second-floor heat pumps, with their validation records kept in the 1.x development plan. Mission Control initially gained consistent six-card controls and matching manual auto-off behavior across all three floors while the existing third-floor Xiaomi plug remained unchanged. After dedicated Heat Pumps and Water Systems views were added, the floor controls moved into Heat Pumps with electrical and consumption data, leaving Mission Control focused on whole-house operation.

At 21:30 on 2026-08-02, an Ember `ASH_ERROR_TIMEOUTS` transaction failure stopped Zigbee2MQTT while the Home Assistant app Watchdog was disabled. At 17:29 on 2026-08-03, an attended manual Start recovered the coordinator, the same Zigbee network, both paired devices and states, MQTT, availability, and Home Assistant discovery without re-pairing or an observed relay command. Watchdog was enabled only after that recovery.

Second-floor Offline-to-Online availability and safe OFF power recovery passed. A later Home Assistant restart retained both devices Online; the first-floor plug remained ON and its heat pump continued cooling. First-floor compressor ramp-up telemetry arrived asynchronously, with a stabilized example of 804 W, 3.37 A, and 226 V. These readings and the observed second-floor measurements are trend data, not reference-meter calibration, electrical-protection inputs, or proof of heat-pump suitability.

The incident established a stricter recovery rule for future automation because last-known electrical telemetry may remain stale across an outage. Automatic Smart Thermal control must wait for fresh post-recovery inputs and safe ownership reconstruction, not merely an online availability state. Ember failure diagnosis, bounded recovery, and heat-pump nameplate verification remain pending.

On 2026-08-05, a second Ember incident reset ASH but failed to start the EZSP layer with `HOST_FATAL_ERROR`. Zigbee2MQTT exited while its Home Assistant app Watchdog was enabled, and no autonomous recovery was observed. This moved bridge/app monitoring and bounded recovery from an untested resilience question to active high-priority work.

On 2026-08-06 at 07:30, a third incident was captured from a healthy bridge through recovery. A `SEND_UNICAST` transaction failed with `ASH_ERROR_TIMEOUTS`; the bridge published offline and stopped cleanly. Supervisor Watchdog launched ten app restarts through 07:35. Each restart opened the serial port and attempted five ASH resets, but the NCP never completed startup and every run ended with `HOST_FATAL_ERROR`. The crash loop then stopped. An attended manual Start at 11:51 connected on its second ASH reset and resumed the same coordinator network, both devices and ON relay states, MQTT, availability, and fresh reports without re-pairing or an observed relay toggle. This proved that Watchdog restart attempts occurred but were insufficient while the Ember NCP remained unresponsive.

On 2026-08-06, an apparently stale EnergyHub beacon color was traced to expired authentication for the Tuya Wi-Fi integration. Home Assistant Repairs exposed the reauthentication requirement, and attended confirmation through the Tuya app restored lamp control. The EnergyHub automation had calculated the correct color, demonstrating that policy correctness, integration health, and physical command delivery are separate observability layers.

The first colder-season policy follow-up was also defined as Adaptive Night Hybrid: project SOC through the expected start of useful solar, enter Grid Hold before protected reserve is crossed, and return to Solar only after useful generation is confirmed. The design remains pending and will preserve the released 1.0.2 behavior until implemented behind tests and staged validation.
