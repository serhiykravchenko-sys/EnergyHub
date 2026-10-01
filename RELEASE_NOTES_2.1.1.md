# EnergyHub 2.1.1 / Family Assistant 2.1.4 — Dry Run hardening

Prepared privately on 2026-09-06. Not deployed, committed, pushed or published.

## What changes

- Peak Load Guard retains 40/30/20. Recovery requires 60 seconds of observed
  load at/below 20%, no native overload warning, and no sample gap over 30
  seconds. This is an observation-profile choice, not a verified hardware
  trip threshold. Restart begins a new confirmation interval.
- The latest 64 events persist with stream/cycle identifiers. Family Assistant
  consumes unseen events in order, rather than observing only the latest one.
- Battery Reserve retains the baseline + deficit + grid + weather formula,
  capped at 95%. A successful daily forecast is captured once at/after 05:00;
  a missed run is caught up after startup or the next valid input. Baseline,
  weather and grid changes can reevaluate without recapturing that forecast.
- Three positive recent end-of-day snapshots (within seven days, source time
  23:50 or later) are required for a confirmed consumption average. Older or
  partial history does not imply zero consumption. A final snapshot is not
  proof of uninterrupted meter coverage; that remains a monitoring limitation.
- Missing/stale evidence holds an existing advised modifier. Source freshness
  expires after 30 minutes. A clear, fresh warning source can release weather
  reserve; unknown/expired source evidence cannot establish an all-clear.
- Baseline preference is a separate HA helper. The existing AHM slider remains
  the manually applied minimum. Following a recommendation does not compound
  the baseline. The active daytime strategy may still use a different target.
- Battery Reserve Auto is read-only OFF, including in the backend. There is no
  automatic adjustment or new inverter/relay/smart-plug command path.
- Family reporting keeps morning monitoring, uses one reserve recommendation,
  defers overnight target changes to 08:00, and reports daytime changes.
- UHMC region/severity ambiguity remains unknown; explicit hazard-specific
  cancellations do not cancel unrelated warnings. Road ice remains included.

## Boundaries and deferred work

The active daytime Grid Confidence targets remain 20/60/80/95. The observer's
base-20 grid-only recommendations remain 20/40/60/80. No automatic integration
of those two policies is authorized by this release. Future Automatic mode
requires a separate ownership/charging/release/restart review and monitoring.
Renaming internal Hybrid/Panic modes and heat-pump heating control are deferred.
Threat Monitor is outside this release.
The existing manually applied minimum retains its 20–50% control range.
Recommendations above that range are advisory evidence, not instructions to
bypass existing control limits. Automatic integration needs its own target path.

The reported two live recoveries are not conclusively diagnosed without the
matching logs. Local bounce/polling behavior is reproduced and corrected.
Telegram delivery is not exactly-once across an ambiguous API timeout/crash.
The bounded journal can overflow during a long bot outage; gaps are logged.

## Deployment handoff (requires separate approval)

1. Homeowner creates a HA backup. Compare local app and HA configuration files;
   preserve manual changes. Keep backups outside the scanned local-app tree.
2. Synchronize EnergyHub and Family app sources only through the documented
   guarded workflow. No Threat Monitor files are included.
3. Separately synchronize `configuration.yaml`, `automations.yaml` and
   `lovelace.dashboard_powmr1`. Homeowner must stop Core before `.storage`
   copy, then run `ha core check` and start Core after the final files arrive.
4. Set **Baseline Preference** to the intended long-term minimum (20% for the
   current agreed household baseline). The new helper defaults to its minimum
   on first creation; do not mistake the existing applied slider for baseline.
5. Reload the App store and update the two apps. Verify 2.1.1 / 2.1.4 banners,
   startup reconstruction, MQTT and fresh telemetry. Neither app-only update
   requires a separate Core restart.
6. Verify Battery Reserve Auto OFF/non-interactive, separate baseline/applied
   values, evidence quality, six plug participants, 40/30/20 and journal data.
7. Observe a natural overload/recovery and an 08:00 report. Confirm no Dry Run
   switch or AHM action. Monitor the new build before any automatic-control work.

See candidate validation (private development record).
