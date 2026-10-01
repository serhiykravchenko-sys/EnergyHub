# EnergyHub 1.3.14 — Grid-Available Reserve Guard

EnergyHub 1.3.14 is the corrected public-review candidate for the coordinated
1.3 release line. It preserves the 1.3.13 daytime ownership and Normal-grid
hysteresis while making grid availability an explicit entry condition.

## Correction

With Grid Confidence Normal, no missed AHM debt, and fresh telemetry:

- Solar at or below 20% requests Panic Grid Hold only while the physical grid
  is present;
- if the grid is absent, EnergyHub remains Solar and reports that it is waiting
  for grid return;
- the same floor is reevaluated immediately after fresh telemetry confirms the
  grid has returned;
- Panic Grid Hold releases Solar at 30% only while the grid is present.

The same rule also applies below 20%: Normal-grid Solar remains command-free
while the physical grid is absent. Non-Normal Panic targets still arm their
request and wait for grid return as designed.

## Reliability corrections from independent review

- Non-finite PI30MAX values (`NaN`/Infinity) are rejected before retained MQTT,
  control-state creation, and battery-health classification; SOC outside
  0–100% is invalid.
- Non-Panic Hybrid entry clears stale persisted Panic ownership before writing
  the shared inverter settings. A failed Menu 01 entry now attempts bounded
  Solar recovery for both Hybrid and Panic.
- Direct inverter-message changes close the prior incident as `superseded`,
  malformed optional journal fields no longer discard valid retained history,
  and Home Assistant fault states are limited to 255 characters.
- PV1 freshness used by Total PV scales with a configured long PV2 poll
  interval, avoiding an artificial Total PV gap just before the next poll.
- Grid-import tariff tests cover the Europe/Kyiv spring and autumn clock
  transitions. Migration-day tariff values remain intentionally incomplete,
  and a missing Daily Summary snapshot cannot be created retroactively.

## Home Assistant and companion corrections

- Smart-load trust now consistently requires Grid Confidence Normal, fresh
  telemetry, and inverter grid voltage above 180 V.
- Boiler and heat-pump lockout creation, enforcement, and clearance reconcile
  after Home Assistant startup. A remembered lockout remains conservatively
  enforceable when telemetry becomes stale; new SOC-derived actions still
  require fresh data.
- Mission Control distinguishes PV1 from PV2/Total PV, exposes PV2 health and
  SOC anomaly diagnostics, shows 48-hour grid availability, and labels Grid
  Import as a non-billing-grade estimate. Heat Pumps and Water Systems show
  current authority separately from remembered lockout state.
- Telegram persists the exact logical morning report before delivery and
  retries that outbox after restart. Telegram provides no idempotency key, so
  delivery is at-least-once: a crash after API acceptance but before the local
  acknowledgement can still produce a rare duplicate.
- Telegram translations now cover every app option, and a current AHM minimum
  is no longer mislabeled as a recommendation while advice is still learning.

The correction avoids an unavailable transition during an outage. It adds no
new inverter command and does not promise reserve that cannot be supplied.

## Preserved 1.3.13 behavior

- AHM owns the configured cheap-tariff night and hands daytime ownership to
  Panic at 07:00.
- A confirmed `SUB` + `OSO` Hybrid Grid Hold transfers ownership without a
  redundant inverter write.
- Confirmed `SUB` + `SNU` Hybrid Charging also transfers ownership without a
  redundant inverter write.
- A genuinely missed AHM target remains authoritative until recovered.
- Unstable, Risk, and Panic Grid Confidence retain 60%, 80%, and 95% targets.
- Trusted, present grid plus fresh telemetry leaves the water boiler and heat
  pumps under family control. EnergyHub never starts those loads.

## Companion and future interface

Telegram Family Assistant 1.3.14 is the optional coordinated companion. It is
outbound-only: morning briefings, tariff estimates, inverter diagnostics, grid
events, and reserve warnings. Future Telegram-first Mission Control remains a
separate 3.0 design: bilingual text first, confirmed voice later, translated
into authenticated EnergyHub intents rather than raw Home Assistant or
inverter commands.

## Validation boundary

Repository regression tests cover the unavailable-grid floor, immediate grid
return evaluation, 20%/30% hysteresis, missed-AHM debt, non-Normal targets, and
the no-write ownership transfer. Deployment, startup, live entities, and
threshold transitions require separate guarded validation before publication.
