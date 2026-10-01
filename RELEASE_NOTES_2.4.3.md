# EnergyHub 2.4.4 / Family Assistant 2.4.7

Private corrective candidate; not published.

EnergyHub 2.4.4 removes the output-only Hybrid Calculation MQTT entity, clears
its retained discovery and state records during startup, and removes its
dashboard tile. The Battery Reserve controller and inverter-control inputs are
unchanged.

## User-visible behavior

- First-floor Smart Heating has no Turbo path. It uses Normal, Quiet from
  23:00–08:00, and Eco while external grid voltage is absent. It pauses at 40%
  SOC and restores at 50% only when it owns that pause.
- The 08:00 family report shows current operating mode, current SOC, 15-minute
  average PV, a conservative grid-support estimate and EV potential only when
  forecast energy remains after house demand and battery recharge to 100%.
- Forecast accuracy is shown only for a completed day when the battery did not
  reach 100%, because battery-full curtailment makes the comparison ambiguous.
- Grid-import detail is sent for the completed previous week on Monday and for
  the completed previous month on day one, rather than every morning.
- Home Assistant restart summaries include current SOC.
- Family Assistant no longer schedules the obsolete 07:00 SOC/night-import
  snapshot; it reads current SOC and operating mode while preparing the 08:00
  report.

## Resource discipline

- The inverter safety/control poll remains 10 seconds.
- Ordinary telemetry uses per-signal deadbands with a 30-second heartbeat.
- HA participant snapshots use 30 seconds while idle and 10 seconds during an
  active/pending protection cycle.
- Peak Load Guard publishes control transitions immediately and refreshes full
  attributes every 60 seconds while unchanged.
- Recorder keeps ten days of raw history, excludes verbose diagnostic payloads,
  and retains Home Assistant long-term statistics.
- This release does not purge or repack the existing database.

## Deployment ownership

Repository files may be synchronized privately. The homeowner still performs
App-store Reload/Update and Home Assistant Core check/restart, then confirms the
version banners and live entities.
