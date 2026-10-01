# EnergyHub 2.4.2 private candidate

EnergyHub 2.4.2 and Family Assistant 2.4.1 are a coordinated resilience and
presentation update. They are prepared in the repository but are not committed,
pushed, synchronized, installed, restarted, or live-validated.

## Control behavior

- An unavailable, rejected, or unconfirmed participant is quarantined for the
  current protection cycle instead of creating a global controller fault.
- Shedding continues with the next eligible appliance. An ambiguous OFF result
  never creates EnergyHub ownership and is therefore never restored blindly.
- Restoration considers only confirmed EnergyHub-owned OFF states. An
  unavailable owned device remains owned for later recovery while other safe,
  eligible owned devices can restore.
- Fatal journal/storage faults still block control globally. Telemetry required
  for the inverter-level decision still fails conservatively.

## Family and technical Telegram delivery

- `technical_chat_id` optionally selects a private diagnostic destination. When
  empty, technical delivery falls back to the family destination for backward
  compatibility.
- SOC anomalies, data-source outages and recoveries, command-attention events,
  restart diagnostics, and the morning technical report use the technical chat.
- Grid loss/recovery, confirmed Grid Hold, confirmed appliance OFF, and confirmed
  restoration remain family-facing operational events.
- Grid Hold messages report the applied reserve and the dynamic Solar release at
  reserve +10 points. A 95% reserve has no automatic 105% release boundary.

## Beacon and Smart Heating

- Fresh solar/battery operation is steady at 30%; intentional grid supply is
  steady at 100%.
- A grid outage breathes through 20/50/80/50% brightness using the current SOC
  color. At SOC <=30%, red and dark burgundy alternate every two seconds without
  turning the lamp off.
- Missing telemetry remains steady white. While Smart Heating is enabled and
  telemetry is fresh, a two-second white pulse occurs every 20 seconds.
- Smart Heating selects Quiet from 23:00 through 07:00, suppresses Turbo in that
  interval, and leaves manual heat-pump settings untouched while Smart Heating
  is disabled.

## Deployment boundary

This candidate changes both add-ons and Home Assistant automation YAML. Add-on
synchronization alone is insufficient. The Home Assistant configuration must be
compared and deployed under its separate guarded scope, followed by `ha core
check` and focused live validation by the homeowner.
