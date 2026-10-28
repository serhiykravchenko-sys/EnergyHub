# Changelog

## 3.6.37

Fix five-minute solar observation timing. Clean retired plug notifications and
participant diagnostics without affecting native HA notification transport or HP
control. Correct technical severity/boot/grace deduplication and delivery expiry,
isolate fresh state defaults, qualify recovery wording and reduce repeat logs.
No destination, quiet-hours, dashboard or control-policy change.

## 3.6.36

Use Dacha-style apartment outage/restoration lines in the morning message; retain
unknown onset without Hub attribution. Dacha grid events include qualified,
time-weighted five-minute PV power from existing monitoring samples. Freeze the
observation for delayed delivery; gaps and stale evidence remain unknown.


## 3.6.35

Shorter night/HP/water and forecast quality reports; weekly/monthly forecast-surplus day counts; independent observed battery counters/coverage; qualified off-grid reminders and explicit HP warning floor.


## 3.6.33 — native control notices and clearer morning evidence

- Correct absolute-time ordering of hourly forecasts across repeated DST hours; add forecast rejection/coverage evidence.

Retire Python overload notices; preserve HP1 notices. Explain deficit preparation in message one; compact message two includes hot water, significant HP consumption and one forecast outlook. Weekly quality averages, dated CO and ordered grid/precharge delivery.

## 3.6.30 — artifact audit patch (October 23, 2026)

- Remove unused BR-relative multi-HP protection formatter and two obsolete tests.
  It had no production callers; this is dead-code removal, not a new live-message
  behavior change. Retired queued-warning cleanup remains.
- Preserve HP1 climate and overload messages until their separate migrations.
  Native automation no-op/cause improvements and morning refinements remain queued.

## 3.6.27 — private candidate (October 23, 2026)

- Shorten emergency outage notices to scope, one schedule caveat, published
  windows and source; omit repeated warnings and reserve-calculation details.

- Move selected plug battery control to one native HA strict <40% OFF / >50%
  ON rule and direct Mission Control automation toggle; fridge and selected plugs
  now switch OFF only without DTEK and allow ON when confirmed DTEK returns.
- Retire migrated-plug battery dispatch, obsolete lockouts, duplicated warnings and
  floor-2/floor-3 plug timers; preserve overload and first-floor climate behavior.
- Remove first-floor relay recovery/monitoring notices and restart options;
  discard stale queued notices while retaining climate and energy reporting.
- Consolidate daily energy information into the second morning message; keep
  historical/freshness evidence, weekly forecast quality and compact normal CO.
- Show five days of forecast with verified point-centered dates and automatic
  Y maximum. Preparation only; no live deployment or publication.

## 3.6.26

- Add opt-in MQTT-discovered native HA notification target, persistent outbox,
  Telegram adapter, quiet hours, deduplication, expiry, retries and status sensor.
- Explain historical night forecasts and verified current preparation; label newer
  forecasts only with source evidence, and distinguish safety margin from outage ETA.
- Retain solar generation, forward consumption and grid charging estimates;
  add concise district facts and coverage-checked Monday battery counter summaries.
- Route known Xiaomi future-compatibility warnings to maintenance summary;
  keep functional failures actionable. Existing fridge rules are unchanged.

## 3.6.25 — private candidate (October 21, 2026)

- Retire custom fridge execution/status code; preserve the homeowner's native
  20/30 automations and five-minute minimum OFF rule without ownership helpers.
- Use complete rolling-hour house load for preparation solar surplus, with
  conservative fallback and unchanged outage coverage demand. Explain gross
  solar, household use and grid battery energy before the charging deadline.
- Repair completed-night reporting, show consumption/night arithmetic in the
  first morning message and report observed SOC rather than release thresholds.
- Suppress unchanged/expired regional notices; validate household district and
  cancellation provenance; omit finished schedule intervals.
- Center all seven forecast dates; add confirmed live grid status and rename
  retained automation aliases without release numbers. Preserve helper values.
- Prepared locally only; native control handover and live HA/add-on deployment
  remain separate approval and validation steps. No public promotion.

## 3.6.24 — private candidate (October 20, 2026)

- Release acquired scheduled grid hold when current SOC covers remaining
  conservative demand plus active BR and a five-point margin; retain qualified
  control/persistence guards and reassess extensions or changed reserve.
- Shorten charging/restoration notices and suppress routine online window-entry
  messages. Preserve actual outages and justified charging/completion notices.
- Remove custom Zigbee plug/hub diagnostics, obsolete options and persisted
  diagnostic state; preserve functional control checks and real CO alarms.
- Read yesterday's HA daily energy-change statistics, exactly as the HP
  chart does; hide valid usage <=0.1 kWh and keep missing data explicit.
- Show CO's last valid dated reading beyond 24 hours and add tomorrow/day-after
  solar outlook. Prepare a separate seven-day orange forecast/blue consumption
  chart without changing existing charts or charging policy.

## 3.6.23 — private candidate (October 19, 2026)

- Present compact night decisions and actual morning SOC outcomes; honor quiet
  hours, persist deduplication and refresh queued decision text before delivery.
- Require fresh qualified supply for charging/grid-use claims and an actual
  ongoing outage for restoration reminders. Clarify active-window top-up/hold.
- Retry missing tomorrow schedules without a standalone family failure warning.
- Report every configured HP over 24 elapsed hours, including zero and explicit
  unavailable/reset history; remove the verified first-floor reporting flag.

## 3.6.22 — prepared privately (October 17, 2026)

- Compose HA restart summary once from structured evidence: one SOC/BR/target
  line, regional status and applicable dated schedule. Preserve current-boot
  freshness and restart/delivery deduplication. Condense heating policy.
- Describe confirmed online/offline/unknown supply without an unconditional
  grid-disconnection promise. Rearm a released early charging episode so the
  real later start is announced and measured separately. All 694 tests pass.

## 3.6.21 — prepared privately (October 17, 2026)

- Apply mixed district bulletins per household, clear obsolete emergency BR
  authority on positive evidence and show stabilization/cancellation accurately.
- Poll at :10/:40; process completed reads before revalidating queued reminders.
  Bound refresh deferral without delaying physical grid/SOC/CO messages.
- Keep fresh timetable context during emergency notices and early grid losses;
  show an ongoing window and confirmed preparation reason after restoration.
- Add SOC-target energy, clarify solar surplus and confirmed charging, simplify
  completion and remove routine family capacity-shortfall alarms.
- Send a private deduplicated exhausted Eco diagnostic based on switch feedback.
- All 688 Family tests pass. Prepared locally; no deployment or live validation.

## 3.6.20 — prepared privately (October 17, 2026)

- Separate reserve recovery from scheduled charging. Explain recent confirmed
  BR increases, current SOC/target and measured solar shortfall when fresh;
  keep the scheduled preparation's distinct window/time/energy message.
- Restore yesterday's forecast comparison for days that did not reach full SOC;
  validate its date, use completed native generation where verified, and show
  insufficient data explicitly instead of silently omitting the comparison.
- Split the scheduled family morning digest into overnight observations/current
  status, followed by a shorter daily outlook. Persist each delivery position
  and retain in-flight older reports across upgrade/restart.
- Include house/apartment night events, charging readiness and battery protection;
  condense repeated grid interruptions and omit events outside the night window.
- Repeat applicable emergency/fault status beside the informational published
  schedule; retain stale notices as explicitly last-confirmed observations.
- Remove routine three-day averages and rolling grid statistics. Keep estimated
  DTEK need, measured HP consumption and dated CO readings; show CO batteries
  only at 20% or lower. Never interpret historical zero CO as current safety.
- Keep usable schedules during emergency notices with the controller's extra
  reserve. Add SOC/time/grid-solar energy preparation messages, confirmed near-
  target hold readiness and factual coverage-release explanations.
- Include explicit energy-helper sources for HP floors 1/2/3; label floor 3's
  measured-power integral. First-floor energy trust remains a separate gate.
- Paired with Energy Hub 3.6.20 and revised dashboard; not deployed, restarted,
  committed, pushed or publicly released.

## 3.6.19 — local preparation, not deployed (October 16, 2026)

- Wait three continuous minutes for DTEK loss or return in legacy raw-voltage
  monitoring; consume fresh shared 180-second confirmation without a second
  three-minute delay. Keep incident timestamps at the qualified transition start.
- Say that today's valid schedule remains in use when tomorrow is unavailable;
  do not describe this condition as fallback reserve control.

## 3.6.15 — private candidate (October 12, 2026)

- Preserve owned outage-preparation targets across missing PV/grid/control
  evidence; wait without new commands instead of falling back to ordinary BR.
- Correct HA mode notices: measured SOC is separate from target; 95% never
  creates a 105% release threshold. Scope Quiet retries to each night and report
  exhausted acknowledgement once per window.
- Require commissioned HP metering: stopped below 2 W, running at least 10 W;
  unknown/deadband readings block recovery. Remove forced running-HP cuts,
  require fresh relay acknowledgements, retain owned supply restoration and
  policy-checked HVAC resumption. Shorten family recovery/IP messages.
- Group Solcast 429 incidents, persist delivery/recovery, follow up once after
  24 hours, and explain recurring HA ingress errors without guessing an app.
- Show the approved daily shortfall and charging-equivalent estimate; report
  apartment rolling 24-hour availability as a Xiaomi Hub approximation.
- Label an active outage's remaining time until planned restoration; preserve
  future interval durations and existing emergency schedule suspension.
- Prepare disabled official DTEK observation with bounded reads, strict slot,
  group/date/revision validation and mirror comparison; mirrors keep authority.
- Forecast-assisted Smart heating below 40% remains deferred until the plug
  swap and trustworthy three-hour Eco consumption evidence. Fridge and BMS
  observation remain unchanged.

Prepared only. No commit, push, live synchronization, restart or publication.


## 3.6.14 — private candidate (October 11, 2026)

- Morning reports name the confirmed regional emergency/fault status, show both
  locations' fresh published schedules informationally during suspension, and
  remove repeated measurement time and repetitive missing CO/battery wording.
- Regional notices include both schedules and the existing +20-point reserve
  allowance (95% cap). Explicit cancellation restores validated planning;
  published rows alone cannot restore control authority.
- Xiaomi cloud read-failure notifications require three continuous minutes;
  recovery requires five continuous minutes and a delivered preceding alert.
  Gaps/flapping reset qualification; technical recovery is not grid recovery.
- Morning Grid Hold can release through existing intents when fresh complete
  hourly forecasts predict minimum SOC strictly above active BR plus five points.
  Credit 80% of forecast solar, delay it 30 minutes, assume at least the configured
  heating consumption rate, require one hour of solar coverage within four hours,
  and retain Manual Panic/outage-preparation priority and live floor protection.
- Zigbee power discrepancies and SOC jumps remain under observation. No changes
  to their measurements, device settings or evidence capture.

Prepared locally only; no commit, push, deployment, restart or publication.


## Family Assistant 3.6.13 private candidate — one concise restoration message

Prepared locally after explicit owner implementation authorization; not deployed,
committed, pushed or published. Energy Hub remains 3.6.12. House restoration owns
both directions of related inverter-mode changes and reserve charging notices,
including persisted queued messages. Delivery refreshes the confirmed supply mode
and briefly waits for a settling mode; obsolete mode messages are discarded.

Both locations use the agreed short restoration format. Fresh published raw
schedule rows remain informational during suspension, under the explicit warning;
they never restore control authority. Apartment durations use only its Hub
observations and omit unknown onset. House reserve shows the confirmed selected
value without repeating the +20-point explanation or 95% cap. Facebook reader
code and reader-only tests were removed; a migration filter discards legacy
queued Facebook diagnostics. Existing +20 suspension control remains unchanged.

See Family 3.6.13 release notes (historical reference: ../RELEASE_NOTES_FAMILY_3.6.13.md).


## 3.6.12 private candidate — suspended-schedule reserve and apartment alerts

Explicit schedule suspension adds 20 percentage points to the Grid Confidence
reserve once, before the 95% final cap (40% becomes 60%; 80% becomes 95%). The
allowance persists through restart and unavailable sources until fresh validated
current schedule authority explicitly confirms reinstatement. Existing manual
ownership and Manual Panic priority remain unchanged. Existing reserve diagnostics
and Telegram explanations expose the extra allowance; no new recurring notice.

Fresh Xiaomi cloud offline status can qualify an initial apartment alert after
two minutes, with unknown actual onset. Failed/stale/invalid reads and gaps reset
qualification; read recovery states hub online/offline without claiming power
recovery. Both source manifests are 3.6.12. Source synchronization is authorized;
homeowner App store Update and focused live acceptance remain required. CO2
availability notices and separate fridge HA configuration remain outside scope.

See 3.6.12 release notes (historical reference: ../RELEASE_NOTES_3.6.12.md).


## 3.6.11 (private candidate)

- Short family and actionable personal reports; confirmed HP on/off.
- Read-only Zigbee plug plausibility and bounded isolated Tuya recovery.
- Explicit stabilization-schedule invalidation overrides chart rows until confirmed reinstated.
- :15/:45 preparation checks and remaining-window protection for delayed/repeated outages.
- Separate HA fridge protection: below 20%, restore 30%, minimum five minutes off.
- Prepared only; deployment and live acceptance remain separate.

## 3.6.10 private candidate — preparation cadence and messages

Prepared locally, not deployed. The next-outage battery assessment runs on
:00/:30 and immediately on plan change/grid return. Sufficient SOC keeps normal
operation. Conservative solar reduces the DTEK gap; charging starts by its safe
deadline and retains ownership for that exact outage. Persisted intent alone is
insufficient: controller mode and target must also match. Actual charging sends
one family notification; readiness appears in the one-hour reminder. Shared
policy text distinguishes scheduled preparation, Grid Confidence, regional
fault/emergency and manual Panic. Source polling and HP control are unchanged.


## Family Assistant 3.6.8 — Regional declaration correction (prepared)

- Fix false emergency activation from stabilization notices advising readers to
  avoid emergency outages. Match each outage type to its own active declaration.
- Correct the persisted false restriction on the next successful source read,
  including a source revision unchanged since the false classification.
- 544 Family checks passed. Energy Hub and HA configuration stay at 3.6.7.
- Prepared only; no deployment, commit, push or publication in this correction.


## 3.6.7 (private candidate)

- Fresh Xiaomi apartment availability with verified baseline and unknown-on-error.
- Confirmed grid profiles and retained scheduled preparation through brief loss.
- :15/:45 schedule checks and conditional evening retries; fault/emergency policy.
- Concise preparation/restoration messages, private HP details, CO and CO2 labels.
- Four-level confidence dashboard and explicit bounded Facebook failure handling.
- Reliable unattended Facebook ingestion remains unverified; no live deployment.

## 3.6.6 — Coordinated solar preparation release (private candidate)

Family Assistant remains behaviorally unchanged. Its existing forecast snapshot
feeds the new EnergyHub outage-window deficit calculation; notifications consume
the calculated target. Pro Kyiv primary, Alerts.energy backup, notice policy,
apartment monitoring and quiet hours remain as in 3.6.5. Preparation only.

## 3.6.5 — Pro Kyiv and apartment grid proxy (private candidate)

Pro Kyiv schedules/notices are primary; Alerts.energy backs up schedules.
Official website and Telegram polling are disabled. Fault/stabilization follow
validated schedules unless explicitly invalidated; emergencies use existing
Grid Confidence until superseded, even after grid return. Optional powered-hub
availability monitors apartment outages with persisted 120/60-second debounce.
Power-source wording and restoration/strategy notification duplication are corrected.
Prepared only; 3.6.4 is the last homeowner-confirmed running release.
No HA YAML/storage or inverter policy changes.


## 3.6.4 — official fault notices (private candidate)

Recognizes Kyiv-region fault notices and preserves fault/emergency wording.
Banner extraction survives invalid schedule data. Failed source identities are
reported privately; validated mirrors and 30-minute checks remain active.
Prepared only; 3.6.3 is the latest homeowner-confirmed running release.
No HA YAML/storage or hardware-policy changes.


## 3.6.3 — private schedule-source candidate (October 8)

Official DTEK embedded JSON with validated Alerts.energy and Pro Kyiv fallbacks
replaces the active single-mirror reader. Checks remain every 30 minutes; revised
schedules replace reminders and battery-preparation inputs. Current official
banner scope, source failure reporting and restart deduplication are covered.
Prepared only; monitored 3.6.2 remains live. No HA YAML/storage changes.
See release notes (historical reference: ../RELEASE_NOTES_3.6.3.md).

## 3.6.2 — private corrective candidate (October 8)

The newest Kyiv-region emergency notice replaces older district scope and repairs
saved 3.6.1 status without duplicate forwarding. At the house, notices remain
informational with grid available; confirmed grid loss suspends schedules and
confirmed restoration clears the local override. The reserve dashboard reflects
that distinction. No HA YAML changes. Prepared only; monitored 3.6.1 stays live.
See release notes (historical reference: ../RELEASE_NOTES_3.6.2.md).

## 3.6.1 — private corrective candidate (October 8)

Quiet/Eco become mutually exclusive with feedback checks; preserve and restore
pre-night temperature ownership through mode transitions. Compact overnight
HP summaries and today-only morning schedules replace misleading aggregation.
Tomorrow checks run at 20:00/20:30/21:00 with explicit fallback after three
completed failures. Official DTEK text notices provide emergency overrides,
cleared by confirmed local grid restoration. Preparation only; 3.6.0 stays live.
The reserve dashboard separates base reserve and outage preparation targets,
shows the active authority and source freshness, and flags unconfirmed charging.
One-card storage deployment requires fresh comparison and confirmed Core stop.


## 3.6.0 — prepared private candidate

- Replace active Telegram schedule OCR with validated BezSvitla daily HTML;
  poll every 30 minutes, check tomorrow at 20:00 and apply notified revisions.
- Add 15-minute scheduled restoration reminders with refreshed house SOC/HP.
- Use Eco throughout grid absence; preserve Quiet and manual HP OFF.
- Persist manual Panic 95% ownership until explicit cancellation.
- See RELEASE_NOTES_3.6.0.md for separate add-on/HA YAML scopes and acceptance.

## 3.5.3 — prepared 2026-10-07

- Increase full-chart OCR timeout to 20 seconds after the live HA timeout.
- Keep label/cell limits at 5 seconds; clamp HTTP/OCR to the shared 90-second
  read deadline and reject late results while preserving all validation.
- Coordinate both add-on versions; homeowner Reload/Update and live acceptance
  required. No Core configuration or controller behavior changes.
- See release notes (historical reference: ../RELEASE_NOTES_3.5.3.md).

## 3.5.2 — prepared 2026-10-07

- Correct current-day regional DTEK selection and yellow badge OCR.
- Distinguish absent schedules from read failures; private error/recovery notices,
  morning fallback explanation, 30-minute polling and late reminder catch-up.
- Apply regional level II/III weather +20 points for the full applicable day;
  schedule planning replaces grid-confidence/forecast modifiers and includes weather.
- Add-on-only correction; homeowner Reload/Update and runtime evidence required.
- See release notes (historical reference: ../RELEASE_NOTES_3.5.2.md).

## 3.5.1 — prepared 2026-10-07

- Prefill/preserve the dashboard HP address and separate edit verification from connection/recovery status.
- Add bounded single-IP diagnostics and deduplicated family notices after one hour; respect quiet hours and do not assert an IP move from missing HA control.
- Add observed night/restore/Eco morning summaries and explicit unavailable-control evidence.
- Recover DTEK session energy from the dashboard lifetime counters and bounded change-only history; remove outage parentheticals.
- Route recovery notices to Family under configured quiet hours; acknowledge advance pre-night cut notice and support cooling.
- Keep native power-cycle recovery commissioning separate. Includes scoped HA adapter/helper/dashboard changes; not deployed.
- See release notes (historical reference: ../RELEASE_NOTES_3.5.1.md).

## 3.5.0 — prepared 2026-10-07

- Replace fixed-demand/clustered outage planning with the next-outage 40% floor plus 20/10 SOC points per hour, net solar and measured-progress charging deadlines.
- Add one-hour house/apartment reminders; deduplicate acknowledged preparation and ordinary reserve top-up notices, including old morning entries.
- Preserve quiet hours, stale-source and control guards. Features default OFF pending live acceptance; app-only candidate, not deployed.
- See coordinated release notes (historical reference: ../RELEASE_NOTES_3.5.0.md).

## 3.4.1 — prepared 2026-10-06

- Correct the dashboard-threshold Eco solar exception and acknowledged outage/solar recovery notices; report unavailable HP control.
- Coordinate app versions; EH control code is unchanged. HA package reload is a separate scope. Not deployed.

## 3.4.0 — prepared 2026-10-06

- Add official daily outage schedule notices and deadline-aware preparation with solar-first waiting, bounded utility charging and target preservation.
- Preserve source/telemetry/authority guards; new features default OFF pending actual chart/build and live acceptance.
- See the coordinated 3.4.0 release notes and validation record; not deployed or publicly released.

## 3.3.0 — 2026-10-06

- Notify explicit Smart/Solar-only selection once; suppress routine Off and
  individual Quiet/Eco notices. Retire pending messages from earlier versions.
- Summarize observed night targets, running/OFF intervals and yesterday's
  Solar-only operation using current smart-plug counter deltas in kWh.
- Combine Smart Eco context with grid-loss messages and keep meaningful battery
  protection/Solar pause notices; use neutral unknown-cause wording.
- Simplify house-supply wording to DTEK/solar. Telegram remains read-only except
  the existing owner-notice acknowledgement for the HA recovery boundary.


## 3.2.0 — prepared privately

- Distinguish confirmed already-OFF recovery from owner stop requests; disclose
  the fallback cut 15 minutes before configured night start, report progress
  once and defer automatic overnight results until after the morning report.
- Add independent configurable family Telegram quiet start/end and clarify the
  existing morning delivery time. Apply to routine notices and family fallback;
  preserve scheduled report, CO/urgent CO2 exceptions and personal routing.
- Add observed CO2 maximum over the preceding 24 hours; advisory remains1200ppm.
- Report HA target temperatures with Quiet events and overnight manual HP events
  only when attribution is available.
- Move routine Hisense/cloud/TV failures to the morning technical digest;
  normalize Beacon errors and limit repeated personal notices to one per day.
- Add daytime personal HP-recovery requests and delivery acknowledgement;
  HA owns the hardware controls. Overnight requests wait until08:01 and the
  morning report has actually been delivered. No automatic HA reboot.
## 3.1.7 — prepared privately

Stable two-minute Quiet/Eco notifications, condensed overnight profile events,
consistent DTEK/solar-priority wording and separate telemetry-gap/outage labels.
366 tests pass. Not deployed; physical Quiet feedback investigation continues.

## 3.1.6 — prepared privately

Clear Continuous/Scheduled Smart messages, separate HP/plug notices, evidenced
pause reasons, configured PV thresholds and approximate persistent solar session
summaries with unverified-meter labels. 349 tests pass; not deployed.

## 3.1.5 — prepared privately

- Add an approximate 08:00 solar heating/cooling outlook for Solar-only + Continuous.
- Use 600 W start/400 W hold forecast windows; distinguish gaps and unavailable evidence.
- Keep actual control and personal monitoring routing unchanged; 344 tests passed.

## 3.1.4 — prepared locally

- Route solar/plug diagnostics to monitoring, with no family fallback.
- Report direct climate OFF/ON separately from relay power, using evidenced causes.
- Preserve family CO alarms and policy notices; 338 regressions passed.

## 3.1.3 — prepared locally

- Notify observed first-floor plug ON/OFF changes with time and evidenced cause;
  keep silent startup baselines and retry delivery, including overnight.
- Distinguish missing inverter inputs from insufficient solar. Share pause
  episodes and require 120 seconds of running observations before recovery notice.
- Use actual same-BMS current/voltage reports to distinguish unchanged SOC from
  stale telemetry. Invalid or unavailable primary data still fails closed.
- Keep jump baselines and integrate unchanged current when voltage advances;
  repeated reports, source silence and restarts retain conservative boundaries.
- Preserve historical gaps and totals; no capacity claim or BMS setting change.

## 3.1.2 — prepared locally

- Observe effective heating policy and actual Quiet/Eco switches; retire queued
  legacy flag/status messages. Announce initial confirmed solar start, waiting
  and resume without claiming exclusive solar supply.
- Persist cumulative grid-import episode estimates across midnight/reentry;
  missing history, resets and gaps remain explicit. Shorten morning Grid Hold.
- Add bounded, acknowledged manual host recovery advice after correlated
  inverter/Zigbee loss. No automatic reboot or new Supervisor permissions.

## 3.1.1 — prepared locally

- Read a fresh HA snapshot for configured CO2 sensors when preparing the family
  morning report. Show actual local capture time and urgent ventilation threshold.
- Report unavailable for missing, stale, invalid or offline-parent readings;
  preserve existing alert episode timing and the 1200/2000 ppm thresholds.

## 3.1.0 — installed privately

- Add persistent CO2 ventilation episodes and urgent CO alarm delivery.
- Add bounded structured Core log monitoring and authenticated WebSocket fallback
  for the legacy error-log 404; qualify cached counts and redact credentials.
- Include CO2/CO availability, Solar-only waiting/start and configured-address notices.
- Correct installed/prepared status and split prior-version documentation paragraphs.
- Preserve the 3.0.0 BMS journal and existing household monitoring contracts.

## 3.0.0

- Recognize official Kyiv-region frost warnings, including UHMC post 6075.
  Keep frost-only warnings informational rather than inferring a grid threat.
- Notify all three official warning levels, including fog, heat and unclassified
  hazards. Separate this from the grid-risk allow-list and active +20-point
  reserve evidence; display expiry and avoid false reserve-increase wording.

- Add direct configured-device availability monitoring, including the climate
  entity independently of its power plug, with three-minute warnings, five-minute
  recovery, parent masking, restart continuity and a compact morning inventory.
- Record optional BMS evidence before and after SOC jumps, including exposed
  cell voltages, reported capacity/health, and separate observed charge/discharge
  estimates. Persist bounded captures and archive completed events once.
- Keep the existing hardware control runtime unchanged; this is a prepared
  private monitoring candidate, not a deployed release.

## 2.4.15

- Ignore malformed non-object heat-pump restart events and isolate each event
  observer so one broken entity cannot suppress morning reports and other
  queued alerts.
- Send a deduplicated technical warning when EnergyHub reports an unconfirmed
  inverter strategy after failed recovery; clear the latch after a confirmed
  healthy strategy returns.

## 2.4.14

- Suppress and discard obsolete reserve-relative notifications from the current
  load-controller schema, including queued messages after restart.
- Report the current first-floor Quiet heating status to the family.

## 2.4.13

- Name DTEK consistently in household messages and distinguish confirmed
  below-reserve charging, solar-only charging during Grid Hold, and the
  reserve-plus-10 return to solar priority.
- Preserve the reason for automatic reserve changes in the overnight 08:00
  recap; describe forecast error as signed actual-versus-forecast variance.
- Summarize active UHMC hazards in the morning and preserve the official
  event details in daytime notices.
- Read the current Home Assistant Core session's error log via the existing
  Core API. Do not request Supervisor-manager access merely for its log.

## 2.4.12

- Accept unchanged 60-second EnergyHub load-guard heartbeats for up to 90
  seconds; discard only the historical control incidents generated by the old
  30-second gate, preserving independent device and inverter history.
- Distinguish shared input outages from an individual unavailable load in
  technical warnings. A missing device is skipped, not a halt of protection
  for other available devices.
- Include confirmed overnight grid-hold and solar-return events, with times
  and reserve thresholds, in the 08:00 family report.

## 2.4.11

- Replace watt-age availability guesses with actual bridge, device-state and
  device-availability evidence. Reset incompatible pre-fix incident history.
- Report a rolling 24-hour window ending at 08:00, merge poll-level flaps, mask
  child attribution during parent outages, and apply source-specific duration
  thresholds.
- Monitor the Zigbee2MQTT bridge separately and keep unchanged online plug
  power healthy.
- Read and deduplicate both Core and Supervisor warning/error logs through the
  read-only Supervisor API; keep the clean report compact and never call an
  unavailable journal clean. The app manifest now requests `hassio_api` for
  these log reads.
- Show overload trigger and post-action load separately, translate device
  failures, and consolidate attention events from one cycle for 60 seconds.

## 2.4.10

- Color the morning solar forecast against recent consumption and current
  15-minute generation against the agreed 0.3/1.0 kW thresholds, with bold
  values and no duplicate deficit sentence.
- Preserve the official actionable paragraphs in immediate UHMC alerts, keep
  level-1 alerts free of reserve advice, and reduce overnight warnings to one
  line in the 08:00 report.
- Extend warning validity through the last explicitly mentioned date and report
  the level-2/3 +20-point reserve response and validity.
- Combine each DTEK confidence transition with the confirmed, planned, or
  manual Battery Reserve response. Wait briefly for the matching reserve
  evaluation, then fail visibly instead of suppressing the transition forever.
- Remove five retired saved-option values operationally by re-saving the app's
  current configuration after update; the retired code paths remain absent.

## 2.4.9

- Replace the compact ownership sentence in the morning report with separate
  Automatic and Manual control lines.
- When Smart Heating is later enabled, identify only the first-floor heat pump
  as EnergyHub-controlled and keep the second- and third-floor units manual.

## 2.4.8

- Shorten the 08:00 family report and HA restart summary, use the clear DTEK
  label, and emphasize active official weather/grid-support conditions.
- Omit routine humidity, UHMC all-clear, automatic-reserve recommendation, and
  overnight Grid Hold repetition from the family report.
- Add one compact current-control line for inverter, minimum-reserve, and
  overload authority, followed by the heating authority.
- Add a private 24-hour Home Assistant Core warning/error digest to the 08:00
  technical report, deduplicated by logger and message.
- Remove retired Hybrid target and three-morning reserve-advisor app options and
  read paths.
- Keep the retired SOC snapshot and night-start keys as ignored schema-only
  compatibility options so existing installations upgrade without recurring
  Supervisor warnings.

## 2.4.7

- Remove the obsolete 07:00 SOC/night-import snapshot scheduler, its add-on
  options, and persisted legacy state. The 08:00 report reads current SOC and
  operating mode directly when it is prepared.

## 2.4.6

- Streamline the 08:00 report with current operating mode, current battery SOC,
  and 15-minute average PV power; remove the duplicate 07:00 SOC/night-import
  block.
- Add conservative daily grid-support hours and EV potential after house demand,
  battery recharge to 100%, and configured conversion losses. The 30 A battery
  and 16 A house assumptions are configurable and are not hardware limits.
- Report solar-forecast accuracy only for completed days when the battery never
  reached 100%.
- Move tariff detail to a completed previous-week summary on Monday and a
  completed previous-month summary on the first day of a month.
- Omit reserve recommendations while automatic EnergyHub ownership is active,
  and add current SOC to the delayed Home Assistant restart summary.

## 2.4.5

- Keep the family chat silent from 23:00 until the 08:00 morning report, with a
  short overnight event digest in that report and a delivery buffer through
  08:01. Private technical-chat diagnostics remain immediate.
- Shorten the current Grid Hold status to one line and suppress repeated
  Grid Hold notifications within the same reserve episode, including persisted
  2.4.4 state migration after update or restart.
- Split current-month grid import into night and normal tariff energy and cost,
  followed by the combined monthly total.

## 2.4.4

- Require one continuously confirmed minute of grid loss before sending the
  grid-outage notification, and emit heat-pump reserve warnings only while that
  confirmed outage remains active. Drop a queued reserve warning when reliable
  grid voltage returns.
- Report Home Assistant's guarded restoration of remembered first- and
  second-floor heat-pump plug states. After the one-minute appliance startup
  window, include measured watts and distinguish active consumption from an
  enabled but idle appliance.

## 2.4.3

- Replace obsolete EnergyHub 2.1 Dry Run and Effective Reserve option wording
  with the current Battery Reserve and confirmed protection terminology.
- Keep the established `weather_buffer_entity` option and entity ID for saved
  configuration compatibility; only its user-visible presentation changes.
- Document that the 23:52 and 05:00 calculations update Battery Reserve forecast
  evidence rather than activating a separate night-control strategy.

## 2.4.2

- Make `technical_chat_id` truly optional in the Home Assistant app manifest so
  upgrades from versions that did not have the option can start normally.
- Tell the family when the applied minimum Battery Reserve moves the house to
  Grid Hold, including the live SOC and `reserve + 10` Solar-return threshold.
- Tell the family when a confirmed, fresh Grid Hold returns to Solar, including
  the live SOC and threshold that was reached. A grid-outage fallback to Solar
  does not claim that the reserve release condition was met.

## 2.4.1

- Add an optional private technical chat and route SOC anomalies, data-source
  incidents, command-attention events, restart diagnostics, and the morning
  technical report away from the family group.
- Notify the family after a confirmed transition to Grid Hold, including the
  applied reserve and its dynamic `reserve + 10` Solar release threshold.
- Confirm a startup-time grid outage after debounce instead of silently using
  it as the initial baseline.
- Name only appliances whose OFF action EnergyHub confirmed, and state the
  applicable battery or overload restoration condition.

## 2.4.0

- Report Battery Reserve Manual/Automatic authority changes and manual reserve
  changes; retain the existing confirmed automatic-change message.
- Report manual Smart Heating and Solar-only Heating changes after a stable
  transition.
- Report EH first-floor heating states as short Manual, Waiting, Solar paused,
  Eco, Normal or one-hour Turbo messages.
- Include the active Smart Heating ownership mode in the HA restart summary.

## 2.3.1 - 2026-09-12

- Delay the HA restart summary until current-boot EnergyHub reserve and
  protection evidence is ready, with a five-minute maximum wait.
- Mark unresolved reserve or battery-protection state explicitly instead of
  presenting retained pre-restart state as restored.

## 2.3.0 - 2026-09-12

- Describe Grid Confidence changes without repeating the removed fixed daytime
  reserve ladder; EnergyHub now publishes the resulting Battery Reserve.
- Add one concise family warning at 50% during a grid outage and explain the
  fixed 40% disconnection and 60% restoration thresholds.
- Report the schema-5 discharge-protection policy in the Home Assistant restart
  summary and support Manual versus Automatic Battery Reserve ownership.

## 2.2.7

- Poll the public UHMC source hourly; retry once after five minutes and warn the
  family once when both attempts fail.
- Send morning diagnostics first as a separate message, followed by the shorter
  family-facing energy and weather report; omit diagnostics when there are none.
- Expand the post-restart summary with battery discharge protection and current
  manual heat-pump authority.

## 2.2.6

- Distinguish confirmed battery-preservation stops from inverter overload.
- Suppress legacy reserve-offset relay warnings when the schema-4 controller is present.
- Report unavailable battery-protection participants without claiming successful OFF.

## 2.2.5

- Shared data incidents: warn once after three minutes missing, recover only after
  five continuously observed healthy minutes; keep flaps in the same incident.
- Group simultaneous sources, retain timers/delivery state across restart and
  deliver HA-loss warnings outside the HA-dependent monitoring block.
- Readiness fluctuations no longer generate repeated overload ON notifications.
  Real dashboard ON/OFF changes and operational safety events remain separate.
- Morning summaries show prolonged/repeated data interruptions and distinct-day
  battery-jump recurrence. Missing historical days are never inferred.
- Notification changes only: no control threshold, ownership or inverter changes.

## 2.2.4

- Send one compact HA restart summary after a one-minute settling period, with
  strategy/Autopilot, selected battery minimum/authority and effective overload state.
- Persist boot deduplication, consolidate startup toggle notices, and refresh queued
  summaries at delivery. Bot-only restart does not invent an HA restart.

- Add a short morning UHMC status immediately after weather: no warnings today,
  warnings present, or current data unavailable. Level I warnings still count.
- Persist the source snapshot; stale, missing or malformed evidence cannot produce
  an all-clear. Tomorrow-only warnings do not count as today's warnings.
- No changes to reserve calculations, control or the separate Threat Monitor.

## 2.2.3

- Explain five minutes below 50% and one-minute sequential restoration in Ukrainian.
- List owned OFF loads after a five-minute data outage; ask for checked manual action.

## 2.2.2

- Short Ukrainian Autopilot and overload mode-change notifications, with readiness checks.
- Silent initial baseline, persisted deduplication, stable transitions and obsolete queue suppression.
- No changes to EnergyHub hardware control or Battery Reserve calculation.

## 2.2.1

- Short production overload warnings/recovery in Ukrainian; no false switching claims.
- Suppress retained and queued old trial advice while preserving live action notifications.
- Battery Reserve policy and messaging are unchanged by this correction.

## 2.2.0

- Short Ukrainian confirmed overload actions; suppress duplicate completion notifications.
- Notify only new valid reserve targets different from the manual setting; revalidate queued advice.
- Compact night import, morning battery/minimum and neutral battery-jump messages.
- Preserve raw diagnostic evidence and leave automatic reserve control disabled.

## 2.1.8

- Replace older UHMC warnings covered by a newer same-region/source warning
  with all previous hazards and equal/higher severity over the remaining period.
- Retain the last 100 superseded records separately from active evidence;
  omit replaced warnings from the pending morning digest. Preserve unrelated,
  longer-running or more severe warnings and existing duplicate suppression.

## 2.1.7

- Shorten daytime UHMC warnings to hazard/severity, current Battery Reserve
  with advisory status, and source link. Do not repeat the full policy explanation.
- Missing/stale evidence explicitly means insufficient data; preserve higher
  manual choices and never claim that a recommendation has been applied.
- Keep warning detection, deduplication, quiet hours and morning scheduling unchanged.

## 2.1.6

- Use Ukrainian Battery Reserve and strategy descriptions; separate charging
  from grid hold and historical overnight activity from current strategy.
- Explain the current night/day tariff and target using fresh read-only data.
- Preserve schedules, quiet hours, queue/deduplication state and manual ownership.

## 2.1.5

- Explain reserve conditions in Ukrainian without asking to replace or restore a
  family's manual choice. Deduplicate on conditions, not slider changes.
- Preserve quiet hours and remove obsolete queued restoration advice.

## 2.1.4

- Preserve all 2.1.3 presentation changes.
- Drain the EnergyHub Peak Load Guard journal in order, deduplicate by stream
  and event, and include cycle identity in recommendations/recoveries.
- Keep morning observations but omit the older competing reserve advice when
  the new policy is present; use Battery Reserve wording.
- Report reserve-target changes during the day, with 05:00 changes left for
  the 08:00 report; never claim that a recommendation changed a setting.
- Reject ambiguous multi-region/severity weather evidence and missing source
  timestamps; scope explicit cancellations instead of interpreting ordinary
  'not expected' forecast wording as a cancellation.
- Threat Monitor and inverter control are unchanged.

## 2.1.3

- Keep daytime UHMC alerts to severity, area/hazard, reserve guidance, dry-run
  status, and source link; omit the copied forecast body.
- Label monthly grid import explicitly, show the estimate symbol, and hide zero
  monthly consumption. Remove the separate tariff disclaimer.
- Summarize the largest morning SOC anomaly in one informational line with
  minute precision; make no claim about BMS recovery time.
- Compact manual heat-pump and unchanged/proposed AHM wording. Preserve reserve
  calculations, modifier reasons, and the existing three-morning advisor.

## 2.1.2

- Read the public official `uhmc1921` Telegram preview, normalize active
  Kyiv/Kyiv-region infrastructure warnings, and publish retained structured
  evidence to EnergyHub through Home Assistant MQTT. Preserve active warnings
  across preview pagination and restart; treat source failure as Unknown.
- Handle warning duplicates, edits, cancellations, explicit validity, expiry,
  and the conservative 12-hour fallback. Include road ice; exclude fog, heat,
  ordinary cold, and warnings for other regions.
- Report yesterday's consumption together with EnergyHub's average of up to
  three newest valid completed days and use that average for the forecast
  comparison.
- Report official UHMC warnings received overnight in the 08:00 report and
  send new daytime warnings immediately in Ukrainian. Level II–III messages
  explain the Effective Reserve recommendation; Level I remains information.
- Explain forecast, Grid Confidence, and weather modifiers while stating that
  EnergyHub 2.1 is Dry Run and changed no AHM setting.
- Preserve an overnight weather-reserve restoration for the next morning
  report; send the same explanation immediately when restoration occurs by day.
- Omit `line fail warning` incidents from the morning inverter-history block;
  existing immediate grid-loss and recovery messages remain unchanged.

## 2.1.1

- Observe each new retained EnergyHub SOC anomaly after a silent startup
  baseline and send an immediate Ukrainian diagnostic message with its
  electrical and operating context.
- Persist anomaly deduplication and use the existing durable delivery queue so
  an app restart does not replay an old event or lose an already queued alert.
- Summarize SOC anomalies since the previous successfully delivered morning
  report, while preserving any event that arrives during report delivery.
- State explicitly that this observation release does not filter SOC or change
  EnergyHub control decisions.

## 2.1.0

- Include the persisted 05:00 EnergyHub Weather Buffer decision in the normal
  08:00 Ukrainian family report.
- Explain activation, continuation, missing forecast evidence, and restoration
  while stating explicitly that Dry Run changed no AHM setting.
- Render EnergyHub's temporary 40/30/20 Peak Load Guard trial thresholds in
  Ukrainian recommendation and restoration messages.
- Remain outbound-only; the bot has no Home Assistant, smart-plug, or inverter
  control command.

## 2.0.0

- Observe the EnergyHub Peak Load Guard event entity and send immediate
  Ukrainian family-group explanations for shed, restore, and no-candidate
  recommendations.
- Identify the feature as Dry Run and state explicitly that EnergyHub switched
  nothing.
- Persist the last observed event ID and use the existing durable notification
  queue, without adding Home Assistant, smart-plug, or inverter control.

## 1.3.18

- Simplify the Family Calendar digest to current-day events only.
- Reproduce event titles exactly, without birthday or anniversary inference.
- Prefix timed events with local `HH:MM`; show all-day titles without an
  `all day` label or other classification.

## 1.3.17

- Correct the local-app manifest so Home Assistant displays the optional
  password-masked private iCal URL in the visual configuration form.
- Preserve all 1.3.16 calendar, smart-plug, weather, energy, and notification
  behavior without changing any control boundary.

## 1.3.16

- Add an optional read-only Google Family Calendar section to the scheduled
  08:00 digest using its private iCal feed, stored as a masked local option.
- Show all current-day events in chronological order and warn one day ahead
  only for deterministic special dates: birthdays, anniversaries, and
  name-only all-day events (treated as birthdays).
- Avoid Google OAuth credentials and refresh tokens entirely. Fetch only the
  secret HTTPS iCal feed, never log its URL, cap responses at 5 MiB, and expand
  recurrence rules and exclusions using pinned RFC 5545 libraries.
- Preserve the morning weather and energy report if calendar retrieval fails.
- Check the six configured smart-plug switch entities at 08:00 and report only
  unavailable, unknown, or missing plugs. Do not infer availability from power
  usage or issue any plug command.

## 1.3.15

- Remove per-version test previews and the visible test label; only the
  scheduled 08:00 report remains.
- Compare every temperature/humidity sensor only with its own approximately
  same-hour reading from the previous day. Report persistent changes of at
  least 5 °C or 20 percentage points once, with old/new values and direction,
  and do not call the new value abnormal or send a numeric recovery.
- Preserve separate unavailable, stale, unchanged-for-24-hours, low-battery,
  and connectivity-recovery reporting.
- Omit zero-value operational-night and previous-day tariff rows, omit the
  entire previous-day block when import was zero, and show one combined
  current-month total in Ukrainian hryvnia notation.
- Add conditional 24-hour grid availability and non-Normal Grid Confidence
  lines, a yellow solar-deficit comparison against yesterday's consumption,
  and a yellow marker when AHM suggests changing the selected minimum.
- Show forecast humidity only when it is low, high, or changes materially;
  use yellow attention markers for forecast-derived weather warnings.
- Keep Google Family Calendar integration outside this version.

## 1.3.14

- Join the coordinated EnergyHub public release train. This version contains
  the previously validated 0.2.4 outbound reporting behavior with no new
  command, device-control, or inverter-control capability.
- Keep completed-yesterday and current-month estimated tariff summaries,
  inverter diagnostics, household sensor health, and reserve notifications.
- Align trusted-grid ownership with EnergyHub's physical-grid threshold:
  Normal Grid Confidence, fresh telemetry, and voltage above 180 V.
- Persist the exact logical morning report before delivery and retry it after
  restart. Delivery remains at-least-once because Telegram offers no
  idempotency key for the crash-after-acceptance window.
- Add English and Ukrainian metadata for every tariff option and describe an
  unsuggested AHM value as the current minimum rather than a recommendation.
- Remove an unused Home Assistant weather-discovery method.

## 0.2.4

- Add completed previous-calendar-day estimated night/normal Grid Import and
  UAH cost to the morning report.
- Add current-month night, normal, total import, and estimated cost.
- Omit the tariff section when any required finalized sensor is unavailable
  and label all results as informational rather than billing-grade.

## 0.2.3

- Omit the expected overnight `pv_loss_warning` condition from inverter
  morning-report messages while retaining any other message in a mixed event.
- Format incident durations as seconds below one minute, minutes and seconds
  below one hour, and `HH:MM:SS` from one hour onward.

## 0.2.2

- Add previous-day inverter messages from EnergyHub 1.3.10 to the morning
  report, including available load, operating-mode, grid, duration, and clear
  evidence.
- Avoid claiming an automatic inverter restart when only QPIWS clearance is
  observed.

## 0.2.1

- Report a sensor as suspected offline when both its temperature and humidity
  values remain unchanged for the configured 24-hour freshness window, even
  when Home Assistant continues reporting cached numeric states.
- Collapse accumulated recovery events into one line per physical sensor and
  name whether availability, unchanged values, temperature, humidity, or
  battery recovered.

## 0.2.0

- Added five-minute availability and freshness checks for seven configured
  temperature/humidity sensors.
- Added persistent one-hour temperature and humidity outlier candidates using
  the six-sensor indoor median and same-hour previous-day observations; the
  basement remains outside the indoor peer group.
- Added low-battery reporting for verified sensor battery entities and an
  optional Xiaomi doorbell battery entity at or below 10%.
- Added active issues and one-time recovery lines to the 08:00 report without
  granting the Telegram app any control capability.
- Use an explicit blank default for the optional doorbell entity so existing
  installations can upgrade without a missing-option validation error.

## 0.1.9

- Send SOC reserve warnings only while at least one configured heat pump is
  drawing more than the configured 50 W activity threshold.
- Include the floor and current power of every active heat pump in the warning.
- Suppress reserve warnings from 00:00 through 08:01 and defer any already
  queued reserve warning until the daytime delivery window.

## 0.1.8

- State clearly in the morning report whether heat pumps are under family
  manual control or EnergyHub reserve protection.
- Derive heat-pump thresholds from the selected AHM minimum.
- Send persisted downward-crossing SOC warnings at minimum +30, +20, +10,
  and +0 percentage points.
- Rearm each warning only after SOC recovers two percentage points above its
  threshold, avoiding repeated messages near a boundary.

## 0.1.7

- Add today's sunrise and sunset from Home Assistant Sun.
- Show the Moon line only for new moon or full moon.
- Add the expected Solcast peak power and time.
- Show the AHM advisor's suggested minimum and its existing three-morning learning progress.
- Keep wind information conditional on the configured strong-wind warning threshold.

## 0.1.6

- Observe the actual minimum battery SOC from 07:00 through 12:00.
- Show EnergyHub's centralized three-morning AHM reserve advice, including learning progress and one-step increase/decrease suggestions, without changing the slider automatically.
- Distinguish the current partial morning from the previous completed morning in recommendation wording.

## 0.1.5

- Clarify whether grid reliability improved or deteriorated.
- Rename the notification value to the clearer `Цільовий запас батареї вдень` and explain whether EnergyHub retains more reserve or may use more battery.

## 0.1.4

- Notify the family group when external grid power disappears and recovers.
- Include outage start/recovery time, persisted duration, and current SOC when available.
- Notify on valid Grid Confidence transitions and explain the corresponding 20/60/80/95% daytime Panic reserve target.
- Debounce grid voltage for 30 seconds and persist a Telegram retry queue across network failures and restarts.

## 0.1.3

- Format daily minimum and maximum temperatures as clear whole-number bounds: `від +15 до +30 °C`.

## 0.1.2

- Try every available weather entity until one supplies an hourly forecast.
- Fall back to a daily forecast when no provider supports hourly data.
- Include Home Assistant's validation response in weather API error logs.

## 0.1.1

- Replaced the nullable weather-entity default with the explicit `auto` value so Home Assistant configuration validation succeeds.

## 0.1.0

- Initial independent family-assistant app.
- Captures actual battery SOC and EnergyHub target at 07:00.
- Sends a Ukrainian morning report at 08:00.
- Includes weather condition, temperature, precipitation, forecast-derived bad-weather warnings, Solcast forecast, useful-solar window, yesterday's consumption, night mode, and estimated 23:00–07:00 grid import.
- Persists snapshots and retries Telegram delivery after temporary network failures.

## Family Assistant 3.6.16 — official primary candidate

Official Kyiv-region DTEK is tried first on each scheduled read. Validated
Pro Kyiv and Alerts.energy remain automatic fallbacks per date. Publication
rollback, missing groups, invalid dates/slots and access challenges fail to
fallback; an error never means no outages. The legacy trial option now controls
extra diagnostics only. The official attempt remains bounded to 20 seconds;
there is no bypass, address submission or hardware command.

Development-host access currently encounters an access challenge. HA-host
access still needs live verification. This candidate changes only the Family
add-on; no HA Core restart is required. See RELEASE_NOTES_FAMILY_3.6.16.md.

## Prepared 3.6.17 — outage coverage and mirror schedule reading

Release scheduled grid hold using the uncapped remaining-window requirement plus
2 percentage points, independently of the 95% charging cap. Valid end revisions
preserve ownership, failed saves issue no commands, and acknowledged Solar resumes
ordinary BR while coverage monitoring continues. The existing dashboard explains
remaining duration/coverage/reason; Family sends a short confirmed release message.
Official DTEK transport is removed; Pro Kyiv primary and Alerts.energy backup remain.
Manual/stale/grid guards and commissioning restrictions remain. Prepared, not
synchronized, deployed, committed or published. See RELEASE_NOTES_3.6.17.md.

## 3.6.18 private candidate — October 15, 2026

Prepared locally; running 3.6.17 remains unchanged. The coordinated candidate
adds a shared dashboard grid DC current reference, observed-house solar coverage,
acknowledged precharge completion and signed SOC restoration rates, clearer
morning/outage messages, delayed Solcast incident/recovery notices with source
timestamps, and a persisted hourly/nightly Quiet ON budget. Both add-ons and the
reviewed HA package/automation/dashboard scope require coordinated deployment.
No commit, push, synchronization, restart or public release is implied.
See the repository release notes and private validation record for calculation
assumptions, cold-start fallback, tests and commissioning requirements.
