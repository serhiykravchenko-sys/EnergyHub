# Energy Hub 1.3.8

Energy Hub is a local-first Home Assistant app for a PowMr 10.2M inverter using
PI30MAX and optional read-only PV2 Modbus RTU telemetry.

It publishes inverter telemetry through MQTT Discovery and implements explainable Solar, Adaptive Hybrid Charging/Grid Hold, and conservative daytime Panic Charging/Grid Hold strategies.

On startup, 1.3.8 also replaces any incompatible retained pre-1.3.4 Hybrid
decision reason with a concise initial state and enforces Home Assistant's
255-character state boundary. Version 1.3.8 presents that state
as `awaiting_evaluation`; its reason explains whether a target was retained
and when the next 23:50 evaluation occurs.

At 23:50, AHM calculates a target from the selected 20–50% minimum SOC, a learned hourly essential-load profile, tomorrow's hourly solar, and the aligned post-07:00 energy deficit. It learns 07:00–12:00 house-energy deltas after subtracting all three heat-pump energy deltas, uses the conservative 75th percentile after three complete samples per interval, and confirms solar takeover only when two consecutive forecast hours cover learned essential load. Until learning is ready, the verified 300 W → 600 W ramp model remains authoritative. Projected 07:00 SOC at or above target stays Solar; current SOC at or above target with a lower overnight projection starts Grid Hold; current SOC below target starts Charging. From 07:00 to 23:50, Panic protects 20/60/80/95% according to Grid Confidence and any AHM target genuinely missed at the morning handover.

Version 1.3.8 persists the current night-plan date and target. Until confirmed
morning Solar, fresh SOC above target stays Solar, exact target enters Grid
Hold, and below target enters or resumes Charging. Stale SOC or an absent grid
causes no command; the next fresh grid-present cycle reevaluates the same plan.

Version 1.3.7 adds one 06:05 check while Hybrid Grid Hold
is active. EnergyHub releases to Solar only when the target is reached, grid
and telemetry are fresh, live aligned Total Solar is at least 300 W, and the
06:00–07:00 Solcast interval is at least 1.6 kWh. Any failed gate keeps Grid
Hold unchanged until the normal 07:00 handover.

## Required configuration

Before starting the app, configure:

- `mqtt_user` and `mqtt_password` for your MQTT broker;
- `serial_port` with the inverter FTDI adapter's persistent `/dev/serial/by-id/...` path.

Find the path with:

```bash
ha hardware info
```

Use the FTDI path. Do not use `/dev/ttyUSB0` or `/dev/ttyUSB1`, because those names may change after a restart or when another USB serial device is connected.

Example:

```yaml
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_user: YOUR_MQTT_USER
mqtt_password: YOUR_MQTT_PASSWORD
serial_port: /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_YOUR_ID-if00-port0
protocol: PI30MAX
command: QPIGS
poll_interval: 10
pv2_modbus_enabled: false
pv2_poll_interval: 30
device_name: PowMr 10.2M
```

PV2 Modbus is disabled by default. Enable it only on hardware where slave 5,
function 03, and registers 4563-4564 have been verified. PI30MAX and Modbus use
the same FTDI adapter and are serialized by one in-process lock. The configured
PV2 interval is clamped to at least 10 seconds; 30 seconds is recommended.

When enabled, EnergyHub publishes:

- `sensor.powmr_10_2m_pv2_voltage`;
- `sensor.powmr_10_2m_pv2_power`;
- `sensor.powmr_10_2m_total_pv_power`;
- `sensor.energyhub_pv2_telemetry_status`;
- `sensor.energyhub_pv2_telemetry_freshness`;
- `sensor.energyhub_pv2_sample_age_seconds`.

Total PV is valid only when PV1 and PV2 were sampled no more than 15 seconds
apart and both remain fresh. Retained last-known values stay stored for
diagnostics but their dedicated MQTT availability becomes offline when stale.

## Healthy startup

```text
[Energy Hub] Version 1.3.8
Serial: /dev/serial/by-id/usb-FTDI_...
MQTT connected
OK | SOC=... | PV1=... | Load=... | Grid=online
PV2 OK | Voltage=...V | Power=...W | Total=...W
Startup strategy reconstructed: mode=...
EnergyHub health: Communication starting -> online
```

## Upgrade

Create a backup, stop the app, update or replace its files, reload the App store when `config.yaml` changed, rebuild, start, and verify the log.

Do not delete the app's `/data` directory during a normal upgrade.

## Limitations

- `aarch64` only;
- PowMr 10.2M / PI30MAX only;
- PV2 Modbus registers are verified only on the installed POW-HVM10.2M
  firmware and remain optional;
- Menu 16 cannot be read back and is stored as ACK-confirmed context;
- Grid Import is estimated and not billing-grade;
- the 06:05 early check, 07:00 handover, and 23:50 AHM ownership transition depend on Home Assistant scheduling.

Full documentation: <https://github.com/serhiykravchenko-sys/EnergyHub/blob/main/docs/operations/INSTALLATION.md>
