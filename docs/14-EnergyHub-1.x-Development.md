# EnergyHub 1.x Development Plan

## Purpose

This document is the working plan for EnergyHub 1.x development after the tested EnergyHub 1.0.2 release.

The local `SKrav69/EnergyHub` repository is the development source of truth. The stable public distribution repository is not modified during 1.x development.

## Released baseline

- release: EnergyHub 1.0.2;
- tag: `v1.0.2`;
- status: released and tested;
- invariant: existing Solar, Hybrid Charging, Hybrid Grid Hold, Panic, Autopilot, telemetry, health, persistence, MQTT, and Home Assistant behavior remains unchanged unless a concrete issue requires a narrowly scoped correction.

Every 1.x issue starts from an understood baseline and includes validation proportional to its risk. Smart-load work is additive and must not enter the inverter-control path accidentally.

## Development rules

- work from the local development repository as the source of truth;
- handle one issue at a time;
- avoid broad refactors without a concrete reason and a safety net;
- preserve EnergyHub 1.0.2 behavior;
- edit complete, coherent files rather than leaving implementation fragments;
- keep secrets, Zigbee network keys, runtime exports, and device-specific credentials out of Git;
- do not modify the stable public distribution repository during 1.x development;
- validate pure policy with automated tests and hardware behavior on the real installation.

## EnergyHub 1.1 outcome

EnergyHub 1.1 begins Smart Loads groundwork while continuing the test-drive and telemetry-robustness work planned after 1.0.2.

The target outcome is safe, explainable smart-plug observation, manual control, timed OFF behavior, and conservative reserve-only OFF protection. EnergyHub 1.1 never starts a thermal load. The first automatic Smart Thermal controller remains deferred to 1.5.

## Issue sequence

### Issue 1 — Development documentation

Outcome:

- the roadmap, backlog, architecture, current state, decisions, and history agree on the 1.x direction;
- 1.1 explicitly includes Zigbee2MQTT, two smart-plug validations, focused dashboards, auto-off timers, and reserve-only OFF guards;
- automatic Smart Thermal ownership and starts remain the 1.5 milestone.

Validation:

- no current-state contradiction about 1.1 reserve-only behavior versus 1.5 automatic Smart Thermal scope;
- no change to the tested EnergyHub 1.0.2 inverter runtime or strategy behavior;
- Home Assistant changes remain narrowly scoped to the documented smart-plug functions.

### Issue 2 — Zigbee2MQTT and SONOFF ZBDongle-E

Outcome:

- Zigbee2MQTT owns the coordinator through its persistent `/dev/serial/by-id/...` path;
- the coordinator remains distinct from the PowMr FTDI serial adapter;
- the coordinator reconnects after service and host restart;
- configuration and recovery steps are documented without committing secrets.

Required checks:

- identify the exact SONOFF persistent serial path;
- confirm that ZHA is not using the coordinator;
- select the Zigbee2MQTT adapter appropriate for the ZBDongle-E firmware;
- configure MQTT connectivity, base topic, channel, and secure network settings;
- place the coordinator to reduce 2.4 GHz USB interference;
- verify coordinator startup, MQTT availability, logs, and restart behavior;
- back up the Zigbee coordinator/network data through the supported operational workflow.

Safety boundary:

> EnergyHub never opens the Zigbee coordinator serial device. Zigbee2MQTT owns radio/device transport.

Implementation status on 2026-08-02:

- installed the official stable Zigbee2MQTT Home Assistant app `2.13.0-1`;
- left the discovered SONOFF coordinator unconfigured in ZHA so exactly one Zigbee stack owns it;
- configured the ZBDongle-E through its persistent `/dev/serial/by-id/...` identity with `adapter: ember` and `rtscts: false`;
- kept the coordinator identity separate from the existing PowMr FTDI identity;
- selected Zigbee channel 25 after detecting the closest active 2.4 GHz access point on Wi-Fi channel 1;
- connected to the existing Mosquitto service, enabled Home Assistant discovery, and kept MQTT credentials and generated Zigbee security values outside Git;
- confirmed EmberZNet firmware `7.4.4 [GA]`, coordinator startup, MQTT connection, Home Assistant discovery publication, and successful recovery after both a Zigbee2MQTT app restart and a full Home Assistant host restart;
- confirmed the coordinator is installed on a 1 m USB extension away from the Raspberry Pi and inverter;
- verified a private encrypted Home Assistant backup containing the Zigbee2MQTT app and its data;
- documented configuration, backup, recovery, and pairing gates in [Zigbee2MQTT with SONOFF ZBDongle-E](hardware/zigbee2mqtt-zbdongle-e.md).

Issue 2 completed on 2026-08-02. The coordinator remains owned exclusively by Zigbee2MQTT; the Home Assistant ZHA discovery prompt must not be submitted.

### Issue 3 — Pair and validate two Zigbee smart plugs

Outcome:

- two plugs have stable, room-oriented names;
- both can be controlled manually from Home Assistant;
- device availability and link quality are visible;
- electrical measurements are validated where supported;
- restart and power-loss behavior is known.

Validation matrix for each plug:

| Check | Expected result |
|---|---|
| Pairing interview | Device is fully supported with no interview error |
| Manual on/off | Command and physical state agree |
| Availability | Offline/online changes are observable |
| Link quality | Stable enough for the installation location |
| Power reporting | Plausible under a known test load, if supported |
| Energy reporting | Increases plausibly over time, if supported |
| Plug power cycle | State and configured power-on behavior are understood |
| Zigbee2MQTT restart | State is recovered without an unsafe toggle |
| Home Assistant restart | Entities and manual controls recover |

The plugs remain manual devices after validation. Pairing alone does not authorize EnergyHub automation.

Progress through 2026-08-06:

- `first_floor_heat_pump_plug` paired as `TS011F_plug_1_1` (`Zbeacon`), with direct power monitoring and observed link quality about 164–168;
- `second_floor_heat_pump_plug` paired as `TS011F_plug_3` (`Tuya`), with polled power monitoring and observed link quality about 152–172;
- both pairing interviews completed and both plugs passed Zigbee2MQTT and physical-button on/off synchronization tests;
- both plugs are configured with power-outage memory `off` and remain under manual control;
- at 21:30 on 2026-08-02, one Ember `ASH_ERROR_TIMEOUTS` transaction failure disconnected the adapter and stopped Zigbee2MQTT while the Home Assistant app Watchdog was disabled;
- at 17:29 on 2026-08-03, an attended manual Start recovered the same Zigbee network, both paired devices and states, MQTT, availability, and Home Assistant discovery without re-pairing or an observed relay command;
- Watchdog was enabled only after that successful recovery;
- on 2026-08-05, ASH reset and restarted but EZSP startup failed with `HOST_FATAL_ERROR`; Zigbee2MQTT exited while Watchdog was enabled and no autonomous recovery was observed;
- on 2026-08-06 at 07:30, a healthy bridge hit `ASH_ERROR_TIMEOUTS` during `SEND_UNICAST`; Supervisor Watchdog automatically launched ten restart attempts through 07:35, but every attempt opened the serial port, performed five ASH resets, and failed EZSP startup with `HOST_FATAL_ERROR`;
- the Watchdog crash loop then stopped; an attended manual Start at 11:51 established ASH on its second reset and resumed the same coordinator network, MQTT, both devices and their ON relay states, availability, and fresh telemetry without re-pairing or an observed relay toggle;
- second-floor Offline-to-Online availability recovery passed, and reconnecting power while configured OFF returned safely OFF;
- a later Home Assistant restart retained both devices Online; the first-floor plug remained ON and its heat pump continued cooling;
- first-floor electrical reports arrived asynchronously during inverter-compressor ramp-up, with a stabilized trend example of 804 W, 3.37 A, and 226 V;
- second-floor live power measurements and increasing energy were observed;
- availability recovery did not guarantee that retained or last-known electrical measurements were fresh.

Remaining Issue 3 checks:

- collect host USB/power and Supervisor logs around the failures, validate the extension cable and power path, and review a supported coordinator-firmware update before changing hardware or software;
- implement alerting for bridge offline/crash-loop state and allow no more than bounded recovery attempts with a cooldown and attended escalation;
- compare electrical telemetry with a reference meter if calibrated accuracy becomes necessary;
- verify both heat-pump nameplates, plug electrical load ratings, and inductive/inverter-load suitability before unattended switching.

The observed electrical values are trend data. They are not reference-meter calibration, electrical-protection inputs, or proof that either smart plug is suitable for its heat pump.

For any later automatic controller, recovery is conservative: bridge and device availability must both be online, every required measurement must have a fresh post-recovery report, and ownership must be reconstructed safely before commands resume. A manual or future Watchdog recovery, or an online availability flag alone, must never authorize an automatic start or reuse stale power telemetry.

### Immediate reliability and seasonal reserve follow-up

Before future Smart Thermal automatic starts are considered:

1. deploy and validate the completed Mission Control six-card and auto-off changes;
2. implement observable, bounded health handling for Zigbee2MQTT and required Home Assistant integrations without speculative relay commands or restart loops;
3. add a narrow tested overnight SOC hard-floor guard, then run Adaptive Night Hybrid projection in shadow mode before it can enter Grid Hold automatically; exit only after useful solar is confirmed;
4. keep Smart Thermal automatic starts disabled whenever health, availability, freshness, ownership, or projected reserve is unsafe.

Adaptive Night Hybrid must protect a morning resilience horizon, not merely reach sunrise or the first visible PV production. A September cloud layer can leave SOC near the protected reserve just as normal coffee, cooking, pumps, and other morning activity raise house load. The controller therefore needs two separate thresholds:

- a hard SOC floor that triggers immediate conservative action when fresh repeated readings approach it;
- a dynamic morning resilience target that retains enough energy above the floor to carry a conservative morning net-load allowance if the grid fails.

The proposed target is:

```text
morning_contingency_soc =
    conservative_net_load_energy_until_resilience_horizon
    / usable_battery_energy

morning_resilience_target =
    protected_reserve
    + morning_contingency_soc
    + forecast_and_measurement_margin
```

The net-load estimate must include the known morning load increase and use a conservative PV contribution. Overnight SOC slope alone is not sufficient. When forecast, load history, or SOC-rate quality is unavailable, the calculation must fall back conservatively rather than assume clear-sky generation. Grid Hold should continue beyond the current fixed 07:00 exit when useful solar is not confirmed. Exit requires sustained actual PV surplus, non-declining SOC, and adequate remaining forecast, with hysteresis so one brief cloud break cannot cause Solar/Hybrid oscillation.

The current household cheap-tariff window is 23:00–07:00 and the inverter is configured for 30 A grid charging. Adaptive Night Hybrid must work backward from the 07:00 deadline. It estimates the time required to reach the morning resilience target from a conservative observed SOC-per-hour charge rate and adds a completion margin. For this installation, 06:00 is the initial absolute latest-start backstop, not a guarantee that one hour is always sufficient. If the required SOC gain needs longer, charging must start earlier. The 30 A setting alone is not treated as achieved battery energy because battery capacity, voltage, charge taper, conversion losses, and inverter behavior affect the real rate.

```text
required_charge_soc = max(0, morning_resilience_target - current_soc)

required_charge_hours =
    required_charge_soc / conservative_observed_grid_charge_rate_soc_per_hour

start_by =
    cheap_tariff_end
    - required_charge_hours
    - completion_margin
```

If the target becomes unreachable inside the cheap window, the system needs an explicit configured policy rather than a hidden assumption: continue after 07:00 for resilience, stop at 07:00 to protect cost, or request attended confirmation. The dashboard must show this condition before the deadline whenever possible.

For example, 22% SOC at 06:00 is not safe merely because sunrise has occurred. With grid available, the hard-floor guard should enter Hybrid, charge toward the validated morning resilience target, and then hold it until sustainable solar is confirmed. If grid is already unavailable, the controller can only inhibit discretionary smart loads, protect the remaining reserve, and alert. Exact target values remain pending battery/load analysis and shadow-mode validation; this design does not yet change the released 1.0.2 runtime policy.

### Future configuration control plane

EnergyHub 1.2 will replace trusted household-specific constants with a validated configuration model and a dedicated Home Assistant Settings view. This includes the cheap-tariff window, Hybrid evaluation and target values, battery capacity and charge-rate assumptions, protected reserve, useful-solar confirmation, automatic Panic-check enable, Panic window and 80%/95% targets, and related safe bounds.

Home Assistant provides the editing interface, but EnergyHub owns and persists the effective validated configuration. Every change requires range and cross-field validation, acknowledgement, reconciliation back to the dashboard, and an audit record. Editing a value must not itself issue an inverter command. Feature enables remain separate: automatic Panic may be disabled without disabling manual Panic or health monitoring, and Smart Thermal automation must never be enabled implicitly by Autopilot.

The Settings view should also explain the current decision with read-only values: calculated morning target, required SOC gain, estimated charge duration, start-by time, projected completion, current policy enables, and any validation or deadline warning. Defaults and migration must reproduce 1.0.2 exactly before any parameter becomes editable.

The 2026-08-06 beacon incident exposed a separate integration-health gap. The beacon is a Tuya Wi-Fi light, not a Zigbee device. Home Assistant Repairs reported expired Tuya authentication; attended re-confirmation restored control. EnergyHub had calculated the correct color, so future health reporting must distinguish correct policy output from failed end-to-end actuator delivery.

### Issue 4 — Smart-plug dashboards and reserve protection

Outcome:

- dedicated Heat Pumps and Water Systems views expose compact controls and consumption history;
- all three heat pumps have matching manual switch, live-power, 0–12 h auto-off, and absolute turn-off-time cards;
- the boiler and heat pumps have documented reserve-only OFF policies and explicit lockouts;
- the basement pump remains outside automatic shedding;
- no EnergyHub automation turns a boiler or heat pump on.

The dedicated Heat Pumps view now uses one compact operating section for each first-, second-, and third-floor heat pump: switch, live power, 0–12 h auto-off duration, and absolute local turn-off time. Duration `0` is manual mode. The turn-off sensors render `Manual` while idle and `Today HH:MM`, `Tomorrow HH:MM`, or a local date/time while active. Shared daily/weekly/monthly consumption history remains below the controls. The first- and second-floor controls use the paired Zigbee plugs; the third floor retains its existing Xiaomi plug and locally integrates live watts for history. The duplicated floor sections were removed from Mission Control so it remains a compact whole-house energy/status/decision view. A compact whole-house Smart Thermal summary remains future controller work.

Future 1.5 capability model:

- stable load identifier;
- switch entity/topic;
- availability entity/topic;
- measured or expected power;
- heating or cooling role;
- room temperature input;
- comfort band;
- minimum runtime;
- cooldown;
- priority;
- ownership state;
- manual override state.

The 40 L hot-water boiler is added as a future flexible-load capability, while the basement water pump is initially classified as critical infrastructure rather than a shed load. The Xiaomi devices named `2nd floor water Boiler Smart Power` (`chuangmi_212a01_c91f`) and `Basement Water Smart Power` (`chuangmi_212a01_ac48`) were inventoried. Both expose switch, power, current, voltage, Energy Today, Energy Month, temperature, surge, indicator-light, and diagnostic entities. Units, scaling, reset/statistics behavior, and safe control semantics still require supervised validation.

The working tree now contains separate Heat Pumps and Water Systems views. Compact device cards expose manual on/off, unavailable state, live watts, and heat-pump auto-off controls. Each view shows daily bars for 7 days, weekly bars for 6 weeks, and monthly bars for 12 months. Floor 1/2 history uses native cumulative energy. Third-floor, boiler, and pump history uses local left-method Integral sensors with a five-minute maximum sub-interval after Xiaomi cloud counters produced implausible daily values. These sensors start at deployment and cannot import older Xiaomi cloud history. Local integration and statistics require supervised validation. Pump nameplate, motor starting surge, plug rating, outage behavior, water-system consequences, and safe switching must be validated before any SOC policy is even proposed for it.

Future 1.5 decision inputs:

- capability and current device state;
- room temperature and comfort target;
- battery SOC and protected reserve;
- available or estimated solar surplus;
- cheap-tariff eligibility;
- grid availability and Grid Confidence;
- forecast context where it changes the decision safely;
- required input freshness.

Future 1.5 automatic-control safety behavior:

- never start when required inputs are missing, stale, or invalid;
- never stop a load unless EnergyHub owns the current run;
- release ownership when a manual action overrides the controller;
- enforce minimum runtime and cooldown without defeating an explicit safety stop;
- reconstruct conservatively after restart and do not blindly toggle the load;
- expose the selected action, reason, ownership, and blocking condition;
- bound command retries and surface failures;
- allow immediate homeowner disable/manual control;
- preserve all EnergyHub 1.0.2 inverter behavior.

The first constrained SOC policy is now implemented for the boiler only:

- fresh SOC reaching 50% requests boiler OFF once;
- any ON request at 41–50% is allowed, including the existing Xiaomi motion automation because its source cannot be distinguished reliably from a homeowner action;
- fresh SOC reaching 40% latches `input_boolean.energyhub_water_boiler_soc_lockout`, requests OFF, and rejects later ON requests;
- fresh SOC reaching 60% clears the latch without turning the boiler on;
- persistent notifications expose the action and resulting observed state;
- stale telemetry causes no new plug command, and integration/device unavailability means the lockout remains best effort rather than a physical interlock.

The heat pumps now have a separate grid-confidence-aware reserve-only policy with a fixed household priority order:

- fully trusted means categorical Grid Confidence `normal`, exactly 100% 24-hour availability, 48 available hours over 48 hours, present grid voltage, and fresh EnergyHub telemetry;
- with a fully trusted grid, fresh SOC reaching 50% latches `input_boolean.energyhub_heat_pump_soc_lockout`, requests every heat pump OFF, and rejects later ON requests; fresh 60% SOC clears the latch;
- any missing, stale, unavailable, or degraded confidence input selects the conservative policy;
- in the conservative policy, fresh SOC reaching 80% requests all running heat pumps OFF once;
- a homeowner may override that 80% request while the global lockout is inactive;
- floor 2 is shed again at 70%, floor 1 at 60%, and floor 3 remains protected until 50%;
- fresh SOC reaching 50% latches the all-floor lockout, and fresh 90% SOC clears the conservative latch;
- neither recovery threshold turns a heat pump on;
- intermediate shedding is not reconstructed blindly after restart or device recovery, while the 50% lockout is re-evaluated after trustworthy telemetry returns;
- degradation from fully trusted grid conditions applies the conservative all-floor shed when SOC is already at or below 80%;
- dashboard lockout and forced OFF remain best-effort controls and cannot be represented as physically guaranteed while Home Assistant, Zigbee2MQTT, an integration, the network, or a plug is unavailable.

There is no automatic heat-pump start or Smart Thermal ownership in this version. A later Smart Thermal controller requires explicit participation, ownership, demand, availability, freshness, runtime, cooldown, and priority state. It must never interpret SOC recovery alone as permission to turn a homeowner-disabled heat pump on.

For heat pumps, smart-plug mains removal is an emergency reserve action. Minimum runtime, minimum off-time, compressor cooldown, load/nameplate suitability, bounded retries, and sequential restoration are mandatory. Normal comfort regulation should use a supported climate interface when one becomes available.

Future early-solar permission may bypass the normal 90% threshold only when dependable net surplus and the projected reserve are safe. Raw PV power such as 1 kW is insufficient by itself: house load, battery recovery requirement, forecast uncertainty, expected device power, remaining solar energy, and a sustained observation window all participate. The calculation should first run in observer mode. A later Smart Thermal controller would start loads one at a time and observe the new net state before considering another start.

Future Smart Thermal validation stages:

1. pure unit tests with no MQTT or device commands;
2. observer mode using live inputs but emitting no commands;
3. manual command approval with a benign test load;
4. supervised short thermal-load runs;
5. restart, unavailable-device, stale-input, and manual-override tests;
6. review before any unattended operation.

## Remaining 1.1 test-drive work

Smart Loads does not replace the already agreed 1.1 robustness work:

- correct defects found during real Autopilot operation;
- refine daytime SUB and non-billing-grade Grid Import estimation;
- improve anomaly context and diagnostic logs;
- add telemetry plausibility and suspicious-SOC handling;
- review the Panic live-PV policy using measured evidence;
- improve notifications, entities, charts, dashboards, and usability.

Each item remains a separate issue.

## Later 1.x milestones

### 1.2 — Configurable EnergyHub

Move trusted household strategy values into validated configuration with safe bounds and clear separation between hardware limits and policy preferences.

### 1.3 — Recovery & Resilience

Formalize bounded recovery for MQTT, network, serial communication, `mpp-solar`, Home Assistant connectivity, startup, shutdown, and external watchdog behavior.

### 1.4 — Remote Access & Telegram

Add secure remote visibility, structured alerts, authenticated status queries, and carefully bounded remote commands without moving decision logic into the cloud.

### 1.5 — Smart Thermal Energy Expansion

Mature the validated 1.1 prototype into coordinated multi-load heating and cooling with seasonal comfort policy, priorities, shared electrical limits, and production-grade restart/recovery behavior.

## Definition of done for a 1.x issue

An issue is complete when:

- scope and user outcome are explicit;
- responsibility and safety boundaries are preserved;
- implementation and configuration are complete for that scope;
- automated and real-system checks appropriate to the risk pass;
- failure, restart, and manual-override behavior are understood;
- documentation reflects stable behavior;
- Git contains no secrets, runtime exports, unrelated refactors, or accidental changes;
- the stable public distribution repository remains untouched.
