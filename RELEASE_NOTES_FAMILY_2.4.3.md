# Family Assistant 2.4.3 and Home Assistant cleanup

Private corrective candidate. EnergyHub remains 2.4.2.

## Cleanup

- Remove the disabled 23:50 Low-Tariff schedule, 06:05 Early Solar check,
  07:00 ownership handoff, and retired morning-learning automations.
- Remove obsolete Low-Tariff and Early Solar Home Assistant notification
  branches while retaining current Battery Reserve success/failure messages.
- Preserve the active 23:49/23:51 accounting snapshots and 23:52/05:00 Battery
  Reserve forecast-input updates.
- Replace Family Assistant option and documentation wording that still called
  the current Battery Reserve and protection paths an EnergyHub 2.1 Dry Run.
- Keep established MQTT topics, option keys, entity IDs, and legacy persisted
  strategy recognition where changing identifiers would create migration risk.
- Quote the 23:00 and 07:00 Smart Heating triggers so Home Assistant loads the
  automation reliably.

## Deployment boundary

The Family Assistant add-on source and `automations.yaml` must be synchronized
separately. The homeowner reloads/updates the add-on and reloads Automations.
No Home Assistant Core restart is required when only these files change.
