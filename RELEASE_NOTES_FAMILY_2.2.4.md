# Family Assistant 2.2.4 and dashboard companion

Prepared privately, not deployed.

Scope expanded by user request: see [2.2.4 restart release](RELEASE_NOTES_2.2.4.md).
The dashboard below is already synchronized separately. Current candidate now
includes startup summary plus companion EH/HA restart-state handling; the earlier
dashboard-only deployment scope below is historical and must not be reused.

- Morning weather now includes a short UHMC status, distinguishing fresh no-warning
  evidence from warnings present and unavailable/stale evidence.
- Dashboard lists all six overload devices in agreed order, current state/power
  and device checks. First-floor HP uses native control; its plug measures power.
- EnergyHub 2.2.3 control, Battery Reserve and Threat Monitor are unchanged.
- Separate Smart Heating 2.4 draft gains solar-only budgeting and occupancy/manual
  override policy. It is not shipped with this update or ready for automatic control.

Deployment scope, when authorized: Family add-on and dashboard storage only.
Compare live files and preserve manual differences; back up outside app discovery.
Homeowner stops Core only for the dashboard storage copy, then checks/starts Core.
App-only update needs no Core stop. Verify 2.2.4 startup, morning status and dashboard
readability/freshness; do not run heating hardware experiments as part of this update.
