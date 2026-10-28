# HA configuration responsibilities

Use [the integration examples](../../homeassistant/README.md) and
[installation guide](INSTALLATION.md). HA provides helper settings, mapped
devices, fresh input snapshots and supported service execution.

The current native overload/battery package owns smart plugs. EH's surviving
legacy load controller is HP1-only, with context/acknowledgement and restart
state. Family supplies selected normalized source evidence and Telegram reports;
it is not a second inverter/plug controller.

Do not infer grid availability from Grid Confidence. Settled grid evidence,
measured voltage, fresh SOC and each protection's own guards have distinct roles.
Profile/schedule/manual handling for HP1 is separate from native saved-state plug
restoration. Refer to [current technical diagrams](../Images/README.md) and their
linked implementation rather than superseded Hybrid/Panic policy descriptions.

Real endpoint addresses and cloud/device registry data remain local. Merge YAML
after backup; run `ha core check` and appropriate reload/restart. Helper/dashboard
storage examples are not an instruction to replace an installation's registries.
Core must be stopped before a selected `.storage` copy. No live action is implied
by a passing unit test or successful file synchronization.
