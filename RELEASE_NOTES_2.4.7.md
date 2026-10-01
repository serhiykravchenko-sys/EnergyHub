# EnergyHub 2.4.7 / Family Assistant 2.4.9

Private corrective candidate prepared on 2026-09-21.

## Changes

- Use the first- and second-floor Zigbee plug switch entities as the device
  availability authority. Zigbee2MQTT already changes those entities to
  `unavailable` when the device is offline.
- Remove the redundant manual MQTT availability binary sensors that remained
  `unknown` despite both devices being online in Zigbee2MQTT.
- Keep automatic switching fail-closed for an unavailable or invalid switch
  state and retain strict post-command acknowledgement and power evidence.
- Ignore retired retained Home Assistant input topics without logging them as
  invalid Daily Summary inputs.
- Group the morning report's ownership summary under `Автоматично` and
  `Вручну`. Future Smart Heating identifies only the first-floor heat pump as
  automatic.

## Deployment scope

- Energy Hub add-on 2.4.7.
- Telegram Family Assistant 2.4.9.
- `configuration.yaml` and `automations.yaml`; no dashboard storage change.

No commit, push, deployment, restart, or public promotion is implied.
