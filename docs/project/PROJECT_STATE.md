# EnergyHub Project State

Last updated: 2026-08-06.

## Current milestone

**EnergyHub 1.3.0 — Coordinated Adaptive Hybrid and Panic, under supervised validation.**

## 1.3 coordinated decision state

- AHM owns 23:50–07:00 and calculates a 30–95% target from the morning bridge plus aligned post-07:00 consumption/solar deficit.
- Panic owns 07:00–23:50 and uses simple Grid Confidence targets: normal 20%, unstable 60%, risk 80%, panic 95%.
- Only an AHM target actually missed at the 07:00 handover becomes persisted daytime charging debt.
- Panic can remain armed while grid is offline, charge when it returns, and preserve reserve in the distinct `panic_grid_hold` mode.
- AHM always takes ownership from Panic at 23:50.
- Grid-backed Hybrid and Panic temporarily permit manual heat-pump use; grid loss restores the remembered reserve locks. EnergyHub never starts a heat pump automatically.

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
- pinned `paho-mqtt==1.6.1` and `mppsolar==0.16.56`.

## Implemented operating strategies

| Strategy | State | Target/exit |
|---|---|---|
| Solar | SBU + OSO | default |
| Hybrid Charging | SUB + SNU | adaptive SOC 30–95% |
| Hybrid Grid Hold | SUB + OSO | 07:00 handover |
| Panic Charging | SUB + SNU | effective SOC 20/60/80/95% |
| Panic Grid Hold | SUB + OSO | AHM takeover at 23:50 |

Away Mode is not part of EnergyHub 1.3. EnergyHub supplies monitored smart plugs and reserve-only OFF protection; the first automatic Smart Thermal controller remains the 1.5 milestone.

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
- the target is 20% reserve + 10% margin + the larger of morning-gap or daytime-deficit SOC, capped at 95%;
- AHM selects Solar, Hybrid Charging, or Hybrid Grid Hold and can overtake active Panic;
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

Diagnostics remain visible during serial or telemetry failure.

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
- `input_number.energyhub_daily_solar_surplus_estimated`;
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

## Known limitations and deferred work

- `aarch64` only;
- PowMr 10.2M / PI30MAX only;
- no PV2 telemetry;
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

- 1.1 — Smart Plug Reserve Guard: Zigbee2MQTT, validated smart plugs, focused dashboards, auto-off timers, and reserve-only OFF protection;
- 1.2 — Configurable EnergyHub;
- 1.3 — Recovery & Resilience;
- 1.4 — Remote Access & Telegram;
- 1.5 — first automatic Smart Thermal Energy controller.

The 1.1 work preserves the tested 1.0.2 inverter behavior. Zigbee2MQTT owns the SONOFF coordinator and paired-device transport; EnergyHub does not access the coordinator directly. Reserve guards may request OFF at documented thresholds, but no 1.1 automation starts a boiler or heat pump.

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

The working tree now includes the first Zigbee transport-health increment: Home Assistant derives a dedicated connectivity entity from the retained Zigbee2MQTT bridge-state topic, alerts only after two continuous offline minutes, and reports recovery with an explicit fresh-device-telemetry gate. It is alert-only and never restarts Zigbee2MQTT or issues a relay command. Supervised `ha core check`, restart, offline-delay, recovery, duplicate-notification, and no-relay-action validation remain required.

The dedicated Heat Pumps view presents matching compact first-, second-, and third-floor operating sections: switch state, live power, 0–12 h auto-off duration, and an absolute local turn-off time, with shared consumption history below. Floor 1 and floor 2 use the paired Zigbee plug entities; floor 3 retains the existing Xiaomi plug. Each floor has the same Home Assistant auto-off behavior, with duration `0` meaning manual mode. The duplicate floor sections and empty `New section` headings were removed from Mission Control, which remains focused on whole-house energy, status, decisions, and operating controls. These controls do not enable Smart Thermal automatic starts.

The focused dashboards were deployed and visually verified. The final grid-confidence-aware reserve guard still requires `ha core check`, Core restart, and supervised Home Assistant verification after deployment.

The 2026-08-07 dashboard deployment and Core startup exposed non-fatal MQTT discovery warnings for EnergyHub energy entities published with `device_class: energy` and the invalid `state_class: measurement` combination. Confirmed examples include Hybrid Evaluated Consumption, Daily Solar Forecast, Daily Summary Grid Import, and Daily House Consumption. Current values and dashboards remain operational, but long-term statistics may be incomplete or unsuitable. Before the next release tag, audit every EnergyHub MQTT energy entity, assign `total`, `total_increasing`, or no state class according to its actual reset and accumulation behavior, add metadata tests, rebuild/restart the add-on to replace retained discovery, and confirm a clean supervised startup plus usable dependent statistics and charts.

On 2026-08-06, Home Assistant Repairs reported expired Tuya authentication for the Wi-Fi integration used by the EnergyHub beacon. Re-confirming the login restored lamp control. A trace had shown correct fresh SOC/color calculation, so the stale blue lamp was probably an external integration-authentication failure, not Zigbee2MQTT or EnergyHub color logic. External integration health and end-to-end command confirmation are not yet part of EnergyHub System Health.

Adaptive Hybrid and conservative Panic are implemented together in the 1.3.0 working tree. Future refinements include measured time-of-day load profiles, charge-deadline estimation, and sustained real-PV confirmation before leaving the morning resilience horizon.

EnergyHub 1.2 will add a validated Home Assistant Settings view for the currently hard-coded tariff, Hybrid, battery, Panic, and feature-enable parameters. EnergyHub remains the owner of effective persisted configuration and must validate, acknowledge, reconcile, and audit changes. The dashboard will also show calculated targets, charge duration, start-by time, and decision reasons. Migration defaults must preserve 1.0.2 exactly; disabling automatic Panic checks will not disable manual Panic or health monitoring.

The working-tree dashboard now has separate Heat Pumps and Water Systems views. Heat Pumps presents three compact switch/live-power/auto-off sections. Water Systems presents compact switch/live-power sections for `2nd floor water Boiler Smart Power` (`chuangmi_212a01_c91f`) and `Basement Water Smart Power` (`chuangmi_212a01_ac48`). Both views show daily consumption for 7 days, weekly consumption for 6 weeks, and monthly consumption for 12 months. Floor 1/2 use native cumulative energy. Third-floor, boiler, and pump use new local Integral sensors derived from live watts after Xiaomi cloud counters produced impossible 100–250 kWh daily values. The local sensors persist but start at deployment; older Xiaomi-app history is not imported. Supervised deployment must validate reasonable accumulation and chart rendering.

The working tree now includes the first constrained reserve automation for the water boiler. Fresh SOC reaching 50% requests OFF once; an ON request remains allowed from 41% through 50%; fresh SOC reaching 40% latches an OFF lockout; and fresh SOC reaching 60% clears the lockout without automatically restoring the boiler. The existing Xiaomi motion automation can therefore act as an allowed 41–50% override, but it is rejected while the lockout is latched. Commands are suppressed when EnergyHub telemetry is stale, notifications expose requested and observed state, and the behavior remains best effort if Home Assistant, Xiaomi authentication, the network, or the device is unavailable.

The working tree also contains grid-confidence-aware reserve-only heat-pump protection with the agreed household priority. Fully trusted means Grid Confidence `normal`, exactly 100% 24-hour availability, 48 available hours over 48 hours, present grid voltage, and fresh telemetry. That state uses only the 50% all-floor lockout and clears it at fresh 60% SOC. Every degraded or unknown state uses the conservative policy: fresh SOC reaching 80% requests every running heat pump OFF once, floor 2 is shed again at 70%, floor 1 at 60%, and floor 3 remains protected until the 50% all-floor lockout. The conservative lockout clears at fresh 90% SOC. Neither policy starts a heat pump. Intermediate actions are not reconstructed blindly after restart or availability recovery; the 50% lockout is re-evaluated after trustworthy telemetry returns. Grid degradation applies the conservative all-floor shed when SOC is already at or below 80%. There are no automatic Smart Thermal starts in this version.

The floor-1/floor-2 entities were unavailable during inventory because Zigbee2MQTT was unavailable; the dashboard intentionally exposes that state. The pump remains a critical manual/observational load until motor surge, plug rating, outage behavior, and water-system consequences are validated. Future early-solar permission requires dependable net surplus after house load and battery recovery, not a raw PV threshold such as 1 kW, and should begin in observer mode. Smart Thermal ownership and automatic starts remain later work.

See [Zigbee2MQTT with SONOFF ZBDongle-E](../hardware/zigbee2mqtt-zbdongle-e.md).

See [EnergyHub 1.x Development Plan](../roadmap/14-EnergyHub-1.x-Development.md).
