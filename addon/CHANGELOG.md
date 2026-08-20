# Changelog

## 1.3.8 - 2026-08-18

- Persist the date through which a completed 23:50 AHM plan remains
  authoritative.
- While that dated plan is active, keep Solar above the target, enter Hybrid
  Grid Hold at the exact target, and enter or resume Hybrid Charging below it.
- Reevaluate on every fresh local telemetry cycle instead of waiting up to 30
  minutes; issue commands only for required state transitions.
- Keep stale telemetry and an absent grid command-free, and retry naturally
  after later fresh grid-present telemetry.
- Bound failed-transition retry so one unchanged night condition cannot issue
  repeated inverter requests on every telemetry cycle.
- Clear dated night enforcement only after a confirmed non-AHM Solar handover.

## 1.3.7 - 2026-08-15

- Added a guarded 06:05 release from Hybrid Grid Hold to Solar when the
  retained target is met, live aligned Total Solar is at least 300 W, and the
  dated 06:00-07:00 Solcast interval is at least 1.6 kWh.
- Enforced Autopilot, fresh telemetry, current date, local 06:00-07:00 window,
  grid-present, and confirmed Grid Hold gates inside EnergyHub.
- Added Early Solar MQTT diagnostics and transition-result publication.
- Presented the initial Hybrid state as `awaiting_evaluation` with retained
  target and next-evaluation context.
- Kept every failed or unavailable gate conservative: no inverter command and
  the normal 07:00 Solar handover remains authoritative.

## 1.3.6 - 2026-08-14

- Replace incompatible retained Hybrid decision state with the concise initial
  state whenever the EnergyHub app starts.
- Limit `hybrid_decision_reason` to Home Assistant's 255-character state
  boundary at the publisher.
- Add regression coverage for startup cleanup, retained publication, and the
  publisher boundary.

## 1.3.5 - 2026-08-14

- Added optional, strictly read-only PV2 Modbus RTU polling for verified
  registers 4563-4564 on the installed POW-HVM10.2M.
- Serialized PI30MAX and Modbus access behind the existing adapter-owned serial
  lock and isolated all PV2 failures from the PI30MAX loop.
- Added PV2 voltage, PV2 power, fresh aligned Total PV power, status,
  freshness, and sample-age MQTT entities.
- Added dedicated availability topics so retained PV2 and Total PV values are
  never presented as current after a failure, stale interval, or restart.
- Added protocol, failure-isolation, freshness, alignment, MQTT, and restart
  regression tests.

## 1.3.4 - 2026-08-14

- Published a concise Hybrid decision reason that stays within Home Assistant's sensor-state limit.
- Renamed `legacy_ramp_fallback` to the clearer `verified_ramp_fallback` diagnostic.
- Published `None` when Panic has no inherited AHM target.
- Replaced the exposed AHM slider with confirmed 5% adjustment buttons and clarified 3/3 learning-only diagnostics.
- Grouped the active AHM value, policy explanation, and advisor result with a prominent risk-coloured reserve display.

## 1.3.3 - 2026-08-13

- Fixed unnecessary Hybrid Grid Hold when projected 07:00 SOC already meets the adaptive target.
- Kept Grid Hold only for an overnight target crossing and Charging only when current SOC is below target.
- Preserved authoritative 23:50 AHM takeover from Panic by restoring Solar when reserve is sufficient.

## 1.3.2 - 2026-08-12

- Added a learned 07:00–12:00 essential-load profile that subtracts heat-pump energy from total house energy.
- Added conservative 75th-percentile hourly net-energy planning after three complete morning samples per interval.
- Retained the 1.3.1 verified solar-ramp model as the safe learning/input fallback.
- Added model-source, learning-progress, expected-load, solar, and net-deficit diagnostics.
- Added a persistent three-morning reserve advisor: increase after 2/3 low-margin mornings, decrease only after 3/3 high-margin mornings, otherwise keep or learn.
- Reject non-finite morning meter values and exclude incomplete SOC observations from reserve advice.

## 1.3.1 - 2026-08-12

- Added the configurable 20–50% AHM minimum reserve.
- Added independently validated 300 W → 600 W solar-ramp credit.
- Added retained minimum, raw/effective morning-gap, ramp-power, ramp-credit, and effective-support diagnostics.
- Removed the hidden fixed 10% AHM uncertainty margin from the target equation.
- Made the 23:50 plan actively protect its floor with Charging below target and Grid Hold at or above target.

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
