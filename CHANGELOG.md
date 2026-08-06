# Changelog

All notable EnergyHub changes are recorded here.

## [1.1.0] - 2026-08-06

### Documentation

- Started the EnergyHub 1.x development plan while preserving 1.0.2 as the released baseline.
- Defined and completed the 1.1 scope for Zigbee2MQTT, paired smart-plug validation, focused dashboards, and reserve-only smart-plug OFF protection.
- Clarified the Zigbee2MQTT, Home Assistant, and EnergyHub responsibility boundaries and deferred automatic Smart Thermal starts.
- Added the Zigbee2MQTT/ZBDongle-E configuration, validation, backup, recovery, interference, and pairing guide.
- Documented the observed Ember ASH timeout, attended manual recovery, bridge/device availability recovery, stale-measurement risk, and conservative automatic-control recovery gate.
- Recorded the 2026-08-05 Ember/EZSP `HOST_FATAL_ERROR` recurrence while the app Watchdog was enabled, with no autonomous recovery observed.
- Recorded the 2026-08-06 `ASH_ERROR_TIMEOUTS` recurrence: Supervisor Watchdog made ten restart attempts, every ASH/EZSP startup failed, the crash loop stopped, and a later attended manual Start recovered the existing network and both devices.
- Recorded the expired Tuya authentication repair as the probable cause of the stale EnergyHub beacon color and separated external-integration health from inverter telemetry health.
- Prioritized Adaptive Night Hybrid design so projected overnight SOC is protected until useful solar production, rather than sunrise alone.
- Added a dedicated hand-drawn infographic for the water-boiler and grid-confidence-aware heat-pump reserve logic.

### Home Assistant

- Added matching heat-pump controls for all three floors, then consolidated the dedicated Heat Pumps view to switch, live power, 0–12 h auto-off duration, absolute turn-off time, and shared consumption history.
- Added floor-1 and floor-2 auto-off helpers and automations with the proven floor-3 behavior; duration `0` remains manual mode.
- Removed empty `New section` headings from the dashboard.
- Added dedicated Heat Pumps and Water Systems views with compact manual controls and daily/weekly/monthly consumption graphs; Xiaomi plug energy history is calculated locally from live watts to avoid false cloud-counter jumps.
- Added staged water-boiler reserve protection: a one-time 50% SOC shed, a latched 40% emergency OFF lockout, and fresh-telemetry unlock at 60% without automatic restoration.
- Added grid-confidence-aware heat-pump reserve protection. A fully trusted grid uses only the 50% all-floor lockout and 60% unlock; otherwise all floors shed once at 80%, floor 2 again at 70%, floor 1 at 60%, and the 50% lockout remains until 90%. No heat pump is started automatically.
- Added scoped deployment automation for add-on code versus Home Assistant YAML/storage, including target-file backups, dry runs, post-deploy guidance, and a mandatory stopped-Core assertion for `.storage`.

### Development installation

- Installed and configured the official stable Zigbee2MQTT Home Assistant app for the SONOFF ZBDongle-E using its persistent serial identity, `ember`, software flow control, MQTT discovery, and Zigbee channel 25.
- Validated EmberZNet 7.4.4, coordinator startup, MQTT connection, discovery publication, Zigbee2MQTT app-restart recovery, and full Home Assistant host-restart recovery without changing EnergyHub 1.0.2 runtime behavior.
- Completed the Zigbee2MQTT foundation with a 1 m interference-reducing USB extension and a verified private encrypted backup containing Zigbee2MQTT app data.
- Paired and named the first- and second-floor Zigbee smart plugs, identified their direct-reporting and polled-reporting TS011F variants, and validated manual relay/physical-button state synchronization with safe power-outage behavior.
- Recorded the 2026-08-02 Ember `ASH_ERROR_TIMEOUTS` stop while the Home Assistant app Watchdog was disabled and the attended manual Start on 2026-08-03 that recovered the coordinator, both paired devices, MQTT, availability, and Home Assistant discovery without re-pairing or an observed relay command.
- Enabled the Home Assistant app Watchdog only after manual recovery; the 2026-08-05 recurrence did not recover autonomously, so bounded monitoring and recovery remain open work.
- Confirmed from the 2026-08-06 log that Supervisor Watchdog can restart the app but cannot recover an Ember NCP that remains unresponsive across restarts.
- Validated second-floor Offline-to-Online availability and safe OFF power recovery, plus a later Home Assistant restart that retained both devices Online while the first-floor plug remained ON and its heat pump continued running.
- Recorded first-floor asynchronous compressor ramp-up telemetry, including a stabilized 804 W, 3.37 A, 226 V example, as trend data rather than calibrated electrical-protection input.

## [1.0.2] - 2026-08-01

First release-ready EnergyHub 1.0 build.

### Added

- Solar, Hybrid Charging, Hybrid Grid Hold, and Panic operating strategies.
- Explainable Hybrid and Panic decision services.
- Verified PowMr Menu 01 control with QPIRI read-back.
- ACK-confirmed and persisted Menu 16 control.
- Startup strategy reconstruction without unnecessary inverter writes.
- Communication, Battery, Telemetry Freshness, Inverter, and System Health monitoring.
- QPIWS warning and fault polling.
- Rolling Grid History, Grid Availability, and weighted Grid Confidence.
- Persistent Daily Summary and mode-aware Grid Import estimation.
- MQTT Discovery for EnergyHub and PowMr entities.
- Home Assistant Autopilot, schedules, manual Panic control, notifications, dashboards, and selected configuration synchronization.
- Executable release tests for decision boundaries, telemetry freshness, restart reconstruction, transition sequencing, and recovery behavior.
- Docker build test gate using `python3 -m unittest discover -s tests -v`.
- Installation, upgrade, app-store, release, project-state, roadmap, and Home Assistant integration documentation.

### Changed

- Pinned tested Python dependencies:
  - `paho-mqtt==1.6.1`;
  - `mppsolar==0.16.56`.
- Replaced weak public MQTT credential defaults with blank values that must be configured by the installer.
- Changed serial access from unstable `/dev/ttyUSB*` numbering to a configurable persistent `/dev/serial/by-id/...` path.
- Enabled app access to UART and udev device information.
- Made the startup banner use the Home Assistant build version instead of a hard-coded string.
- Removed the experimental Away Mode runtime from EnergyHub 1.0 and deferred the broader concept to Smart Thermal Energy.
- Removed obsolete MQTT Discovery/state for the raw inverter warning sensor.
- Standardized Daily Summary Grid Import naming as `sensor.energyhub_daily_summary_grid_import`.
- Clarified that Menu 16 is ACK-confirmed but cannot be independently read back on the current inverter.
- Clarified that Grid Import is informational and not billing-grade.

### Fixed

- App startup after USB device numbering changes.
- Serial permission/access behavior after Home Assistant restarts.
- Packaging path mismatch between `/publisher.py` and `/app/publisher.py`.
- Hard-coded `1.0.0` startup banner in later 1.0.x builds.
- False Telemetry Freshness warnings caused by unchanged but valid house-load telemetry.
- Startup ambiguity and unnecessary inverter writes during consistent Solar reconstruction.
- Partial Hybrid transition recovery back to Solar.
- Stale Daily Summary snapshot handling across date boundaries.
- Invalid raw inverter warning MQTT entity publication.

### Validation

- Rebuilt successfully on Home Assistant OS for `linux/arm64`.
- All 24 release tests passed during the Docker image build.
- Live telemetry and MQTT Discovery validated after rebuild.
- Full Home Assistant host restart validated with both the inverter FTDI adapter and a SONOFF Zigbee coordinator connected.
- Solar mode reconstructed from actual Menu 01 plus persisted Menu 16 without inverter writes.

### Known limitations

- `aarch64` only in 1.0.2.
- Current hardware support is PowMr 10.2M / PI30MAX.
- No PV2 or output-2 telemetry.
- Menu 16 cannot be read back.
- Grid Import is estimated and may be affected by simultaneous daytime PV.
- Strategy parameters are still code/configuration constants.
- The 07:00 return to Solar depends on Home Assistant scheduling.
- General telemetry quarantine, direct BMS integration, and bounded recovery services are future work.

## [0.1] - 2026-06

### Added

- Project philosophy, manifesto, vision, design principles, initial architecture, roadmap, backlog, and repository structure.
