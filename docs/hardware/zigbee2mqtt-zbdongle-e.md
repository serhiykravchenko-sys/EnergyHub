# Zigbee2MQTT with SONOFF ZBDongle-E

## Purpose

This guide records the EnergyHub 1.1 Zigbee transport setup without storing Zigbee network keys, PAN identifiers, MQTT credentials, or the coordinator's unique serial token in Git.

Zigbee2MQTT owns the coordinator and Zigbee device transport. Home Assistant owns pairing and manual controls. EnergyHub consumes Home Assistant/MQTT device state and must never open the coordinator serial device directly.

## Validated installation

Live validation on 2026-08-02 used:

- official stable Zigbee2MQTT Home Assistant app `2.13.0-1`;
- SONOFF Zigbee 3.0 USB Dongle Plus V2 (ZBDongle-E);
- adapter `ember`;
- software flow control, `rtscts: false`;
- EmberZNet firmware `7.4.4 [GA]`;
- persistent coordinator path with the form `/dev/serial/by-id/usb-Itead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_V2_<device-id>-if00-port0`;
- Mosquitto at `mqtt://core-mosquitto:1883`, with credentials managed by Home Assistant and not stored in this repository;
- MQTT base topic `zigbee2mqtt`;
- Home Assistant discovery enabled;
- Zigbee2MQTT frontend enabled;
- Zigbee channel `25`.

The coordinator is installed on a 1 m USB extension cable away from the Raspberry Pi and inverter to reduce interference.

The closest active 2.4 GHz access point was detected at 2412 MHz, Wi-Fi channel 1. Zigbee2MQTT's onboarding selection maps that Wi-Fi channel to Zigbee channel 25.

The PowMr inverter remains on its separate FTDI persistent identity. Do not substitute `/dev/ttyUSB0` or `/dev/ttyUSB1` for either device in persistent configuration because those names can change after reconnect or restart.

## Ownership and safety rules

- Do not add the coordinator to ZHA while Zigbee2MQTT owns it.
- Do not configure EnergyHub to access the coordinator serial path.
- Use `adapter: ember`; the older `ezsp` setting is deprecated for this coordinator family.
- Keep `rtscts: false` for the ZBDongle-E V2 software-flow-control connection.
- Keep the dongle on a USB extension cable and away from USB 3, Wi-Fi, and other 2.4 GHz interference where practical.
- Never commit `network_key`, `pan_id`, `ext_pan_id`, MQTT credentials, `database.db`, or coordinator backup data.
- Do not change the Zigbee channel after devices are paired without a migration plan and revalidation.

## Configuration outline

Use the Zigbee2MQTT onboarding page or supported app configuration flow. The resulting non-secret settings must be equivalent to:

```yaml
mqtt:
  server: mqtt://core-mosquitto:1883
serial:
  port: /dev/serial/by-id/usb-Itead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_V2_<device-id>-if00-port0
  adapter: ember
  rtscts: false
advanced:
  channel: 25
frontend:
  enabled: true
homeassistant:
  enabled: true
```

The live `configuration.yaml` also contains generated security values and Home Assistant-managed MQTT credentials. Preserve those values during edits and recovery; do not replace them from this example.

## Validation

The initial start, a Zigbee2MQTT app restart, and an attended full Home Assistant host restart passed. The logs confirmed:

- Zigbee2MQTT `2.13.0` started;
- `zigbee-herdsman` started and resumed after restart;
- the coordinator reported EmberZNet `7.4.4 [GA]`;
- MQTT connected successfully;
- Home Assistant discovery messages were published;
- Zigbee2MQTT reached the started state after each restart;
- after the full Home Assistant restart, the existing Zigbee network resumed with zero paired devices, the bridge reported `online`, and periodic health reports continued with MQTT connected for at least 30 minutes.

The full Home Assistant host-restart check was completed on 2026-08-02. No coordinator reconfiguration or ZHA ownership was required.

A private encrypted Home Assistant backup was verified on 2026-08-02. Its restore contents include the Zigbee2MQTT app `2.13.0-1` and application data. Backup contents, Zigbee security values, and credentials remain outside the repository.

### Observed Ember ASH timeout and attended recovery

At 21:30 on 2026-08-02, one Ember `ASH_ERROR_TIMEOUTS` transaction failure disconnected the Ember adapter and stopped Zigbee2MQTT. The Home Assistant app Watchdog was disabled at the time, so no automatic watchdog recovery occurred.

At 17:29 on 2026-08-03, an attended manual Start recovered the same coordinator and Zigbee network. Both paired devices and their states, MQTT, bridge/device availability, and Home Assistant discovery returned without re-pairing or an observed relay command. The Home Assistant app Watchdog was enabled only after that successful recovery.

At 10:35 on 2026-08-05, a second observed failure reset and restarted ASH, then failed to start the EZSP layer with `HOST_FATAL_ERROR`. Zigbee2MQTT exited while the Home Assistant app Watchdog was enabled, and no autonomous recovery was observed. The complete attended recovery timeline still needs to be captured. This incident shows that the app Watchdog alone is not a demonstrated recovery mechanism for the current Ember failure mode.

At 07:30 on 2026-08-06, a third incident began from a healthy bridge. The preceding health report showed MQTT connected, low host load, about 30% memory use, two low-traffic devices, and roughly 50 minutes of process uptime. A `SEND_UNICAST` transaction then failed with `ASH_ERROR_TIMEOUTS`. ASH counters reported zero CRC errors, communication errors, retry frames, and ACK timeouts before the port closed and the bridge published `offline`.

Supervisor Watchdog automatically launched ten restart attempts between 07:30 and 07:35. Every attempt opened the serial port and performed five ASH adapter resets, but none received a successful ASH/EZSP startup and all ended with `HOST_FATAL_ERROR`. The crash loop then stopped. The add-on log line `Starting Zigbee2MQTT without watchdog` refers to Zigbee2MQTT's internal watchdog; it does not mean the Home Assistant Supervisor Watchdog was disabled.

At 11:51 on 2026-08-06, an attended manual Start established ASH on its second reset. Zigbee2MQTT resumed the existing network, both paired devices, MQTT, bridge/device availability, and Home Assistant discovery without re-pairing or an observed relay toggle. Both plugs reported ON after recovery and produced new electrical reports. This validates attended recovery again, but it also confirms that repeated immediate app restarts are ineffective while the Ember NCP remains unresponsive.

The evidence does not yet identify the root cause. The low process load and low Zigbee message rate make resource exhaustion and network flooding less likely for this incident. Zero ASH CRC/communication counters do not prove the USB path is healthy because host/kernel USB disconnect and power events are outside those counters. Before firmware or hardware changes, retain host USB/power logs, Supervisor restart logs, and the full Zigbee2MQTT debug log; inspect the 1 m extension cable and Raspberry Pi power path; and preserve a verified coordinator/network backup.

The later attended diagnostic check on 2026-08-06 found no retained host-log match for USB, CP210x, serial, reset, or undervoltage around the failure. The only matches were unrelated `wlan0` disconnect/reconnect activity at 09:00. The retained Supervisor log began after the 07:30 restart loop and therefore could not independently reconstruct it. Current app information confirmed Zigbee2MQTT `2.13.0-1` in `started` state with Supervisor `watchdog: true`, `uart: true`, and `udev: true`. These checks confirm current configuration and recovery but neither prove nor exclude a transient USB, power, or NCP fault at 07:30.

This observation validates attended recovery, but it does not prove that every retained entity value is current. Electrical values such as power, current, voltage, and energy can continue to show the last reported value across an availability interruption. Bridge `online` and device `online` therefore mean transport reachability, not measurement freshness.

### Paired-device recovery and electrical observations

- the second-floor plug completed an Offline-to-Online availability transition and returned safely OFF after power was reconnected while its configured state was OFF;
- during a later Home Assistant restart, both devices remained Online, the first-floor plug remained ON, and the first-floor heat pump continued cooling;
- first-floor electrical reports arrived asynchronously during inverter-compressor ramp-up; a stabilized example was 804 W, 3.37 A, and 226 V;
- the second-floor polled device produced live heat-pump measurements and increasing energy.

These values are useful operational trend data. They are not reference-meter calibration, electrical-protection inputs, or proof that either plug is electrically suitable for its heat pump. Ember failure diagnosis, bounded recovery monitoring, and verification against both heat-pump nameplates remain pending.

After any adapter, MQTT, Zigbee2MQTT, or Home Assistant interruption:

1. confirm the Zigbee2MQTT bridge is online;
2. confirm the individual device is available;
3. require a new report for every measurement used by a decision, with a timestamp later than the recovery;
4. reconstruct controller ownership and timer state conservatively;
5. keep automatic starts inhibited if availability, freshness, switch state, or ownership is uncertain.

Do not issue a speculative toggle to force state synchronization. Manual control and the Home Assistant auto-off timers may remain available, but future EnergyHub Smart Thermal control must not resume commands from bridge availability or retained telemetry alone. A future Watchdog recovery must pass the same state, availability, freshness, ownership, and no-unintended-relay checks before it is trusted. Heat-pump nameplate and load-suitability checks remain separate validation gates.

## Backup and recovery

Before firmware, channel, coordinator, or host migration:

1. stop Zigbee2MQTT;
2. create and verify a Home Assistant backup that includes the Zigbee2MQTT app and its data;
3. retain the complete `/config/zigbee2mqtt` data directory through an approved private backup path;
4. keep the backup outside Git and protect it as a secret-bearing artifact;
5. restart Zigbee2MQTT and verify normal operation.

For recovery, restore the complete data set rather than reconstructing only `configuration.yaml`. Keep the existing network key, PAN identifiers, device database, and coordinator backup together. Restore the stable coordinator path, start Zigbee2MQTT, and validate the logs, bridge/device availability, fresh post-recovery telemetry, and ownership state before permitting device joins or enabling EnergyHub automation.

## Pairing gate

Keep `permit_join` disabled except during an attended pairing window. Pair one plug at a time and complete the validation matrix in the [EnergyHub 1.x Development Plan](../14-EnergyHub-1.x-Development.md) before any unattended automatic Smart Thermal use is considered.
