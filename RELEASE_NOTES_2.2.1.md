# EH / Family Assistant 2.2.1 — overload mode correction

Prepared privately; not deployed or activated.

- One dedicated dashboard switch: **Overload Protection — Automatic**.
- OFF: warnings only at production 85/75/60 thresholds. No new device commands.
- ON: existing acknowledged sequential native/relay control, subject to safety,
  device readiness, restart allowances and restoration checks. No trial profile.
- Retain ownership and observe acknowledgements/family changes while OFF;
  turning OFF never causes an immediate mass restoration.
- Short Ukrainian warnings and recovery notifications; no trial cycle IDs,
  old 40/30/20 advice or false claims that a warning restored devices.
- Consume old retained trial events without sending them; discard queued trial
  advice. Preserve production action evidence and deduplication.
- The old app flag is optional compatibility data and no longer selects a mode.
  Updated HA bridge schema 2 is required; old retained snapshots cannot arm it.
- Battery Reserve controls, inverter strategy, Smart Heating draft and Threat
  Monitor are unchanged.

See validation and deployment gates (private development record).
