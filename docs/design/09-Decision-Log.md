# EnergyHub Decision Log

This document records durable architectural and product decisions. Dates are approximate milestone dates; Git history is authoritative for implementation detail.

## D001 — Home Assistant is the integration and user-experience platform

**Status:** accepted.

Home Assistant owns helpers, schedules, scripts, household automations, notifications, and dashboards. EnergyHub does not recreate those platform capabilities.

## D002 — Prefer local communication

**Status:** accepted.

Inverter telemetry and control use local USB-RS232. MQTT is local. Cloud forecast data is an input, not the control plane.

## D003 — PI30MAX is the current PowMr interface

**Status:** accepted.

EnergyHub supports the verified command set of the installed PowMr 10.2M through `mpp-solar`.

## D004 — Decision logic and hardware execution are separate

**Status:** accepted.

Decision services select strategy and target. Inverter Controller executes and confirms transitions.

## D005 — Vendor independence is a direction, not a current claim

**Status:** accepted.

Current code is PowMr-specific. Future adapters should expose capabilities without weakening present reliability.

## D006 — Grid Confidence is derived from recent history

**Status:** accepted.

Grid Confidence uses the average of 24-hour and 48-hour availability and maps it to normal, unstable, risk, or panic.

## D007 — 1.0 operating strategies are Solar, Hybrid Charging, Hybrid Grid Hold, and Panic

**Status:** accepted.

These are household strategies, not raw inverter menu names.

## D008 — Manual Panic and automatic Panic are different intents

**Status:** accepted.

Manual Panic targets 95%. Automatic Panic targets 80% or 95% according to Grid Confidence and reserve conditions.

## D009 — Automatic strategies are reversible

**Status:** accepted.

Solar is the default and recovery strategy. Automatic modes have explicit exits.

## D010 — Hybrid is evaluated once at 23:50

**Status:** accepted.

Home Assistant supplies the scheduled trigger. EnergyHub evaluates current SOC, today's consumption, and tomorrow's live forecast.

## D011 — MQTT is the integration bus

**Status:** accepted.

EnergyHub publishes Discovery, state, and events. Home Assistant publishes controls and forecast inputs.

## D012 — `main.py` remains an orchestrator

**Status:** accepted with technical debt.

It may coordinate services and lifecycle but should not absorb new policy calculations indefinitely.

## D013 — EnergyHub owns inverter strategy execution

**Status:** accepted.

Home Assistant requests strategies; it does not directly send POP/PCP commands.

## D014 — EnergyHub optimizes policy, not individual device scripts

**Status:** accepted.

Device-specific household automations remain in HA until a real EnergyHub service owns the capability.

## D015 — Menu 01 is approved for autonomous use

**Status:** accepted.

Mappings:

- SUB → POP01;
- SBU → POP02.

A write is successful only after QPIRI read-back matches the expected value.

## D016 — Menu 16 is approved as ACK-confirmed state

**Status:** accepted with hardware limitation.

Mappings:

- SNU → PCP01;
- OSO → PCP02.

The inverter provides no supported read-back query. EnergyHub persists the last successful ACK-confirmed value.

## D017 — Hybrid uses a two-stage strategy

**Status:** superseded by D041 for 1.3.0.

Hybrid Charging reaches 80% SOC, then Hybrid Grid Hold preserves the battery while the house remains on the cheap grid until 07:00.

## D018 — Panic is reevaluated during the day

**Status:** superseded by D042 for 1.3.0.

Evaluation occurs every 15 minutes from 12:00 until 23:50 while Solar is active.

## D019 — Notifications originate from EnergyHub events

**Status:** accepted.

Home Assistant renders persistent notifications from `energyhub/event/notification`.

## D020 — Grid Import is estimated inside EnergyHub

**Status:** accepted.

The inverter lacks reliable import telemetry. EnergyHub estimates house energy during SUB plus positive battery SOC gain.

## D021 — Grid Import follows confirmed strategy intervals

**Status:** accepted.

Accounting is enabled for confirmed Hybrid Charging, Hybrid Grid Hold, and Panic, rather than inferred only from instantaneous voltage.

## D022 — Grid Import state is persistent and versioned

**Status:** accepted.

Schema migration may discard an incompatible current-day estimate rather than silently combine incompatible accounting models.

## D023 — Flexible-load automation must preserve ownership

**Status:** accepted for future work.

EnergyHub may stop a flexible load only when EnergyHub previously started it.

## D024 — Remove Away Mode and replace the concept with Smart Thermal Energy

**Status:** accepted and implemented for 1.0 cleanup.

The old runtime implementation, helpers, and dashboard control were removed. Future thermal optimization works regardless of occupancy.

## D025 — Home Assistant configuration is selectively versioned

**Status:** accepted.

Version controlled items include YAML config and selected `.storage` helpers/dashboard resources. Secrets, entity registry, runtime databases, and unrelated state are excluded.

## D026 — HA synchronization is bidirectional in the workflow

**Status:** accepted.

Git-to-HA deployment and HA-to-Git synchronization are separate explicit operations followed by review.

## D027 — Raw inverter and EnergyHub diagnostic availability are separate

**Status:** accepted and implemented.

Raw sensors require `energyhub/status` and `powmr/status`. Diagnostics require only EnergyHub process availability.

## D028 — Live forecasts and historical snapshots are separate inputs

**Status:** accepted and implemented.

Live Solcast values update decision inputs. Scheduled Daily Summary values create historical snapshots only through one atomic payload.

## D029 — Daily Summary snapshots are atomic

**Status:** accepted and implemented.

Sequential retained input messages may update stored inputs but never create a snapshot. The 23:51 JSON payload is the snapshot boundary.

## D030 — Midnight Grid Import finalization is a persistent hand-off

**Status:** accepted and implemented.

Grid Import queues the completed day; Daily Summary reconciles it; Grid Import
acknowledges only after a non-invalid result. `updated` and `unchanged` are
idempotent successes. `missing` is a terminal reconciliation result because a
scheduled historical snapshot cannot appear later; the completed value remains
in Grid Import history and the condition is logged. Invalid input stays queued.

## D031 — Restart strategy reconstruction combines physical and remembered state

**Status:** accepted and implemented.

Use actual Menu 01, remembered ACK-confirmed Menu 16, persisted mode, and Panic target. Do not use clock time as the source of truth.

## D032 — Safe Solar queue requests have priority

**Status:** accepted and implemented.

The MQTT callback and main loop share a lock-protected queue. Ordinary requests cannot overwrite a pending safe Solar recovery.

## D033 — Existing MQTT unique IDs are preserved during naming cleanup

**Status:** accepted and implemented.

The finalized Daily Summary Grid Import entity was renamed in the HA registry without deleting/recreating it, preserving history and unique ID.

## D034 — Unchanged load is diagnostic, not freshness evidence

**Status:** accepted and implemented.

Telemetry freshness depends on valid telemetry age. `House Load Unchanged` remains informational.

## D035 — Activation notifications require transition success

**Status:** accepted and implemented.

A decision being queued is not an activation. Success or failure is published only after Inverter Controller returns.

## D036 — Persistence is atomic and routine writes are throttled

**Status:** accepted and implemented.

Critical boundaries save immediately. Incremental Grid Import and raw telemetry snapshots are limited to approximately one write per minute.

## D037 — No fake Smart Thermal switch in 1.0

**Status:** accepted.

The dashboard may show the planned capability, but no active helper exists until a real controller is implemented.

## D038 — Visual language is consistent across charts and dashboards

**Status:** accepted.

- orange: solar;
- blue: house load/consumption;
- green: battery/healthy/online;
- purple: grid import or technical load;
- red: temperature risk, failure, or emergency.

## D039 — Documentation is updated after code and UI stabilization

**Status:** accepted.

Current-state documentation is audited once after coherent functional and dashboard changes, reducing transient contradictions.

## D040 — EnergyHub 1.1 limits Smart Loads to monitoring and reserve-only OFF guards

**Status:** accepted.

EnergyHub 1.1 combines real-world 1.0.2 corrections with the first Smart Loads work. Zigbee2MQTT owns the SONOFF coordinator and device transport. Home Assistant owns pairing, manual controls, dashboards, timers, local energy integration, and the narrow reserve-only OFF automations. The EnergyHub inverter runtime remains unchanged.

EnergyHub 1.1 never turns the boiler or a heat pump on. The water-boiler guard and grid-confidence-aware heat-pump guard may request OFF at documented reserve thresholds and reject ON while an emergency lockout is latched. Missing or stale EnergyHub telemetry produces no command. Automatic Smart Thermal ownership, starts, comfort decisions, surplus use, minimum runtime, and compressor cooldown remain deferred to 2.0.

The 2026-08-02 Ember `ASH_ERROR_TIMEOUTS` failure stopped Zigbee2MQTT while the Home Assistant app Watchdog was disabled. An attended manual Start on 2026-08-03 recovered the same network, both devices and states, MQTT, availability, and Home Assistant discovery without re-pairing or an observed relay command. On 2026-08-05, ASH reset but EZSP startup failed with `HOST_FATAL_ERROR`; Zigbee2MQTT exited while Watchdog was enabled and no autonomous recovery was observed. On 2026-08-06, Supervisor Watchdog made ten restart attempts after another `ASH_ERROR_TIMEOUTS`, but every attempt failed to establish ASH/EZSP and the crash loop stopped. App Watchdog alone is therefore not an accepted recovery mechanism for this failure mode.

Bridge/device availability recovery does not make retained electrical values intrinsically fresh. Automatic control may resume only after bridge and device availability, fresh post-recovery inputs, and ownership state are all confirmed; an online flag alone is insufficient. Smart-plug electrical telemetry is operational trend data unless separately calibrated and must not replace load-rating, nameplate, or protection checks.

## D041 — AHM uses aligned post-07 energy and owns 23:50

**Status:** accepted and implemented for 1.3.0.

AHM excludes the cheap-grid night interval from expected battery demand, projects today's consumption onto 07:00–24:00, compares it with tomorrow's hourly solar over the same interval, and uses the larger of morning-gap or daytime-deficit SOC. AHM is authoritative at 23:50 and may overtake Panic Charging or Panic Grid Hold.

## D042 — Panic is simple, conservative, and grid-opportunity aware

**Status:** accepted and implemented for 1.3.0.

Automatic Panic uses fixed Grid Confidence targets of 20/60/80/95% for normal/unstable/risk/panic. It does not require a solar shortage. It can be armed while grid is absent, charges when grid returns, and preserves recovered reserve in Panic Grid Hold until AHM takes ownership.

## D043 — Only a missed morning AHM target becomes Panic debt

**Status:** accepted and implemented for 1.3.0.

The persisted AHM target is compared with actual SOC at the first daytime evaluation after 07:00. Only a real shortfall is stored as dated debt. The debt survives restart, clears after recovery, and is not recreated later from normal daytime battery discharge.

## D044 — AHM minimum reserve is user-selected and ramp credit is verified

**Status:** accepted and implemented for 1.3.1.

AHM replaces the hidden fixed 20% reserve plus 10% margin with a visible 20–50% Home Assistant minimum-reserve setting. The first 300 W forecast remains the raw solar threshold. A following hourly forecast of at least 600 W may advance effective support by one hour, but the EnergyHub add-on independently verifies both retained power values before applying the credit. Panic remains governed by separate Grid Confidence targets.

## D045 — Learned essential morning load supersedes fixed hourly SOC after confidence

**Status:** accepted and implemented for 1.3.2 monitoring.

EnergyHub learns 07:00–12:00 essential load from total-house energy deltas minus all three heat-pump energy deltas. It retains 21 days, uses the per-interval 75th percentile, and requires three valid samples for every interval before the flexible model becomes authoritative. Solar takeover requires two consecutive forecast hours to cover expected essential load. The verified 1.3.1 300 W → 600 W ramp model remains authoritative while learning or forecast inputs are incomplete. The AHM minimum slider remains the user-selected residual reserve and is never changed automatically.

## D046 — AHM reserve advice uses three completed mornings

**Status:** accepted and implemented for 1.3.2 monitoring.

EnergyHub compares the 07:00–12:00 minimum SOC only across mornings recorded at the current AHM slider value. It suggests an increase after at least two of three low-margin mornings, a decrease only after three high-margin mornings, and otherwise keeps the setting. Advice moves one named 20/30/40/50% step, is shared with the dashboard and Telegram, and never changes AHM or Panic automatically.

## D047 — Projected 07:00 SOC gates night-grid use

**Status:** accepted and implemented for 1.3.3.

AHM remains Solar when projected 07:00 SOC meets or exceeds the calculated target. It selects Hybrid Grid Hold only when current SOC is already at or above target but the conservative overnight projection crosses below it, and Hybrid Charging when current SOC is below target. At 23:50 AHM still takes ownership from Panic and restores Solar when grid support is unnecessary.

## D048 — Roadmap prioritizes verified physical value before conversational and economic expansion

**Status:** accepted on 2026-08-14.

The planned sequence after EnergyHub 1.3.4 is:

1. EnergyHub 1.3.5 — verified read-only PV2 telemetry and derived Total PV;
2. EnergyHub 2.0 — Fault-Aware Smart Thermal and Flexible Loads, beginning with fault/recovery evidence and observer-first Peak Load Guard behavior;
3. EnergyHub 3.0 — Telegram-first conversational access for explanations and structured safe intents, including voice messages;
4. EnergyHub 4.0 — multiple configurable cheap-tariff intervals, with optional day-ahead import-price support later;
5. EnergyHub 5.0 — additional verified inverter adapters and optional Net Billing/export optimization for compatible hardware, contracts, and markets.

Configuration validation, forecast fallback, dependency health, diagnostics, recovery, and replay remain cross-cutting engineering requirements rather than a separate release theme. Telegram or another messenger is an interface to EnergyHub's validated intent boundary, not a proxy for raw inverter commands. Net Billing is an optional ecosystem capability and does not replace the core positioning around adaptive solar planning, smart tariff use, and outage-ready reserve.

## D049 — Startup replaces incompatible retained Hybrid reason state

**Status:** accepted, implemented, and deployment/startup-validated in the
private 1.3.6 build.

Home Assistant Core 2026.8.1 exposed a retained pre-1.3.4
`hybrid_decision_reason` whose 355 characters exceeded the 255-character state
limit. The next scheduled AHM evaluation replaced it with the current concise
summary and control behavior remained correct.

EnergyHub 1.3.6 publishes the concise initial Hybrid state after Discovery on
every app start, retaining the replacement for later Home Assistant restarts.
The publisher also limits the reason to 255 characters as a final compatibility
boundary. Full calculation diagnostics remain separate, and this migration does
not alter AHM, Panic, or inverter-control decisions.

## D050 — Flexible-load reserve bands follow the selected AHM minimum

**Status:** implemented, deployed, and privately monitored in EnergyHub 1.3.8.

The homeowner-selected 20–50% AHM minimum is the common preference baseline
for participating heat-pump protection. While Grid Confidence is Normal, the
grid is physically present, and telemetry is fresh, the family retains manual
control. Otherwise one-time shed, Mandatory OFF, and recovery/unlock are
derived as minimum +30, +20, and +40 percentage points respectively. The
Home Assistant policy and outbound Telegram companion use the same selected
minimum and covered formula.

These bands are homeowner strategy preferences, not hardware safety limits.
Grid Confidence, Panic, grid loss, telemetry quality, Peak Load Guard,
device-specific timing, and immutable safety constraints may produce a more
conservative result. Recovery clears a lockout but does not automatically
restart a manually controlled load.

## D051 — Family messaging is bilingual and text precedes voice

**Status:** accepted product direction; planned for Conversational EnergyHub.

Telegram begins with authenticated Ukrainian/English text intents. Voice uses
the same structured intent contract only after text authorization, audit,
bounded duration, and device-state acknowledgement are reliable. A
voice-derived control request must echo the interpreted device and duration in
the family member's configured or detected language and require explicit
confirmation. Language models and messaging transports never receive raw
inverter commands or arbitrary Home Assistant entity access.

## D052 — Hybrid Grid Hold may release once at 06:05 on verified early solar

**Status:** implemented in EnergyHub 1.3.7 and carried into the deployed 1.3.8
baseline.

Through 1.3.12, the ordinary 07:00 Solar handover was the conservative
fallback; D055 replaces it in 1.3.13. One
Home Assistant schedule event at 06:05 publishes the dated 06:00–07:00 Solcast
interval, but EnergyHub owns the decision and inverter transition.

Only confirmed Hybrid Grid Hold is eligible. EnergyHub requires Autopilot,
fresh inverter telemetry, fresh aligned Total Solar, present grid power, a
persisted Adaptive Hybrid target already met by SOC, at least 300 W of live
Total Solar, and at least 1.6 kWh forecast for 06:00–07:00. The add-on enforces
the local 06:00–07:00 window and current request date independently. Missing,
stale, insufficient, or inconsistent input makes no inverter change. Hybrid
Charging is never released by this check, and transition confirmation or
failure remains observable.

## D053 — Overload protection is evidence-first and fault-aware

**Status:** accepted design direction for the EnergyHub 2.0 family; no runtime
behavior implemented by this decision.

EnergyHub must not infer a safe automatic-shedding threshold from the nominal
10.2 kW inverter rating or from one suspected overload restart. It first
captures QPIWS transitions, persists warning/fault history, and records a
bounded pre-fault operating snapshot. Calibration distinguishes inverter/
battery operation from grid/bypass and accounts for the duration and inrush of
participating loads.

The community-reported POW-HVM10.2M Modbus register 4530 Error Code and Menu 25
Record Fault Code are research leads, not verified capabilities. Any probe is
bounded and read-only, PI30MAX and Modbus remain separate capability layers,
and undocumented writes are prohibited.

Active protection follows diagnostics, observation, Dry Run, and attended
single-load validation. It sheds only explicitly participating loads in a
configured order, confirms each physical result, and restores conservatively
with ownership, hysteresis, appliance timing, and inrush safeguards. Missing
telemetry or a failed smart-load command never implies that load was removed.

## D054 — AHM continuously enforces its dated target during the night

**Status:** implemented, deployed, and privately monitored in EnergyHub 1.3.8.

AHM remains the sole owner from its 23:50 evaluation until a confirmed morning
Solar handover; no separate Reserve Floor Guard or public operating mode is
introduced. The evaluated target is persisted together with the date through
which it is authoritative.

On each fresh local telemetry cycle, Solar remains unchanged above the target,
exact target requests Hybrid Grid Hold, and a value below target requests or
resumes Hybrid Charging. Existing target-reached logic then selects Grid Hold.
An absent grid or stale/unavailable SOC makes no inverter request. A confirmed
non-AHM Solar handover clears the dated enforcement context. The date prevents
a retained target from a previous night becoming authoritative after restart.

## D055 — Normal grid uses a 20%/30% daytime reserve band

**Status:** implemented in 1.3.13, corrected in 1.3.14, privately deployed,
startup-validated, and monitored.

The 07:00 schedule requests a Panic evaluation rather than unconditionally
restoring Solar. Panic may take ownership directly from Hybrid Charging or
Hybrid Grid Hold. A confirmed `SUB` + `OSO` Hybrid Grid Hold transfers to
Panic Grid Hold through persisted ownership only, without redundant inverter
writes.

With Grid Confidence Normal, physical grid present, fresh SOC, and no active
missed-AHM debt, 20% is the reserve floor and 30% is the Solar-release
threshold. Solar at or below 20% requests Grid Hold only while the grid is
present; if the grid is absent, Solar remains unchanged and reports
`waiting_for_grid`. A value below 20% with grid available charges back to the
floor; Grid Hold releases Solar only at 30%. The ten-point band prevents rapid
switching. A genuine AHM debt and the existing Unstable/Risk/Panic 60/80/95%
targets retain priority.

The same trusted-grid gate leaves participating heat pumps and the water
boiler under family/manual-demand control at every SOC without clearing any
remembered lockout. Losing trust restores the existing reserve policy. The
basement pump remains outside shedding, and EnergyHub never starts a protected
load automatically.
