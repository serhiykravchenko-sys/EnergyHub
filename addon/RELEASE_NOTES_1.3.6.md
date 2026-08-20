# Energy Hub 1.3.6

- Replace incompatible retained Hybrid decision reason state during app
  startup.
- Retain the concise initial state for later Home Assistant restarts.
- Enforce the 255-character state boundary at the MQTT publisher.
- No change to AHM, Panic, PV2, Total PV, or inverter control.
