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

EnergyHub 1.3.1 supersedes the fixed 20% + 10% reserve terms with a visible
20–50% minimum SOC setting. A first 300 W forecast followed by at least 600 W
earns one verified hour of ramp credit; the original threshold remains retained
for decision audit.

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

Status: the 1.3.0 fallback uses the explicit 17/24 aligned-load projection, hourly post-07 Solcast sum, 16 kWh battery model, and 90% conservative efficiency. EnergyHub 1.3.2 additionally learns the 07:00–12:00 essential-load profile from measured history after subtracting heat-pump energy; broader full-day and weather-sensitive profiling remains future work.

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

### Smart Thermal Load Controller — deferred to 1.4

User outcome: EnergyHub can decide whether one registered thermal load may run without compromising comfort, battery reserve, or homeowner control.

Future controller inputs:

- an independently selectable participation flag for each heat pump, with the
  first-floor heat pump proposed as the default participant and the other
  floors opt-in;
- registered load capability and measured or expected power;
- room temperature and comfort band;
- battery SOC and protected reserve;
- solar surplus or cheap-tariff eligibility;
- grid availability/confidence and relevant forecast context;
- current switch state, availability, and manual override.

Adaptive Hybrid coordination requirements:

- publish the selected participants and their planned post-07:00 run windows
  or duty cycles to the AHM calculation;
- exclude cheap-grid thermal energy scheduled before 07:00 from battery demand;
- add the aligned post-07:00 net thermal deficit for selected participants to
  the AHM target until forecast solar can carry the planned loads;
- validate provisional maximum planning rates of 1.5 kWh per running hour for
  floors 1 and 2 and 0.8 kWh per running hour for floor 3 before using them as
  authoritative coefficients;
- retain Panic as the recovery layer for forecast error, unexpected household
  demand, or thermal consumption above plan.

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

EnergyHub 1.3.8 starts with an SOC-only observer:

- persist jumps and short oscillations rather than losing the evidence on the
  next normal sample;
- record previous/current SOC, delta, interval, battery voltage/current, PV,
  load, grid, operating mode, freshness, process uptime, and recovery context;
- keep a bounded rolling history with latest-event and event-count diagnostics;
- distinguish top-of-charge behavior from mid-range jumps in the event data;
- do not infer battery degradation from SOC telemetry alone;
- do not reject a sample, inhibit control, send a command, or change an energy
  decision in this first observer.

Design:

- quality flags per telemetry sample;
- plausible rate-of-change checks;
- quarantine of suspicious values from accounting;
- separate warning from control inhibition;
- configurable hardware-specific limits.

### Reserve-relative flexible-load policy — target 1.3.9

Use the dashboard-selected 20–50% AHM minimum SOC as the homeowner-preference
baseline for flexible-load protection:

```text
normal shed / warning = selected minimum + 30 percentage points
mandatory OFF         = selected minimum + 20 percentage points
recovery / unlock     = selected minimum + 40 percentage points
```

This reproduces the current 50/40/60 boiler bands when the selected minimum is
20%, and shifts them to 60/50/70, 70/60/80, or 80/70/90 as the homeowner
selects a more conservative reserve. EnergyHub publishes the effective bands
as the single source of truth; Home Assistant, dashboards, and messaging
adapters must not duplicate the calculation.

Initial boundaries:

- boiler and explicitly participating heat pumps only; exclude the basement
  pump;
- sustained, fresh, plausible SOC is required before acting;
- between Normal and Mandatory, a confirmed manual request may run with a
  clear warning and a declared stop threshold;
- at Mandatory, request OFF and reject new ON requests while locked;
- at Recovery, clear the lockout without automatically restarting the load;
- Grid Confidence, grid loss, Panic, Peak Load Guard, telemetry uncertainty,
  device availability, compressor timing, and immutable safety limits may
  tighten or deny the baseline policy;
- grid-backed Hybrid permission remains explicit and cannot silently erase a
  remembered reserve lockout.

### Grid Import validation

- compare estimated import against external meter or smart plug data;
- test daytime Panic with simultaneous PV;
- determine whether full house load during SUB overestimates grid contribution;
- avoid replacing one known approximation with an unvalidated subtraction formula;
- preserve explicit non-billing-grade labelling.

Planned 1.3.11 accounting increment:

- classify estimated import into configured cheap and standard tariff periods;
- persist daily counters across restart and midnight rollover;
- expose daily, weekly, and monthly energy statistics for both classes;
- apply configurable prices for informational cost estimates;
- include the previous day's split and cost in the Telegram morning report;
- keep tariff accounting separate from later multi-window charging control.

### Panic policy review

The current code uses Grid Confidence, SOC, and forecast sufficiency. Review whether a live PV power gate should be restored and, if so, whether it should use a fixed threshold, forecast trend, or net energy state.

### Notification improvements

- optional transition completion message for manual requests;
- configurable notification channels;
- concise family message plus technical detail link;
- deduplication and severity policy.

## Post-1.3 configuration and supportability

### Validated settings and policy profiles

User outcome: a homeowner can choose understandable energy priorities without editing Python or weakening hardware safety.

- configuration schema, migration, validation, acknowledgement, persistence, reconciliation, and audit;
- immutable battery/inverter limits separated from homeowner strategy preferences;
- Home Assistant Settings view with effective-value and decision previews;
- `Resilience`, `Balanced`, and `Economy` profiles;
- profile-controlled reserve preference, forecast margin, tariff flexibility, export willingness, and flexible-load permissions;
- emergency SOC floors, stale-data inhibition, unsupported commands, and hardware limits remain invariant;
- safe reset and profile export/import.

Validation: unit-test every profile at Grid Confidence boundaries and verify that no profile can cross a hardware or emergency limit.

### Generic tariff schedule

User outcome: EnergyHub can use the household's actual low-cost periods rather than assuming that every installation has one night window.

- represent one or more fixed tariff intervals per day;
- handle intervals crossing midnight, timezone changes, and daylight-saving transitions;
- publish the active interval and next eligible interval;
- keep EnergyHub 1.3's current night window as the migration default;
- do not treat a missing or malformed schedule as free electricity.

### Forecast quality and fallback

User outcome: an internet or forecast-provider problem produces visible conservative behavior rather than an optimistic plan.

- persist the last complete hourly forecast with target date and retrieval time;
- classify forecast input as fresh, stale-but-applicable, incomplete, expired, or unavailable;
- allow a same-date stale forecast only with a documented conservative haircut or reserve margin;
- never reuse a forecast for the wrong date as tomorrow's plan;
- fall back to a conservative historical/seasonal baseline or no dependable forecast solar;
- expose source, age, coverage, quality, and fallback reason in Home Assistant.

### Support bundle, replay, and shadow mode

User outcome: unexpected decisions can be reproduced without sharing secrets or writing to hardware.

- sanitized version, hardware, capability, configuration, telemetry, forecast, tariff, Grid Confidence, controller-state, decision, transition, and error snapshot;
- automatic redaction of credentials, network identities, precise private paths, and device identifiers;
- normalized replay input accepted by decision tests;
- shadow mode that publishes proposed actions but performs no inverter or load writes;
- requested, ACK-confirmed, read-back-confirmed, duplicate-avoided, and failed inverter-write counters.

### Recovery and dependency health

- classify MQTT connection failures;
- classify network and DNS failures;
- classify serial lock, timeout, and malformed response failures;
- bounded adapter retries;
- process-level heartbeat;
- missed schedule recovery;
- Home Assistant-unavailable behavior;
- delayed retained-input behavior;
- external watchdog;
- recovery test matrix.

## Messaging and remote access

User outcome: the homeowner can receive concise alerts and request status through a preferred secure messaging provider without moving EnergyHub control into the cloud.

Current foundation: Telegram Family Assistant 0.1.6 sends a morning energy/weather plan, debounced grid-loss and recovery events, Grid Confidence changes, and centralized AHM reserve advice. It is outbound-only and cannot execute Home Assistant commands.

- provider-neutral messaging interface;
- Telegram as the first candidate adapter, without making Telegram the permanent product boundary;
- future WhatsApp, Signal, Matrix, or other adapters only where supported authentication and API terms permit them;
- read-only `/status`, `/health`, `/mode`, `/forecast`, `/tariff`, and `/reserve` capabilities first;
- begin inbound experimentation with authenticated Ukrainian/English text;
- add Ukrainian/English voice only after text intents, authorization,
  confirmation, audit, device-state acknowledgement, and bounded durations are
  reliable;
- store a language preference per authorized family member or detect the
  current message language, and reply in the same language where unambiguous;
- map Ukrainian and English household phrases to fixed registered aliases,
  never to arbitrary Home Assistant entity IDs;
- echo every voice-derived action with the interpreted device and duration and
  require confirmation before execution;
- health, outage, anomaly, forecast-fallback, strategy-transition, and low-reserve alerts;
- notification severity, deduplication, quiet hours, and rate limiting;
- authenticated identities, role-based authorization, explicit Autopilot checks, and an audit trail before any remote command;
- Cloudflare Tunnel deployment/security review and WireGuard backup for remote Home Assistant access.

Messaging and voice assistants submit requests. They never decide whether a hardware action is safe.

### Shared intent gateway

User outcome: dashboard, Home Assistant automation, voice, and messenger requests use the same understandable EnergyHub vocabulary and receive the same safety decision.

- define a versioned structured intent envelope with requester, source, intent, parameters, creation time, expiry, correlation ID, and optional confirmation state;
- begin with read-only intents such as status, health, mode, forecast, tariff, reserve, and explanation of the last decision;
- add only bounded, explicitly authorized control intents after authentication, audit, Autopilot, freshness, reserve, and hardware-limit checks exist;
- translate natural-language Telegram and future Home Assistant Assist input into the structured contract before evaluation;
- respond with EnergyHub's interpretation and `allow`, `shorten`, `delay`, `deny`, or read-only result; ambiguous input performs no hardware action;
- publish intent-level outcomes rather than exposing MQTT topic names, entity IDs, PI30MAX commands, or internal service boundaries;
- keep transport adapters replaceable so Telegram is the first adapter, not the product architecture.

Target: the shared intent contract belongs with 2.0 Conversational EnergyHub; a native Home Assistant integration remains later 2.x/3.0 ecosystem work.

### Future native Home Assistant integration

- expose human-readable events such as Grid became unstable, Grid risk detected, Panic mode started, reserve target reached, solar surplus available, and return to Solar;
- support purpose-specific triggers and conditions such as `When EnergyHub enters Panic mode` and `When grid reliability becomes Risk`;
- keep Hybrid, Panic, Grid Confidence, recovery, reserve, and flexible-load policy inside EnergyHub rather than reproducing it in Home Assistant automations;
- use current Home Assistant terminology and modern automation syntax whenever README examples or sample automations are refreshed.

## Flexible Energy and EV charging

### Capability-based Load Manager

- capability registry for heat pumps, boiler, EVSE, and future loads;
- observed/expected power, availability, command/state confirmation, and power-on behavior;
- priority, hysteresis, minimum runtime, minimum off-time, cooldown, and sequential starts;
- explicit EnergyHub ownership marker and restart reconstruction;
- comfort, hot-water, departure, and homeowner-override requirements;
- base household load separated from EnergyHub-controlled flexible energy;
- conservative behavior when telemetry, Home Assistant, messaging, or the device is unavailable.

### Smart Thermal research and validation

- real heat-pump power curves;
- effect of inverter modes on available surplus;
- best thermal storage periods by season;
- preheating/precooling value;
- room-specific comfort priorities;
- staged observer mode before automatic starts.

### Inverter Fault Diagnostics and Adaptive Overload Protection

User outcome: EnergyHub preserves enough evidence around a warning, fault, or
unexpected inverter restart to explain what happened and later prevent a
repeat by shedding explicitly participating flexible loads safely.

Current verified foundation:

- EnergyHub reads PI30MAX `QPIWS` every 60 seconds and publishes active warning
  names through Inverter Health;
- QPIWS represents current warning bits, so a short event can disappear before
  the next scheduled read;
- a recent inverter restart is suspected to be load-related, but the exact
  cause and load boundary are not established by retained evidence.

Phase A — diagnostics only:

- investigate a shorter or event-prioritized QPIWS interval without starving
  normal PI30MAX telemetry or increasing serial contention;
- detect and latch warning transitions, especially `0 → 1`;
- persist a bounded fault/event history across EnergyHub and Home Assistant
  restarts;
- keep a bounded in-memory pre-event telemetry ring so the snapshot includes
  conditions before communication loss or inverter restart;
- record timestamp, warning/fault identity, inverter load W and %, battery SOC,
  voltage/current, grid state, PV, operating mode/source priority, controlled
  loads observed ON, telemetry freshness, and process/recovery context;
- expose Current Fault, Last Fault, Last Fault Time, Last-Fault Snapshot, and
  recent event history for diagnostics and Mission Control;
- perform no automatic load or inverter action in this phase.

Read-only hardware research:

- confirm whether POW-HVM10.2M Menu 25 / Record Fault Code is enabled and what
  it means on the installed firmware;
- treat the community-reported Modbus register 4530 Error Code as an unverified
  lead until a bounded read-only probe returns meaningful repeatable data;
- compare any result with the inverter display, QPIWS, and a known observed
  event before documenting support;
- keep PI30MAX and Modbus capabilities separate;
- never write register 4530 or any undocumented Modbus register.

Phase B — observation and calibration:

- collect real continuous load, startup peaks, warnings, faults, and restart
  evidence;
- determine whether tolerable power and duration differ under battery/Solar,
  Hybrid, grid/bypass, charging, and outage operation;
- establish whether a warning reliably precedes shutdown;
- derive preventive and emergency limits with margin from evidence rather than
  the theoretical 10.2 kW rating;
- retain uncertainty explicitly when the event sample is incomplete.

Phase C — Dry Run:

- publish which participating load would be shed, why, the observed load, the
  proposed threshold, and the expected reduction;
- execute no physical switch command;
- compare decisions with several days or weeks of real operation and faults;
- reject promotion when telemetry, load ownership, device suitability, or
  thresholds are not trustworthy.

Phase D — attended then automatic protection:

- preventive shedding uses a sustained threshold below the proven boundary;
- emergency shedding responds to a verified overload warning or rapid
  excessive load under separately tested rules;
- shed one configurable, explicitly opted-in load at a time, confirm observed
  OFF/power reduction, wait for stabilization, and reevaluate;
- restore only loads owned or paused by the guard, one at a time, with
  hysteresis, minimum ON/OFF time, compressor cooldown, inrush allowance, and
  explicit restoration permission;
- a smart-load communication failure is a failed protection action and never
  authorizes an inverter command or an assumption that demand fell;
- manual override remains available within immutable electrical, reserve, and
  emergency boundaries;
- the basement pump and every non-participating critical load remain excluded.

Mission Control should eventually explain, for example:

```text
Boiler disabled — overload protection
Load before action: 8.9 kW
Protection threshold: 8.5 kW
Next eligible restore: 14:42
```

Target: EnergyHub 1.4 begins with Phase A. Later 1.4.x stages require their own
repository, attended hardware, Dry Run, and monitored release evidence.

### Smart Thermal Peak Load Guard

User outcome: keep short periods of high household power from becoming an
uncontrolled inverter, battery, or grid-loading event by temporarily pausing
explicitly opted-in flexible thermal loads.

This is a demand/power controller measured in kW, not an accumulated-energy
controller measured in kWh. It supplements rather than replaces inverter,
battery, cable, breaker, plug, and appliance protection.

Proposed research policy, not approved production thresholds:

- consider shedding only after total house power remains above 6.0 kW for a
  sustained 20-30 second window;
- first pause the electric water boiler, and only when its measured draw is
  above an idle/noise threshold provisionally set near 100 W;
- remeasure after every confirmed command before considering another load;
- if demand remains high, pause one opted-in heat pump at a time in the
  provisional order: second floor, first floor, then third floor;
- begin restoration only after total house power remains below 5.0 kW for a
  sustained 3-5 minute window;
- restore one load at a time with a post-start observation delay;
- restore only a device that the guard actually paused and whose recorded
  pre-shed state and restoration policy permit automatic restart;
- never shed the basement water pump or another critical/non-opted-in load;
- treat unavailable power/state telemetry or an unconfirmed switch command as
  a failed action, not as a successful reduction.

The final trigger, release, dwell, maximum-off, and per-operating-mode values
must be selected from recorded load, inverter-fault, and appliance evidence. Grid,
battery, Solar, Hybrid, Panic, and outage operation may require different
limits; a single 6/5 kW pair must not be assumed universally safe.

Each load capability must record:

- exact switch and power entities plus availability semantics;
- criticality and shedding/restoration priority;
- active-power threshold and expected power reduction;
- plug rating, appliance rating, inrush/start behavior, and suitability for
  mains interruption;
- minimum runtime, minimum off-time, compressor cooldown, and maximum temporary
  off-time;
- command acknowledgement/state confirmation and bounded retry behavior;
- power-on behavior after plug, Home Assistant, EnergyHub, or host restart;
- ownership, pre-shed state, active manual override, and restoration permission;
- comfort/hot-water constraints and hard reserve/operating-mode exclusions.

Required delivery stages:

1. collect load history and complete the capability/safety inventory;
2. run observer mode for several days and publish proposed actions/reasons;
3. validate boiler-only attended shedding and restoration;
4. validate each heat pump individually with compressor-safe timing;
5. enable sequential automatic shedding;
6. enable conservative sequential restoration;
7. integrate the guard with later solar-, tariff-, comfort-, and
   forecast-aware Smart Thermal scheduling.

Explanations should distinguish states such as `Peak Load Guard`, `Waiting for
minimum runtime`, `Cooldown`, `Manual override`, `Unavailable`, and `Restoring
after demand recovery`.

Target: EnergyHub 1.4 Smart Thermal. The 6.0/5.0 kW values and provisional load
order remain discussion inputs until explicitly approved.

### Solar-first EV charging

User outcome: the EV receives the maximum practical direct-solar energy without silently consuming protected household reserve.

- connection state, EV/EVSE availability, present power, minimum/maximum current, and phase capabilities;
- requested energy or target SOC and departure deadline;
- `Solar Surplus`, `Smart Schedule`, `Immediate`, and `Paused for Reserve` states;
- sustained dependable surplus rather than raw PV power;
- optional low-price tariff completion when forecast solar cannot meet the departure target;
- no household-battery discharge into the EV unless explicitly enabled;
- EV charging excluded from learned base household consumption;
- direct control only after EVSE validation, with evcc coordination preferred where it already owns the charger safely.

### Time-bounded manual override evaluator

User outcome: a homeowner can ask through the dashboard, automation, voice, or messaging to run a flexible load temporarily and receive an explainable safe answer.

- evaluate telemetry freshness, current and projected SOC, grid availability, Grid Confidence, load energy, active strategy, tariff, solar, other loads, and immutable emergency limits;
- respond `allow`, `shorten`, `delay`, or `deny` with a reason and projected outcome;
- record requester, source, load, start, expiry, energy budget, and interrupt conditions;
- terminate an override when grid loss or reserve decline crosses the applicable hard boundary;
- never justify a risky request by assuming that Panic can charge from a grid that may be unavailable.

## Economic planning and Net Billing

User outcome: EnergyHub can decide when to consume, store, import, or export energy using the actual tariff contract while preserving outage reserve.

- day-ahead import and export price ingestion in arbitrary 15/30/60-minute intervals;
- currency, timezone, DST, data completeness, source, and freshness normalization;
- supplier markup, taxes, distribution charges, settlement periods, export compensation caps, and negative-price behavior;
- Net Billing rules and separate import/export meters;
- expected load, flexible load, solar, charge, discharge, import, export, SOC, cost, revenue, and reserve per interval;
- battery efficiency, charge/discharge power, optional wear allowance, and export limits;
- protected reserve and hardware capability as hard constraints;
- planned-versus-actual cost/revenue and forecast-error reporting;
- replanning after material tariff, forecast, load, grid, or device changes;
- staged delivery: monitoring, visualization, shadow plan, attended import, bounded automatic import, export shadow mode, attended export, then separately validated automatic export.

## Inverter and transport ecosystem

User outcome: additional inverters can reuse EnergyHub policy without treating similar RS232 commands as proof of safe compatibility.

- normalized capability model between policy and hardware control;
- separate model adapter from communication transport;
- model/firmware fingerprint, telemetry queries, write commands, supported values, strategy mapping, ACK semantics, read-back semantics, limits, and recovery capabilities;
- unknown models default to telemetry-only and shadow decisions;
- validate additional PowMr models before broader Voltronic-compatible PI30/PI30MAX claims;
- validate USB-RS232, Solar2MQTT, ESPHome, or other transports independently from model support;
- require raw capture, read-only validation, shadow decisions, attended commands, failure testing, restart reconstruction, and compatibility documentation before automatic writes;
- consider Deye, GoodWe, Victron, Solax, and other families only after the capability boundary is stable.

### PowMr 10.2M Modbus PV2 telemetry

User outcome: expose both PV arrays separately and derive trustworthy total PV
without depending on unsupported `QPIGS2`.

- live read-only verification completed on 2026-08-14: slave 5, function 03,
  2400 baud, byte-swapped holding registers 4563 (PV2 voltage, 0.1 V) and 4564
  (PV2 power, W);
- complete: optional Modbus reads use the same adapter-owned serial lock as
  PI30MAX;
- complete: CRC, ranges, freshness, restart, timeout, malformed response, and
  unsupported-firmware behavior have regression coverage;
- complete: PV2 health and Total PV are published only from fresh component
  samples;
- complete: high-production, full-battery/curtailed, nighttime, and
  homeowner-observed daylight chart behavior were validated; a separate
  medium-production sample is useful but not a release blocker;
- complete: every undocumented Modbus write remains disabled;
- pending: 2–3 days of private monitoring before public promotion.

Target: EnergyHub 1.3.5.

### PowMr dual-output research

User outcome: eventually manage the inverter's second load output from Home
Assistant through safe EnergyHub intents rather than raw register access.

- the PowMr manual confirms dual-output enable/disable, exit thresholds, and a
  3400 W maximum second load in battery mode for the 10.2 kW model;
- no trustworthy register mapping or read-back contract is verified yet;
- first capture and verify read-only state/settings, then build shadow-mode HA
  behavior and immutable power/reserve limits;
- allow an attended write experiment only after exact frames, accepted ranges,
  read-back, rollback, and recovery are independently established;
- never expose raw Modbus writes to Home Assistant, messaging, voice, or AI.

Target: research after PV2 telemetry integration; control remains unplanned
until the safety contract is verified.

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
