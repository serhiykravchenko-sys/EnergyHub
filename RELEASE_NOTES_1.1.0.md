# EnergyHub 1.1.0 — Smart Plug Reserve Guard

EnergyHub 1.1.0 extends the tested 1.0.2 inverter baseline with monitored smart plugs, focused Home Assistant dashboards, matching heat-pump auto-off timers, and reserve-only OFF protection.

The EnergyHub Python inverter runtime is intentionally unchanged. Solar, Hybrid Charging, Hybrid Grid Hold, Panic, Autopilot, telemetry, health, persistence, MQTT, and restart reconstruction retain their 1.0.2 behavior.

## Added

- Zigbee2MQTT `2.13.0-1` configuration and recovery documentation for the SONOFF ZBDongle-E using EmberZNet 7.4.4 and a persistent serial path;
- paired and validated first- and second-floor Zigbee heat-pump plugs;
- matching three-floor switch, live-power, 0–12 h auto-off-duration, and absolute turn-off-time controls;
- separate Heat Pumps and Water Systems dashboard views;
- local kWh accumulation for the third-floor Xiaomi plug, water boiler, and basement pump;
- daily, weekly, and monthly consumption charts;
- water-boiler reserve protection;
- grid-confidence-aware heat-pump reserve protection;
- guarded Home Assistant deployment with backups, dry runs, and stopped-Core protection for `.storage` files;
- operational records for the observed Ember ASH/EZSP failures and Tuya reauthentication incident.

## Reserve-only behavior

EnergyHub 1.1.0 never turns the boiler or a heat pump on.

Water boiler:

- 50% SOC: request OFF once;
- 41–50%: homeowner or motion automation may request ON;
- 40%: request OFF and latch the lockout;
- 60%: clear the lockout without turning the boiler on.

Heat pumps with a fully trusted grid:

- 50% SOC: request every heat pump OFF and latch the lockout;
- 60%: clear the lockout without turning anything on.

Fully trusted means Grid Confidence `normal`, 100% availability over 24 hours, 48 available hours over 48 hours, present grid voltage, and fresh EnergyHub telemetry.

Heat pumps under every degraded or unknown grid state:

- 80% SOC: request all running heat pumps OFF once;
- 70%: request floor 2 OFF again after an override;
- 60%: request floor 1 OFF again after an override;
- 50%: request floor 3 and every other heat pump OFF and latch the lockout;
- 90%: clear the lockout without turning anything on.

Stale EnergyHub telemetry produces no new smart-plug command. Lockouts remain best effort when Home Assistant, Zigbee2MQTT, the Xiaomi integration, the network, or a device is unavailable.

## Deployment

The add-on and Home Assistant configuration are deployed separately. Review [Installation and Upgrade](docs/INSTALLATION.md) and [Home Assistant Configuration](docs/12-HomeAssistant-Configuration.md) before copying files.

The Home Assistant changes require:

1. a backup;
2. guarded deployment of the selected YAML and `.storage` files;
3. `ha core check`;
4. a Core start or restart as instructed by the deployment scope;
5. supervised dashboard, entity, automation, notification, and log inspection.

## Validation status

- all 24 inherited add-on release tests pass;
- dashboard and helper storage files parse as JSON;
- deployment dry runs pass;
- the dashboard, auto-off timers, local energy sensors, and water-boiler helper were observed on the reference installation;
- final `ha core check`, restart, and supervised validation of the grid-confidence-aware heat-pump guard remain required before tagging `v1.1.0`.

## Known limitations

- no automatic Smart Thermal starts;
- no automatic Zigbee2MQTT/Ember recovery;
- Home Assistant Repairs and cloud-authentication failures are not yet aggregated into EnergyHub System Health;
- smart-plug measurements are operational trend data, not calibrated electrical-protection inputs;
- heat-pump nameplate and plug suitability verification remain installation responsibilities;
- Adaptive Night Hybrid is documented design work, not 1.1.0 runtime behavior;
- the stable public distribution repository is not modified by this local development work.
