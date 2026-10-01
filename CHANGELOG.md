# Changelog

## [EnergyHub 2.4.12 / Family Assistant 2.4.15] - 2026-10-01 (monitored candidate)

Close the 2.x candidate with continuous forecast/weather/grid-informed Battery
Reserve, guarded overload/outage load control, family-owned heating settings,
and Telegram briefings. Correct persistence uncertainty before inverter writes,
family OFF intent eviction, timer expiry/pause, missing-device snapshots,
numeric MQTT states and delayed fault wording. Both apps started on 2026-09-29;
the homeowner reports the agreed monitoring window passed with no new Core or
Supervisor errors. Public promotion is prepared separately. Cold-weather
heating and rare negative cases remain explicitly unverified on hardware.

See [EnergyHub notes](RELEASE_NOTES_2.4.12.md),
[Family notes](RELEASE_NOTES_FAMILY_2.4.15.md), and
[validation](docs/validation/RELEASE_2.4.12.md).

## [EnergyHub 2.4.10 / Family Assistant 2.4.13] - 2026-09-26 (private candidate)

Apply one 20-point solar-deficit reserve allowance, align the beacon color
boundary with 40% battery protection, clarify DTEK/solar charging and Grid
Hold messages, improve overnight reserve and UHMC morning summaries, and
exclude solar-only hold SOC gain from the estimated grid-import battery
component. Replace forbidden Supervisor log requests with Core's existing API. No live
deployment, public release, or Xiaomi Miot integration change is included.

## [2.4.9 / Family 2.4.11] - 2026-09-22 (prepared corrective candidate)

Correct overload acknowledgement and ownership, separate online availability
from unchanged watts, and preserve both trigger and post-action load evidence.
The 08:00 technical report now measures a rolling 24-hour window, masks parent
outages from child devices, applies meaningful HA/inverter/Zigbee thresholds,
and deduplicates Core plus Supervisor warnings. See
[release notes](RELEASE_NOTES_2.4.9.md).

## [2.4.8 / Family 2.4.10] - 2026-09-22 (private corrective candidate)

Make official weather reserve independent of current Grid Confidence, add a
prominent dashboard Grid Confidence panel and larger mission-control buttons,
pair Zigbee2MQTT offline/recovery notices at two minutes, and improve compact
morning weather/solar presentation. Family notifications
now preserve actionable UHMC wording and combine DTEK confidence transitions
with the confirmed or pending Battery Reserve reaction. See
[release notes](RELEASE_NOTES_2.4.8.md).

## [2.4.7 / Family 2.4.9] - 2026-09-21 (private corrective candidate)

Derive Zigbee plug availability from their existing Home Assistant switch
entities, ignore retired input topics without startup noise, and present morning
control ownership as clean Automatic and Manual groups. Future Smart Heating
assigns only the first-floor heat pump to EnergyHub. See
[release notes](RELEASE_NOTES_2.4.7.md).

## [2.4.6] - 2026-09-21 (private corrective candidate)

Separate Zigbee device availability from unchanged plug watts while retaining
strict command acknowledgement and post-command verification. Document global
Zigbee2MQTT availability as the online/offline authority and add bounded online
telemetry diagnosis/recovery to the 3.x roadmap. See
[release notes](RELEASE_NOTES_2.4.6.md).

## [2.4.5 / Family 2.4.8] - 2026-09-20 (private candidate)

Remove retired night-planning and reserve-advisor artifacts, align dashboard
sensor lineage, keep last-known overload watts visible with honest freshness,
and streamline family/restart messages. The private 08:00 technical report now
includes a deduplicated 24-hour HA Core warning/error digest. See
[release notes](RELEASE_NOTES_2.4.5.md).

## [2.4.3 / Family 2.4.6] - 2026-09-19 (private corrective candidate)

Simplify Smart Heating to Normal, Quiet and Eco with owned 40/50 SOC pause and
recovery; correct EV/forecast reporting; move tariff detail to weekly/monthly
summaries; add morning grid-support estimates; and reduce MQTT/Recorder churn
without slowing the control loop. See [release notes](RELEASE_NOTES_2.4.3.md).

## [Family 2.4.5] - 2026-09-14 (private corrective candidate)

Keep the family chat silent overnight, summarize collected events in the 08:00
report, suppress repeated Grid Hold messages within one reserve episode, use a
short current Grid Hold status, and show the current month's night/normal tariff
split. EnergyHub remains 2.4.2. See
[Family release notes](RELEASE_NOTES_FAMILY_2.4.5.md).

## [Family 2.4.3 / HA cleanup] - 2026-09-13 (private corrective candidate)

Remove retired 23:50 Low-Tariff, 06:05 Early Solar, and morning-learning
automations and their obsolete Home Assistant notification branches. Preserve
23:49/23:51 accounting and 23:52/05:00 Battery Reserve forecast updates. Replace
Family Assistant Dry Run and Effective Reserve presentation with current
Battery Reserve and confirmed protection terminology. Includes the corrected
quoted Smart Heating schedule. See
[release notes](RELEASE_NOTES_FAMILY_2.4.3.md).

## [Family 2.4.2] - 2026-09-13 (private corrective candidate)

Correct the optional technical-chat option migration and add paired family
messages for reaching minimum Battery Reserve Grid Hold and returning to Solar.
EnergyHub remains 2.4.2. See [Family release notes](RELEASE_NOTES_FAMILY_2.4.2.md).

## [2.4.2] - 2026-09-13 (private candidate)

Make load protection continue past unavailable or unconfirmed participants,
restore only confirmed EnergyHub ownership, add simplified beacon signalling,
and enforce Smart Heating Quiet mode from 23:00 through 07:00. Family Assistant
2.4.1 separates technical delivery and reports Grid Hold and confirmed appliance
actions more clearly. See [release notes](RELEASE_NOTES_2.4.2.md).

## [2.4.1] - 2026-09-12 (private corrective candidate)

Battery Reserve becomes the sole 24/7 reserve controller. The separate 23:50
night target, 06:05 early-Solar gamble, 07:00 ownership handoff, and morning
learning automations are retired. See [release notes](RELEASE_NOTES_2.4.1.md).

## [2.3.2] - 2026-09-12 (private candidate)

Add a preliminary next-day Battery Reserve plan at 23:52, a replacing 05:00
revision, and mode-aware dashboard controls. See
[release notes](RELEASE_NOTES_2.3.2.md).

## [2.3.1] - 2026-09-12 (private corrective candidate)

Recover completed consumption evidence stored with Home Assistant Unix
timestamps and make the family restart summary wait for current-boot state.
See [release notes](RELEASE_NOTES_2.3.1.md).

## [2.3.0] - 2026-09-12 (private candidate)

One additive Battery Reserve calculation, guarded Manual/Automatic authority,
one-to-three-day consumption evidence, and fixed 50/40/60 outage discharge
protection over schema 5. See [release notes](RELEASE_NOTES_2.3.0.md).

## [2.2.5] - 2026-09-09 (prepared, not deployed)

Shared battery/overload ownership, schema-4 HA boundary, actual-grid exception,
default 50/40/60 discharge thresholds and native first-floor HP stop. Family 2.2.6
uses confirmed battery-action messages. [Scope and gates](RELEASE_NOTES_2.2.5.md).

## [2.2.3] - 2026-09-08 (prepared)

Sequential 85/75/50 overload policy without mandatory watt allowances; five-minute
recovery, one-minute restore spacing, telemetry timeout notice. [Notes](RELEASE_NOTES_2.2.3.md).

## [2.2.1] - 2026-09-07 (private correction)

Single overload Automatic switch, production warnings-only mode and old trial
notification retirement. See [release notes](RELEASE_NOTES_2.2.1.md). Not deployed.

## [2.4.0-dev] - 2026-09-07 (parked, not installable)

Offline first-floor Smart Heating planner and scenario tests. Waits for 2.3;
no deployed-tree or app-version changes. See draft notes (private development record).

## [2.2.0] - 2026-09-07 (private candidate)

Opt-in acknowledged overload control and compact Family 2.2.0 notifications.
Default disarmed; Battery Reserve calculation unchanged. See [release notes](RELEASE_NOTES_2.2.0.md).

## [2.1.4] - 2026-09-06 (private corrective candidate)

Daytime manual Battery Reserve correction and compact UHMC warning messages in
Family 2.1.7. No automatic advisory control. See [release notes](RELEASE_NOTES_2.1.4.md).

## [2.1.3] - 2026-09-06 (private naming candidate)

Battery Reserve and clear strategy names, coordinated with Family Assistant
2.1.6. No control or Dry Run changes. See [release notes](RELEASE_NOTES_2.1.3.md).

## [2.1.2] - 2026-09-06 (private corrective candidate)

Manual Battery Reserve ownership and Family Assistant 2.1.5 condition-only advice.
See [release notes](RELEASE_NOTES_2.1.2.md).

All notable EnergyHub changes are recorded here.

## [2.1.1] - 2026-09-06 (private candidate)

- Harden the 40/30/20 observer-only Peak Load Guard with continuous 60-second
  recovery confirmation, a persisted 64-event journal, and stable cycle IDs.
- Freeze the first valid daily forecast at/after 05:00. Retain urgent weather
  and grid reevaluation without restarting the daily plan on every forecast.
- Separate Battery Reserve baseline and applied minimum; reject stale retained
  inputs and hold advised buffers when evidence becomes unknown.
- Require three recent end-of-day consumption samples for the deficit rule.
- Add a backend-locked OFF Battery Reserve Auto indicator; no new control path.
- Pair with Family Assistant 2.1.4 for journal delivery, one morning reserve
  recommendation, quiet-hour-aware target changes and safer UHMC parsing.
- Existing Hybrid/Panic control targets, morning monitoring and Threat Monitor
  are unchanged. No deployment, commit, push or publication is included.

## [2.1.0] - 2026-09-05

### Added

- Added an Effective Reserve Dry Run that evaluates today's Solcast forecast
  at 05:00 against the average of up to three newest valid completed
  consumption days.
- Added a 20-point forecast-deficit modifier, cumulative 0/20/40/60 Grid
  Confidence modifiers, conditional 20-point official UHMC Level II–III
  weather risk, and a 95% cap.
- Added persisted warning/update/cancellation/expiry handling, conservative
  Unknown source semantics, Manual/Advisory authority, dashboard evidence, and
  Ukrainian daytime and morning explanations.
- Assigned official `uhmc1921` preview ingestion and normalized retained MQTT
  evidence publishing to Telegram Family Assistant 2.1.2. Telegram Threat
  Monitor remains the independent 0.1.9 air-threat service.

### Changed

- Guarded the 23:49/23:51 Home Assistant Daily Summary publication against
  brief source-entity gaps. It now waits up to 90 seconds for numeric house
  consumption and aborts instead of converting `unavailable` to `0 kWh`.
- Temporarily lowered the observer-only Peak Load Guard profile to 40% trigger,
  30% relief, and 20% restoration for a one-week household Dry Run. Dashboard
  and Ukrainian Telegram explanations use the event's trial thresholds.
- Grouped the Peak Load Guard card with the Effective Reserve controls.
- Placed Heat Pumps and Appliances & Water daily/weekly/monthly charts in
  three-column rows and added current-week/current-month/current-year totals
  for every displayed load.
- Corrected Home Assistant smart-plug authority so calculated Grid Confidence
  `normal` always preserves family control. Brief instantaneous grid-voltage
  or telemetry transitions can no longer activate a remembered boiler or
  heat-pump reserve lockout while confidence remains Normal.

### Safety

- Version 2.1.0 never changes the selected AHM minimum, inverter settings, or
  smart plugs. Missing forecast evidence is not interpreted as clear weather.
- Automatic weather authority is deliberately deferred until Dry Run evidence
  has been reviewed.

## [2.0.0] - 2026-08-27

### Added

- Introduced the observer-only Peak Load Guard foundation using native
  inverter Load %, W, VA, and QPIWS overload-warning evidence.
- Added a retained Home Assistant participant snapshot for six explicitly
  listed smart plugs, a persisted recommendation cycle, MQTT status/event
  entities, and a Mission Control Dry Run card.
- Added Ukrainian Telegram notifications for shed, restore, and no-candidate
  recommendations. Every notification states that EnergyHub switched nothing.

### Behavior

- At 85% load, recommend smart plugs one by one in this order: water pump,
  water boiler, second-floor heat pump, first-floor heat pump, third-floor
  heat pump, and microwave. Include an ON plug even when its instantaneous
  power is zero, but do not count zero watts as estimated relief.
- Continue through the ordered list until observed participant power could
  reduce the triggering load toward 75%. Hold the cycle and recommend
  restoring the recorded pre-event states in the same order at 60%.
- Reject stale inverter telemetry and participant snapshots. Native overload
  warnings can start a cycle independently, and one warning episode creates
  at most one recommendation cycle.

### Safety

- Version 2.0.0 is Dry Run only. It contains no smart-plug switching path and
  adds no inverter command.
- The 85/75/60 policy is an explicit household trial configuration, not a
  proven hardware safety limit. Promotion to physical control remains gated
  by 1.3.10+ fault evidence, attended validation, acknowledgement, appliance
  timing, ownership, and conservative restoration.

## [1.3.14] - 2026-08-26

### Added

- Expanded the Water Systems dashboard into Appliances & Water with a
  first-floor microwave switch/live-power section, first-floor bathroom
  temperature/humidity, and locally integrated microwave consumption in the
  daily, weekly, and monthly charts.

### Fixed

- When Grid Confidence is Normal and Solar reaches the 20% reserve floor while
  the physical grid is absent, keep Solar unchanged and wait for grid return
  instead of requesting an unavailable Grid Hold transition.
- Reevaluate the same floor immediately when fresh telemetry confirms that the
  grid has returned.
- Transfer confirmed Hybrid Charging ownership to Panic Charging without
  rewriting the identical `SUB` + `SNU` settings.
- Reject non-finite PI30MAX numbers and out-of-range SOC before retained MQTT,
  control-state construction, or battery-health classification.
- Clear stale Panic ownership before non-Panic Hybrid writes and attempt Solar
  recovery when Hybrid or Panic Menu 01 entry fails.
- Close superseded inverter-message incidents consistently, preserve valid
  journal history when optional persisted fields are malformed, and constrain
  Home Assistant fault states to 255 characters.
- Use the same 180 V physical-grid threshold in Telegram and smart-load
  automations, reconcile heat-pump lockouts after startup, and preserve
  already-latched OFF enforcement when telemetry becomes stale.
- Persist a logical Telegram morning-report outbox before delivery, complete
  all app-option translations, and label an unevaluated AHM value as current
  rather than recommended.
- Clarify Mission Control PV1/PV2 diagnostics, SOC anomaly evidence, 48-hour
  grid availability, and non-billing-grade Grid Import; add live authority and
  remembered-lockout cards to the smart-load views.

### Safety

- The correction adds no new inverter command. It prevents a transition when
  its required energy source is unavailable and preserves all 1.3.13
  ownership, hysteresis, missed-AHM, and non-Normal behavior.
- Telegram Family Assistant joins the coordinated public release train at
  1.3.14. It remains outbound-only and gains no control capability.
- Telegram morning delivery is at-least-once because `sendMessage` provides no
  idempotency key; the persisted outbox narrows but cannot eliminate the rare
  crash-after-acceptance duplicate window.

## [1.3.13] - 2026-08-23

### Changed

- Replaced the unconditional 07:00 Solar request with an immediate daytime
  Panic ownership evaluation.
- Added Normal-grid 20%/30% hysteresis: enter Panic Grid Hold at 20% or below,
  preserve the battery while solar recovers it, and return to Solar at 30%.
- Transfer confirmed Hybrid Grid Hold ownership to Panic Grid Hold without
  rewriting the identical `SUB` + `OSO` inverter settings.
- Give the water boiler the same temporary trusted-grid manual permission as
  the heat pumps; remembered lockouts remain available if grid trust is lost.
- Use routine Daytime Reserve wording for Normal-grid hold/release events.
- Group Energy Statistics visually with blue PV1/PV2 series and pink
  night/normal Grid Import series, keep both tariff legend entries visible,
  center daily/weekly columns in their periods, and label the Mission Control
  aggregate as `Total Grid Import Est.`

### Safety

- A genuinely missed AHM target still overrides the Normal-grid cycle until
  recovered. Unstable/Risk/Panic targets remain 60/80/95%.
- Solar release requires present grid and fresh evaluated SOC. Offline or
  stale conditions never manufacture a release.
- EnergyHub does not turn any heat pump, water boiler, or basement pump on.
  The basement pump remains outside automatic shedding.

## [1.3.12] - 2026-08-22

### Fixed

- Kept expected `pv_loss_warning` transitions in the persistent diagnostic
  journal while excluding them from the current and latest-three Home
  Assistant dashboard entities.
- Skip PV-loss-only events when selecting the three visible incidents and
  retain every other message from a mixed QPIWS event.

### Safety

- This is presentation filtering only. It does not discard diagnostic
  evidence, change QPIWS polling, or add inverter or household-load control.

## [1.3.11] - 2026-08-22

### Added

- Added restart-safe, timezone-aware estimated Grid Import accounting for the
  `00:00–07:00` plus `23:00–24:00` night tariff and the `07:00–23:00`
  normal tariff.
- Added dedicated today, completed-yesterday, lifetime-statistics, and
  current-month MQTT sensors, including estimated UAH cost at initial prices
  of 2.50 UAH/kWh and 5.00 UAH/kWh.
- Expanded the existing daily, weekly, and monthly generation charts with
  night/normal Grid Import series and a compact current-month summary.
- Added Telegram Family Assistant 0.2.4 completed-yesterday tariff and
  current-month estimated import/cost reporting.

### Safety

- All tariff and cost results remain informational estimates. They do not
  represent billing-grade meter readings and never enter a control decision.
- Schema migration preserves the existing current-day total without guessing
  a historical tariff split; the first partial tariff day is not presented as
  a complete previous-day result.
- Fixed a heat-pump protection recovery race: reserve shed and critical
  lockout now require fresh telemetry and revalidate that Grid Confidence is
  not Normal or grid power is absent immediately before any plug command.

## [1.3.10] - 2026-08-21

### Added

- Added a persistent, bounded journal for named QPIWS active-set transitions,
  recovery time, and the preceding five minutes of inverter telemetry.
- Added retained Home Assistant MQTT entities for the current inverter message
  and the latest three incidents, including their contextual attributes.
- Added the latest three inverter messages to the EnergyHub Status dashboard.
- Added Telegram Family Assistant 0.2.2 previous-day inverter diagnostics with
  message name, load, operating mode, grid state, and observed clearance.

### Safety

- Diagnostics remain read-only and perform no inverter or household-load
  action. A cleared QPIWS message is not described as an automatic restart.
- Modbus register 4530 remains an unverified research lead and is not polled by
  the release runtime.

## [1.3.9] - 2026-08-20

### Added

- Added a bounded, persistent SOC anomaly journal for changes of at least five
  percentage points within five minutes, retaining electrical, operating-mode,
  freshness, restart, and communication-recovery evidence.
- Added Home Assistant MQTT diagnostics for the latest SOC anomaly and lifetime
  event count; the latest entity carries the full event as attributes.
- Added Telegram Family Assistant 0.2.1 monitoring for seven Xiaomi
  temperature/humidity sensors, same-hour previous-day and indoor-median
  anomaly checks, recovery reporting, verified sensor batteries, and an
  optional Xiaomi doorbell battery warning in the 08:00 report.
- Added suspected-offline detection when both readings remain unchanged for 24
  hours and collapsed repeated recovery history to one detailed line per
  sensor.

### Safety

- SOC anomalies remain evidence only: they do not reject telemetry, inhibit a
  decision, change inverter mode, switch a load, or send a Telegram alarm.
- Environmental and device-battery warnings are outbound-only and never
  become control inputs.
- Missing, unknown, unavailable, and stale device states are never converted
  to numeric zero or used as peer measurements.

## [1.3.8] - 2026-08-18

### Added

- Added continuous enforcement of the dated Adaptive Hybrid target from the
  23:50 evaluation until the confirmed morning Solar handover.
- Added reserve-relative heat-pump protection from the selected AHM minimum:
  one-time shed at minimum +30, mandatory lockout at minimum +20, and recovery
  at minimum +40 percentage points while the grid is not trusted.
- Added Telegram Family Assistant 0.1.9 morning ownership guidance and
  downward-crossing SOC warnings at minimum +30, +20, +10, and the minimum.

### Changed

- Give the family normal manual heat-pump control while Grid Confidence is
  Normal, the grid is physically present, and EnergyHub telemetry is fresh.
- Preserve the evaluated night target and its dated enforcement context across
  EnergyHub restarts.
- Deliver reserve warnings only while at least one configured heat pump is
  drawing more than the configured activity threshold; name every active floor
  and observed power, and defer reserve delivery through 08:01.

### Safety

- At the exact night target, Hybrid enters Grid Hold; below the target it uses
  Hybrid Charging and the existing ACK-confirmed transition path.
- Missing or stale SOC produces no inverter or smart-plug command. If the grid
  is absent, night enforcement remains observational and retries only after a
  later fresh, grid-present evaluation.
- A failed night transition is not retried on every telemetry poll; the same
  unchanged request remains latched until its condition clears or the grid
  state changes.
- EnergyHub never turns a heat pump on. Telegram remains outbound-only and
  cannot execute Home Assistant or inverter commands.

## [1.3.7] - 2026-08-15

### Added

- Added one guarded 06:05 Early Solar handover check while Adaptive Hybrid is
  in Grid Hold.
- Added separate MQTT diagnostics for the check result, reason, evaluation
  time, live aligned Total Solar, and the 06:00-07:00 forecast interval.
- Added dashboard visibility and an updated Adaptive Hybrid infographic.

### Changed

- Present the post-startup Hybrid state as `awaiting_evaluation` with a clear
  explanation of the retained target, when available, and the next scheduled
  23:50 evaluation.
- Use the clearer homeowner-facing name **Adaptive Hybrid Reserve** while
  preserving internal AHM identifiers for compatibility.
- Reject incomplete AHM morning-observation samples after a Home Assistant
  restart by requiring a valid 07:00 initialization before the 12:05 publish.

### Safety

- Early Solar is eligible only from confirmed Hybrid Grid Hold between 06:00
  and 07:00 with Autopilot enabled, current dated forecast input, fresh
  inverter telemetry, fresh aligned Total Solar, present grid power, SOC at or
  above the retained target, at least 300 W live Total Solar, and at least
  1.6 kWh forecast for 06:00-07:00.
- Missing, stale, insufficient, inconsistent, or failed input keeps Grid Hold
  unchanged. The ordinary 07:00 Solar handover remains the fallback.

## [1.3.6] - 2026-08-14

### Fixed

- Publish the initial concise Hybrid decision state during EnergyHub startup so
  an incompatible retained pre-1.3.4 reason is replaced before a later Home
  Assistant Core restart reloads it.
- Enforce Home Assistant's 255-character state boundary at the
  `hybrid_decision_reason` publisher as defense in depth.

### Validation

- Confirmed that the 23:50 evaluation on the deployed 1.3.5 baseline replaced
  the historical 355-character reason with the concise current summary; the
  migration warning affected presentation only and did not affect AHM or
  inverter control.

## [1.3.5] - 2026-08-14

### Added

- Added optional read-only Modbus RTU telemetry for PV2 voltage and power from
  independently hardware-verified registers 4563-4564.
- Added Total PV power derived only from fresh PV1 and fresh PV2 samples within
  a 15-second alignment window.
- Added PV2 telemetry status, freshness, sample age, dedicated availability,
  and restart-safe stale-value handling.
- Added focused regression coverage for verified frames, byte swapping,
  scaling, CRC, timeout, malformed and exception responses, invalid ranges,
  stale/alignment policy, failure isolation, and restart behavior.

### Safety

- PI30MAX and Modbus transactions share one adapter-owned serial lock.
- The Modbus interface exposes only the fixed function-03 read of registers
  4563-4564; it provides no generic register access or write path.
- PV2 and Total PV remain observational and do not affect AHM, Panic, Hybrid,
  or inverter-control decisions.

## [1.3.4] - 2026-08-14

### Changed

- Replaced the exposed AHM slider with confirmed 5% decrease/increase controls to prevent accidental changes.
- Grouped the active reserve, its policy explanation, and its three-morning recommendation under one AHM management section with a prominent risk-coloured value.
- Renamed the learning fallback diagnostic to `verified_ramp_fallback` and labelled learned energy values as available after 3/3 samples.

### Fixed

- Hybrid Decision Reason now publishes a short Home Assistant-safe summary while the full calculation and notification explanation remain available separately.
- Panic now publishes `None` instead of `Unknown` when there is no inherited AHM target.

## [1.3.3] - 2026-08-13

### Fixed

- AHM now remains in Solar when projected 07:00 SOC already meets its calculated target.
- Hybrid Grid Hold is now reserved for the case where current SOC is at or above target but projected overnight discharge would cross below it.
- AHM still takes ownership from an active Panic strategy at 23:50, restoring Solar when no night-grid support is required.

## [1.3.2] - 2026-08-12

### Added

- Added 07:00–12:00 essential-load learning from hourly house-energy deltas after subtracting all three heat-pump energy deltas.
- Added a 21-day, per-hour 75th-percentile morning load profile and diagnostics for model source, learning progress, expected essential load, forecast solar, and net deficit.
- Added a three-completed-morning AHM reserve advisor with dashboard and Telegram learning/increase/decrease/keep guidance.

### Changed

- AHM uses hourly net-energy deficit after three complete morning samples per interval and requires two consecutive forecast hours to cover learned essential load before confirming solar takeover.
- The verified 300 W → 600 W ramp calculation remains the authoritative fallback while learning is incomplete or inputs are unavailable.
- Reserve advice is informational and changes by one named 20/30/40/50% step; it never changes AHM or Panic automatically.

### Fixed

- Reject non-finite morning meter values and skip incomplete SOC observations after missing 07:00 telemetry or a Home Assistant restart.

## [1.3.1] - 2026-08-12

### Added

- Added a user-selectable AHM Minimum SOC helper from 20% to 50% in 5% steps, with dashboard risk guidance.
- Added retained diagnostics for the raw morning gap, 300 W threshold, following-hour forecast, ramp confirmation, one-hour credit, and effective solar-support time.

### Changed

- Replaced the hidden fixed 10% AHM margin with the selected minimum SOC.
- A confirmed forecast ramp from at least 300 W to at least 600 W in the following hour now advances effective solar support by one hour.
- EnergyHub independently validates the 300 W/600 W values before accepting the Home Assistant ramp credit.
- The 23:50 plan now actively preserves its target: SOC below target charges, while SOC at or above target enters Hybrid Grid Hold until 07:00.

## [1.3.0] - 2026-08-08

### Added

- Extended Adaptive Hybrid Mode with an aligned post-07:00 energy balance using today's consumption, tomorrow's hourly solar forecast, the 16 kWh battery model, and a conservative 90% efficiency.
- Added explainable daytime-deficit kWh/SOC diagnostics and persisted adaptive targets.
- Added conservative Panic targets for every Grid Confidence level: normal 20%, unstable 60%, risk 80%, and panic 95%.
- Added explicit Panic phases, restart-safe AHM morning debt, and a persistent `panic_grid_hold` operating mode.

### Changed

- Panic now evaluates from 07:00 to 23:50 every five minutes and on grid transitions, without a solar-forecast gate.
- Panic arms while grid is offline, charges when grid becomes available, and holds the recovered reserve instead of returning to Solar.
- AHM takes ownership from Panic at 23:50 and selects Solar, Hybrid Charging, or Hybrid Grid Hold.
- Grid-backed Panic now receives the same temporary manual heat-pump permission as grid-backed Hybrid; reserve locks return when grid is lost.
- Standardized daily dashboard charts to `dd.MM`, corrected live Grid Import, and restored the native pastel chart styling.
- Corrected snapshot-style MQTT energy metadata so Home Assistant no longer receives the invalid `device_class: energy` plus `state_class: measurement` combination.

## [1.1.0] - 2026-08-06

### Documentation

- Started the EnergyHub 1.x development plan while preserving 1.0.2 as the released baseline.
- Defined and completed the 1.1 scope for Zigbee2MQTT, paired smart-plug validation, focused dashboards, and reserve-only smart-plug OFF protection.
- Clarified the Zigbee2MQTT, Home Assistant, and EnergyHub responsibility boundaries and deferred automatic Smart Thermal starts.
- Added the Zigbee2MQTT/ZBDongle-E configuration, validation, backup, recovery, interference, and pairing guide.
- Documented the observed Ember ASH timeout, attended manual recovery, bridge/device availability recovery, stale-measurement risk, and conservative automatic-control recovery gate.
- Recorded the 2026-08-05 Ember/EZSP `HOST_FATAL_ERROR` recurrence while the app Watchdog was enabled, with no autonomous recovery observed.
- Recorded the 2026-08-06 `ASH_ERROR_TIMEOUTS` recurrence: Supervisor Watchdog made ten restart attempts, every ASH/EZSP startup failed, the crash loop stopped, and a later attended manual Start recovered the existing network and both devices.
- Recorded the expired Tuya authentication repair as the probable cause of the stale EnergyHub beacon color and separated external-integration health from inverter telemetry health.
- Prioritized Adaptive Night Hybrid design so projected overnight SOC is protected until useful solar production, rather than sunrise alone.
- Added a dedicated hand-drawn infographic for the water-boiler and grid-confidence-aware heat-pump reserve logic.

### Home Assistant

- Added matching heat-pump controls for all three floors, then consolidated the dedicated Heat Pumps view to switch, live power, 0–12 h auto-off duration, absolute turn-off time, and shared consumption history.
- Added floor-1 and floor-2 auto-off helpers and automations with the proven floor-3 behavior; duration `0` remains manual mode.
- Removed empty `New section` headings from the dashboard.
- Added dedicated Heat Pumps and Water Systems views with compact manual controls and daily/weekly/monthly consumption graphs; Xiaomi plug energy history is calculated locally from live watts to avoid false cloud-counter jumps.
- Added staged water-boiler reserve protection: a one-time 50% SOC shed, a latched 40% emergency OFF lockout, and fresh-telemetry unlock at 60% without automatic restoration.
- Added grid-confidence-aware heat-pump reserve protection. A fully trusted grid uses only the 50% all-floor lockout and 60% unlock; otherwise all floors shed once at 80%, floor 2 again at 70%, floor 1 at 60%, and the 50% lockout remains until 90%. No heat pump is started automatically.
- Added scoped deployment automation for add-on code versus Home Assistant YAML/storage, including target-file backups, dry runs, post-deploy guidance, and a mandatory stopped-Core assertion for `.storage`.

### Development installation

- Installed and configured the official stable Zigbee2MQTT Home Assistant app for the SONOFF ZBDongle-E using its persistent serial identity, `ember`, software flow control, MQTT discovery, and Zigbee channel 25.
- Validated EmberZNet 7.4.4, coordinator startup, MQTT connection, discovery publication, Zigbee2MQTT app-restart recovery, and full Home Assistant host-restart recovery without changing EnergyHub 1.0.2 runtime behavior.
- Completed the Zigbee2MQTT foundation with a 1 m interference-reducing USB extension and a verified private encrypted backup containing Zigbee2MQTT app data.
- Paired and named the first- and second-floor Zigbee smart plugs, identified their direct-reporting and polled-reporting TS011F variants, and validated manual relay/physical-button state synchronization with safe power-outage behavior.
- Recorded the 2026-08-02 Ember `ASH_ERROR_TIMEOUTS` stop while the Home Assistant app Watchdog was disabled and the attended manual Start on 2026-08-03 that recovered the coordinator, both paired devices, MQTT, availability, and Home Assistant discovery without re-pairing or an observed relay command.
- Enabled the Home Assistant app Watchdog only after manual recovery; the 2026-08-05 recurrence did not recover autonomously, so bounded monitoring and recovery remain open work.
- Confirmed from the 2026-08-06 log that Supervisor Watchdog can restart the app but cannot recover an Ember NCP that remains unresponsive across restarts.
- Validated second-floor Offline-to-Online availability and safe OFF power recovery, plus a later Home Assistant restart that retained both devices Online while the first-floor plug remained ON and its heat pump continued running.
- Recorded first-floor asynchronous compressor ramp-up telemetry, including a stabilized 804 W, 3.37 A, 226 V example, as trend data rather than calibrated electrical-protection input.

## [1.0.2] - 2026-08-01

First release-ready EnergyHub 1.0 build.

### Added

- Solar, Hybrid Charging, Hybrid Grid Hold, and Panic operating strategies.
- Explainable Hybrid and Panic decision services.
- Verified PowMr Menu 01 control with QPIRI read-back.
- ACK-confirmed and persisted Menu 16 control.
- Startup strategy reconstruction without unnecessary inverter writes.
- Communication, Battery, Telemetry Freshness, Inverter, and System Health monitoring.
- QPIWS warning and fault polling.
- Rolling Grid History, Grid Availability, and weighted Grid Confidence.
- Persistent Daily Summary and mode-aware Grid Import estimation.
- MQTT Discovery for EnergyHub and PowMr entities.
- Home Assistant Autopilot, schedules, manual Panic control, notifications, dashboards, and selected configuration synchronization.
- Executable release tests for decision boundaries, telemetry freshness, restart reconstruction, transition sequencing, and recovery behavior.
- Docker build test gate using `python3 -m unittest discover -s tests -v`.
- Installation, upgrade, app-store, release, project-state, roadmap, and Home Assistant integration documentation.

### Changed

- Pinned tested Python dependencies:
  - `paho-mqtt==1.6.1`;
  - `mppsolar==0.16.56`.
- Replaced weak public MQTT credential defaults with blank values that must be configured by the installer.
- Changed serial access from unstable `/dev/ttyUSB*` numbering to a configurable persistent `/dev/serial/by-id/...` path.
- Enabled app access to UART and udev device information.
- Made the startup banner use the Home Assistant build version instead of a hard-coded string.
- Removed the experimental Away Mode runtime from EnergyHub 1.0 and deferred the broader concept to Smart Thermal Energy.
- Removed obsolete MQTT Discovery/state for the raw inverter warning sensor.
- Standardized Daily Summary Grid Import naming as `sensor.energyhub_daily_summary_grid_import`.
- Clarified that Menu 16 is ACK-confirmed but cannot be independently read back on the current inverter.
- Clarified that Grid Import is informational and not billing-grade.

### Fixed

- App startup after USB device numbering changes.
- Serial permission/access behavior after Home Assistant restarts.
- Packaging path mismatch between `/publisher.py` and `/app/publisher.py`.
- Hard-coded `1.0.0` startup banner in later 1.0.x builds.
- False Telemetry Freshness warnings caused by unchanged but valid house-load telemetry.
- Startup ambiguity and unnecessary inverter writes during consistent Solar reconstruction.
- Partial Hybrid transition recovery back to Solar.
- Stale Daily Summary snapshot handling across date boundaries.
- Invalid raw inverter warning MQTT entity publication.

### Validation

- Rebuilt successfully on Home Assistant OS for `linux/arm64`.
- All 24 release tests passed during the Docker image build.
- Live telemetry and MQTT Discovery validated after rebuild.
- Full Home Assistant host restart validated with both the inverter FTDI adapter and a SONOFF Zigbee coordinator connected.
- Solar mode reconstructed from actual Menu 01 plus persisted Menu 16 without inverter writes.

### Known limitations

- `aarch64` only in 1.0.2.
- Current hardware support is PowMr 10.2M / PI30MAX.
- No PV2 or output-2 telemetry.
- Menu 16 cannot be read back.
- Grid Import is estimated and may be affected by simultaneous daytime PV.
- Strategy parameters are still code/configuration constants.
- The 07:00 return to Solar depends on Home Assistant scheduling.
- General telemetry quarantine, direct BMS integration, and bounded recovery services are future work.

## [0.1] - 2026-06

### Added

- Project philosophy, manifesto, vision, design principles, initial architecture, roadmap, backlog, and repository structure.
