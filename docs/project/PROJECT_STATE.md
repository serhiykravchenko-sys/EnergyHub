# EnergyHub Project State

Last updated: 2026-08-20.

## Current milestone

**EnergyHub 1.3.8 — Night Target and Heat-Pump Ownership is the current public distribution baseline.**

The reviewed add-on, Home Assistant automations, and Telegram Family Assistant
0.1.9 are synchronized, started, and privately monitored. EnergyHub keeps the
dated 23:50 AHM target authoritative until confirmed morning Solar, gives the
family normal heat-pump control while the grid is trusted, and applies
reserve-relative protection otherwise. The companion reports ownership and
sends active-heat-pump SOC warnings outside its overnight quiet window.
The monitored release was selectively promoted after repository, privacy, and
public-scope review.

## 1.3.3 coordinated decision state

- AHM owns 23:50–07:00 and calculates a target from a user-selected 20–50% minimum reserve plus the larger of the effective morning bridge or aligned post-07:00 consumption/solar deficit.
- A first forecast hour at or above 300 W followed by at least 600 W earns one independently validated hour of morning-gap credit; the raw threshold time remains retained for audit.
- Panic owns 07:00–23:50 and uses simple Grid Confidence targets: normal 20%, unstable 60%, risk 80%, panic 95%.
- Only an AHM target actually missed at the 07:00 handover becomes persisted daytime charging debt.
- Panic can remain armed while grid is offline, charge when it returns, and preserve reserve in the distinct `panic_grid_hold` mode.
- AHM always takes ownership from Panic at 23:50.
- In 1.3.8, Normal Grid Confidence plus present grid and fresh
  telemetry permits family heat-pump control in any operating strategy;
  otherwise AHM-relative protection applies. EnergyHub never starts a heat
  pump automatically.

EnergyHub 1.0.2 is tagged, released, and tested. Feature development and the functional release audit for that baseline are complete. Selected Medium-priority corrections, dependency pinning, credential hardening, packaging fixes, persistent serial access, executable build tests, Home Assistant rebuild validation, and full host-restart validation are complete.

The 1.0.2 behavior is the compatibility baseline for all 1.x work.

## Current architecture

```text
PowMr inverter
  ↕ PI30MAX / persistent FTDI USB-RS232 path
EnergyHub app
  ↕ MQTT
Home Assistant
  ↕
Solar forecast, helpers, schedules, dashboards, notifications, smart plugs
```

Responsibilities:

- decision services decide;
- `InverterController` executes and verifies;
- `main.py` orchestrates;
- Home Assistant owns UI, schedules, integrations, and notification delivery.

## Release platform

- Home Assistant OS with Supervisor/Apps;
- `aarch64`, validated on Raspberry Pi 4;
- PowMr 10.2M / PI30MAX;
- FTDI USB-RS232 through `/dev/serial/by-id/...`;
- Mosquitto MQTT broker;
- Python 3.11 Alpine image;
- pinned `paho-mqtt==1.6.1`, `mppsolar==0.16.56`, and `pyserial==3.5`.

## Implemented operating strategies

| Strategy | State | Target/exit |
|---|---|---|
| Solar | SBU + OSO | default |
| Hybrid Charging | SUB + SNU | adaptive SOC 30–95% |
| Hybrid Grid Hold | SUB + OSO | 07:00 handover |
| Panic Charging | SUB + SNU | effective SOC 20/60/80/95% |
| Panic Grid Hold | SUB + OSO | AHM takeover at 23:50 |

Away Mode is not part of EnergyHub 1.3. EnergyHub supplies monitored smart plugs and reserve-only OFF protection; the first automatic Smart Thermal controller remains the 1.4 milestone.

## Confirmed inverter behavior

### Menu 01

- SUB → `POP01`;
- SBU → `POP02`;
- read back through QPIRI;
- independently verified before transition success.

### Menu 16

- SNU → `PCP01`;
- OSO → `PCP02`;
- ACK-confirmed and persisted;
- no supported read-back command exists on the current inverter.

## Current decision logic

### Hybrid

- Home Assistant publishes fresh decision inputs at 23:49;
- Home Assistant requests evaluation at 23:50;
- EnergyHub aligns today's projected 07:00–24:00 consumption with tomorrow's hourly solar over the same interval;
- after three complete samples per 07:00–12:00 interval, the morning term is a learned 75th-percentile essential-load net-energy deficit with heat-pump energy removed; until then the verified 1.3.1 ramp model remains authoritative;
- the target is the selected 20–50% minimum SOC plus the larger of morning-net-deficit or daytime-deficit SOC, capped at 95%;
- AHM can overtake active Panic; projected 07:00 SOC at or above target selects Solar, an overnight target crossing selects Hybrid Grid Hold, and current SOC below target selects Hybrid Charging;
- from 23:50 until confirmed morning Solar, fresh SOC at the dated target
  selects Hybrid Grid Hold and SOC below it selects or resumes Hybrid Charging;
- battery reaching the adaptive target selects Hybrid Grid Hold;
- Home Assistant requests Solar at 07:00 when Autopilot is enabled.

### Panic

- evaluation window: 07:00–23:50;
- reevaluation every five minutes and after grid transitions;
- normal/unstable/risk/panic Grid Confidence → 20/60/80/95% target;
- an AHM target genuinely missed at 07:00 is inherited until recovered;
- Panic remains armed while grid is offline and charges when grid returns;
- reaching target selects Panic Grid Hold rather than Solar;
- AHM takes ownership at 23:50;
- forecast and live PV are not Panic gates.

## Health and availability

Implemented:

- Communication Watchdog;
- Battery Health;
- Telemetry Freshness;
- Inverter Health;
- System Health aggregation;
- QPIWS polling every 60 seconds.

Availability topics remain separated:

- `energyhub/status` — EnergyHub process and diagnostic intelligence;
- `powmr/status` — valid inverter telemetry.
- `powmr/pv2/status` — fresh valid PV2 measurement;
- `powmr/total_pv/status` — fresh aligned PV1 + PV2 total.

Diagnostics remain visible during serial or telemetry failure.

EnergyHub 1.3.5 was deployed on 2026-08-14 with PV2 polling enabled at 30
seconds. `ha core check` passed. Repeated nighttime reads returned PV2 0.0 V and
1 W alongside PI30MAX PV1 0 W, producing Total PV 1 W. PI30MAX polling
continued, health became online, MQTT entities were discovered, and Solar
reconstructed without inverter writes. The PV1, PV2, and Total PV 24-hour
chart was later deployed and homeowner-verified under daylight production; all
three series rendered and Total PV tracked the combined components. The
repository does not retain a numeric daylight snapshot. The 2–3-day private
monitoring period is now in progress after the supervised 1.3.6 deployment.

After Home Assistant Core 2026.8.1 restarted on 2026-08-14, MQTT Discovery
loaded a historical retained `hybrid_decision_reason` from before the 1.3.4
summary change. Its 355-character state exceeded Home Assistant's 255-character
limit and temporarily appeared as `unknown`. The scheduled 23:50 AHM evaluation
published `Projected 07:00 SOC 54.0% meets target 20.0%; remain Solar`, proving
that current 1.3.5 decision output was concise and control behavior was healthy.
The deployed 1.3.6 build now republishes the concise initial Hybrid state at
app startup and enforces the state boundary at the publisher. Repository
regression validation and supervised add-on deployment/startup validation are
complete. The observed initial state was
`Adaptive Hybrid has not been evaluated yet`; a later planned Home Assistant
Core restart remains pending as an independent retained-state restoration
check.

Current System Health does not yet cover Home Assistant Repairs, cloud-integration authentication, Zigbee2MQTT app/bridge health, individual smart-load availability, or command-to-observed-device confirmation. These are now high-priority operational dependency gaps before unattended Smart Thermal control.

## Daily Summary

- retained inputs update current stored values;
- one atomic JSON snapshot at 23:51 creates or refreshes the completed record;
- duplicate snapshots are idempotent;
- midnight Grid Import finalization updates or confirms the completed day;
- stale retained snapshots from a previous date are ignored.

## Grid Import

- accounting is tied to confirmed SUB strategies;
- house output energy is integrated during the SUB interval;
- positive battery SOC gain is converted using nominal 16 kWh capacity;
- interval and daily state survive restarts;
- current-day, previous-day, and finalized Daily Summary values are separate;
- naming cleanup is complete;
- the result is informational and not billing-grade.

Known limitation: simultaneous daytime PV may affect estimated Grid Import accuracy.

## Restart reconstruction

Implemented and validated:

- load persisted controller state;
- read actual Menu 01;
- combine it with remembered Menu 16, confirmed-mode context, and Panic target;
- accept consistent Solar, Hybrid Grid Hold, Hybrid Charging, or Panic states without inverter writes;
- report an inconsistent state rather than guessing;
- queue one prioritized safe Solar recovery only when required and allowed.

## Persistent USB access

EnergyHub now uses a configurable FTDI `/dev/serial/by-id/...` path.

The app manifest enables:

```yaml
uart: true
udev: true
```

This avoids dependence on changing `/dev/ttyUSB0` and `/dev/ttyUSB1` assignments. Live validation passed with the inverter adapter and a SONOFF Zigbee coordinator connected through separate persistent device identities.

## Persistence

Current service state uses atomic JSON replacement.

- raw telemetry snapshots are throttled;
- Grid Import incremental saves are throttled;
- important transitions and day boundaries save immediately;
- controller state persists the confirmed mode, Menu 16 context, and Panic target.

## Home Assistant runtime

Current EnergyHub-specific integration includes:

- Autopilot helper publication;
- fresh solar forecast and daily input publication;
- 23:50 Hybrid schedule;
- 07:00 Solar restoration schedule;
- atomic Daily Summary snapshot;
- manual Panic script;
- EnergyHub notification delivery;
- EnergyHub beacon;
- selected household automation and dashboards.

Current helpers:

- `input_boolean.energyhub_autopilot`;
- `input_number.daily_solar_surplus_estimated`;
- first-, second-, and third-floor auto-off durations;
- first-, second-, and third-floor timers.

Away Mode helpers and automation are removed.

## Release tests

The Docker build runs:

```text
python3 -m unittest discover -s tests -v
```

Current suite: 24 tests.

Covered areas:

- Hybrid branches and required-energy calculation;
- Panic thresholds, target selection, active-strategy guards, and window boundaries;
- Grid Confidence boundaries and 24/48-hour inputs;
- no-valid-telemetry and 60-second freshness behavior;
- unchanged-load diagnostic behavior;
- Solar, Grid Hold, and Panic restart reconstruction;
- ambiguous-state rejection;
- verified Hybrid transition;
- partial Hybrid failure recovery to Solar;
- invalid Panic target rejection.

## Release validation completed on 2026-08-01

- Home Assistant app image rebuilt successfully for `linux/arm64`;
- all 24 tests passed during the Docker build;
- version banner displayed `1.0.2` from `BUILD_VERSION`;
- persistent FTDI `by-id` path opened successfully;
- MQTT Discovery and retained inputs loaded successfully;
- valid inverter telemetry resumed;
- Solar was reconstructed without inverter writes;
- Communication health moved from starting to online;
- automatic Panic evaluation returned normal no-action;
- full Home Assistant host restart passed with the Zigbee coordinator connected.

## EnergyHub 1.3 release validation completed on 2026-08-09

- all 44 release-logic tests passed in both the development and public-release worktrees;
- the deployed Home Assistant add-on mirror matched the committed 1.3.0 source;
- Supervisor reported Energy Hub 1.3.0 started and current;
- live runtime logs showed valid telemetry, coordinated Panic evaluation, and normal recovery from one transient invalid sample;
- the MQTT energy-metadata regression test passed and current Home Assistant logs contained no matching metadata warning;
- the Zigbee2MQTT bridge automations were aligned with the discovered bridge connection entity;
- `ha core check` completed successfully after the final YAML deployment;
- public promotion was prepared locally without pushing, tagging, or changing repository visibility.

## Known limitations and deferred work

- `aarch64` only;
- PowMr 10.2M / PI30MAX only;
- PV2 voltage and power are live-verified, repository-integrated, deployed, and
  validated through optional read-only Modbus registers 4563 and 4564 across
  high, curtailed, nighttime, and homeowner-observed daylight chart operation;
  cross-firmware compatibility remains unknown;
- no output-2 telemetry;
- no direct reliable Grid Import counter;
- Menu 16 cannot be read back;
- strategy parameters remain hard-coded or Home Assistant-configured;
- the 07:00 Solar transition depends on Home Assistant;
- no general trusted/raw telemetry quarantine layer;
- no direct JK BMS integration;
- no general bounded recovery service yet;
- no external heartbeat capable of detecting a fully frozen platform.

## Next product milestones

The immediate sequence is fixed:

```text
Monitor 1.3.8
→ publish 1.3.8
→ 1.3.9 SOC journal
→ 1.3.10 fault diagnostics
→ 1.4 Smart Thermal in Dry Run
→ Telegram text experiment
→ Telegram voice
```

- 1.3.8 — continuous dated night-target enforcement, trusted-grid family heat-pump ownership, reserve-relative protection, and outbound Telegram warnings are deployed, monitored, and publicly released;
- 1.3.9 — persist an SOC-only anomaly journal with electrical and restart context, without changing telemetry acceptance or control behavior;
- 1.3.10 — preserve verified inverter fault transitions and bounded pre-fault context before control is added;
- 1.3.11 — split estimated Grid Import into cheap and standard tariff energy and cost statistics without changing scheduling or inverter control;
- 1.4 family — evidence-based overload calibration, Dry Run, attended Peak Load Guard, capability-based Smart Thermal, and later solar-first EV charging;
- post-1.4 experiment — EnergyHub Telegram Intents: authenticated Ukrainian/English text first, then confirmed voice requests through the same bounded intent contract;
- 2.0 — Telegram-first conversational EnergyHub with authenticated Ukrainian/English text followed by confirmed Ukrainian/English voice intents through the safe EnergyHub control boundary;
- 2.x — one to three configurable cheap-price windows and later optional dynamic import pricing;
- 3.0 — additional validated inverter adapters, dynamic import/export planning, and optional Net Billing for compatible hardware and contracts.

The 1.1 work preserves the tested 1.0.2 inverter behavior. Zigbee2MQTT owns the SONOFF coordinator and paired-device transport; EnergyHub does not access the coordinator directly. Reserve guards may request OFF at documented thresholds, but no 1.1 automation starts a boiler or heat pump.

Cross-interface direction: Telegram, future Home Assistant Assist voice input, dashboards, and automations should translate user input into the same structured EnergyHub intents. They are request and presentation interfaces, not safety authorities. Telegram starts with authenticated Ukrainian/English chat and adds voice only after the text contract is reliable; voice-derived actions require an explicit echo and confirmation. EnergyHub retains Hybrid, Panic, Grid Confidence, recovery, reserve, and future flexible-load policy, and publishes human-readable domain events without requiring consumers to know internal MQTT topics or entity IDs.

## EnergyHub 1.1 release-candidate status — 2026-08-06

Issue 1, the 1.x development documentation baseline, is complete in the working tree.

Issue 2, Zigbee2MQTT with the SONOFF ZBDongle-E, completed on 2026-08-02:

- official stable Zigbee2MQTT Home Assistant app `2.13.0-1` is installed and running;
- ZHA does not own the discovered coordinator;
- the coordinator uses its persistent `/dev/serial/by-id/...` identity, `adapter: ember`, and `rtscts: false`;
- the existing PowMr FTDI device remains separate;
- Zigbee channel 25 was selected against the detected Wi-Fi channel 1 environment;
- Mosquitto, Home Assistant discovery, and the Zigbee2MQTT frontend are enabled;
- EmberZNet firmware `7.4.4 [GA]`, coordinator startup, MQTT connection, Zigbee2MQTT app-restart recovery, and full Home Assistant host-restart recovery passed;
- after the host restart, the existing Zigbee network resumed, the bridge remained online, and MQTT health reporting continued for at least 30 minutes;
- the coordinator is positioned on a 1 m USB extension away from the Raspberry Pi and inverter;
- a private encrypted Home Assistant backup was verified to contain the Zigbee2MQTT app and its data.

Issue 3, pairing and validating two Zigbee smart plugs, is in progress:

- `first_floor_heat_pump_plug` paired as `TS011F_plug_1_1` (`Zbeacon`) with direct power monitoring and observed LQI about 164–168;
- `second_floor_heat_pump_plug` paired as `TS011F_plug_3` (`Tuya`) with polled power monitoring and observed LQI about 152–172;
- both pairing interviews and manual Zigbee2MQTT/physical-button state-synchronization tests passed;
- both plugs use power-outage memory `off`; manual ON remains homeowner-owned while the 1.1 reserve guard may request OFF;
- at 21:30 on 2026-08-02, one Ember `ASH_ERROR_TIMEOUTS` transaction failure disconnected the adapter and stopped Zigbee2MQTT while the Home Assistant app Watchdog was disabled;
- at 17:29 on 2026-08-03, an attended manual Start recovered the same network, both devices and states, MQTT, availability, and Home Assistant discovery without re-pairing or an observed relay command;
- Watchdog was enabled after manual recovery;
- on 2026-08-05, ASH reset and restarted but EZSP startup failed with `HOST_FATAL_ERROR`; Zigbee2MQTT exited while Watchdog was enabled and no autonomous recovery was observed;
- on 2026-08-06 at 07:30, a third incident started from a healthy bridge and MQTT connection with `ASH_ERROR_TIMEOUTS`; Supervisor Watchdog made ten restart attempts, but all failed ASH/EZSP startup with `HOST_FATAL_ERROR` before the crash loop stopped;
- an attended manual Start at 11:51 resumed the existing network, MQTT, both devices, their ON relay states, availability, and fresh reports without re-pairing or an observed relay toggle;
- second-floor Offline-to-Online availability and safe OFF power recovery passed;
- a later Home Assistant restart retained both devices Online, while the first-floor plug remained ON and its heat pump continued running;
- first-floor compressor ramp-up reports were asynchronous; the stabilized 804 W, 3.37 A, 226 V example and second-floor live energy data are trend observations rather than calibrated protection data;
- retained or last-known electrical readings can remain stale across an availability interruption, so later automation must require fresh post-recovery telemetry and safe ownership reconstruction before resuming commands;
- Ember failure diagnosis and bounded recovery, optional reference-meter comparison, and both heat-pump nameplate/load-suitability checks remain.

The working tree now includes the first Zigbee transport-health increment: Home Assistant monitors Zigbee2MQTT's discovered bridge-connection entity, alerts only after two continuous offline minutes, and reports recovery with an explicit fresh-device-telemetry gate. It is alert-only and never restarts Zigbee2MQTT or issues a relay command. Supervised `ha core check`, restart, offline-delay, recovery, duplicate-notification, and no-relay-action validation remain required.

On 2026-08-08, the new USB extension cable did not prevent another `SEND_UNICAST` / `ASH_ERROR_TIMEOUTS` stop at 07:40. Manual recovery at 08:16 succeeded, but a second failure followed at 09:16:23, 3,607 seconds after restart. Its stack trace identifies the Ember driver's hourly `watchdogCounters()` / `ezspReadAndClearCounters()` path. A later 12:38:41 failure directly named `READ_AND_CLEAR_COUNTERS` as the timed-out frame, confirming the periodic counter transaction as the failure point while leaving the deeper firmware/NCP/USB/driver cause open. Zigbee2MQTT `2.13.0-1` is current in the installed app channel. Backups were completed and downloaded. The official SONOFF flasher successfully updated the ZBDongle-E from coordinator firmware 7.4.4 to official stable 8.0.2 at 115200 baud. At 16:34, Zigbee2MQTT resumed the existing network with EmberZNet `8.0.2 [GA]` build 397, both paired plugs, MQTT, discovery, and matching known relay states without re-pairing or an observed relay command. At 19:33, however, the same timeout stopped Zigbee2MQTT again, so firmware 8.0.2 alone did not resolve the fault. On 2026-08-09, the controlled polling-isolation test set the second-floor TS011F plug's `measurement_poll_interval` to `-1` and restarted Zigbee2MQTT at 10:06. The one-minute reports stopped, but at 11:28 an active availability ping to that plug ended in `SEND_UNICAST` / `ASH_ERROR_TIMEOUTS` and stopped the bridge. A further availability-ping failure occurred at 15:36 on 2026-08-10. At 21:58, the stronger isolation test disabled the entire second-floor device in Zigbee2MQTT while keeping its physical relay OFF and measurement polling disabled. That test still failed at 06:58 on 2026-08-11 after about nine hours. The exception directly came from `watchdogCounters()` / `ezspReadAndClearCounters()`, again with clean reported ASH error counters. Second-floor measurement polling, availability pings, and other Zigbee2MQTT-managed traffic are therefore not required triggers. An attended Start at 08:47 recovered firmware 8.0.2, the existing network, and MQTT without re-pairing or an observed relay command. The unresolved scope is now the Ember driver/NCP, coordinator hardware, or host USB/power path; Supervisor Watchdog stays disabled pending a bounded recovery decision.

The attended Supervisor Watchdog test began later on 2026-08-11 after restoring the second-floor device. Five adapter crashes occurred between 13:10 and 14:11. Supervisor launched eight starts: five succeeded, while three consecutive attempts during the 13:21 recovery failed with `HOST_FATAL_ERROR` before the fourth connected. The final automatic recovery completed at 14:12 and remained healthy through at least 22:15, passing eight subsequent hourly NCP/ASH counter reads. Both devices returned Online and retained their published OFF states. Watchdog is therefore retained as useful availability mitigation, but the rapid crash cluster and transient fatal-start loop confirm that it is not the root-cause fix. The next engineering action is an upstream report and, if no software remedy is available, a coordinator or powered-USB hardware A/B test.

Unattended Watchdog recovery failed on 2026-08-12. A 06:58 adapter timeout was followed by five `HOST_FATAL_ERROR` starts before the sixth recovered at 07:01. The adapter failed again at 07:15, after which four more fatal starts exhausted the Supervisor retry sequence and left Zigbee2MQTT stopped. Watchdog is therefore not accepted as reliable self-healing; it remains only opportunistic mitigation. Hardware A/B testing and the upstream defect report are now required rather than waiting passively for an app update.

The first hardware A/B test began at 11:10 on 2026-08-12 with the extension cable removed and the coordinator connected directly to the host USB port. Startup passed on the first ASH attempt with the existing network, MQTT, both devices Online, and both known OFF states retained. No other Zigbee setting changed. Stability must now be checked at four, 24, and 48 hours; another timeout will rule out both tested extension cables as the necessary cause.

Direct USB remained stable through at least 07:16 on 2026-08-13, just over 20 hours, with MQTT connected, both devices producing traffic, and successful hourly counter reads. No adapter error or restart appeared in the supplied interval. The four-hour checkpoint passed; the 24-hour checkpoint remains 11:10 on 2026-08-13.

By 10:50 on 2026-08-16, the direct-USB run had reached about 95 hours 40 minutes without an adapter crash or restart, while MQTT and hourly NCP/ASH counter reads remained healthy. The 24-hour and 48-hour checkpoints therefore passed, making the USB extension path the leading local cause rather than the plugs, polling, availability checks, firmware 7.4.4 alone, or normal Ember counter reads. A separate transient second-floor endpoint event produced failed availability pings at 08:35 and 09:02; the coordinator remained healthy. The plug recovered Online at 09:07:52 and then published fresh LQI 156 / OFF state twice, matching the known physical state.

The dedicated Heat Pumps view presents matching compact first-, second-, and third-floor operating sections: switch state, live power, 0–12 h auto-off duration, and an absolute local turn-off time, with shared consumption history below. Floor 1 and floor 2 use the paired Zigbee plug entities; floor 3 retains the existing Xiaomi plug. Each floor has the same Home Assistant auto-off behavior, with duration `0` meaning manual mode. The duplicate floor sections and empty `New section` headings were removed from Mission Control, which remains focused on whole-house energy, status, decisions, and operating controls. These controls do not enable Smart Thermal automatic starts.

The focused dashboards were deployed and visually verified. The final
reserve-relative heat-pump guard passed repository review, guarded deployment,
and `ha core check`; low-SOC protection paths remain intentionally unforced and
are not claimed as live transitions.

The 2026-08-07 dashboard deployment and Core startup exposed non-fatal MQTT discovery warnings for EnergyHub energy entities published with `device_class: energy` and the invalid `state_class: measurement` combination. Confirmed examples include Hybrid Evaluated Consumption, Daily Solar Forecast, Daily Summary Grid Import, and Daily House Consumption. Current values and dashboards remain operational, but long-term statistics may be incomplete or unsuitable. Before the next release tag, audit every EnergyHub MQTT energy entity, assign `total`, `total_increasing`, or no state class according to its actual reset and accumulation behavior, add metadata tests, rebuild/restart the add-on to replace retained discovery, and confirm a clean supervised startup plus usable dependent statistics and charts.

The Energy Balance history stopped advancing after the last valid `20.2 kWh` consumption / `24.3 kWh` surplus snapshot. The saved 2026-08-08 Home Assistant traces proved that fresh consumption (`12.39 kWh`) and forecast (`14.56 kWh`) were published, and the 23:50 surplus calculation produced `2.2 kWh`, but the automation still targeted the orphaned legacy registry entity `input_number.energyhub_daily_solar_surplus_estimated`, which remained `unavailable`. The current helper is `input_number.daily_solar_surplus_estimated`. The 23:51 atomic payload therefore contained an invalid surplus and was correctly rejected by EnergyHub. The working-tree correction targets the current helper, calculates consumption, forecast, and surplus once inside the publishing automation, and uses those values directly for both retained inputs and the atomic snapshot. A future orphaned helper can no longer block Daily Summary history.

On 2026-08-06, Home Assistant Repairs reported expired Tuya authentication for the Wi-Fi integration used by the EnergyHub beacon. Re-confirming the login restored lamp control. A trace had shown correct fresh SOC/color calculation, so the stale blue lamp was probably an external integration-authentication failure, not Zigbee2MQTT or EnergyHub color logic. External integration health and end-to-end command confirmation are not yet part of EnergyHub System Health.

Adaptive Hybrid and conservative Panic were released together in 1.3.0. Version 1.3.1 added the configurable minimum reserve and explainable 300 W → 600 W ramp credit. Version 1.3.2 added learned 07:00–12:00 essential net energy and one-step reserve advice while retaining the 1.3.1 fallback. Version 1.3.3 gates night-grid use with the conservative projected 07:00 SOC. Broader full-day load profiling, charge-deadline estimation, and sustained real-PV confirmation remain future refinements.

A later settings increment will expose the remaining hard-coded tariff, Hybrid, battery, Panic, and feature-enable parameters through a validated Home Assistant view. EnergyHub remains the owner of effective persisted configuration and must validate, acknowledge, reconcile, and audit changes. Migration defaults must preserve current behavior exactly; disabling automatic Panic checks will not disable manual Panic or health monitoring.

The working-tree dashboard now has separate Heat Pumps and Water Systems views. Heat Pumps presents three compact switch/live-power/auto-off sections. Water Systems presents compact switch/live-power sections for `2nd floor water Boiler Smart Power` (`chuangmi_212a01_c91f`) and `Basement Water Smart Power` (`chuangmi_212a01_ac48`). Both views show daily consumption for 7 days, weekly consumption for 6 weeks, and monthly consumption for 12 months. Floor 1/2 use native cumulative energy. Third-floor, boiler, and pump use new local Integral sensors derived from live watts after Xiaomi cloud counters produced impossible 100–250 kWh daily values. The local sensors persist but start at deployment; older Xiaomi-app history is not imported. Supervised deployment must validate reasonable accumulation and chart rendering.

The working tree now includes the first constrained reserve automation for the water boiler. Fresh SOC reaching 50% requests OFF once; an ON request remains allowed from 41% through 50%; fresh SOC reaching 40% latches an OFF lockout; and fresh SOC reaching 60% clears the lockout without automatically restoring the boiler. The existing Xiaomi motion automation can therefore act as an allowed 41–50% override, but it is rejected while the lockout is latched. Commands are suppressed when EnergyHub telemetry is stale, notifications expose requested and observed state, and the behavior remains best effort if Home Assistant, Xiaomi authentication, the network, or the device is unavailable.

EnergyHub 1.3.8 uses one reserve-relative heat-pump policy. Trusted operation
requires Grid Confidence `normal`, present grid voltage, and fresh telemetry;
the family then retains manual control. Otherwise the selected AHM minimum is
the reference: minimum +30 requests all running participating heat pumps OFF
once while another manual start remains possible, minimum +20 latches the
mandatory OFF lockout, and minimum +40 clears it without starting a pump.
Stale telemetry issues no plug command. There are no automatic Smart Thermal
starts in this version.

The floor-1/floor-2 entities were unavailable during inventory because Zigbee2MQTT was unavailable; the dashboard intentionally exposes that state. The pump remains a critical manual/observational load until motor surge, plug rating, outage behavior, and water-system consequences are validated. Future early-solar permission requires dependable net surplus after house load and battery recovery, not a raw PV threshold such as 1 kW, and should begin in observer mode. Smart Thermal ownership and automatic starts remain later work.

See [Zigbee2MQTT with SONOFF ZBDongle-E](../hardware/zigbee2mqtt-zbdongle-e.md).

See [EnergyHub 1.x Development Plan](../roadmap/14-EnergyHub-1.x-Development.md).
