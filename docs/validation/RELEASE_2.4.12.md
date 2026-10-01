# EnergyHub 2.4.12 / Family Assistant 2.4.15 release evidence

Release bundle dated 2026-10-01: EnergyHub 2.4.12 / Family Assistant 2.4.15.
Publication is tracked by the [v2.4.12 GitHub release](https://github.com/serhiykravchenko-sys/EnergyHub/releases/tag/v2.4.12).

## Repository evidence

The final corrective candidate passed 202 EnergyHub, 63 Home Assistant bridge,
and 257 Family Assistant tests on 2026-09-29. All three suites passed again in
both the private source and prepared public copy on 2026-10-01. Tests use fake hardware, MQTT,
Home Assistant and Telegram with disposable persistence fixtures. Independent
reviews found persistence/ownership/timer/delayed-report problems; corrective
regressions cover those paths. The final focused review found no remaining
control blocker, and its report-wording correction was tested afterward.

The five current SVG/PNG diagrams describe one continuous reserve, separate
overload and outage protection, native Smart Heating and guarded execution.
The heating diagram reflects family-owned temperature/fan settings and timer
pause/restore behavior. Public-copy tests and privacy/link checks are recorded
before publication. The prepared public copy passed syntax checks for 98 Python
files, parsing for six HA JSON files and five SVG files, and local-link checks
for 89 Markdown files. Identifier/credential-pattern scans found no matches;
these are heuristic checks, not a claim of exhaustive secret detection.

## Supplied Home Assistant evidence

- On 2026-09-29, after a homeowner backup, both local app trees were
  synchronized and verified against source by hash.
- The reviewed automation bridge was synchronized with a backup; source/target
  hashes matched. configuration.yaml already matched. No storage copy occurred.
- The homeowner supplied successful `ha core check`, YAML reload confirmation,
  EnergyHub 2.4.12 and Family Assistant 2.4.15 startup banners.
- EnergyHub logs show MQTT connected, PV2/Total PV present, persisted journals
  loaded, health online and Solar reconstructed without inverter writes.
- A real grid outage agreed with inverter telemetry, the dashboard and
  Telegram outage/recovery messages. Historical Grid Confidence is distinct
  from instantaneous grid availability.
- On 2026-10-01, the homeowner reported normal operation after the agreed
  24-hour observation period and no new Core/Supervisor errors.
- A read-only source/deployed comparison on 2026-10-01 matched all 39 EnergyHub
  and 21 Family Assistant runtime/build/manifest files, plus automations.yaml
  and configuration.yaml. Documentation changed afterward; this is not an
  assertion that every deployed documentation file is identical.

Codex evaluated supplied evidence; this is not a claim of continuous remote
monitoring. Supervisor logs were checked by the homeowner, not monitored by
the Family Assistant's Core-log digest.

## Remaining limits

- Routine monitoring does not prove rare persistence failures, pending-intent
  eviction during restore, all timer/protection orderings or failed Solar
  recovery on real hardware. Those cases have repository regression coverage.
- Smart Heating needs extended cold-weather observations. A new installation
  must validate its device mapping, manual OFF, timers, shedding and restore
  before enabling unattended load control.
- A recommendation's reevaluation timestamp does not independently prove the
  origin-age of the Solcast forecast. Grid Import is estimated, not metered or
  billing-grade; no quantified saving is claimed.
- Menu 16 is ACK-confirmed without independent readback. Later Menu 01 drift
  is not automatically reconciled by periodic readback. Uncertain or failed
  transitions require attended verification; no automatic hardware retry is
  promised.
- AI control, EV charging, multiple cheap-slot optimization and export/Net
  Billing are future work.
