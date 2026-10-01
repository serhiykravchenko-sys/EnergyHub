# EnergyHub 2.4.9 / Family Assistant 2.4.11

Prepared corrective candidate. Not deployed, committed, pushed, or publicly
released.

## What changed

- Separate plug availability, switch/climate state, power validity, power age,
  and post-command acknowledgement.
- Accept unchanged old 0/1 W as diagnostic evidence for an online plug while
  still rejecting fresh power that contradicts a confirmed OFF transition.
- Confirm commands from a fresh target-state transition, matching command
  context, accepted executor acknowledgement, and a newer bridge snapshot.
- Stop targetless Home Assistant service calls from falsely claiming external
  control of all six protected loads.
- Keep first-floor heat-pump ownership across passive integration attribute
  refreshes; explicit external intent or a conflicting state still releases it.
- Retain overload trigger percentage/reason separately from post-action load.
- Translate and consolidate overload-attention evidence instead of repeating a
  generic check message for each participant.
- Replace the morning availability calculation with a rolling 24-hour window
  ending at 08:00. Mask child attribution during parent outages, merge short
  poll flaps, and use source-specific duration thresholds.
- Monitor Zigbee2MQTT bridge availability separately. An online plug with an
  unchanged watt value remains healthy.
- Read and deduplicate both Home Assistant Core and Supervisor warning/error
  logs through the read-only Supervisor API. A clean technical report stays
  compact and is claimed only for journals that were actually read.

## Unchanged safety boundaries

- Overload trigger remains immediate at 85% or on an explicit inverter
  overload warning.
- Shedding stops at 75%; restoration still requires load below 50% for five
  continuous minutes and proceeds one device at a time.
- Commands remain allow-listed, non-retained, expiring, acknowledged, and
  write-before-send persisted.
- Uncertain or contradictory outcomes fail closed. No Zigbee restart, relay
  retry, raw inverter command, or blind restoration was added.

## Deployment scope

The candidate changes both app trees plus Home Assistant automations and the
EnergyHub dashboard. App synchronization alone is insufficient. Before live
deployment, compare the current HA files, preserve manual differences, and use
the guarded YAML/storage workflow. Home Assistant Core must not be stopped until
the storage deployment is separately authorized and ready. Family Assistant
2.4.11 also enables the app's `hassio_api` permission so it can read Core and
Supervisor logs; it does not call restart or control endpoints.

## Live validation required

- an online Zigbee plug at unchanged 0/1 W remains available and quiet;
- a real device/bridge outage crosses the intended threshold once and recovers
  once;
- an overload message shows trigger and post-action load separately;
- OFF/restore acknowledgement succeeds without a new watt publication when the
  target state is fresh, while fresh contradictory power is rejected;
- first-floor passive attribute refresh does not release ownership, but a real
  family/automation command does;
- attention reasons are consolidated and identify affected devices;
- the 08:00 report covers the preceding 24 hours and reads both Core and
  Supervisor logs;
- restart reconstruction preserves confirmed ownership and performs no
  unrequested inverter or relay action.
