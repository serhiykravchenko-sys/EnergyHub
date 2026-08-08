# Energy Hub 1.3.0

Energy Hub is a local-first Home Assistant app for a PowMr 10.2M inverter using PI30MAX.

It publishes inverter telemetry through MQTT Discovery and implements explainable Solar, Adaptive Hybrid Charging/Grid Hold, and conservative daytime Panic Charging/Grid Hold strategies.

At 23:50, AHM calculates a 30–95% target from the morning bridge and aligned post-07:00 energy deficit. From 07:00 to 23:50, Panic protects 20/60/80/95% according to Grid Confidence and any AHM target genuinely missed at the morning handover.

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
device_name: PowMr 10.2M
```

## Healthy startup

```text
[Energy Hub] Version 1.3.0
Serial: /dev/serial/by-id/usb-FTDI_...
MQTT connected
OK | SOC=... | PV1=... | Load=... | Grid=online
Startup strategy reconstructed: mode=...
EnergyHub health: Communication starting -> online
```

## Upgrade

Create a backup, stop the app, update or replace its files, reload the App store when `config.yaml` changed, rebuild, start, and verify the log.

Do not delete the app's `/data` directory during a normal upgrade.

## Limitations

- `aarch64` only;
- PowMr 10.2M / PI30MAX only;
- Menu 16 cannot be read back and is stored as ACK-confirmed context;
- Grid Import is estimated and not billing-grade;
- the 07:00 handover and 23:50 AHM ownership transition depend on Home Assistant scheduling.

Full documentation: <https://github.com/serhiykravchenko-sys/EnergyHub/blob/main/docs/operations/INSTALLATION.md>
