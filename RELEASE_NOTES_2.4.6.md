# EnergyHub 2.4.6

Private corrective candidate prepared on 2026-09-21. It is not committed,
pushed, synchronized, updated, live-validated, or publicly released.

## Device availability correction

- Separate a current device state from an unchanged watt measurement. Idle
  smart plugs may retain the same 0–1 W value for hours without being offline.
- Keep last-known valid watts visible and label them `power unchanged`.
- Permit an online participant with a valid current switch/climate state to
  remain eligible for shedding or restoration.
- Preserve strict safety boundaries: a command still requires the current HA
  bridge snapshot, context/revision checks, acknowledgement, and a new
  post-command state/power observation before EnergyHub accepts ownership.

## Zigbee2MQTT prerequisite

Enable Zigbee2MQTT device availability so Home Assistant entities become
unavailable when an active device cannot be reached. Use the default active
10-minute and passive 25-hour classes initially; do not apply a short active
timeout to sleeping CO/CO2 or other battery devices.

Zigbee2MQTT must be restarted for the setting to take effect. That restart is a
separate attended homeowner action and is not part of repository preparation.

## Deployment boundary

The EnergyHub add-on is an ordinary local-app update. The dashboard storage
change remains a separate guarded Home Assistant deployment and requires Core
to be stopped before `.storage` is copied.
