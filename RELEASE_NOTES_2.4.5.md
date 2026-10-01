# EnergyHub 2.4.5 / Family Assistant 2.4.8

Private candidate prepared on 2026-09-20. It is not committed, pushed,
deployed, live-validated, or publicly released.

## EnergyHub and Home Assistant

- Remove the retired Adaptive Hybrid, Early Solar, morning-load learner, and
  three-morning reserve-advisor services and runtime paths.
- Clear their retained MQTT discovery/state/input topics once at add-on startup.
- Remove obsolete restart-watt helpers, the duplicate Daily Summary grid-import
  sensor, and the hidden legacy decision panel.
- Use the same raw PV, house-load, SOC, and appliance-power sources across live
  cards, charts, statistics helpers, and the overload participant snapshot.
- Keep a valid last-known device state/power visible in the overload table;
  freshness remains explicit and automatic control still requires current
  verified evidence.

## Family Assistant

- Shorten family morning and HA-restart messages and use **DTEK** for external
  grid supply/support.
- Highlight active UHMC warnings and required DTEK support; omit routine
  humidity, all-clear, automatic-reserve advice, and routine overnight Grid Hold
  repetition.
- Show one compact control-authority line for inverter, minimum reserve, and
  overload protection, followed by heating authority.
- Read SOC and operating mode live at 08:00 and show current 15-minute PV power.
- Send the private technical chat a deduplicated summary of HA Core warnings and
  errors from the previous 24 hours.
- Remove retired target/advisor configuration fields and translations.

## Deployment boundary

The add-on and Family Assistant updates are ordinary local-app updates. The
Home Assistant `configuration.yaml`, `automations.yaml`, and dashboard storage
changes are a separate deployment scope and require comparison, backup, Core
stop for `.storage`, `ha core check`, Core start, and focused validation.
