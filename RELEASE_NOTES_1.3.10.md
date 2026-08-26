# EnergyHub 1.3.10 — Inverter Fault Diagnostics

EnergyHub 1.3.10 preserves the 1.3.9 control policy and adds read-only inverter
incident evidence.

## Added

- named QPIWS active-set transition and recovery recording;
- a persistent latest-100 incident journal;
- up to five minutes of pre-incident load, battery, solar, grid, operating-mode,
  and telemetry-freshness context;
- retained Home Assistant entities for the current and latest three inverter
  messages;
- the latest three messages on the EnergyHub Status dashboard;
- Telegram Family Assistant 0.2.2 previous-day incident summaries.

## Safety boundary

This release performs no automatic load shedding and adds no inverter control.
It reports QPIWS clearance as clearance, not as a verified automatic restart.
Possible Modbus register 4530 remains an unverified read-only research lead and
is not part of runtime polling.

## Validation status

Repository tests and configuration checks are required before private
finalization. Live QPIWS transition capture, dashboard rendering, Telegram
formatting, persistence across restart, and any separate register 4530 probe
remain deployment or attended-hardware evidence.
