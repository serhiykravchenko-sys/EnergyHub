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

The 1.1 work was folded into the validated 1.3.0 release candidate rather than tagged separately.

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
- original adaptive 30–95% target with persisted context (superseded by the
  1.3.1 configurable minimum; the current target range is 20–95%);
- 07:00–23:50 Panic ownership with 20/60/80/95% targets;
- offline waiting, charging, and Panic Grid Hold phases;
- dated AHM morning-debt handoff;
- explicit AHM takeover from Panic at 23:50;
- expanded MQTT/dashboard diagnostics and coordinated heat-pump permission;
- release tests, documentation, and updated infographics.

Delivered in the 1.3.1 maintenance increment:

- dashboard-selected 20–50% AHM minimum SOC;
- verified 300 W → 600 W one-hour solar-ramp credit;
- retained raw/effective morning-gap and ramp diagnostics.

Delivered in the 1.3.2 monitoring increment:

- 07:00–12:00 essential-load learning after subtracting heat-pump energy;
- a conservative 21-day per-interval profile with three-sample activation and observable fallback;
- aligned learned-load/hourly-solar net-energy planning;
- a three-completed-morning, one-step AHM reserve advisor;
- an optional outbound-only Telegram Family Assistant for morning plans, grid events, Grid Confidence changes, and reserve advice.

Safety rule:

> Panic preserves reserve conservatively; neither AHM nor Panic automatically starts a smart thermal load.

Status:

Implementation and supervised deployment validation completed on 2026-08-09;
the increment is included in the 1.3.14 closure release.

---

## EnergyHub 1.3.5 — PV2 and Total PV Telemetry

Goal:

Expose both installed PV arrays and trustworthy combined production, then use
those entities in the solar charts.

Planned work:

- optional read-only Modbus polling behind the existing serial owner/lock;
- PV2 voltage, PV2 power, and telemetry freshness/health;
- Total PV Power derived only from fresh PV1 and PV2 samples;
- CRC, range, timeout, malformed-response, unsupported-firmware, restart, and
  recovery behavior;
- MQTT discovery, tests, release notes, and documentation;
- monitored deployment followed by PV1/PV2/Total PV chart integration.

No undocumented Modbus writes or output-2 control belong in this release.

Status:

Implementation, supervised deployment, nighttime validation, and homeowner-
observed daylight chart validation are complete. Read-only
registers 4563 and 4564 passed high-production and full-battery/curtailed-
production probes on the installed inverter. The increment is included in the
monitored 1.3.14 closure release.

---

## EnergyHub 1.3.6 — Retained Hybrid State Cleanup

Goal:

Ensure an EnergyHub upgrade deterministically replaces an incompatible retained
Hybrid decision reason before a later Home Assistant restart reloads it.

Scope:

- publish the concise initial Hybrid state after MQTT Discovery during app
  startup;
- retain the replacement so future Home Assistant restarts receive it;
- enforce the 255-character Home Assistant state boundary at the reason
  publisher;
- keep the full calculation and control decisions unchanged.

Status:

Implemented, regression-tested, deployed, and startup-validated. The increment
is included in the monitored 1.3.14 closure release.

---

## EnergyHub 1.3.7 — Early Solar Handover

Goal:

Avoid unnecessary grid use between 06:05 and 07:00 when Adaptive Hybrid has
already reached its reserve and strong early solar is independently confirmed.

Scope:

- request one dated 06:00-07:00 Solcast interval from Home Assistant at 06:05;
- permit release only from confirmed Hybrid Grid Hold, never Charging;
- require Autopilot, current date, local 06:00-07:00 time, fresh inverter
  telemetry, fresh aligned Total Solar, grid present, and SOC at or above the
  retained target;
- require at least 300 W live Total Solar and 1.6 kWh forecast for the interval;
- publish focused evidence and the confirmed transition outcome;
- keep Grid Hold unchanged on every missing, stale, insufficient, invalid, or
  failed gate, with the normal 07:00 Solar handover as fallback.

Status:

Prepared, privately deployed, startup-validated, and included in the monitored
1.3.8 baseline and the 1.3.14 closure release.

---

## EnergyHub 1.3.8 — Night Target and Heat-Pump Ownership

Goal:

Close the unexpected-night-load gap without introducing another public
controller: AHM remains the night owner, Panic remains the daytime owner, and
the family can use heat pumps normally while the grid is trusted.

Scope:

- persist the date through which the 23:50 AHM target is authoritative;
- on every fresh night telemetry cycle, remain Solar above target, enter Grid
  Hold at target, and enter or resume Charging below target;
- keep an offline request observational and retry only after the grid returns;
- clear night enforcement after a confirmed non-AHM morning Solar handover;
- define trusted heat-pump use as Normal Grid Confidence, present grid, and
  fresh EnergyHub telemetry;
- while trusted, leave every heat pump under family manual control;
- while untrusted, shed once at AHM minimum +30, lock OFF at minimum +20, and
  unlock at minimum +40 without automatically restarting anything;
- add outbound Telegram ownership guidance plus SOC warnings at AHM minimum
  +30, +20, +10, and +0.

Status:

Regression-tested, synchronized to Home Assistant, started, privately
monitored, and publicly released as the previous public baseline.

---

## EnergyHub 1.3.9 — SOC Anomaly Journal

Goal:

Persist suspicious SOC changes with enough surrounding evidence to distinguish
a possible battery/BMS issue from inverter estimation, PI30MAX telemetry,
rounding, communication recovery, or an app restart.

Scope:

- record SOC jumps and short oscillations in a bounded persistent journal;
- capture previous/current SOC, delta, elapsed time, battery voltage/current,
  PV, load, grid state, operating mode, telemetry freshness, and restart or
  recovery context;
- expose the latest event and event count for diagnostics;
- treat the journal as evidence, not as a battery-health diagnosis;
- keep the observer strictly read-only: no telemetry quarantine, control
  inhibition, inverter action, load action, or automatic notification.

Status:

Delivered, privately deployed, live-validated, and included in the monitored
1.3.14 closure release.

---

## EnergyHub 1.3.10 — Inverter Fault Diagnostics

Goal:

Preserve inverter faults and the conditions preceding them before introducing
automatic overload action.

Scope:

- decode and persist verified QPIWS fault/warning transitions;
- retain a bounded pre-fault telemetry snapshot;
- expose current and recent faults to Home Assistant and the morning report;
- research community-reported register 4530 only through bounded read-only
  probes on the installed firmware;
- keep fault observation separate from automatic load shedding.

Status:

Delivered, privately deployed, and included in the monitored 1.3.14 closure
release. Automatic fault recovery and overload action remain deferred to 2.0.

---

## EnergyHub 1.3.11 — Tariff-Split Grid Import Accounting

Goal:

Turn the existing estimated Grid Import stream into understandable cheap- and
standard-tariff energy and cost statistics without changing inverter control.

Scope:

- classify every estimated import interval by the configured tariff window;
- persist daily cheap and standard import separately across restart and
  midnight rollover;
- expose daily, weekly, and monthly kWh totals for both classes;
- apply configurable informational prices and publish estimated cost;
- add tariff-split dashboard statistics and a concise Telegram morning line;
- preserve the current warning that EnergyHub Grid Import is estimated and is
  not a billing-grade meter.

This release does not add multiple charging windows, dynamic prices, or Net
Billing control. Those remain later tariff-scheduling/economic-planning work.

Status:

Delivered, privately deployed, and included in the monitored 1.3.14 closure
release without changing inverter scheduling or control.

---

## EnergyHub 1.3.12 — Meaningful Inverter Messages

Goal:

Preserve raw QPIWS evidence while keeping routine overnight PV-loss-only
transitions out of operational dashboard incident positions.

Status:

Delivered, deployed, and monitored. Mixed incidents retain every meaningful
message, while diagnostic history remains available for investigation.

---

## EnergyHub 1.3.13 — Normal-Grid Reserve Hysteresis

Goal:

Transfer AHM ownership to daytime Panic at 07:00, hold a Normal-grid 20% floor,
release Solar at 30%, and leave protected smart plugs under family control
while grid trust is valid.

Status:

Delivered and incorporated into the monitored 1.3.14 closure release.

---

## EnergyHub 1.3.14 — Grid-Available Reserve Guard

Goal:

Require physical grid availability before Normal-grid Solar requests the 20%
Grid Hold, remain command-free while the grid is absent, and reevaluate
immediately after grid return.

Status:

Repository-tested, deployed on 2026-08-24, startup-validated, monitored through
2026-08-26 without a reported release blocker, and publicly released as the
planned close of the 1.x feature line.

---

## EnergyHub Telegram Intents — Ukrainian/English Text and Voice Experiment

Goal:

Test family-friendly conversational control before committing to the complete
3.0 interface, using the existing timed Home Assistant load controls and the
central EnergyHub safety decision.

Representative requests:

- `Увімкни кондиціонер на третьому поверсі на три години.`
- `Чи вистачить батареї до ранку?`
- `Why are we using the grid?`
- `Prepare the house for a possible outage.`

Required control boundary:

```text
Telegram/voice
→ authenticated structured intent
→ EnergyHub safety evaluation
→ allow / shorten / delay / deny
→ Home Assistant action
→ observed-state confirmation
```

Sequence:

1. authenticated Ukrainian/English chat with read-only questions;
2. bounded text requests for registered devices, such as running the
   third-floor air conditioner for three hours;
3. interpreted-action echo, explicit confirmation, expiry, audit, and observed
   device-state acknowledgement;
4. Ukrainian/English Telegram voice messages translated into the same tested
   intent contract;
5. no raw entity IDs, MQTT, PI30MAX, or Modbus commands exposed to the
   assistant.

This experiment informs the full 3.0 architecture; it does not bypass reserve
lockouts, Grid Confidence, Panic, device timing, or immutable safety limits.

---

## EnergyHub 2.0 — Fault-Aware Smart Thermal & Flexible Loads

Goal:

Use flexible heating, cooling, water heating, and EV charging as energy assets while preserving comfort, departure requirements, and battery resilience.

This milestone introduces a capability-based Load Manager with tested automatic starts, ownership, priority, hysteresis, minimum runtime/off-time, and coordinated operation. The design replaces the old narrow Away Mode concept.

Planned inputs:

- current and transitioned QPIWS warning/fault bits;
- persistent inverter fault history and a bounded pre-fault telemetry buffer;
- optional model/firmware-verified read-only fault-code telemetry;
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

- begin with persistent inverter-fault diagnostics and operating-condition
  snapshots rather than guessing a permanent overload threshold;
- calibrate separate safe-load margins for battery/inverter and grid/bypass
  operation from observed load, warnings, faults, restarts, and startup peaks;
- run overload protection in Dry Run before any automatic load command;
- use otherwise curtailed or unused solar for useful heating/cooling;
- preheat or precool during cheap-tariff periods when justified;
- preserve required battery reserve;
- coordinate multiple heat pumps and thermal loads;
- provide an observer-first Peak Load Guard that pauses explicitly opted-in
  thermal loads one at a time after sustained high household power, confirms
  the measured result, and restores conservatively after sustained recovery;
- maximize direct solar use for EV charging and use approved low-price periods when solar alone cannot meet a departure target;
- prevent household-battery discharge into an EV unless the homeowner explicitly permits it;
- exclude EnergyHub-controlled flexible energy from the learned base household load;
- under normal optimization, stop only loads that EnergyHub previously started;
  Peak Load Guard may additionally pause an explicitly opted-in manually
  started load, but must remember its pre-shed state and apply its separate
  restoration permission;
- support time-bounded dashboard, automation, voice, or messenger requests through a deterministic EnergyHub override evaluator;
- introduce a generic Grid Input / Breaker Guard that can reduce charging current when household demand rises.

Fault diagnostics and overload protection are staged independently:

1. improve QPIWS transition capture and persist fault snapshots;
2. perform a bounded read-only POW-HVM10.2M probe for any independently
   verified fault-code register, treating PI30MAX and Modbus as separate
   capability layers;
3. collect sufficient operating history to select mode-specific thresholds and
   safety margins;
4. run observer/Dry Run decisions for several days or weeks;
5. validate attended preventive and emergency shedding one load at a time;
6. enable sequential automatic shedding and later conservative restoration
   only after every preceding gate passes.

Community reports that Modbus register 4530 may expose an error code and that
Menu 25 may retain fault codes are research leads only. EnergyHub must verify
the installed model/firmware with read-only access and must never write an
undocumented register.

Voice or messenger assistants are request interfaces, not safety authorities. EnergyHub evaluates data freshness, projected reserve, grid availability, active strategy, load energy, and immutable emergency limits before allowing, shortening, delaying, or denying an override.

Status:

Planned. The 2.0 family begins with diagnostics, bounded recovery research,
and calibration; it does not
ship a guessed active overload threshold.

---

## EnergyHub 3.0 — Conversational EnergyHub

Goal:

Provide secure text and voice interaction through Telegram first, while keeping
messaging providers and language models outside the EnergyHub safety boundary.

Planned work:

- evolve the outbound Telegram Family Assistant into the first adapter behind a
  provider-neutral messaging interface;
- versioned structured intents shared by Telegram, dashboards, automations, and
  future Home Assistant Assist;
- read-only status, health, mode, forecast, tariff, reserve, and decision
  explanations first;
- authenticated, authorized, audited, rate-limited, and bounded control intents
  only after the read-only stage;
- Telegram voice-message transcription into the same intent contract;
- Ukrainian and English text, aliases, confirmations, explanations, and voice
  transcription, with replies in the requester's configured or detected
  language;
- deterministic handling of bilingual device names, durations, and explicit
  confirmation before a voice-derived control request;
- EnergyHub responses of `allow`, `shorten`, `delay`, or `deny` with reasons;
- future WhatsApp, Signal, Matrix, or other adapters only where their supported
  APIs and authentication models are suitable;
- no raw PI30MAX, Modbus, MQTT, switch-entity, or inverter commands exposed to
  users, messaging providers, voice systems, or language models.

Telegram and other messengers are request/presentation adapters, not direct
command proxies or safety authorities.

Status:

Outbound Telegram reporting and notifications are implemented. A bounded
Ukrainian/English text-then-voice experiment is planned after 2.0. Full
inbound authentication, authorization, audit, and generalized bounded intents
remain the 3.0 milestone.

---

## EnergyHub 4.0 — Tariff Scheduling

Goal:

Generalize the current single night window into safe fixed or dynamic import
schedules without making electricity export a prerequisite.

Planned direction:

- one, two, or three configurable cheap periods per day;
- weekday/weekend schedules, midnight crossing, timezone, and daylight-saving
  handling;
- active and next eligible tariff interval visibility;
- AHM/Hybrid evaluation for each eligible period;
- avoid grid charging when forecast and protected reserve already suffice;
- preserve the current single night window as the migration default;
- later optional day-ahead import prices and shadow planning;
- later optional dynamic import prices after fixed-window behavior is proven;
- implement only when household need or public adoption justifies the work.

Profiles, configuration validation, forecast fallback, support bundles, replay,
shadow mode, dependency health, and bounded recovery remain cross-cutting
engineering requirements and may land incrementally in any release that needs
them.

---

## EnergyHub 5.0 — Hardware & Economic Ecosystem

Goal:

Support additional validated inverter capabilities and optional economic import
and export planning without weakening resilience or hardware safety.

Planned direction:

- normalized inverter capability model separated from communication transport;
- additional PowMr and other vendor adapters only after model/firmware-specific
  telemetry, commands, acknowledgement, limits, and recovery are verified;
- telemetry-only and shadow modes for unknown or unvalidated models;
- day-ahead import/export prices and interval energy plans;
- optional Net Billing, export limits, revenue, battery wear, and
  planned-versus-actual accounting;
- staged monitoring, shadow planning, attended control, automatic import, and
  stricter separately validated export control;
- export only with compatible hardware, appropriate metering, supplier
  contract, and applicable regional/grid permission;
- a future native Home Assistant integration exposing intent-level EnergyHub
  triggers, conditions, actions, and events without exposing internal topics or
  command mappings.

Net Billing is an advanced optional capability, not EnergyHub's central product
promise.

Research backlog supporting these milestones:

- PowMr second-output control, beginning with model/firmware verification and
  bounded read-only capability discovery;
- a generic inverter capability model;
- a replay and what-if laboratory;
- conservative forecast fallback;
- privacy-sanitized support bundles;
- solar-first EV charging.

---

## Long-term vision — Full Home Energy Management System

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
