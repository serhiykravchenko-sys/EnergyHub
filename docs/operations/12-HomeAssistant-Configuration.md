# Home Assistant Configuration

> This document describes the Home Assistant configuration, objects, dashboards, and integration boundaries used by EnergyHub.

---

# Purpose

Home Assistant is the integration, presentation, and user-interaction platform for EnergyHub.

EnergyHub owns energy intelligence, persistent operational state, health evaluation, strategy decisions, inverter control, and historical EnergyHub data.

The architectural boundary is:

```text
Home Assistant
→ Integrations
→ Presentation
→ User Interaction
→ Household Automation
→ Notification Delivery

EnergyHub
→ Energy Intelligence
→ Historical Knowledge
→ Health Evaluation
→ Strategy Decisions
→ Inverter Control
→ Persistent Operational State
```

---

# Current Home Assistant Responsibilities

Home Assistant currently owns:

- hardware and service integrations;
- Solcast integration;
- dashboards;
- user-facing controls;
- helpers;
- timers;
- selected household automations;
- publishing selected Home Assistant data to EnergyHub;
- notification delivery;
- Home Assistant configuration storage.

EnergyHub currently owns:

- inverter telemetry processing;
- Grid Availability history;
- Grid Confidence;
- Daily Summary history;
- Battery Health;
- Telemetry Freshness;
- Inverter Health;
- System Health;
- Hybrid decisions;
- Panic decisions;
- inverter strategy execution;
- Operating Mode;
- Grid Import estimation;
- significant decision events.

---

# Current EnergyHub Helpers

Current EnergyHub-specific Home Assistant helpers include:

```text
input_boolean.energyhub_autopilot
input_boolean.energyhub_water_boiler_soc_lockout
input_boolean.energyhub_heat_pump_soc_lockout
input_number.energyhub_daily_solar_surplus_estimated
input_number.input_number_floor1_heat_pump_timer_hours
input_number.input_number_floor2_heat_pump_timer_hours
input_number.input_number_floor3_heat_pump_timer_hours
timer.floor_1_heat_pump_auto_off
timer.floor_2_heat_pump_auto_off
timer.floor_3_heat_pump_auto_off
```

---

# Autopilot Helper

Entity:

```text
input_boolean.energyhub_autopilot
```

Purpose:

Provides the user-facing control for automatic EnergyHub strategy execution.

The helper state is published to EnergyHub through retained MQTT.

EnergyHub publishes the resulting status as:

```text
sensor.energyhub_autopilot_status
```

Autopilot is separate from:

- Operating Mode;
- manual strategy requests.

Disabling Autopilot does not disable monitoring, telemetry, history, or health evaluation.

---

# Smart Load Boundary

The original EnergyHub 1.0 Away Mode helpers and automation were removed from the active 1.0 architecture.

EnergyHub 1.1 adds manual smart-plug controls, per-floor auto-off timers, and reserve-only OFF guards as Home Assistant household automation. It never turns the boiler or a heat pump on. Automatic Smart Thermal ownership and starts remain deferred to 1.5.

The ownership principle remains valid:

> EnergyHub should automatically stop a household load only when EnergyHub previously started it.

---

# Daily Solar Surplus Estimated Helper

Entity:

```text
input_number.energyhub_daily_solar_surplus_estimated
```

Purpose:

Stores the estimated daily solar energy that was probably not used.

Current formula:

```text
max(0, Solcast Forecast Today - Daily House Consumption)
```

Source entities:

```text
sensor.solcast_pv_forecast_forecast_today
sensor.powmr_10_2m_daily_house_consumption
```

The calculation intentionally uses Solcast forecast rather than inverter PV generation.

The PowMr inverter exposes PV1 telemetry only and does not provide reliable total PV1 + PV2 production.

The previous concept:

```text
Daily Energy Balance
```

was renamed to:

```text
Daily Solar Surplus Estimated
```

---

# Floor Heat Pump Helpers

Auto-Off duration helpers:

```text
input_number.input_number_floor1_heat_pump_timer_hours
input_number.input_number_floor2_heat_pump_timer_hours
input_number.input_number_floor3_heat_pump_timer_hours
```

Values:

```text
0 = Manual
1..9 = Auto-Off after N hours
```

Countdown timers:

```text
timer.floor_1_heat_pump_auto_off
timer.floor_2_heat_pump_auto_off
timer.floor_3_heat_pump_auto_off
```

Purpose:

Each helper controls only its matching floor timer. A non-zero duration starts or restarts the countdown while that floor's plug is on. Duration `0` cancels the countdown without switching the plug, so it is manual mode. Switching the plug off cancels its timer and resets the duration to `0`; timer expiry switches the matching plug off and also resets the duration.

---

# Current EnergyHub Automations

The authoritative current automation configuration is stored in:

```text
homeassistant/live/config/automations.yaml
```

Current EnergyHub integration responsibilities include:

- publishing Autopilot state;
- publishing Daily Summary and decision inputs;
- requesting Hybrid evaluation at 23:50;
- restoring Solar at 07:00 when Autopilot is enabled;
- restoring / requesting mode handling after restart;
- delivering EnergyHub notification events;
- selected household automations such as the floor 1, 2, and 3 heat-pump auto-off controls.

This document describes architecture and responsibilities.

It should not duplicate the complete automation YAML.

---

# Daily Summary and Hybrid Schedule

The final nightly sequence is:

```text
23:49
→ Home Assistant publishes fresh decision inputs, including the first
  tomorrow hourly Solcast estimate at or above 300 W

23:50
→ Home Assistant requests Hybrid evaluation

23:51
→ Daily Summary refreshes the final daily snapshot
```

This ordering ensures that the Hybrid Decision Engine evaluates current Home Assistant inputs before the final daily history snapshot is completed.

---

# Publish Daily Summary Inputs

Home Assistant publishes selected energy data to EnergyHub through retained MQTT messages.

Current Daily Summary inputs include:

```text
energyhub/input/ha/daily_house_consumption
energyhub/input/ha/solar_forecast_today
energyhub/input/ha/solar_forecast_tomorrow
energyhub/input/ha/daily_solar_surplus_estimated
```

EnergyHub subscribes to:

```text
energyhub/input/ha/#
```

Messages are retained.

This allows EnergyHub to receive the latest Home Assistant inputs after restart.

Architecture:

```text
Home Assistant Sensors
        ↓
Home Assistant Snapshot / Publication
        ↓
Retained MQTT Inputs
        ↓
EnergyHub
        ↓
DailySummaryService
```

---

# Daily Summary Integration

Home Assistant provides selected energy values that are not reliably available from the PowMr inverter.

EnergyHub then owns:

- the Daily Summary data model;
- persistent daily snapshots;
- historical Daily Summary state;
- EnergyHub Daily Summary MQTT sensors;
- the data interface used by dashboards;
- decision-service inputs.

Architecture:

```text
Home Assistant Sensors
        ↓
energyhub/input/ha/*
        ↓
DailySummaryService
        ↓
Persistent Daily History
        +
EnergyHub MQTT Sensors
        ↓
Home Assistant Dashboards
        +
Decision Services
```

---

# EnergyHub Daily Summary Entities

Current EnergyHub Daily Summary entities include:

```text
sensor.energyhub_daily_house_consumption
sensor.energyhub_daily_solar_forecast
sensor.energyhub_daily_solar_surplus_estimated
sensor.energyhub_daily_grid_availability
sensor.energyhub_daily_summary_grid_import
```

Dashboards should prefer EnergyHub Daily Summary entities when displaying completed historical daily statistics.

Live current-day information may continue to use the appropriate source entities.

---

# Operating Mode Integration

Current EnergyHub Operating Mode entities:

```text
sensor.energyhub_operating_mode
sensor.energyhub_operating_mode_reason
sensor.energyhub_output_source_priority
sensor.energyhub_charger_source_priority
```

Current mode values include:

```text
solar
hybrid_charging
hybrid_grid_hold
panic
transitioning
transition_failed
unknown
```

Home Assistant displays Operating Mode and its reason.

EnergyHub owns:

- strategy execution;
- inverter command sequencing;
- verification;
- confirmed Operating Mode.

Home Assistant must not infer a confirmed Operating Mode solely from a button press or requested transition.

---

# Manual Panic Control

Current manual control:

```text
script.energyhub_start_panic
```

The Developer Dashboard exposes this script as a button for testing and manual activation.

Automatic Panic evaluation remains owned by EnergyHub.

Current diagnostic entities:

```text
sensor.energyhub_panic_decision
sensor.energyhub_panic_decision_reason
```

Manual requests still use the normal EnergyHub control architecture.

They do not bypass the Inverter Controller.

---

# Hybrid Integration

Home Assistant currently provides schedule and integration support for the Hybrid strategy.

EnergyHub owns:

- Hybrid decision logic;
- target calculation;
- Operating Mode transitions;
- inverter execution.

Current Hybrid phases:

```text
Hybrid Charging
        ↓
Hybrid Grid Hold
        ↓
Solar
```

Adaptive Night Hybrid evaluates once at 23:50. EnergyHub calculates:

    projected_soc_at_07 = current_soc - 15
    morning_gap_soc = hours_from_07_to_first_300W_forecast × 10
    target_soc = min(95, 20 + morning_gap_soc + 10)

The three outcomes are:

- projected SOC meets target: remain Solar;
- current SOC meets target but projected SOC does not: enter Grid Hold;
- current SOC is below target: enter Hybrid Charging, then Grid Hold at target.

The 07:00 schedule restores Solar. Grid Confidence does not change this
cheap-tariff plan; Panic remains the separate grid-risk strategy. If hourly
Solcast data is unavailable, EnergyHub uses a conservative five-hour morning
gap, producing the previous 80% target as a visible fallback.

Home Assistant should not duplicate Hybrid decision formulas.

The authoritative Hybrid decision architecture is documented in:

```text
DECISION_ENGINE.md
```

---

# Hybrid Decision Entities

EnergyHub publishes retained explainable Hybrid evaluation data.

Current entities include:

```text
sensor.energyhub_hybrid_decision
sensor.energyhub_hybrid_decision_reason
sensor.energyhub_hybrid_evaluated_at
sensor.energyhub_hybrid_calculation
sensor.energyhub_hybrid_evaluated_soc
sensor.energyhub_hybrid_evaluated_consumption
sensor.energyhub_hybrid_battery_refill_required
sensor.energyhub_hybrid_total_energy_required
sensor.energyhub_hybrid_evaluated_forecast
sensor.energyhub_hybrid_projected_soc_at_07
sensor.energyhub_hybrid_morning_hours
sensor.energyhub_hybrid_useful_solar_start
sensor.energyhub_hybrid_morning_reserve_soc
sensor.energyhub_hybrid_target_soc
sensor.energyhub_hybrid_target_capped
sensor.energyhub_hybrid_forecast_fallback
```

These entities allow Home Assistant to show both the final decision and the exact values used during the most recent Hybrid evaluation.

Home Assistant displays these values but does not duplicate the Hybrid decision formula.

The complete 23:50 evaluation is retained in MQTT until the next nightly
evaluation replaces it. EnergyHub startup publishes discovery but does not
replace that retained snapshot with `not_evaluated`, so restarting Home
Assistant or the add-on does not erase the explanation shown on the dashboard.

---

# Smart Heating / Away Integration

Away Mode is not part of the final EnergyHub 1.0 architecture.

The original implementation was deferred after design review showed that occupancy, comfort, solar surplus, cheap-tariff use, and battery reserve should be handled through a broader Smart Heating / flexible-load architecture.

EnergyHub 1.1 provides the monitored-device, dashboard, timer, and reserve-guard foundation. Automatic Smart Thermal control remains deferred to 1.5.

---

# Floor Heat Pump Auto-Off

Each floor's Auto-Off automation currently:

- starts the countdown timer;
- restarts the timer when duration changes;
- cancels the timer without toggling the plug when duration is set to `0` manual mode;
- cancels the timer when the heat pump is switched off;
- switches the heat pump off when the timer finishes;
- resets the Auto-Off helper to 0.

This is a household automation and remains an appropriate Home Assistant responsibility.

---

# Grid Import Integration

The PowMr inverter does not expose a reliable accumulated Grid Import counter.

EnergyHub therefore estimates Grid Import while SUB-based strategies are active.

Current entities include:

```text
sensor.energyhub_grid_import_power_estimated
sensor.energyhub_daily_grid_import_estimated
sensor.energyhub_grid_import_yesterday_estimated
sensor.energyhub_daily_summary_grid_import
```

Daily Summary history uses the stable finalized entity shown above.

## Accounting Window

Accounting starts when EnergyHub enters a SUB-based strategy:

- Hybrid Charging;
- Hybrid Grid Hold;
- Panic Charging;
- Panic Grid Hold.

Accounting stops after EnergyHub returns to Solar/SBU.

## Current Calculation

```text
Grid Import
=
House Energy Supplied During SUB
+
Positive Battery SOC Gain × Nominal Battery Capacity
```

Current nominal battery capacity:

```text
16 kWh
```

Battery contribution uses positive SOC gain relative to the start of the SUB interval.

Temporary SOC drops do not inflate the estimate.

EnergyHub persists current-day Grid Import state and publishes yesterday and Daily Summary values for Home Assistant history.

Current persistence schema:

```text
schema_version = 2
```

The schema migration discarded incompatible current-day values produced by the previous estimator.

Daily Grid Import Estimated remains:

- informational;
- useful for historical comparison;
- useful for dashboard analysis;
- not billing-grade.

---

# Notification Integration

EnergyHub owns significant automatic decision events.

Home Assistant owns notification delivery.

Current event topic:

```text
energyhub/event/notification
```

Architecture:

```text
EnergyHub Decision / Event
        ↓
MQTT Notification Event
        ↓
Home Assistant Automation
        ↓
Persistent Notification
        +
Mobile Notification
        +
Future Telegram Notification
```

This keeps decision context in EnergyHub while leaving delivery channels in Home Assistant.

Routine telemetry and expected no-action evaluations should normally remain in logs.

## External integration health and the beacon

The EnergyHub beacon is `light.colorful_pir_night_light`, a Tuya Wi-Fi device. It is not a Zigbee2MQTT device. Its color logic can calculate and execute successfully in Home Assistant while a Tuya authentication or availability failure prevents the physical lamp from receiving the command.

On 2026-08-06, Home Assistant Repairs reported that Tuya authentication had expired. Re-confirming the Tuya login through the app restored lamp control. A trace at 66% SOC had already shown fresh EnergyHub telemetry and the correct yellow `[255, 220, 0]` result, and both a direct light action and a later manual beacon run produced yellow after authentication was restored. This strongly identifies Tuya authentication as the cause of the stale blue lamp state; it was not a Zigbee2MQTT failure or an SOC threshold error.

Current EnergyHub System Health covers the EnergyHub process and inverter-facing communication, battery, telemetry freshness, and inverter warning inputs. It does not yet aggregate Home Assistant Repairs, Tuya authentication, Zigbee2MQTT app/bridge availability, or command-to-observed-device confirmation. Those dependencies must be represented separately so a retained or stale entity value cannot be mistaken for healthy end-to-end telemetry. Reauthentication remains an attended action; EnergyHub must alert but must not attempt to automate cloud-account login.

The working-tree Zigbee reliability increment adds `binary_sensor.zigbee2mqtt_bridge_connectivity` from the retained `zigbee2mqtt/bridge/state` MQTT topic. If it remains offline for two minutes, Home Assistant creates one persistent notification stating that readings may be stale and that no restart or relay action was attempted. An online transition dismisses that alert and creates a recovery notice that requires individual-device availability and fresh post-recovery reports to be checked. This is bridge transport monitoring only: it does not prove that the Zigbee2MQTT app is healthy, that a device is reachable, or that any retained measurement is fresh.

---

# Dashboard Architecture

Current EnergyHub dashboards separate operational state, decision intelligence, and historical energy results.

The current dashboard set is functional and forms the EnergyHub 1.0 reference UI. Further visual refinement may continue in later releases.

## EnergyHub Status

Purpose:

```text
What is happening now?
```

Current information includes:

- Autopilot;
- Operating Mode;
- Operating Mode reason;
- Output Source Priority;
- Charger Source Priority;
- Communication;
- Battery SOC;
- House Load;
- PV1 Power;
- Grid Voltage;
- Grid Import information;
- manual developer controls.

Operating Mode is displayed prominently with strategy-specific icons.

## Heat Pumps View

The dedicated Heat Pumps view uses the same compact four-card operating layout for each floor:

1. heat-pump switch state and manual toggle;
2. live plug power in watts;
3. auto-off duration from `0` to `9` hours;
4. absolute local turn-off time, or `Manual` when no timer is active.

Floor 1 uses `switch.first_floor_heat_pump_plug` and `sensor.first_floor_heat_pump_plug_power`. Floor 2 uses `switch.second_floor_heat_pump_plug` and `sensor.second_floor_heat_pump_plug_power`. Floor 3 retains `switch.chuangmi_212a01_ea40_switch` and `sensor.chuangmi_212a01_ea40_electric_power`. Template sensors `sensor.floor_1_heat_pump_turns_off_at`, `sensor.floor_2_heat_pump_turns_off_at`, and `sensor.floor_3_heat_pump_turns_off_at` render `Today HH:MM`, `Tomorrow HH:MM`, another local date/time, or `Manual` from each timer's `finishes_at` attribute. Daily, weekly, and monthly consumption graphs remain below the compact controls.

These cards expose Home Assistant household controls only. They do not indicate that EnergyHub owns the run or that Smart Thermal automatic starts are enabled. A displayed electrical value can be stale after a Zigbee availability interruption; later automatic policy must verify bridge/device availability, a fresh post-recovery report, and safe ownership reconstruction as documented in [Zigbee2MQTT with SONOFF ZBDongle-E](../hardware/zigbee2mqtt-zbdongle-e.md).

Mission Control intentionally omits these floor sections after the dedicated view was introduced. Its first screen remains focused on whole-house energy, EnergyHub status, decision logic, and operating controls.

## Smart-Plug Views

![Smart-plug reserve protection logic](../Images/Infographic%233_smart_plug_reserve_logic.png)

The working-tree dashboard has three explicit tabs: **Mission Control**, **Heat Pumps**, and **Water Systems**. The two focused manual/observational views are:

- **Heat Pumps** — separate first-, second-, and third-floor sections with switch, live power, auto-off duration, absolute turn-off time, plus daily consumption for 7 days, weekly consumption for 6 weeks, and monthly consumption for 12 months;
- **Water Systems** — separate 2nd-floor boiler and basement-pump sections with switch and live power, plus the same daily/weekly/monthly history periods.

The first two heat pumps use their verified native cumulative entities `sensor.first_floor_heat_pump_plug_energy` and `sensor.second_floor_heat_pump_plug_energy`. The third-floor heat pump, boiler, and pump use local Integral sensors derived from live watts: `sensor.third_floor_heat_pump_energy_calculated`, `sensor.water_boiler_energy_calculated`, and `sensor.basement_water_pump_energy_calculated`. They use the left Riemann-sum method, kWh units, three-decimal precision, and a five-minute maximum sub-interval. This replaced Xiaomi daily/monthly cloud counters after those counters produced implausible 100–250 kWh daily changes.

The local Integral sensors persist across Home Assistant restarts but begin accumulating only after deployment. Home Assistant cannot retroactively import the Xiaomi app's cloud-only history. The charts therefore show accurate local history from that point forward; empty older third-floor/water periods are expected.

The water-boiler plug now has a deliberately narrow reserve policy. With fresh EnergyHub telemetry, reaching 50% SOC requests boiler OFF once. An ON request between 41% and 50% remains allowed; Home Assistant cannot reliably distinguish a physical/app action from the existing Xiaomi motion automation. At 40%, `input_boolean.energyhub_water_boiler_soc_lockout` latches, the boiler is requested OFF, and later ON requests are rejected. Fresh SOC of at least 60% clears the latch but never turns the boiler on automatically. The homeowner or Xiaomi demand automation remains responsible for restoration.

Heat pumps use a separate grid-confidence-aware reserve-only policy. EnergyHub exposes four categorical Grid Confidence states (`normal`, `unstable`, `risk`, and `panic`), so the relaxed case is intentionally stricter than `normal`: Grid Confidence must be `normal`, 24-hour availability must equal 100%, 48-hour available time must equal 48 hours, the grid must currently be present, and EnergyHub telemetry must be fresh. In that fully trusted state, only fresh SOC reaching 50% latches the all-floor lockout and requests every running heat pump OFF. Fresh SOC of at least 60% clears it.

Every missing, stale, unavailable, or degraded grid-confidence input selects the conservative policy. With fresh telemetry, reaching 80% SOC requests every running heat-pump plug OFF once. Manual overrides remain possible: floor 2 is shed again at 70%, floor 1 at 60%, and floor 3 is protected until 50%. At 50%, `input_boolean.energyhub_heat_pump_soc_lockout` latches, every running heat pump is requested OFF, and any later ON request is rejected. Fresh SOC of at least 90% clears the conservative lockout. Neither policy turns a heat pump on. Smart Thermal automatic starts remain deferred.

Confirmed `hybrid_charging`, `hybrid_grid_hold`, `panic`, or `panic_grid_hold` with fresh EnergyHub telemetry and current inverter grid voltage above 50 V temporarily permits manual heat-pump plug requests because the house is grid-backed. The underlying SOC lockout remains latched rather than being cleared. If strategy confirmation or present grid power is lost, the remembered lockout is immediately effective again on fresh telemetry and running heat pumps are requested OFF. The permission never turns a heat pump on; automatic Smart Thermal ownership and starts remain deferred.

No command is issued from stale EnergyHub telemetry. The lockouts are best effort: Home Assistant cannot physically prevent a local, Zigbee, or cloud command while Core, Zigbee2MQTT, the Xiaomi integration, the network, or a plug is unavailable. Persistent notifications show requested actions and observed plug states so failed commands are visible. Intermediate 80%/70%/60% shedding is not reconstructed blindly after restart or availability recovery; the 50% safety lockout is re-evaluated when trustworthy telemetry returns. A transition from the fully trusted grid state to a degraded state while SOC is already at or below 80% applies the conservative all-floor shed. The basement pump remains outside both policies. Local integration and long-term-statistics rendering require supervised validation after deployment. Power and calculated energy remain operational trend data rather than electrical-protection inputs.

## EnergyHub Decision Logic

Purpose:

```text
Why did EnergyHub make this decision?
```

Current sections include:

### Grid Situation

- Grid Confidence;
- Grid Available — Last 24 Hours;
- Grid Available — Last 48 Hours.

### Night Tariff Decision

- final Hybrid decision;
- Battery SOC used;
- House Consumption used;
- Battery Energy to Full;
- Total Energy Required;
- Solar Forecast Tomorrow;
- Decision Reason.

### Panic Decision

- Panic Decision;
- Panic Decision Reason;
- Panic Phase;
- Panic Target SOC;
- Grid Confidence Target;
- inherited AHM Target;
- Panic Target Source.

The main decision lines are visually emphasized while detailed evaluation inputs remain available below them.

## Energy Balance Chart

The current 7-day chart displays:

- House Consumption;
- Solar Surplus Estimated;
- Grid Import;
- Grid Availability.

Live header values include:

- Consumption Today;
- Grid Import Today;
- Forecast Today;
- Forecast Tomorrow.

Daily Summary history uses `sensor.energyhub_daily_summary_grid_import`.

Further chart and dashboard refinement may continue during 1.1 without changing the 1.0 operating architecture.

---

# Dashboard Responsibilities

The main EnergyHub dashboard components have separate responsibilities.

## Energy Balance

```text
What happened over time?
```

Provides:

- historical House Consumption;
- historical Solar Surplus Estimated;
- historical Grid Import Estimated;
- historical Grid Availability;
- live Consumption Today;
- current solar forecasts.

## EnergyHub Status

```text
What is happening now?
```

Provides:

- current Operating Mode;
- current strategy reason;
- inverter settings;
- battery behavior;
- current power telemetry;
- Grid Import estimation;
- communication state;
- user controls.

## EnergyHub Intelligence

```text
What does EnergyHub know?
```

Provides:

- Grid Confidence;
- recent Grid Availability;
- previous-day energy facts;
- future solar forecasts.

---

# Home Assistant Repository Structure

Selected current Home Assistant configuration is versioned in Git.

```text
homeassistant/
└── live/
    ├── config/
    │   ├── automations.yaml
    │   ├── configuration.yaml
    │   ├── scenes.yaml
    │   └── scripts.yaml
    └── storage/
        ├── input_boolean
        ├── input_number
        ├── timer
        ├── lovelace.dashboard_powmr1
        ├── lovelace_dashboards
        └── lovelace_resources
```

`live/` contains selected configuration synchronized from the current Home Assistant installation.

The old manually maintained `homeassistant/legacy/` structure was removed from Git.

The complete Home Assistant `.storage` directory must never be committed.

---

# Synchronization from Home Assistant

Current tool:

```text
tools/dev/sync-from-ha.ps1
```

Workflow:

```text
Edit and Test in Home Assistant
        ↓
Run sync-from-ha.ps1
        ↓
Copy Selected Configuration
        ↓
homeassistant/live/
        ↓
Review Git Changes
        ↓
Commit
```

Only explicitly approved Home Assistant files should be synchronized.

The repository copy is a selected, reviewable representation of the real installation.

It is not a complete Home Assistant backup.


---

# Persistent USB Serial Access

EnergyHub must use the inverter FTDI adapter's persistent device identity:

```text
/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_<device-id>-if00-port0
```

Do not configure `/dev/ttyUSB0` or `/dev/ttyUSB1` because numerical assignment can change after a host restart or when another USB serial device is connected.

The EnergyHub app manifest enables:

```yaml
uart: true
udev: true
```

A Zigbee coordinator may remain connected through its own persistent `by-id` path. EnergyHub must always be configured with the FTDI path, not an Itead/Sonoff Zigbee path.

Installation and upgrade steps are documented in:

```text
docs/operations/INSTALLATION.md
```

---

# Development Deployment

Current deployment tool:

```text
tools/dev/deploy-to-ha.ps1
```

The add-on scope uses the existing lower-level synchronization tool:

```text
tools/dev/sync-to-ha.ps1
```

The default scope preserves the historical add-on workflow:

```text
Git Repository
        ↓
deploy-to-ha.ps1
        ↓
sync-to-ha.ps1
        ↓
Home Assistant Add-on Directory
        ↓
Manual Add-on Restart
        ↓
Inspect Logs
        ↓
Test
```

Explicit scopes keep post-deploy actions separate:

```powershell
# Add-on only; this is also the default.
.\tools\dev\deploy-to-ha.ps1 -Scope Addon

# Selected HA YAML while Core is running.
.\tools\dev\deploy-to-ha.ps1 `
    -Scope HomeAssistant `
    -ConfigFiles automations.yaml

# Selected HA YAML and storage while Core is stopped.
.\tools\dev\deploy-to-ha.ps1 `
    -Scope HomeAssistant `
    -ConfigFiles automations.yaml `
    -StorageFiles input_number,timer,lovelace.dashboard_powmr1 `
    -HomeAssistantStopped
```

Add-on and Home Assistant configuration are deliberately separate deployment runs. `-DryRun` validates sources and prints targets without contacting or modifying Home Assistant.

Before replacing a Home Assistant file, the synchronization tool copies the current target to `\\homeassistant\config\energyhub-deploy-backups\<timestamp>`. Storage deployment is refused unless `-HomeAssistantStopped` is present. That switch is an operator assertion: the script does not remotely stop or verify HA Core.

Post-deploy behavior is scoped:

- add-on files changed: rebuild and restart the Energy Hub add-on, then inspect its logs;
- `automations.yaml`, `scripts.yaml`, or `scenes.yaml` changed while Core stayed running: reload only the matching component;
- `configuration.yaml` changed: check configuration and restart HA Core;
- `.storage` changed: keep Core stopped during the copy, run `ha core check`, start Core, and do not perform a separate YAML reload.

---

# Deployment and Synchronization Boundary

The two workflows have different purposes.

## EnergyHub Application Code

```text
Git
→ Home Assistant
```

## Selected Home Assistant Configuration

```text
Git ↔ Home Assistant
```

Intentional UI changes are synchronized from Home Assistant to Git for review. Reviewed repository configuration is deployed from Git to Home Assistant through the guarded workflow above.

Architecture:

```text
EnergyHub Code
        ↓
Deploy
        ↓
Home Assistant Add-on

Home Assistant Configuration
        ↕
Guarded Deploy / Synchronize
        ↕
Git Repository
```

These workflows should remain separate and explicit.

---

# Configuration Authority

The Git repository is the development source of truth for the selected Home Assistant configuration listed below. The real Home Assistant installation is the runtime instance; intentional UI changes must be synchronized back to Git and reviewed before they become the next repository baseline.

The repository stores selected configuration for:

- review;
- history;
- architectural understanding;
- recovery of important configuration.

Current synchronized files include:

```text
homeassistant/live/config/automations.yaml
homeassistant/live/config/configuration.yaml
homeassistant/live/config/scenes.yaml
homeassistant/live/config/scripts.yaml
homeassistant/live/storage/input_boolean
homeassistant/live/storage/input_number
homeassistant/live/storage/timer
homeassistant/live/storage/lovelace.dashboard_powmr1
homeassistant/live/storage/lovelace_dashboards
homeassistant/live/storage/lovelace_resources
```

---

# Configuration Rule

Home Assistant configuration stored in Git should remain:

- selected;
- understandable;
- reviewable;
- safe to commit;
- useful for EnergyHub development.

The goals are:

```text
Understand Changes
        ↓
Review Changes
        ↓
Preserve EnergyHub Integration
        ↓
Recover Important Configuration
        ↓
Maintain Architectural Documentation
```

The goal is not to turn the EnergyHub repository into a complete Home Assistant backup.
