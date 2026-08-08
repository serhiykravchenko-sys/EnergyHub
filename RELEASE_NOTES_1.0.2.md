# EnergyHub 1.0.2

EnergyHub 1.0.2 is the first release-ready build of EnergyHub 1.0 — Autonomous Home.

## Highlights

- Local-first Home Assistant energy management for PowMr 10.2M / PI30MAX.
- Solar, Hybrid Charging, Hybrid Grid Hold, and Panic strategies.
- Explainable Hybrid and Panic decisions.
- Verified inverter control and safe Solar recovery.
- Restart strategy reconstruction without unnecessary inverter writes.
- Grid History, Grid Confidence, Daily Summary, and estimated Grid Import.
- Layered health monitoring and QPIWS warning/fault polling.
- Persistent FTDI serial access through `/dev/serial/by-id`.
- Executable tests enforced during the Docker image build.

## Release validation

The 1.0.2 image was rebuilt successfully on Home Assistant OS for `linux/arm64`. All 24 release tests passed. Live MQTT, serial telemetry, startup reconstruction, and a full Home Assistant host restart were validated with both the inverter adapter and a SONOFF Zigbee coordinator connected.

## Installation

Read [docs/operations/INSTALLATION.md](docs/operations/INSTALLATION.md) before starting the app. New installations must configure:

- MQTT username and password;
- the FTDI adapter's persistent `/dev/serial/by-id/...` path.

## Important limitations

- `aarch64` only;
- PowMr 10.2M / PI30MAX only;
- Menu 16 is ACK-confirmed but cannot be read back;
- Grid Import is informational, not billing-grade;
- strategy parameters are not yet configurable through the UI;
- the 07:00 Solar restoration is scheduled by Home Assistant.

## Upgrade note

Existing local installations should preserve their app options and `/data` state. After replacing files, reload the app store, rebuild the app, start it, and verify the startup log. A backup is recommended before upgrading.
