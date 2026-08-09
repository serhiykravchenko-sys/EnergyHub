# EnergyHub Roadmap

> Build the foundation first. Add intelligence second. Scale third.

## EnergyHub 1.0 — Autonomous Home

Goal:

Create a reliable local-first energy system that monitors the house, understands current conditions, makes explainable decisions, and safely controls the real inverter.

Status:

**Released and tested as EnergyHub 1.0.2.**

Delivered:

- PowMr PI30MAX telemetry and control;
- MQTT communication and Discovery;
- verified Menu 01 control and ACK-confirmed Menu 16 control;
- Solar, Hybrid Charging, Hybrid Grid Hold, and Panic;
- Autopilot and explainable decision reasons;
- Grid History, Grid Availability, and weighted Grid Confidence;
- Communication, Battery, Telemetry, Inverter, and System Health;
- QPIWS monitoring;
- persistent Daily Summary and estimated Grid Import;
- Home Assistant schedules, controls, notifications, dashboards, and selected configuration synchronization;
- atomic persistence and restart strategy reconstruction;
- persistent FTDI serial identity;
- pinned dependencies and public-safe defaults;
- executable Docker-build release tests;
- installation, upgrade, and release documentation.

Success criterion:

> The house operates safely and economically with minimal homeowner intervention, while every important automated decision remains understandable.

---

## EnergyHub 1.1 — Smart Plug Reserve Guard

Goal:

Add observable household smart plugs and conservative reserve protection without changing the tested 1.0.2 inverter runtime or introducing automatic load starts.

Delivered in the 1.1.0 working tree:

- configure Zigbee2MQTT with the SONOFF ZBDongle-E through its persistent serial identity;
- pair and validate two Zigbee smart plugs, including manual control, availability, link quality, restart recovery, and power reporting where supported;
- inventory the existing Xiaomi boiler and basement water-pump devices and add a manual Water Systems dashboard with live power and validated daily/weekly/monthly consumption history;
- add matching first-, second-, and third-floor auto-off controls with duration `0` as manual mode;
- add focused Heat Pumps and Water Systems views with local consumption history;
- add water-boiler reserve-only OFF/lockout protection;
- add grid-confidence-aware heat-pump reserve-only OFF/lockout protection;
- preserve manual restoration above documented emergency thresholds;
- issue no smart-plug command from stale EnergyHub telemetry;
- document the observed Ember failures, manual recovery, stale telemetry boundary, and Tuya reauthentication;
- add guarded repository-to-Home-Assistant deployment with backups and dry runs.

Non-goals:

- no broad refactor of the 1.0.2 inverter runtime;
- no automatic smart-plug ON command;
- no Smart Thermal comfort or surplus controller;
- no assumption that every smart plug reports trustworthy power;
- no automatic Zigbee2MQTT/Ember recovery;
- no production multi-room thermal optimization.

Status:

1.1.0 release candidate. Final `ha core check`, restart, and supervised reserve-guard validation are required before tagging.

---

## EnergyHub 1.2 — Adaptive Hybrid Prototype

Historical outcome:

The Adaptive Hybrid morning-bridge prototype was implemented and night-tested in the working tree. It was not published as a separate release; the work was folded into 1.3.0 together with the coordinated Panic redesign.

Deferred configuration goal:

Make trusted household strategy variables adjustable without editing Python or Home Assistant YAML.

Planned parameters:

- cheap-tariff start and end times;
- latest acceptable cheap-tariff charging start and completion margin;
- Hybrid evaluation time;
- Hybrid target SOC;
- morning Solar restoration time;
- nominal battery capacity;
- grid charging current within hardware-safe bounds;
- conservative effective grid-charge rate used for deadline planning;
- Adaptive Night Hybrid enable, protected reserve, resilience horizon, target cap, useful-solar confirmation, and after-tariff safety policy;
- automatic Panic evaluation enable without removing manual Panic or health monitoring;
- Panic evaluation window;
- Panic SOC thresholds and targets;
- selectable Panic profiles;
- per-load normal shed/restore thresholds, emergency manual-override thresholds, recovery lockouts, priority tiers, minimum runtime/off-time, cooldown, and early-solar eligibility;
- technical monitoring thresholds where appropriate.

Requirements:

- safe parameter bounds;
- clear descriptions;
- separation between hardware limits and household strategy;
- persistent configuration;
- understandable defaults;
- no need to edit source code.
- a dedicated Home Assistant Settings view with grouped controls and a read-only preview of effective settings, calculated target, required charge time, start-by deadline, and decision reason;
- EnergyHub-side validation, acknowledgement, reconciliation, and audit for accepted changes;
- editing a setting does not itself execute an inverter command;
- migration defaults reproduce EnergyHub 1.0.2 behavior exactly.

Status:

Prototype completed; full configuration control plane deferred.

---

## EnergyHub 1.3 — Coordinated Adaptive Hybrid and Panic

Goal:

Coordinate cheap-night planning with conservative daytime reserve recovery.

Delivered in the 1.3.0 working tree:

- aligned post-07:00 consumption/solar energy balance for AHM;
- adaptive 30–95% target with persisted context;
- 07:00–23:50 Panic ownership with 20/60/80/95% targets;
- offline waiting, charging, and Panic Grid Hold phases;
- dated AHM morning-debt handoff;
- explicit AHM takeover from Panic at 23:50;
- expanded MQTT/dashboard diagnostics and coordinated heat-pump permission;
- release tests, documentation, and updated infographics.

Safety rule:

> Panic preserves reserve conservatively; neither AHM nor Panic automatically starts a smart thermal load.

Status:

Implementation complete; supervised deployment validation pending.

---

## EnergyHub 1.4 — Configuration, Recovery & Messaging

Goal:

Make EnergyHub configurable and supportable, add bounded communication/service recovery, and provide secure provider-neutral messaging without moving decision logic into cloud services.

Planned work:

- a validated settings model that separates immutable hardware limits from homeowner preferences;
- user-facing `Resilience`, `Balanced`, and `Economy` policy profiles;
- arbitrary fixed tariff schedules with one or more eligible periods per day;
- persisted forecast quality, same-date last-known forecast fallback, and conservative unavailable-forecast behavior;
- charge-duration and latest-start estimates;
- sanitized support bundles, replayable decision inputs, shadow mode, and inverter-write counters;
- secure remote Home Assistant access;
- Cloudflare Tunnel with WireGuard backup strategy;
- structured EnergyHub notification events;
- a provider-neutral messaging interface with Telegram as the first candidate adapter and room for WhatsApp, Signal, Matrix, or other supported providers;
- read-only status, health, mode, forecast, tariff, and reserve queries before remote control is considered;
- health, outage, anomaly, and strategy-transition alerts;
- authenticated, authorized, audited, and carefully bounded remote commands;
- notification policy and rate limiting.

Profiles modify household preferences only. They never replace battery, inverter, telemetry-freshness, or emergency safety limits.

Status:

Planned.

---

## EnergyHub 1.5 — Flexible Energy & EV Charging

Goal:

Use flexible heating, cooling, water heating, and EV charging as energy assets while preserving comfort, departure requirements, and battery resilience.

This milestone introduces a capability-based Load Manager with tested automatic starts, ownership, priority, hysteresis, minimum runtime/off-time, and coordinated operation. The design replaces the old narrow Away Mode concept.

Planned inputs:

- room temperature and comfort targets;
- occupancy context without making occupancy the only trigger;
- available solar surplus;
- cheap-tariff opportunities;
- battery SOC and reserve;
- solar forecast;
- grid reliability;
- current and projected household demand;
- EV connection state, requested energy or target SOC, and departure deadline;
- EVSE minimum/maximum current and phase capabilities;
- tariff schedule and optional permission to use the household battery for EV charging.

Planned behavior:

- use otherwise curtailed or unused solar for useful heating/cooling;
- preheat or precool during cheap-tariff periods when justified;
- preserve required battery reserve;
- coordinate multiple heat pumps and thermal loads;
- maximize direct solar use for EV charging and use approved low-price periods when solar alone cannot meet a departure target;
- prevent household-battery discharge into an EV unless the homeowner explicitly permits it;
- exclude EnergyHub-controlled flexible energy from the learned base household load;
- stop only loads that EnergyHub previously started;
- support time-bounded dashboard, automation, voice, or messenger requests through a deterministic EnergyHub override evaluator;
- introduce a generic Grid Input / Breaker Guard that can reduce charging current when household demand rises.

Voice or messenger assistants are request interfaces, not safety authorities. EnergyHub evaluates data freshness, projected reserve, grid availability, active strategy, load energy, and immutable emergency limits before allowing, shortening, delaying, or denying an override.

Status:

Planned.

---

## EnergyHub 2.x — Economic Planning & Hardware Ecosystem

Goal:

Plan import, export, storage, and flexible-load energy across broader hardware and tariff ecosystems while keeping resilience and hardware safety as hard constraints.

Planned direction:

- day-ahead import and export prices normalized into arbitrary market intervals;
- multiple fixed or dynamic tariff periods per day;
- supplier markup, tax, network-charge, negative-price, export-limit, and Net Billing rules;
- interval plans for expected load, solar, charge, discharge, import, export, SOC, cost, revenue, and protected reserve;
- planned-versus-actual cost and revenue accounting;
- staged price monitoring, shadow planning, attended control, automatic import, and stricter automatic-export validation;
- a normalized inverter capability model separated from transport;
- additional validated PowMr and Voltronic-compatible PI30/PI30MAX models;
- telemetry-only and shadow modes for unknown or unvalidated models;
- USB-RS232, Solar2MQTT, ESPHome, or other transports only where telemetry, command, acknowledgement, freshness, and recovery semantics are validated;
- eventual Deye, GoodWe, Victron, and other vendor adapters;
- additional BMS vendors;
- battery degradation models;
- cost-aware reserve management.

Economic planning may use spare battery capacity, but it must never silently import, export, or discharge through a protected reserve or unsupported hardware boundary.

Core question:

> Is it better to consume, store, import, or export energy now?

---

## EnergyHub 3.x — Full Home Energy Management System

Goal:

Coordinate the complete household energy ecosystem.

Future scope:

- solar generation;
- weather forecasting;
- dynamic electricity markets;
- battery storage;
- EV charging;
- vehicle-to-home or vehicle-to-grid where supported;
- heat pumps and water heating;
- flexible household loads;
- grid reliability;
- energy trading;
- whole-home optimization.

Vision:

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

## Product principles

EnergyHub should remain:

- local-first;
- human-centric;
- calm;
- explainable;
- modular;
- hardware-aware;
- progressively automated;
- safe by design;
- resilient to communication failures.

Development progression:

```text
Monitoring
    ↓
Reliable Facts
    ↓
Health Awareness
    ↓
Explainable Decisions
    ↓
Validated Automation
    ↓
Autonomous Home Operation
    ↓
Telemetry Robustness
    ↓
Configurable Strategy
    ↓
Recovery & Resilience
    ↓
Smart Household Loads
    ↓
Whole-Home Energy Optimization
```

## Success metric

> How often does the homeowner need to think about the energy system?

**Almost never.**
