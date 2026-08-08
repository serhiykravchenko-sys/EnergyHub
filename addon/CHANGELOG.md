# Changelog

## 1.3.0 - 2026-08-08

- Added post-07:00 Adaptive Hybrid energy-balance planning and persisted AHM targets.
- Reworked automatic Panic into a 07:00–23:50 conservative reserve controller with 20/60/80/95% Grid Confidence targets.
- Added offline waiting, grid charging, and Panic Grid Hold phases with restart-safe strategy reconstruction.
- Added AHM-to-Panic morning-debt handoff and authoritative AHM takeover at 23:50.
- Expanded MQTT diagnostics, release tests, and Home Assistant dashboard visibility.

## 1.1.0 - 2026-08-06

- Preserved the tested EnergyHub 1.0.2 inverter runtime and 24-test build gate.
- Added the repository-side Home Assistant smart-plug dashboards, matching heat-pump auto-off controls, local energy history, and reserve-only OFF protection.
- Added guarded deployment tooling and Zigbee2MQTT/ZBDongle-E setup and resilience documentation.
- Deferred every automatic smart-plug ON action and Smart Thermal control to a later milestone.

## 1.0.2 - 2026-08-01

- First release-ready EnergyHub 1.0 build.
- Added persistent FTDI `/dev/serial/by-id` configuration with UART/udev access.
- Added executable release tests enforced during the Docker image build.
- Pinned `paho-mqtt` and `mppsolar` dependencies.
- Removed weak public MQTT credential defaults.
- Fixed the runtime publisher path and build-version startup banner.
- Removed obsolete raw inverter warning MQTT Discovery/state.
- Validated rebuild and full Home Assistant host restart on the real installation.

See the repository root `CHANGELOG.md` for complete details.
