# Changelog

## Unreleased

## 2.4.12

- Render Home Assistant-compatible optional numeric MQTT states, including
  PV2 sample age and daily solar diagnostics, without numeric `unknown` errors.
- Bound external-intent history without latching overload protection off after
  queue pressure; retain fresh snapshot and intent-revision safety gates.
- Fail closed and start without an automatic reserve recommendation when its
  persisted document is malformed.
- Publish inverter offline availability before secondary timeout/error work,
  and explicitly report a failed single-shot Solar recovery for attended review.
- Coordinate the HA corrective Smart Heating policy: preserve family setpoint,
  fan and Super choices; revoke stale auto-resume after confirmed Heat; preserve
  family auto-off hours through automatic plug shedding.
- Keep the six-load HA snapshot publishing when one plug or power entity is
  missing, without inventing state, timestamp, or context evidence for it.

## 2.4.11

- Require a valid grid-voltage field before a telemetry sample can drive control;
  unknown grid evidence no longer becomes a false outage.
- Require current physical-grid evidence for estimated Grid Import and break
  integration across an outage or missing sample.
- Publish a timestamped Battery Reserve control-evidence heartbeat; the HA
  executor checks availability, date and age before applying a recommendation.
- Require a current, valid QPIWS overload warning for load shedding, preserve
  active incidents on malformed replies, and recover from malformed persisted
  inverter-controller targets without a startup crash.
- Preserve communication-interruption context across read exceptions for SOC
  anomaly diagnostics.
- Coordinate HA Smart Heating and restart plug restoration through guarded
  ownership, load, recovery and sequential-start conditions.

## 2.4.10

- Limit the solar-forecast shortfall allowance to one 20-point increment,
  including when forecast generation is less than half of recent consumption.
  Grid, weather, Smart Heating, stale-evidence, and 95% cap rules are unchanged.
- Exclude solar-only Grid Hold battery SOC gains from estimated grid-charged
  battery energy. Historic estimates remain unchanged; the house-load component
  is still not a direct grid meter.

## 2.4.9

- Confirm load-control commands from a fresh target-state transition and
  matching Home Assistant context. Unchanged old 0/1 W readings no longer make
  an otherwise confirmed relay or climate transition fail; a fresh
  contradictory power reading still vetoes confirmation.
- Retain the initial overload percentage and trigger reason alongside the
  post-action load for honest dashboard and Telegram evidence.
- Release first-floor heat-pump ownership only for explicit external intent or
  a conflicting state, not passive integration attribute refreshes.

## 2.4.8

- Apply the official level-2/3 weather reserve independently of Normal,
  Unstable, Risk, or Panic Grid Confidence; retain the additive calculation and
  95% cap.
- Preserve the existing forecast policy: +20 points for a forecast deficit and
  +40 points when forecast generation is below half of recent consumption.

## 2.4.7

- Use each Zigbee2MQTT plug's existing Home Assistant switch entity as the
  online/offline authority instead of redundant manual MQTT binary sensors.
- Ignore retired or unrelated Home Assistant input topics silently after their
  retained MQTT cleanup, avoiding misleading startup warnings.

## 2.4.6

- Separate online device state from an unchanged per-device watt reading in
  Load Protection. A current HA switch/climate state and bridge snapshot may
  remain eligible even when an idle plug has not republished the same watts.
- Keep strict command acknowledgement and require a new post-command target
  state observation before EnergyHub accepts ownership of a switched load.
- Present old but valid plug watts as `power unchanged` rather than incorrectly
  describing the online device as stale.

## 2.4.5

- Remove the retired Adaptive Hybrid, Early Solar, morning-load learner, and
  reserve-advisor runtime/services instead of keeping uncalled compatibility
  code.
- Clear their retained MQTT discovery, state, and input topics at startup, and
  retire the duplicate Daily Summary grid-import presentation entity.
- Remove unused Home Assistant restart-watt helpers and the hidden legacy
  decision panel; preserve valid last-known appliance state/power in the
  overload table while marking stale evidence explicitly.
- Clear unavailable completed-period MQTT values instead of publishing the
  non-numeric `unknown` sentinel to Home Assistant energy sensors.

## 2.4.4

- Retire the presentation-only Hybrid Calculation MQTT sensor and remove its
  retained discovery/state records during upgrade. Battery Reserve and inverter
  control do not depend on this verbose legacy explanation.

## 2.4.3

- Reduce Recorder/MQTT churn without slowing the 10-second safety loop: inverter
  telemetry now uses deadbands plus a 30-second heartbeat, idle HA participant
  snapshots run every 30 seconds, and Peak Load Guard attributes publish on a
  control-state change or 60-second heartbeat.
- Store completed-day actual PV, forecast error and the battery-full qualifier;
  correct estimated solar surplus by including the energy required to recharge
  the battery.
- Add complete previous-week and previous-month tariff totals for scheduled
  family summaries, fix the monthly monetary state class, and bound the Hybrid
  calculation state to Home Assistant's 255-character limit.
- Simplify first-floor Smart Heating to Normal, Quiet (23:00–08:00), and Eco on
  battery. Remove Turbo; pause at 40% SOC and restore at 50% only when Smart
  Heating owns the pause.
- Exclude verbose diagnostic payload entities from Recorder while retaining ten
  days of raw history and Home Assistant long-term statistics.

- Use a yellow two-second signalling-indicator pulse for Smart Heating with
  Solar-only Heating enabled; retain the white pulse for ordinary Smart Heating.
- Add guarded Home Assistant restart recovery for explicit family ON choices on
  the first- and second-floor Zigbee heat-pump plugs. Restoration waits for a
  stable HA session, fresh telemetry, reliable grid voltage, ready device states
  and no controller ownership, then records measured power after one minute for
  Family Assistant reporting.

## 2.4.2

- Quarantine an unavailable, rejected, or unconfirmed appliance per device so
  protection can continue with other eligible participants.
- Preserve restoration ownership only after confirmed OFF evidence and skip an
  unavailable owned appliance while other owned appliances recover.
- Simplify the EnergyHub beacon: solid 30% on solar/battery, solid 100% on
  intentional grid supply, 20/50/80/50 breathing during outages, alternating
  red/burgundy at critical SOC, steady white on stale telemetry, and a
  two-second Smart Heating pulse every 20 seconds.
- Enforce first-floor Smart Heating Quiet mode from 23:00 through 07:00 and
  suppress Turbo during that interval.

## 2.4.1

- Make the applied Battery Reserve the sole 24/7 inverter reserve target.
- Retire the 23:50 Low-Tariff Plan, 06:05 Early Solar handover, 07:00
  ownership handoff, and learned morning-reserve observations.
- Redirect stale legacy requests and persisted Hybrid modes into the current
  Battery Reserve controller instead of allowing a competing target.
- Replace the large legacy decision panel with compact reserve-control status.

## 2.4.0

- Add the severe forecast-deficit tier: +40 points when forecast generation is
  less than half the completed-day consumption average.
- Add one fixed +20-point Battery Reserve allowance while Smart Heating is ON.
- Coordinate battery recovery so the native first-floor heat pump may restore
  in Eco at 50%, while the other protected loads continue to wait for 60%.
- Keep Smart Heating and Solar-only Heating OFF by default.

## 2.3.2 - 2026-09-12

- Create a preliminary next-day forecast allowance after the 23:51 completed
  consumption snapshot and replace it, without accumulation, from the updated
  05:00 forecast.
- Retain the safe preliminary allowance when the morning forecast is missing;
  continue live Grid Confidence and UHMC reevaluation throughout the day.
- Expose the dated forecast-plan stage and revision status for Home Assistant
  presentation.

## 2.3.1 - 2026-09-12

- Accept Home Assistant Unix timestamps as well as ISO timestamps when
  validating completed daily-consumption snapshots, recovering existing valid
  history for Battery Reserve without waiting for new days.

## 2.3.0 - 2026-09-12

- Replace the separate daytime 20/60/80/95 ladder with one additive Battery
  Reserve: 20% base, forecast/grid/weather allowances, capped at 95%.
- Add Manual and Automatic Battery Reserve authority. Automatic application is
  permitted only for a fresh, complete recommendation; Manual preserves the
  family-selected value and remains recommendations-only.
- Use one or more valid completed consumption days while up to three days of
  history are accumulated.
- Separate discharge protection from Battery Reserve: warn at 50%, disconnect
  noncritical loads at 40%, and restore at 60% or after verified grid recovery.
- Upgrade the Home Assistant load-control bridge to schema 5 so stale schema-4
  snapshots and commands cannot arm the changed policy.

## 2.2.6

- Accept fresh UHMC evidence for 75 minutes to match the hourly source poll.
- Keep forecast and grid-input freshness limits unchanged.
- No reserve modifier, device-control or inverter-control rule changes.

## 2.2.5

- Coordinate battery and overload protection through one schema-4 command journal.
- Use actual outages and default 50/40/60 battery thresholds, excluding microwave.
- Replace first-floor battery relay shutdown with native OFF; preserve restoration ownership.
- Qualify grid/battery recovery and pause unverified native-setting restoration.

## 2.2.4

- Reset overload recovery qualification when the HA bridge session changes while
  retaining control intent, confirmed ownership and uncertain-command safeguards.
- Companion HA configuration restores the last overload ON/OFF setting instead
  of unconditionally disarming at startup. Missing restore state defaults OFF.

## 2.2.3

- Remove mandatory restart watt allowances; require schema-3 bridge/commands.
- Restore after five minutes below 50%, sequentially at least one minute apart.
- Persist one missing-data notice per outage; never restore blind; preserve ownership.

## 2.2.1 - 2026-09-07

- Use one HA switch for automatic versus warnings-only overload operation at 85/75/60.
- Retire runtime 40/30/20 selection; keep the old app flag only as optional compatibility.
- Persist warning episodes, retain ownership while OFF, and observe late acknowledgements.
- Require updated schema-2 bridge evidence before arming; safety checks unchanged.

## 2.2.0 - 2026-09-07

- Add opt-in 85/75/60 overload controller with persisted command/ownership evidence.
- Use an allow-listed HA executor, expiring non-retained commands and dual OFF-by-default gates.
- Native first-floor Heat/Off precedes the remaining heat-pump relays; preserve family changes.
- Require approved restoration allowances and attended validation; Battery Reserve unchanged.

## 2.1.4 - 2026-09-06

- Apply the family-selected Battery Reserve to daytime protection, retaining
  higher grid-safety and missed-night targets. On Normal grid without debt,
  hold at the selected floor and release at floor +10 points, capped at 100%.
- Reevaluate changed manual input on valid telemetry; reject missing/invalid
  manual values rather than silently assuming 20%. Advisory Dry Runs unchanged.
- Existing night-plan scheduling and dated targets are unchanged.

## 2.1.3 - 2026-09-06

- Use Battery Reserve, Low-Tariff and Reserve Protection friendly names and
  explanations without changing MQTT identity, raw modes, settings or control.
- Keep both Dry Runs and persisted event/decision state unchanged.

## 2.1.2 - 2026-09-06

- Keep reserve ownership manual; report condition allowances without rebasing on
  manual overrides. Remove the second baseline control and support manual 20–95%.
- Automatic reserve and Peak Load Guard remain Dry Run only.

## 2.1.1 - 2026-09-06

- Keep 40/30/20 Dry Run; confirm recovery for 60 seconds without a native
  overload warning. Stale observations, gaps over 30 seconds and restart reset
  confirmation, not the active cycle.
- Persist the latest 64 events with stream/cycle identifiers for Family bot
  delivery; retain the legacy latest-event field.
- Freeze the daily forecast at/after 05:00, separate preferred baseline from
  the manually applied minimum, and hold buffers on incomplete evidence.
- Expose Battery Reserve Auto as read-only OFF; no inverter or plug commands.

## 2.1.0 - 2026-09-05

- Add a persisted, observer-only Effective Reserve policy evaluated at 05:00
  from the selected AHM minimum, today's Solcast generation forecast, the
  average of up to three newest valid completed consumption days, Grid
  Confidence, and normalized official UHMC warnings.
- Add 20 points when generation forecast is below expected consumption; add
  cumulative Grid Confidence modifiers of 0/20/40/60 points for
  Normal/Unstable/Risk/Panic; cap the recommendation at 95%.
- Add a 20-point weather modifier only for active, grid-relevant Level II or
  III Kyiv/Kyiv-region warnings while Grid Confidence is Normal. Level I is
  retained for reporting but does not change the recommendation.
- Preserve active warnings across restart and unknown source intervals;
  expire or cancel them only from dated evidence. Unknown never means clear.
- Expose a retained MQTT status entity and add no AHM, inverter, or smart-plug
  control path. Manual mode suppresses every advisory modifier.
- Temporarily use a 40/30/20 Peak Load Guard Dry Run profile for a one-week
  household observation of recommendations, recovery, and Telegram messages.
  The guard remains observer-only.

## 2.0.0 - 2026-08-27

- Add an observer-only Peak Load Guard using native inverter Load %, W, VA,
  and the native overload warning.
- At 85% load, recommend an ordered prefix of participating loads until their
  observed power could reduce load toward 75%; at 60%, recommend restoring
  the recorded pre-event states in the same order.
- Use the household order water pump, water boiler, second-floor heat pump,
  first-floor heat pump, third-floor heat pump, then microwave.
- Persist the active Dry Run cycle and expose retained MQTT status and event
  entities. Stale inverter or participant telemetry produces no recommendation.
- Add no smart-plug or inverter control command. The 85/75/60 policy is a
  Dry Run candidate to be checked against recorded 1.3.10+ fault evidence.

## 1.3.14 - 2026-08-24

- Keep Solar unchanged at the Normal 20% reserve floor when the physical grid
  is absent, and reevaluate immediately after grid availability returns.
- Require present grid for the Normal-grid 20% immediate hold boundary.
- Transfer confirmed `SUB` + `SNU` Hybrid Charging ownership to Panic Charging
  without redundant inverter writes at the daytime handoff.
- Preserve the 1.3.13 07:00 ownership handoff, 20%/30% hysteresis, missed-AHM
  debt, and non-Normal 60/80/95% reserve behavior.
- Reject non-finite telemetry and out-of-range SOC before MQTT publication,
  controller state, and battery-health classification.
- Clear stale Panic context before non-Panic Hybrid writes and recover Solar
  after a failed Hybrid/Panic Menu 01 entry when the bounded recovery succeeds.
- Mark direct fault-set replacements as superseded, preserve valid journal
  history across malformed optional fields, and limit Home Assistant fault
  state strings to 255 characters while retaining full attributes.
- Derive the PV1 freshness allowance used by Total PV from longer configured
  PV2 poll intervals.

## 1.3.13 - 2026-08-23

- Transfer 07:00 ownership from AHM to Panic without forcing Solar first.
- Under Normal Grid Confidence, hold the 20% floor and release Solar only at
  30%, creating a 10-point hysteresis band.
- Preserve missed AHM debt and the existing 60/80/95% non-Normal targets.
- Transfer an already-confirmed `SUB` + `OSO` Grid Hold between owners without
  redundant inverter writes.
- Use routine Normal-grid reserve notifications and extend trusted-grid manual
  permission to the water boiler.

## 1.3.12 - 2026-08-22

- Hide expected `pv_loss_warning` transitions from the four dashboard-facing
  inverter-message entities while retaining them in the bounded journal.
- Select the latest three meaningful incidents across skipped PV-loss-only
  records and preserve real messages from mixed incidents.

## 1.3.11 - 2026-08-22

- Split estimated Grid Import into local calendar-day night (`00:00–07:00`
  and `23:00–24:00`) and normal (`07:00–23:00`) tariff periods.
- Persist bounded daily tariff records, lifetime chart counters, completed
  yesterday values, and current-month kWh and estimated UAH cost.
- Use initial informational prices of 2.50 UAH/kWh at night and
  5.00 UAH/kWh during the normal period.
- Preserve the existing total Grid Import and Daily Summary finalization path;
  no tariff result enters inverter or household-load control.

## 1.3.10 - 2026-08-21

- Persist the latest 100 named QPIWS incidents and their clear transitions.
- Retain up to five minutes of pre-incident load, load percentage, battery,
  solar, grid, operating-mode, and telemetry-freshness samples.
- Publish the current inverter message and latest three incidents through
  retained Home Assistant MQTT Discovery entities.
- Keep the observer outside every inverter and household-load control path.

## 1.3.9 - 2026-08-20

- Added a read-only, restart-aware SOC anomaly journal for changes of at least
  five percentage points within five minutes.
- Persisted the latest 100 events with SOC, interval, battery voltage and
  charge/discharge current, PV1/PV2/Total PV, load, grid, operating mode,
  freshness, process uptime, and communication-recovery evidence.
- Exposed the lifetime event count and latest event with full MQTT attributes
  through Home Assistant Discovery.
- Kept anomaly observation outside telemetry acceptance and every inverter or
  household-load control path.

## 1.3.8 - 2026-08-18

- Persist the date through which a completed 23:50 AHM plan remains
  authoritative.
- While that dated plan is active, keep Solar above the target, enter Hybrid
  Grid Hold at the exact target, and enter or resume Hybrid Charging below it.
- Reevaluate on every fresh local telemetry cycle instead of waiting up to 30
  minutes; issue commands only for required state transitions.
- Keep stale telemetry and an absent grid command-free, and retry naturally
  after later fresh grid-present telemetry.
- Bound failed-transition retry so one unchanged night condition cannot issue
  repeated inverter requests on every telemetry cycle.
- Clear dated night enforcement only after a confirmed non-AHM Solar handover.

## 1.3.7 - 2026-08-15

- Added a guarded 06:05 release from Hybrid Grid Hold to Solar when the
  retained target is met, live aligned Total Solar is at least 300 W, and the
  dated 06:00-07:00 Solcast interval is at least 1.6 kWh.
- Enforced Autopilot, fresh telemetry, current date, local 06:00-07:00 window,
  grid-present, and confirmed Grid Hold gates inside EnergyHub.
- Added Early Solar MQTT diagnostics and transition-result publication.
- Presented the initial Hybrid state as `awaiting_evaluation` with retained
  target and next-evaluation context.
- Kept every failed or unavailable gate conservative: no inverter command and
  the normal 07:00 Solar handover remains authoritative.

## 1.3.6 - 2026-08-14

- Replace incompatible retained Hybrid decision state with the concise initial
  state whenever the EnergyHub app starts.
- Limit `hybrid_decision_reason` to Home Assistant's 255-character state
  boundary at the publisher.
- Add regression coverage for startup cleanup, retained publication, and the
  publisher boundary.

## 1.3.5 - 2026-08-14

- Added optional, strictly read-only PV2 Modbus RTU polling for verified
  registers 4563-4564 on the installed POW-HVM10.2M.
- Serialized PI30MAX and Modbus access behind the existing adapter-owned serial
  lock and isolated all PV2 failures from the PI30MAX loop.
- Added PV2 voltage, PV2 power, fresh aligned Total PV power, status,
  freshness, and sample-age MQTT entities.
- Added dedicated availability topics so retained PV2 and Total PV values are
  never presented as current after a failure, stale interval, or restart.
- Added protocol, failure-isolation, freshness, alignment, MQTT, and restart
  regression tests.

## 1.3.4 - 2026-08-14

- Published a concise Hybrid decision reason that stays within Home Assistant's sensor-state limit.
- Renamed `legacy_ramp_fallback` to the clearer `verified_ramp_fallback` diagnostic.
- Published `None` when Panic has no inherited AHM target.
- Replaced the exposed AHM slider with confirmed 5% adjustment buttons and clarified 3/3 learning-only diagnostics.
- Grouped the active AHM value, policy explanation, and advisor result with a prominent risk-coloured reserve display.

## 1.3.3 - 2026-08-13

- Fixed unnecessary Hybrid Grid Hold when projected 07:00 SOC already meets the adaptive target.
- Kept Grid Hold only for an overnight target crossing and Charging only when current SOC is below target.
- Preserved authoritative 23:50 AHM takeover from Panic by restoring Solar when reserve is sufficient.

## 1.3.2 - 2026-08-12

- Added a learned 07:00–12:00 essential-load profile that subtracts heat-pump energy from total house energy.
- Added conservative 75th-percentile hourly net-energy planning after three complete morning samples per interval.
- Retained the 1.3.1 verified solar-ramp model as the safe learning/input fallback.
- Added model-source, learning-progress, expected-load, solar, and net-deficit diagnostics.
- Added a persistent three-morning reserve advisor: increase after 2/3 low-margin mornings, decrease only after 3/3 high-margin mornings, otherwise keep or learn.
- Reject non-finite morning meter values and exclude incomplete SOC observations from reserve advice.

## 1.3.1 - 2026-08-12

- Added the configurable 20–50% AHM minimum reserve.
- Added independently validated 300 W → 600 W solar-ramp credit.
- Added retained minimum, raw/effective morning-gap, ramp-power, ramp-credit, and effective-support diagnostics.
- Removed the hidden fixed 10% AHM uncertainty margin from the target equation.
- Made the 23:50 plan actively protect its floor with Charging below target and Grid Hold at or above target.

## 1.3.0 - 2026-08-08

- Added post-07:00 Adaptive Hybrid energy-balance planning and persisted AHM targets.
- Reworked automatic Panic into a 07:00–23:50 conservative reserve controller with 20/60/80/95% Grid Confidence targets.
- Added offline waiting, grid charging, and Panic Grid Hold phases with restart-safe strategy reconstruction.
- Added AHM-to-Panic morning-debt handoff and authoritative AHM takeover at 23:50.
- Expanded MQTT diagnostics, release tests, and Home Assistant dashboard visibility.

## 1.1.0 - 2026-08-06

- Preserved the tested EnergyHub 1.0.2 inverter runtime and 24-test build gate.
- Added the repository-side Home Assistant smart-plug dashboards, matching heat-pump auto-off controls, local energy history, and reserve-only OFF protection.
- Added guarded deployment tooling and Zigbee2MQTT/ZBDongle-E setup and resilience documentation.
- Deferred every automatic smart-plug ON action and Smart Thermal control to a later milestone.

## 1.0.2 - 2026-08-01

- First release-ready EnergyHub 1.0 build.
- Added persistent FTDI `/dev/serial/by-id` configuration with UART/udev access.
- Added executable release tests enforced during the Docker image build.
- Pinned `paho-mqtt` and `mppsolar` dependencies.
- Removed weak public MQTT credential defaults.
- Fixed the runtime publisher path and build-version startup banner.
- Removed obsolete raw inverter warning MQTT Discovery/state.
- Validated rebuild and full Home Assistant host restart on the real installation.

See the repository root `CHANGELOG.md` for complete details.
