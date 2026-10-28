# EnergyHub app — reference configuration

This 3.6.37 source snapshot targets the verified PowMr 10.2M PI30MAX installation.
Configure MQTT, persistent serial path, timezone and reviewed optional services
in local app options. PV2 is a separate bounded read-only capability on verified
firmware; there is no generic Modbus-write support.

Reserve/night/outage charging need current helper/source evidence and the
reviewed HA bridge. Outage preparation defaults disabled until group, usable
capacity, charge-current/headroom and device behavior are commissioned. Night
permission is separate from Autopilot and valid-input requirements; installation
does not by itself provide those inputs. Keep controllers disabled until local
checks pass. Source examples are not a universal installer.

Native HA, not this Python app, owns plug overload/battery protection. The
surviving legacy load controller owns only first-floor HP climate management.
Do not remove old IDs/journal names without tracing current consumers. A sent
inverter request is not success: Menu 01 uses readback, Menu 16 ACK only,
and uncertain/failed persistence requires attended verification.

See [installation](../docs/operations/INSTALLATION.md),
[architecture](../docs/design/05-System-Architecture.md),
[reserve](../docs/design/BATTERY_RESERVE_CURRENT.md),
[charging](../docs/design/DECISION_ENGINE.md), and
[validation](../docs/validation/RELEASE_3.6.37.md).
