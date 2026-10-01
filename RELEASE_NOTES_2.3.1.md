# EnergyHub 2.3.1 / Telegram Family Assistant 2.3.1

Prepared 2026-09-12 as a private corrective candidate.

## Corrections

- EnergyHub accepts both Unix and ISO timestamps for completed Daily Summary
  consumption evidence. Existing valid history can therefore supply the
  one-to-three-day Battery Reserve average immediately.
- Family Assistant waits at least one minute and until current-boot EnergyHub
  reserve and protection evidence is ready before sending the HA restart
  summary. It waits no longer than five minutes and labels unresolved state.

## Scope

Add-on files only. No Home Assistant YAML, dashboard, control threshold, entity
ID, inverter-control or load-control behavior changes.
