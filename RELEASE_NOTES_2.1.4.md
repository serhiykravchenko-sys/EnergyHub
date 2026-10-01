# EnergyHub 2.1.4 / Family Assistant 2.1.7 — private corrective candidate

Prepared 2026-09-06. Not deployed, committed, pushed or published.

## Daytime manual reserve

The daytime controller now receives the actual family-selected Battery Reserve.
Its target is the maximum of that setting, the existing 20/60/80/95 grid safety
ladder and any outstanding missed-night target. The observer cannot set it.
With Normal grid and no missed-night debt, selecting 60% means charging to 60%
if below it, grid hold at 60%, then Solar release at 70%. Solar release is capped
at 100%, not 95%, so a 95% floor does not repeatedly switch hold/solar at the
same SOC. Grid charging still stops at the floor; solar supplies release headroom.

Changed settings request evaluation on the next valid telemetry loop, not in
the MQTT callback. Missing/invalid manual input cannot silently select 20%.
Autopilot, supported-mode, time-window and grid checks remain in force.
HA retains the family setting; runtime receives it again after restart.

This is a daytime correction, not a new night planner: the scheduled low-tariff
plan still uses the manual minimum when evaluated. Editing the slider does not
recalculate an already dated night plan. Emergency/debt targets may exceed the
manual floor. Automatic reserve management remains unavailable.

## Short UHMC warnings

Daytime messages contain three lines when a source URL exists: severity/hazards,
current manual reserve plus recommendation status, and source link. Complete
equal-target evidence says no change recommended. Incomplete evidence says
insufficient data. A higher recommendation explicitly requests a manual change
in Dry Run; a higher manual choice is preserved, not automatically reduced.

No warning parser, delivery/deduplication, quiet-hour or morning-report changes.
No Threat Monitor, HA YAML/dashboard, entity IDs, MQTT topics or schemas changed.
Both Dry Runs retain their logic, journals and thresholds.

## Deployment handoff

Separate app-only synchronization approval is required. Use the standard guarded
scripts and backups outside local-app discovery, then homeowner Store Reload /
Update. Core does not need stopping for this app-only candidate. Verify both
version banners, reconstruction, fresh inputs and manual target/release evidence.
Do not deliberately discharge or cycle equipment to test. Existing queued Telegram
messages retain their already-rendered text; newly generated warnings use the
short format. Monitoring and live behavior are not proven by repository tests.

Validation (private development record)
