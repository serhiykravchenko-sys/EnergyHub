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

Grid Import queues the completed day; Daily Summary reconciles it; Grid Import acknowledges only after a non-invalid result. The operation is idempotent.

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

EnergyHub 1.1 never turns the boiler or a heat pump on. The water-boiler guard and grid-confidence-aware heat-pump guard may request OFF at documented reserve thresholds and reject ON while an emergency lockout is latched. Missing or stale EnergyHub telemetry produces no command. Automatic Smart Thermal ownership, starts, comfort decisions, surplus use, minimum runtime, and compressor cooldown remain deferred to 1.5.

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
