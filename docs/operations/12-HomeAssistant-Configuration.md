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
- optional PV2 telemetry validation, freshness, and aligned Total PV;
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
input_number.daily_solar_surplus_estimated
input_number.ahm_minimum_soc
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

# AHM Minimum SOC Helper

Entity:

```text
input_number.ahm_minimum_soc
```

The helper selects the minimum reserve used by Adaptive Hybrid Mode. It ranges from 20% to 50% in 5% steps and is published through retained MQTT. Suggested interpretations are 20% economy, 30% balanced, 40% conservative, and 50% very conservative. The value is advisory and manual; Grid Confidence does not change it automatically. Panic retains its independent 20/60/80/95% targets.

## Morning essential-load learning

`EnergyHub - Capture Essential Morning Load` publishes non-retained cumulative
energy snapshots at 07:00–12:00 hourly boundaries from:

```text
sensor.powmr_10_2m_daily_house_consumption
sensor.first_floor_heat_pump_plug_energy
sensor.second_floor_heat_pump_plug_energy
sensor.third_floor_heat_pump_energy_calculated
```

EnergyHub subtracts the combined heat-pump delta from the total-house delta,
retains 21 days, and learns the 75th percentile for each interval. Every
interval needs three samples before the flexible model can replace the verified
300 W → 600 W fallback. Missing/unavailable inputs skip the sample rather than
manufacturing zero consumption.

---

# Smart Load Boundary

The original EnergyHub 1.0 Away Mode helpers and automation were removed from the active 1.0 architecture.

EnergyHub 1.1 adds manual smart-plug controls, per-floor auto-off timers, and reserve-only OFF guards as Home Assistant household automation. It never turns the boiler or a heat pump on. Automatic Smart Thermal ownership and starts remain deferred to 2.0.

The ownership principle remains valid:

> EnergyHub should automatically stop a household load only when EnergyHub previously started it.

---

# Daily Solar Surplus Estimated Helper

Entity:

```text
input_number.daily_solar_surplus_estimated
```

Purpose:

Stores the estimated daily solar energy that was probably not used. The helper
is retained for compatibility, but the atomic Daily Summary no longer depends
on its availability.

Current formula:

```text
max(0, Solcast Forecast Today - Daily House Consumption)
```

Source entities:

```text
sensor.solcast_pv_forecast_forecast_today
sensor.powmr_10_2m_daily_house_consumption
```

The 23:49/23:51 Daily Summary publishing automation calculates the same value
directly from the live source entities and includes it in the atomic snapshot.
This prevents an unavailable helper from blocking all daily history updates.

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
- requesting a Panic ownership evaluation at 07:00 when Autopilot is enabled;
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

# PV2 and Total PV Entities

EnergyHub 1.3.5 publishes the following MQTT Discovery entities when the app is
running, whether optional Modbus polling is enabled or disabled:

```text
sensor.powmr_10_2m_pv1_voltage
sensor.powmr_10_2m_pv1_power
sensor.powmr_10_2m_pv2_voltage
sensor.powmr_10_2m_pv2_power
sensor.powmr_10_2m_total_pv_power
sensor.energyhub_pv2_telemetry_status
sensor.energyhub_pv2_telemetry_freshness
sensor.energyhub_pv2_sample_age_seconds
```

PV1 remains the existing PI30MAX telemetry. PV2 uses optional read-only Modbus.
Total PV is a derived measurement and is available only when the component
samples are within 15 seconds and both remain fresh. Dedicated
`powmr/pv2/status` and `powmr/total_pv/status` topics mask retained last-known
values when disabled, failed, stale, or awaiting the first post-restart sample.

PV2 status remains visible through `energyhub/status` so Home Assistant can
distinguish `disabled`, `awaiting_sample`, `fresh`, `stale`, `timeout`,
`crc_error`, `malformed_response`, `invalid_value`, `unsupported`,
`modbus_exception`, and `error` without treating the diagnostic itself as
inverter production.

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

Adaptive Night Hybrid calculates its target once at 23:50:

    projected_soc_at_07 = current_soc - 15
    morning_gap_soc = hours_from_07_to_first_300W_forecast × 10
    target_soc = min(95, 20 + morning_gap_soc + 10)

EnergyHub 1.3.8 persists the date through which that target is authoritative.
Until a confirmed morning Solar handover, each fresh telemetry cycle keeps
Solar above target, selects Hybrid Grid Hold at exact target, and selects or
resumes Hybrid Charging below target. An offline grid or stale SOC causes no
command. This is continuous enforcement of the existing AHM plan, not a new
operating mode or repeated target calculation.

The three outcomes are:

- projected SOC meets target: remain Solar;
- current SOC meets target but projected SOC does not: enter Grid Hold;
- current SOC is below target: enter Hybrid Charging, then Grid Hold at target.

The 07:00 schedule requests a Panic evaluation rather than restoring Solar.
Panic can transfer confirmed `SUB` + `OSO` Grid Hold ownership without another
inverter write. Under Normal confidence with present grid and no AHM debt, it
holds 20% and releases Solar at 30%. If hourly
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
sensor.energyhub_hybrid_minimum_soc
sensor.energyhub_hybrid_raw_morning_hours
sensor.energyhub_hybrid_morning_hours
sensor.energyhub_hybrid_useful_solar_start
sensor.energyhub_hybrid_effective_solar_start
sensor.energyhub_hybrid_ramp_confirmed
sensor.energyhub_hybrid_ramp_credit_hours
sensor.energyhub_hybrid_ramp_start_power_w
sensor.energyhub_hybrid_ramp_next_power_w
sensor.energyhub_hybrid_morning_reserve_soc
sensor.energyhub_hybrid_target_soc
sensor.energyhub_hybrid_target_capped
sensor.energyhub_hybrid_forecast_fallback
sensor.energyhub_hybrid_early_solar_check
sensor.energyhub_hybrid_early_solar_reason
sensor.energyhub_hybrid_early_solar_evaluated_at
sensor.energyhub_hybrid_early_solar_live_power_w
sensor.energyhub_hybrid_early_solar_forecast_kwh
```

These entities allow Home Assistant to show both the final decision and the exact values used during the most recent Hybrid evaluation.

The five Early Solar entities show the separate 06:05 Grid Hold release check,
including its final transition result, reason, live aligned Total Solar, and
the current-day 06:00–07:00 Solcast interval supplied by Home Assistant.

Home Assistant displays these values but does not duplicate the Hybrid decision formula.

The detailed 23:50 values are retained in MQTT until a later evaluation
replaces them. EnergyHub startup deliberately replaces only the decision and
reason presentation with `awaiting_evaluation`, because those detailed values
were not calculated by the new process. If a target was restored, the reason
states that it was retained while the detailed night plan is unavailable. A
Home Assistant-only restart restores these retained presentation values.

---

# Smart Heating / Away Integration

Away Mode is not part of the final EnergyHub 1.0 architecture.

The original implementation was deferred after design review showed that occupancy, comfort, solar surplus, cheap-tariff use, and battery reserve should be handled through a broader Smart Heating / flexible-load architecture.

EnergyHub 1.1 provides the monitored-device, dashboard, timer, and reserve-guard foundation. Automatic Smart Thermal control remains deferred to 2.0.

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

EnergyHub 1.3.9 adds two diagnostic MQTT entities without changing System
Health or control:

- `sensor.energyhub_soc_anomaly_event_count` — persistent lifetime count;
- `sensor.energyhub_soc_anomaly_latest` — timestamp state with the full latest
  event in attributes.

The add-on retains only the latest 100 detailed events. A five-point SOC change
over more than five minutes is not classified as a jump because the missing
interval may contain legitimate battery movement.

Telegram Family Assistant 1.3.14 separately reads the seven configured Xiaomi
temperature/humidity pairs every five minutes. It prefers Home Assistant's
`last_reported` freshness timestamp and falls back to `last_updated`. It also
uses `last_changed` to report a pair whose temperature and humidity both stay
unchanged for 24 hours as suspected offline, covering integrations that refresh
cached values. The six
indoor locations use their peer median; the basement is isolated from that
comparison. Same-hour previous-day observations provide the per-sensor
baseline. Unavailable/stale states, persistent 5 °C or 20-percentage-point
outliers, per-sensor deduplicated recoveries, verified sensor batteries, and an
optional doorbell battery appear only in the 08:00 report. They are not
EnergyHub decision inputs.

EnergyHub 1.3.10 adds `sensor.energyhub_inverter_fault_current` and
`sensor.energyhub_inverter_fault_recent_1` through `_3`. The EnergyHub Status
dashboard shows these four read-only rows. Selecting a recent row opens the
retained incident attributes, including timestamp, clearance, and bounded
pre-event conditions. Telegram Family Assistant 1.3.14 reads the three recent
entities for its previous-day morning summary.

The working-tree Zigbee reliability increment uses Zigbee2MQTT's Home Assistant-discovered `binary_sensor.zigbee2mqtt_bridge_connection_state`, which reads the retained `zigbee2mqtt/bridge/state` MQTT topic. If it remains offline for two minutes, Home Assistant creates one persistent notification stating that readings may be stale and that no restart or relay action was attempted. An online transition dismisses that alert and creates a recovery notice that requires individual-device availability and fresh post-recovery reports to be checked. This is bridge transport monitoring only: it does not prove that the Zigbee2MQTT app is healthy, that a device is reachable, or that any retained measurement is fresh.

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
- AHM Minimum SOC with profile and Grid Confidence guidance;
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

The dedicated Heat Pumps view begins with a live policy card that distinguishes
current family/EnergyHub authority from a remembered lockout. Each floor then
uses the same compact operating layout:

1. heat-pump switch state and manual toggle;
2. live plug power in watts;
3. auto-off duration from `0` to `9` hours;
4. absolute local turn-off time, or `Manual` when no timer is active.

Floor 1 uses `switch.first_floor_heat_pump_plug` and `sensor.first_floor_heat_pump_plug_power`. Floor 2 uses `switch.second_floor_heat_pump_plug` and `sensor.second_floor_heat_pump_plug_power`. Floor 3 retains `switch.energyhub_heat_pump_floor_3` and `sensor.energyhub_heat_pump_floor_3_power`. Template sensors `sensor.floor_1_heat_pump_turns_off_at`, `sensor.floor_2_heat_pump_turns_off_at`, and `sensor.floor_3_heat_pump_turns_off_at` render `Today HH:MM`, `Tomorrow HH:MM`, another local date/time, or `Manual` from each timer's `finishes_at` attribute. Daily, weekly, and monthly consumption graphs remain below the compact controls.

These cards expose Home Assistant household controls only. The policy card
shows reserve authority but does not claim that Smart Thermal automatic starts
are enabled. A displayed electrical value can be stale after a Zigbee
availability interruption; later automatic policy must verify bridge/device
availability, a fresh post-recovery report, and safe ownership reconstruction
as documented in [Zigbee2MQTT with SONOFF ZBDongle-E](../hardware/zigbee2mqtt-zbdongle-e.md).

Mission Control intentionally omits these floor sections after the dedicated view was introduced. Its first screen remains focused on whole-house energy, EnergyHub status, decision logic, and operating controls.

## Smart-Plug Views

![Smart-plug reserve protection logic](../Images/Infographic%233_smart_plug_reserve_logic.png)

The working-tree dashboard has four explicit tabs: **Mission Control**, **Energy Statistics**, **Heat Pumps**, and **Water Systems**. The focused observational/manual views are:

- **Energy Statistics** — side-by-side PV1/PV2 generation and estimated
  night/normal Grid Import for 7 days, 7 weeks, and 12 months, plus a compact
  current-month tariff kWh/cost summary and the read-only prices used. PV
  generation uses dark/light blue, while estimated night/normal import uses
  dark/light pink; both tariff legend entries remain visible when one is zero;
- **Heat Pumps** — separate first-, second-, and third-floor sections with switch, live power, auto-off duration, absolute turn-off time, plus daily consumption for 7 days, weekly consumption for 6 weeks, and monthly consumption for 12 months;
- **Water Systems** — separate 2nd-floor boiler and basement-pump sections with switch and live power, plus the same daily/weekly/monthly history periods.

The first two heat pumps use their verified native cumulative entities `sensor.first_floor_heat_pump_plug_energy` and `sensor.second_floor_heat_pump_plug_energy`. The third-floor heat pump, boiler, and pump use local Integral sensors derived from live watts: `sensor.third_floor_heat_pump_energy_calculated`, `sensor.water_boiler_energy_calculated`, and `sensor.basement_water_pump_energy_calculated`. They use the left Riemann-sum method, kWh units, three-decimal precision, and a five-minute maximum sub-interval. This replaced Xiaomi daily/monthly cloud counters after those counters produced implausible 100–250 kWh daily changes.

The local Integral sensors persist across Home Assistant restarts but begin accumulating only after deployment. Home Assistant cannot retroactively import the Xiaomi app's cloud-only history. The charts therefore show accurate local history from that point forward; empty older third-floor/water periods are expected.

The tariff chart series use the monotonic
`sensor.energyhub_grid_import_night_total_estimated` and
`sensor.energyhub_grid_import_normal_total_estimated` sources with Home
Assistant `change` statistics. Tariff history begins with EnergyHub 1.3.11 and
cannot reconstruct the split before deployment. Grid Import and UAH cost remain
informational estimates rather than billing-grade meter readings.

The water-boiler plug has a deliberately narrow reserve policy when the grid
is not trusted. With fresh EnergyHub telemetry, reaching 50% SOC requests
boiler OFF once. An ON request between 41% and 50% remains allowed. At 40%,
`input_boolean.energyhub_water_boiler_soc_lockout` latches, requests OFF, and
rejects later ON requests. Fresh SOC of at least 60% clears the latch without
turning the boiler on. While Grid Confidence is Normal, grid voltage is above
180 V, and telemetry is fresh, manual/demand control is permitted at every SOC;
the remembered latch remains available if trust is later lost.

Heat pumps use the same trust gate with a separate reserve-relative policy. The family
retains manual control when Grid Confidence is `normal`, current inverter grid
voltage is above 180 V, and EnergyHub telemetry is `fresh`. A remembered lockout
may remain latched underneath that permission so protection can return
immediately if the trust gate is lost. Manual permission never starts a heat
pump.

When the grid is not trusted, the selected AHM minimum `S` defines the
heat-pump bands. At `S+30`, Home Assistant requests all running participating
heat pumps OFF once; a later manual override remains possible. At `S+20`,
`input_boolean.energyhub_heat_pump_soc_lockout` latches, all running heat pumps
are requested OFF, and later ON requests are rejected. Fresh SOC at `S+40`
clears the latch without restarting any load. For `S=20%`, the thresholds are
50% shed, 40% lockout, and 60% recovery. For `S=50%`, they are 80%, 70%, and
90%.

Template triggers evaluate SOC, Grid Confidence, present grid, telemetry
freshness, and AHM minimum together. A transition from trusted to untrusted
conditions therefore applies the appropriate current band even if SOC crossed
it earlier. The shed and lockout paths repeat the grid-trust check after fresh
telemetry is confirmed and immediately before their actions. This prevents an
SOC `unavailable` → threshold recovery from carrying a stale untrusted result
into a plug command after the grid has already been confirmed Normal and
present. Stale telemetry cannot create or clear an SOC-derived lockout. If a
lockout was already latched, stale telemetry conservatively removes trusted-grid
manual permission and may reassert OFF; it never starts a load. Lockouts are
best effort: Home Assistant cannot physically prevent a local, Zigbee, or
cloud command while Core, Zigbee2MQTT, the Xiaomi integration, the network, or
a plug is unavailable. Persistent notifications show requested actions and
observed plug states. The basement pump remains outside this policy, and
automatic Smart Thermal starts remain deferred.

At Home Assistant startup, the boiler and heat-pump latch, enforcement, and
clear paths wait ten seconds and then reconcile restored helper state with the
current trust and SOC conditions. This closes the restart interval without
creating an automatic ON path.

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

The following Early Solar handover subsection shows the 06:05 check result,
reason, evaluation time, live Total Solar, and forecast energy for
06:00–07:00. The main controls use the user-facing title **Adaptive Hybrid
Reserve** and **Active reserve** rather than requiring the homeowner to know
the internal `AHM` abbreviation.

### Panic Decision

- Panic Decision;
- Panic Decision Reason;
- Panic Phase;
- Panic Target SOC;
- Grid Confidence Target;
- inherited AHM Target;
- Panic Target Source.

The main decision lines are visually emphasized while detailed evaluation inputs remain available below them.

## Mission Control Solar Charts

The working-tree Mission Control view uses two complementary 24-hour power charts:

- **Energy Flow** compares `sensor.powmr_10_2m_total_pv_power` with house load and Battery SOC. The live W series is labelled **Total Solar Now**.
- **PV Power** shows only PV1 and PV2 power so neither array is obscured by a Total Solar line. Its header shows PV1 Today, PV2 Today, and **Total Solar Today** energy in kWh.

Total Solar uses an orange two-pixel line in Energy Flow. PV1 uses a dark-blue two-pixel line and PV2 uses a light-blue two-pixel line in PV Power. House Load remains blue and Battery SOC remains green.

Both charts use five-minute aggregation and a 24-hour `HH:mm` time axis. Total PV follows the add-on's conservative availability contract: it is unavailable instead of silently falling back to PV1 when the PV2 sample is missing, stale, invalid, or not sufficiently aligned with PV1.

The dashboard does not yet present house load as a stacked grid-versus-solar/battery split. Grid import is estimated, and the available telemetry does not provide a signed battery-power measurement suitable for an honest solar-versus-battery decomposition.

The Solar view is backed by three repository-managed Integral sensors: `sensor.energyhub_pv1_energy_total`, `sensor.energyhub_pv2_energy_total`, and `sensor.energyhub_total_solar_energy`. The Total Solar energy sensor integrates Total PV Power directly; it is not calculated by adding independently rounded period values. All three use the trapezoidal method, kWh units, three-decimal precision, and a five-minute maximum sub-interval. Daily, weekly, monthly, and yearly Utility Meter sensors provide progressively broader chart-header totals: today above the 24-hour chart, this week above the 7-day chart, this month above the 7-week chart, and this year above the 12-month chart. Home Assistant derives their entity IDs from the configured display names: `sensor.pv1_generated_today`, `sensor.pv2_generated_today`, `sensor.total_solar_generated_today`, with matching `*_this_week`, `*_this_month`, and `*_this_year` forms. Chart columns use Recorder long-term-statistics change values over day, week, and month periods.

These energy entities begin accumulating only after deployment and cannot reconstruct earlier PV2 history automatically. The pre-existing UI helper `sensor.powmr_10_2m_pv_energy_total` and its Daily/Weekly/Monthly PV Generation helpers are not used because the live audit proved that their source is PV1 Power only despite the ambiguous Total/PV naming. They remain untouched pending supervised cleanup after the replacement entities are validated.

## Energy Balance Chart

The current 7-day chart displays:

- House Consumption;
- EV Potential Estimated;
- Grid Import Estimated.

Live header values include:

- Consumption Today;
- Solar Forecast Today;
- Solar Forecast Tomorrow.

Daily Summary history uses `sensor.energyhub_daily_summary_grid_import`.

`EV Potential Est.` is the existing Daily Solar Surplus Estimated value under a clearer dashboard label. It is a planning estimate based on forecast solar minus house consumption, not measured curtailed or lost solar. It excludes charging and inverter losses and must not be treated as guaranteed EV charging energy or an automatic-control input.

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
