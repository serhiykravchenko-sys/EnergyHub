# Energy Hub 1.3.5

- Optional read-only PV2 Modbus RTU polling on verified registers 4563-4564.
- PV2 voltage, PV2 power, fresh aligned Total PV, status, freshness, and sample
  age through MQTT Discovery.
- One adapter-owned lock for PI30MAX and Modbus serial access.
- Dedicated availability prevents retained stale PV2 and Total PV values from
  appearing current.
- PV2 failure isolation preserves the existing PI30MAX and decision loop.
- No Modbus writes and no use of PV2 in control decisions.

See `CHANGELOG.md` and `DOCS.md` for configuration and validation details.
