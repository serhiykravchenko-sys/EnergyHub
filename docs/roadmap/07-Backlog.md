# EnergyHub Backlog

This backlog contains open work. Completed High and selected Medium audit items are recorded in the changelog and project history rather than left as active tasks.

## EnergyHub 1.0 — Release closure

### Automated tests

Priority: High before external release.

Add tests for:

- Hybrid decision formula and skipped states;
- Panic thresholds and time window;
- queue priority for `safe_solar`;
- transition success/failure events;
- Menu 01 verification behavior;
- restart reconstruction combinations;
- Grid Import rollover and finalization;
- atomic Daily Summary idempotence;
- JSON persistence failure handling.

### Release security

- remove weak default MQTT username/password from published defaults;
- document secret configuration;
- verify no runtime exports or credentials are tracked;
- review add-on permissions and device mapping.

### Dependency pinning

- capture tested `paho-mqtt` and `mpp-solar` versions from the working add-on;
- pin exact compatible versions;
- rebuild from a clean environment;
- record upgrade policy.

### Installation and operations guide

- fresh add-on installation;
- Mosquitto user setup;
- serial device selection;
- HA configuration synchronization;
- Solcast prerequisites;
- dashboard resource prerequisites;
- backup and rollback;
- troubleshooting startup and MQTT.

### Final UI cleanup

- verify mobile layout;
- confirm all icons and colours in light and dark themes;
- ensure the technical chart does not dominate the family view;
- verify Smart Thermal is visibly planned, not active.

### Real transition validation

- observe a real automatic Hybrid Charging entry;
- observe Hybrid target → Grid Hold;
- observe 07:00 Solar restoration;
- observe automatic Panic 80% and 95% paths when conditions permit;
- verify success and failure notification ordering.

## EnergyHub 1.1 — Smart Plug Reserve Guard

### MQTT energy metadata pre-release audit

Priority: High before the next release tag.

Home Assistant Core reported MQTT discovery warnings on 2026-08-07 because several EnergyHub sensors combine `device_class: energy` with the now-invalid `state_class: measurement`. Observed examples include Daily House Consumption, Daily Solar Forecast, Daily Summary Grid Import, and Hybrid Evaluated Consumption. The audit must cover every EnergyHub MQTT energy sensor rather than only the entities named in the startup log.

- classify each published energy value by behavior: instantaneous snapshot or estimate, resettable daily total, monotonic lifetime counter, or finalized period total;
- assign `state_class: total`, `total_increasing`, or no state class according to that behavior; never retain `measurement` on an energy device class;
- add discovery-payload tests that reject invalid energy metadata and verify reset behavior assumptions;
- rebuild and restart the Energy Hub add-on so corrected retained MQTT discovery replaces the existing payloads;
- restart or reload the affected integration as required, then confirm the warnings no longer appear;
- verify current values, Recorder long-term statistics, and dependent dashboard charts after the metadata migration.

Acceptance criterion: a supervised pre-release startup produces no EnergyHub MQTT energy metadata warnings, all affected entities retain correct units and values, and their intended statistics remain usable.

### Adaptive Night Hybrid reserve protection

Priority: High before unattended Smart Thermal control and before shorter, less-sunny days materially increase overnight reserve risk.

User outcome: EnergyHub enters the morning with enough stored energy to survive a plausible grid outage and the morning load peak, even when sunrise occurs but cloud prevents useful solar production.

Initial scheduled increment implemented and live-validated on 2026-08-07:
one 23:50 calculation, a 15-point overnight allowance, the first tomorrow
Solcast hourly period at or above 300 W, 10 SOC points per morning-gap hour,
a 20% protected reserve, a 10% uncertainty margin, a 95% cap, immediate
Charging or Grid Hold when required, retained dashboard explanation, and 07:00
Solar restoration.

- estimate the real discharge rate from a robust rolling SOC window while excluding charging and mode-transition periods;
- retain one scheduled 23:50 target decision; consider only a separate bounded
  emergency-floor check if observation later proves it necessary, rather than
  repeatedly retargeting Hybrid overnight;
- treat measured overnight SOC decline as only one input because predictable morning loads can be materially higher than the overnight baseline;
- calculate a morning resilience target from the protected reserve, a conservative estimate of net house energy through a configurable resilience horizon, and a forecast-uncertainty margin;
- use conservative forecast solar, not sunrise or the first non-zero PV report; if forecast quality is stale or unavailable, assume little or no dependable PV for the protected interval;
- calculate expected charge duration at 23:50 from the SOC gain and a
  conservative observed grid-charge rate, start required charging immediately,
  and warn when the target is unlikely to be reachable before 07:00;
- expose an explicit policy for a target that cannot be reached before cheap tariff ends: safety-first charging after 07:00, cost-first stop, or attended confirmation; never silently choose between cost and reserve;
- enter Hybrid preventively before SOC crosses the dynamic target, charge to the target when required, and otherwise use Grid Hold to preserve an already adequate reserve;
- first implement a narrow overnight hard-floor guard using fresh, repeated SOC readings and an initial candidate floor of protected reserve plus a configurable margin; this provides protection while the predictor is still being validated;
- continue comparing the live adaptive projection, target, useful-solar time,
  and observed outcome over several nights after the successful first
  automatic validation;
- confirm sustainable useful solar from actual PV surplus, non-declining battery SOC, and adequate remaining forecast before returning to Solar; a brief cloud break must not cause an early exit;
- add entry/exit hysteresis, conservative fallbacks for unreliable rate data, fresh-input gates, persisted ownership, and restart-safe reconstruction;
- keep scheduled cheap-tariff Hybrid and Panic as distinct intents with explicit priority;
- keep Grid Confidence out of the cheap-tariff Hybrid target; use the separate
  Panic strategy for grid-risk-driven reserve recovery;
- inhibit future Smart Thermal starts whenever the projected reserve is unsafe;
- cover the projection, target, priority, hysteresis, stale-input, and restart boundaries with unit tests before live activation.

Initial conceptual model:

```text
morning_contingency_soc =
    conservative_net_load_energy_until_resilience_horizon
    / usable_battery_energy

morning_resilience_target =
    protected_reserve
    + morning_contingency_soc
    + forecast_and_measurement_margin
```

The target represents energy to retain for a possible grid outage; it is not a prediction that the battery will continue supplying the house after Grid Hold begins. The entry projection and post-entry charge target remain separate because Grid Hold carries the live house load from grid. If the grid is already unavailable, EnergyHub cannot create reserve: it must inhibit discretionary loads, preserve the hard floor, and alert.

#### Next increment: cold-season post-07:00 energy balance

Status: implemented for EnergyHub 1.3.0 using the explicit 17/24 aligned-load projection, hourly post-07 Solcast sum, 16 kWh battery model, and 90% conservative efficiency. Measured time-of-day load profiles remain a future refinement.

Priority: planned after several nights of Adaptive Hybrid observation; important
before cold-season consumption reaches roughly 30-40 kWh/day while generation
may be only about 15 kWh/day.

- estimate expected house consumption from 07:00 to the next cheap-tariff
  window rather than using the complete calendar-day total;
- compare it with forecast solar over the same interval;
- exclude night-window consumption because Grid Hold supplies that load
  directly from cheap grid power;
- convert only the remaining positive energy deficit to SOC using usable
  battery capacity and a conservative efficiency;
- calculate the target as protected reserve plus uncertainty margin plus the
  larger of morning-gap SOC or post-07:00 deficit SOC, avoiding double-counting;
- keep the 20% reserve protected rather than treating it as normal forecast
  deficit energy;
- display whole-day consumption and generation totals as context, not as a
  direct subtraction formula;
- learn the time-of-day load profile from measured history and later consider
  thermal-load plans and weather sensitivity;
- publish the daytime deficit, SOC conversion, cap, and reason on the dashboard;
- test winter scenarios such as 30/15 and 40/15 kWh consumption/generation,
  forecast error, target-cap saturation, and unavailable load history.

```text
post_07_energy_deficit_kwh =
    max(0,
        expected_house_consumption_after_07
        - forecast_solar_after_07)

future_target_soc =
    min(95,
        protected_reserve
        + uncertainty_margin
        + max(morning_gap_soc, daytime_deficit_soc))
```

Panic remains a distinct daytime recovery layer. A later, lower-priority policy
may use actual SOC trajectory and remaining forecast to replenish reserve
during the day when the night plan proves insufficient. Do not trigger Panic
from the daily energy gap alone until its grid-risk priority, thresholds,
hysteresis, and interaction with Adaptive Hybrid have been validated.

Initial charge-deadline model:

```text
required_charge_soc = max(0, morning_resilience_target - current_soc)

required_charge_hours =
    required_charge_soc / conservative_observed_grid_charge_rate_soc_per_hour

start_by =
    cheap_tariff_end
    - required_charge_hours
    - completion_margin
```

The configured 30 A grid-charge setting is an installation constraint, not proof of the achieved SOC-per-hour rate. EnergyHub must learn or conservatively configure the effective rate and verify that charging is progressing as expected.

### Configuration and setup dashboard

Priority: planned for EnergyHub 1.2, preceded by a typed configuration model and migration that preserve all 1.0.2 defaults.

Provide a dedicated Home Assistant EnergyHub Settings view with validated, persistent controls and a read-only decision preview. Initial groups:

- tariff: cheap-tariff start/end and latest acceptable charging start;
- battery installation: usable capacity, protected reserve, configured grid-charge current, conservative effective charge rate, and completion margin;
- Hybrid: scheduled evaluation time, scheduled target, Adaptive Night Hybrid enable, resilience horizon, target cap, useful-solar confirmation thresholds, and after-tariff safety policy;
- Panic: automatic Panic evaluation enable, evaluation window, trigger thresholds, and the current 80%/95% targets; disabling automatic checks must not remove manual Panic or health monitoring;
- Smart Loads: separate enable gates, never implied by Autopilot or inverter-policy configuration;
- preview: effective configuration, calculated morning target, required charge duration, start-by time, projected completion, active constraints, and decision reason.

EnergyHub, not an unvalidated dashboard helper, owns the effective persisted configuration. Home Assistant may provide the editing UI and command transport, but EnergyHub validates ranges and cross-field rules, acknowledges accepted values, rejects unsafe combinations, and publishes effective settings back for reconciliation. Editing a field must not itself issue an inverter command.

### Operational dependency monitoring and bounded recovery

Priority: High before unattended smart-load control.

- monitor EnergyHub process health, inverter telemetry freshness, MQTT, Home Assistant, Zigbee2MQTT bridge/app state, individual Zigbee-device availability, and required cloud-integration/entity availability as separate layers;
- surface Home Assistant Repairs and reauthentication requirements operationally instead of treating a stale entity value as trustworthy telemetry;
- verify harmless actuator commands through observed device state when practical;
- alert first, permit only bounded component-specific recovery with cooldown, and stop after failed recovery rather than creating restart loops;
- never use bridge/app recovery alone to authorize a heat-pump relay command;
- use an external observer for Home Assistant/Supervisor failure because Home Assistant cannot fully supervise itself.

Observed gaps:

- on 2026-08-05, Zigbee2MQTT failed its Ember/EZSP startup with `HOST_FATAL_ERROR`, exited while Watchdog was enabled, and did not recover autonomously;
- on 2026-08-06, a healthy bridge hit `ASH_ERROR_TIMEOUTS`; Supervisor Watchdog then made ten restart attempts in about five minutes, but all ten opened the serial port and failed ASH/EZSP startup with `HOST_FATAL_ERROR` before the crash loop stopped;
- an attended manual Start at 11:51 on 2026-08-06 resumed the existing coordinator network, MQTT, both devices and relay states, and fresh reports without re-pairing or an observed relay toggle;
- on 2026-08-06, Home Assistant Repairs exposed expired Tuya authentication; re-confirming the login through the Tuya app restored control, strongly indicating that the beacon's stale color was an integration-authentication failure rather than incorrect EnergyHub SOC/color logic.

### Zigbee2MQTT foundation

User outcome: EnergyHub has a local, observable path to control and measure flexible loads without changing inverter communication.

- configure Zigbee2MQTT for the SONOFF ZBDongle-E using its persistent `/dev/serial/by-id/...` identity;
- use the coordinator in exactly one Zigbee stack; ZHA and Zigbee2MQTT must not claim it simultaneously;
- keep the SONOFF coordinator path distinct from the PowMr FTDI path;
- record adapter, channel, network-key backup, MQTT topic, and recovery procedure without committing secrets;
- validate coordinator availability after Zigbee2MQTT restart and full Home Assistant host restart.

Status on 2026-08-02:

- complete: official stable Zigbee2MQTT installed and configured with the persistent SONOFF identity, `ember`, software flow control, MQTT, Home Assistant discovery, and Zigbee channel 25;
- complete: coordinator firmware 7.4.4, startup, MQTT connection, discovery publication, Zigbee2MQTT restart recovery, and full Home Assistant host-restart recovery validated;
- complete: coordinator positioned on a 1 m USB extension away from the Raspberry Pi and inverter;
- complete: private encrypted Home Assistant backup verified to contain the Zigbee2MQTT app and its data;
- status: Zigbee2MQTT foundation complete on 2026-08-02.

### Two smart-plug validation

User outcome: two named household loads can be controlled manually and observed reliably before automation is introduced.

- pair two compatible Zigbee smart plugs one at a time;
- assign stable, room-oriented friendly names;
- verify on/off control, availability, link quality, and routing behavior;
- verify voltage, current, power, and energy reporting where the device supports them;
- verify retained/reconstructed state after plug, Zigbee2MQTT, and Home Assistant restarts;
- document each plug's power-on behavior and safe default;
- keep automatic starts disabled; EnergyHub 1.1 may only request reserve-protection OFF actions.

Status on 2026-08-02:

- complete: `first_floor_heat_pump_plug` paired as `TS011F_plug_1_1` (`Zbeacon`), direct power monitoring, observed LQI about 164–168;
- complete: `second_floor_heat_pump_plug` paired as `TS011F_plug_3` (`Tuya`), polled power monitoring, observed LQI about 152–172;
- complete: stable friendly names, pairing interviews, Zigbee2MQTT relay control, physical-button state synchronization, and power-outage memory `off`;
- observed: at 21:30 on 2026-08-02, one Ember `ASH_ERROR_TIMEOUTS` transaction failure disconnected the adapter and stopped Zigbee2MQTT while the Home Assistant app Watchdog was disabled;
- complete: an attended manual Start at 17:29 on 2026-08-03 recovered the same network, both paired devices and states, MQTT, availability, and Home Assistant discovery without re-pairing or an observed relay command;
- failed recovery observation: on 2026-08-05, a second Ember failure reset ASH, then failed EZSP startup with `HOST_FATAL_ERROR`; Zigbee2MQTT exited while Watchdog was enabled and no autonomous recovery was observed;
- failed recovery observation: on 2026-08-06, a third incident began with `ASH_ERROR_TIMEOUTS`; Supervisor Watchdog performed ten failed app restarts before stopping, while a later attended manual Start recovered normally;
- complete: second-floor Offline-to-Online availability recovery and power reconnection while configured OFF returned safely OFF;
- complete: a later Home Assistant restart retained both devices Online; the first-floor plug remained ON and the heat pump continued cooling;
- observed: first-floor electrical reports arrived asynchronously during inverter-compressor ramp-up, with a stabilized example of 804 W, 3.37 A, and 226 V; second-floor live measurements and increasing energy were also observed;
- boundary: plug measurements are trend data, not reference-meter calibration, electrical-protection inputs, or proof of heat-pump suitability;
- pending: Ember failure root-cause and bounded-recovery work, reference-meter comparison if needed, and both heat-pump nameplate/load-suitability verification.

### Heat Pumps manual controls

- complete: floors 1, 2, and 3 use the same six-card layout for temperature, humidity, switch state, live power, auto-off duration, and time remaining;
- complete: floor-1 and floor-2 auto-off helpers and automations match the safe floor-3 behavior;
- complete: duration `0` cancels the countdown without switching the plug and therefore remains manual mode;
- complete in working tree: each floor's dashboard shows an absolute local `Turns Off At` value derived from the timer instead of exposing the timer's `active`/`idle` state;
- complete: meaningless `New section` headings were removed;
- complete: the three floor sections were moved from Mission Control into the dedicated Heat Pumps view so the main screen is not duplicated or excessively wide;
- complete: the focused dashboard was deployed and visually verified; final supervised timer-expiry and reserve-guard validation remains;
- boundary: these are Home Assistant manual/auto-off household controls and do not enable EnergyHub Smart Thermal automatic starts.

### Water Systems dashboard and consumption history

User outcome: the electric boiler and basement water pump remain directly controllable and their energy use is understandable. Only the boiler participates in the 1.1 reserve-only OFF guard; the basement pump never does.

- complete in working tree: one Home Assistant Water Systems view with separate `2nd floor water Boiler Smart Power` and `Basement Water Smart Power` sections;
- complete: both Xiaomi devices' switch, power, current, voltage, daily/month energy, temperature, surge, indicator, and diagnostic entity IDs were inventoried;
- the boiler device visibly exposes Switch, Electric Power (`unit 0.01w`), Electric Current, Voltage, Energy Today, Energy Month, Temperature, Surge power, Indicator Light, and Info; validate units, scaling, state classes, and which diagnostic controls are safe to display before use;
- validate the plug rating, boiler nameplate, power-outage behavior, command/state synchronization, and suitability for the resistive load;
- expand the basement water-pump device and capture the same entity inventory, then validate pump nameplate, motor starting surge, smart-plug rating, power-outage behavior, and command/state synchronization;
- complete in working tree: each water device shows switch state, live power, and unavailable state; daily/weekly/monthly graphs use locally integrated energy rather than unreliable Xiaomi cloud counters;
- prefer a native monotonic energy entity with Home Assistant long-term statistics; if the plug exposes only power, create an integration sensor and daily/weekly/monthly utility meters with documented reset behavior;
- complete in working tree: a separate Heat Pumps view shows switch, live power, auto-off controls, and daily/weekly/monthly graphs using the two Zigbee cumulative-energy sensors and locally integrated third-floor watts;
- keep the dashboard controls manual; the separate reserve guard may only request OFF and never interprets the dashboard as permission to start a load;
- classify the basement pump as a critical infrastructure load by default: do not apply boiler or heat-pump SOC thresholds until water-system consequences and safe motor switching are explicitly validated.

Pending supervised Home Assistant validation:

- confirm both new views render correctly on desktop and mobile;
- confirm every tile reports expected values and manual toggles affect only the selected plug;
- confirm daily, weekly, and monthly `change` statistics for the Zigbee cumulative entities and new locally integrated Xiaomi energy sensors;
- compare locally calculated Xiaomi energy against reasonable load/runtime estimates and the Xiaomi app as trend validation, without treating cloud history as calibration;
- treat the currently unavailable floor-1/floor-2 Zigbee entities as an operational dependency issue, not a dashboard defect.

### Reserve-aware flexible-load shedding

EnergyHub 1.1 implements a deliberately narrow Home Assistant reserve guard. It never turns a protected load on and does not claim Smart Thermal ownership.

Implemented boiler policy:

- normal shed threshold: 50% SOC;
- recovery threshold: 60% SOC clears the lockout but never turns the boiler on;
- a homeowner manual-ON override between the normal shed and emergency thresholds may continue temporarily;
- emergency threshold: 40% SOC; force OFF and lock out further dashboard ON requests until a validated recovery threshold is reached;
- below the emergency threshold, UI lockout is best-effort rather than an absolute physical guarantee when Home Assistant, the integration, or the plug is unavailable.

Implemented heat-pump policy:

- fully trusted grid conditions use a 50% all-floor OFF lockout and clear it at 60%;
- every degraded, missing, stale, or unavailable grid-confidence input selects the conservative policy;
- conservative shedding requests all running floors OFF at 80%, then floor 2 at 70%, floor 1 at 60%, and floor 3/all floors at the 50% lockout;
- the conservative lockout clears at 90%; recovery never turns a heat pump on;
- below the active lockout threshold, reject new manual heat-pump ON requests and force observed ON plugs OFF, subject to command availability;
- while confirmed Hybrid Charging or Hybrid Grid Hold is grid-backed and telemetry is fresh, temporarily permit manual heat-pump requests without clearing the remembered SOC lockout; end the permission and re-enforce the latch when Hybrid or current grid power is lost;
- mains interruption is emergency reserve shedding, not normal heat-pump regulation; heat-pump nameplate/load suitability remains a required validation item.

Automatic early starts must use sustained net surplus, not PV generation alone:

```text
dependable_surplus =
    conservative_pv_power
    - house_load
    - battery_recovery_allowance
    - uncertainty_margin
```

A reported 1 kW of PV may still be a deficit when the house is consuming more than 1 kW. An early start before the normal SOC restoration threshold requires fresh data, a safe projected reserve, sustained surplus or an explicitly allowed partial-surplus policy, adequate remaining forecast energy, device demand/eligibility, and sufficient expected runtime. Start flexible loads sequentially and reevaluate after each measured load response.

The current guard needs only observed state, one-shot shed actions, an emergency lockout, and unknown/unavailable handling. Restart recovery must never infer permission to start from SOC alone.

### Smart Thermal Load Controller — deferred to 1.5

User outcome: EnergyHub can decide whether one registered thermal load may run without compromising comfort, battery reserve, or homeowner control.

Future controller inputs:

- registered load capability and measured or expected power;
- room temperature and comfort band;
- battery SOC and protected reserve;
- solar surplus or cheap-tariff eligibility;
- grid availability/confidence and relevant forecast context;
- current switch state, availability, and manual override.

Future controller requirements:

- a pure decision service separated from Zigbee/Home Assistant command execution;
- explicit statuses and reasons for every start, continue, stop, and skipped decision;
- minimum runtime and cooldown protection;
- an ownership marker so EnergyHub stops only a load it started;
- bounded behavior when telemetry, MQTT, Home Assistant, or the smart plug is unavailable;
- restart reconstruction without blindly toggling the load;
- automatic control disabled by default and enabled only for staged validation;
- unit tests before any unattended real-load run.

Initial controller non-goals:

- multi-room optimization;
- direct coordinator control from EnergyHub;
- vendor-specific policy in the decision service;
- EV charging implementation;
- production claim for Smart Thermal Energy.

### Telemetry anomaly framework

Current Battery Health detects low SOC and ≥2% jumps below 95%, but calculations still need a general plausibility policy.

Design:

- quality flags per telemetry sample;
- plausible rate-of-change checks;
- quarantine of suspicious values from accounting;
- separate warning from control inhibition;
- configurable hardware-specific limits.

### Grid Import validation

- compare estimated import against external meter or smart plug data;
- test daytime Panic with simultaneous PV;
- determine whether full house load during SUB overestimates grid contribution;
- avoid replacing one known approximation with an unvalidated subtraction formula;
- preserve explicit non-billing-grade labelling.

### Panic policy review

The current code uses Grid Confidence, SOC, and forecast sufficiency. Review whether a live PV power gate should be restored and, if so, whether it should use a fixed threshold, forecast trend, or net energy state.

### Notification improvements

- optional transition completion message for manual requests;
- configurable notification channels;
- concise family message plus technical detail link;
- deduplication and severity policy.

## EnergyHub 1.2 — Configuration

- configuration schema and validation;
- migration from hard-coded defaults;
- Home Assistant configuration dashboard;
- safe reset to known defaults;
- policy profile export/import;
- separation of hardware limits and strategy preferences.

## EnergyHub 1.3 — Recovery & Resilience

- classify MQTT connection failures;
- classify network and DNS failures;
- classify serial lock, timeout, and malformed response failures;
- bounded adapter retries;
- process-level heartbeat;
- missed schedule recovery;
- HA-unavailable behavior;
- delayed retained-input behavior;
- external watchdog;
- recovery test matrix.

## EnergyHub 1.4 — Remote Access & Telegram

- Cloudflare Tunnel deployment and security review;
- WireGuard backup;
- Telegram bot authentication;
- `/status`, `/health`, `/mode`, `/forecast` commands;
- alerts for offline, transition failure, low reserve, and Panic;
- optional approved mode commands with Autopilot checks;
- audit trail.

## EnergyHub 1.5 — Smart Thermal Energy

### Requirements

- build the first automatic Smart Thermal controller on the validated 1.1 device and reserve-guard foundation;
- capability registry for heat pumps and smart plugs;
- room temperature and humidity inputs;
- comfort bands;
- SOC start/stop bands;
- surplus/cheap-tariff eligibility;
- minimum runtime;
- cooldown;
- ownership marker;
- manual override;
- multiple-load priority;
- restart reconstruction;
- notification policy.

### Research

- real heat-pump power curves;
- effect of inverter modes on available surplus;
- best thermal storage periods by season;
- preheating/precooling value;
- room-specific comfort priorities.

## Technical debt

### `main.py` lifecycle size

Do not perform a broad refactor before tests. Later candidates:

- request processor;
- strategy target monitor;
- startup reconstruction coordinator;
- notification coordinator;
- periodic task scheduler.

### Duplicated constants

Centralize battery capacity, targets, time windows, safety factors, and mappings as part of 1.2 configuration rather than creating a second temporary constants layer.

### Graceful shutdown

Add explicit process shutdown handling and final persistence where useful. Home Assistant add-on termination currently relies on normal process/container behavior.

## Documentation maintenance

After each release milestone:

- compare documentation with code and live HA configuration;
- update project state and changelog;
- preserve historical decisions;
- remove current-state contradictions;
- regenerate architecture visuals only when the architecture changes materially.

## Backlog rule

A backlog item should state:

- user outcome;
- current limitation;
- owner/service boundary;
- safe behavior;
- validation method;
- target milestone.
