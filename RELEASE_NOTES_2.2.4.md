# EH / Family 2.2.4 — restart settings and concise status

Prepared privately, not deployed. Smart Heating remains offline.

- HA restores the overload ON/OFF helper instead of forcing OFF twice at startup.
  Without saved state it defaults OFF. Bridge session rotation, fresh telemetry,
  command identity/revision checks and uncertain-action faults remain required.
- EH resets restoration qualification on a changed bridge session. Retaining ON
  is not permission to replay a command or immediately restore owned devices.
- Family sends a concise restart summary after 60 seconds: strategy and Autopilot,
  actual selected reserve and control authority, overload requested/effective state.
  Missing evidence is explicit; no automatic reserve claim while advisory is active.
- HA boot identity comes from the existing startup bridge-session helper. State
  dedup survives bot restart. First observation of a boot older than ten minutes
  is silently baselined; known later boots are reported. Queued summaries are
  refreshed before delivery; obsolete boot summaries are discarded. Network/API
  failure can delay delivery, and Telegram does not guarantee exactly-once delivery
  if the process crashes after sending but before saving acknowledgement.
- Morning UHMC status is included after weather: fresh no-warning, warnings present
  or data unavailable. Existing immediate warnings remain unchanged.

Approved preparation only. Future deployment requires explicit authorization for
EH/Family app sources plus configuration.yaml and automations.yaml. The already
deployed six-device dashboard needs no additional change. Backups and live comparison
must precede deployment; homeowner performs Core check/restart and app updates.
Verify prior ON and OFF across restart, pending-command faults, new recovery window,
one truthful restart summary and next morning UHMC status. Never induce overload.

HA restore semantics: [Input boolean documentation](https://www.home-assistant.io/integrations/input_boolean/#restore-state).
