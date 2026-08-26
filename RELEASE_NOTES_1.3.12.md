# EnergyHub 1.3.12 — Meaningful Inverter Messages

EnergyHub 1.3.12 preserves the deployed 1.3.11 behavior and removes routine
nightly PV-loss noise from the dashboard-facing inverter diagnostics.

## Changed

- `pv_loss_warning` remains in `/data/inverter_fault_journal.json` as raw
  diagnostic evidence.
- The Current entity reports `Normal` when PV loss is the only active QPIWS
  message.
- The latest-three entities skip PV-loss-only incidents and select the latest
  three meaningful incidents instead.
- Mixed incidents retain every message except expected PV loss.

## Safety

This release changes presentation only. It adds no inverter command, household
load action, or automatic load shedding.
