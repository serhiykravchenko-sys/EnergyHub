# Family Assistant 2.4.4 and heat-pump restart recovery

Private corrective candidate. EnergyHub remains 2.4.2.

## Grid messages

- Require one continuously confirmed minute of grid loss before sending the
  family outage message.
- Send heat-pump reserve warnings only during a confirmed outage with fresh
  telemetry.
- Drop a queued reserve warning if reliable grid voltage returns before
  delivery.

## Restart recovery

- Remember explicit Home Assistant user ON/OFF choices for only the first- and
  second-floor Zigbee heat-pump plugs.
- After restart, restore a remembered-ON plug only when the HA session is
  stable, telemetry is fresh, grid voltage is reliable, both plug states are
  known, and EnergyHub protection is not controlling or quarantining it.
- Wait one minute after a confirmed restoration, then report measured power to
  the family chat and distinguish active consumption from an enabled idle plug.
- Do not restore remembered-OFF, unknown, third-floor, protected, or
  controller-owned plugs.

## Deployment boundary

Synchronize Family Assistant 2.4.4 and the reviewed `automations.yaml` and
`configuration.yaml`. The homeowner reloads the App store and updates the app,
then runs `ha core check` and restarts Core because new YAML helpers are added.
No public promotion is included.
