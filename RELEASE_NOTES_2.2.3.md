# EH / Family 2.2.3 — sequential overload restoration

Prepared privately, not deployed or activated. Coordinated versions skip EH 2.2.2
to align with the next Family version (currently Family 2.2.2 / EH 2.2.1).

- Dashboard ON enables eligible acknowledged control without mandatory watt values.
- Shed at 85% until <=75%; restore after strictly below 50% for five fresh minutes.
- Restore one device at a time, with confirmed state/power and at least one minute
  between restorations. A >=50% sample or missing/stale evidence resets qualification.
- New overload can resume shedding while restoration is settling.
- After five minutes without restoration evidence, notify once with owned OFF
  devices and ask family to check before manual restart. Never restore blindly.
- Preserve minimum off times, scheduled/manual ownership release, uncertain-command
  locks, non-retained expiring intents and native first-floor Heat/Off restrictions.
- Hide unused legacy watt allowances without deleting helpers or histories.
- Bridge/command schema 3 prevents partial upgrades using older policy messages.
- Battery Reserve, Smart Heating, inverter commands and Threat Monitor unchanged.

Deploy scope, after approval: both app trees, automations.yaml and dashboard only.
No configuration.yaml or helper-storage copy. Homeowner Core stop/check/start for
dashboard; update both apps and verify schema/readiness before attended activation.
Polling is not instantaneous overload protection or a guarantee against motor surges.

See validation (private development record).
