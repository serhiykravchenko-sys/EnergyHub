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

On 2026-08-08, after replacing the USB extension cable, the same `SEND_UNICAST` / `ASH_ERROR_TIMEOUTS` signature stopped Zigbee2MQTT at 07:40. An attended manual Start at 08:16 recovered immediately. At 09:16:23, 3,607 seconds after that restart, another `ASH_ERROR_TIMEOUTS` terminated the process. This time the Node.js stack identified `EmberAdapter.watchdogCounters()` calling `ezspReadAndClearCounters()`. At 12:38:41, a later failure named `READ_AND_CLEAR_COUNTERS` directly as the timed-out last frame immediately after the two-hour NCP/ASH counter report. An upstream Zigbee2MQTT report documents a closely matching roughly 60-minute Ember failure during `READ_AND_CLEAR_COUNTERS`, sometimes logging `SEND_UNICAST` as the last frame. The periodic Ember counter transaction is therefore the confirmed failure point, although the underlying firmware, NCP hardware, USB/power, or driver cause remains unresolved. The cable replacement did not eliminate the failure and therefore reduces confidence that the original extension cable was the sole cause.

The installed Zigbee2MQTT app `2.13.0-1` was current in the Home Assistant app store when checked. The coordinator reported EmberZNet `7.4.4 [GA]`, corresponding to the older 7.4.4.0 line. Current Zigbee2MQTT guidance supports EmberZNet 7.4.x through 9.1.x and recommends coordinator firmware 8.0.2 or later for Ember timeout problems associated with high-traffic devices.

On 2026-08-08, the official SONOFF Dongle Flasher identified the device and existing 7.4.4 coordinator firmware correctly, then offered official stable Zigbee Coordinator 8.0.2 at 115200 baud. The attended flash completed successfully. Zigbee2MQTT started at 16:34 with `adapter: ember`, software flow control, and the persistent serial identity unchanged. It reported EmberZNet `8.0.2 [GA]` build 397 / EZSP 14, matched the existing coordinator network to configuration, retained both paired plugs, connected to MQTT, and published bridge online plus fresh device state without re-pairing or an observed relay command. The reported floor-1 OFF and floor-2 ON states matched the known pre-start states, and both devices became available.

At 19:33:10, almost three hours after the 16:34 start, firmware 8.0.2 repeated the same `SEND_UNICAST` / `ASH_ERROR_TIMEOUTS` stop with zero reported ASH CRC, communication, retry, or ACK-timeout counters. This failed the firmware-only remediation. An attended manual Start at 09:34 on 2026-08-09 again resumed firmware 8.0.2, the existing network, both Online devices, MQTT, and the known ON relay states without re-pairing or an observed command.

The next controlled isolation test disables only the second-floor `TS011F_plug_3` electrical poller by setting its supported `measurement_poll_interval` option from the 60-second default to `-1`. Relay state/control and availability remain available, but its power, current, voltage, and energy values must be treated as stale during the test. Surviving at least four periodic counter cycles would implicate the polling/counter interaction; another timeout would move diagnosis toward the driver, coordinator hardware, or host USB/power path.

The polling-isolation test began on 2026-08-09. `measurement_poll_interval` was set to `-1` for `second_floor_heat_pump_plug`, then Zigbee2MQTT was restarted once at 10:06 to reconstruct the device extension without the polling timer. Startup passed with firmware 8.0.2, the existing network, MQTT, both devices Online, and the known ON relay states. The second-floor electrical snapshot published during startup is the reconstructed/initial state and does not by itself show that periodic polling remains active. The next validation is absence of the former one-minute reports, followed by four counter cycles and 24-hour stability.

The one-minute electrical reports stopped as expected, but the isolation test failed at 11:28:47 after about 82 minutes. Zigbee2MQTT attempted an active availability ping to `second_floor_heat_pump_plug`; its `genBasic.read(["zclVersion"])` `SEND_UNICAST` transaction ended in `ASH_ERROR_TIMEOUTS`, the adapter disconnected, and Zigbee2MQTT exited. ASH again reported zero CRC, communication, retry, and ACK-timeout counters. A manual Start at 15:38 required two ASH reset attempts, then recovered firmware 8.0.2, the same network, both Online devices, MQTT, and the known ON relay states without an observed command.

Disabling measurement polling therefore did not resolve the failure. The next controlled isolation test keeps `measurement_poll_interval: -1` and sets per-device `availability: false` only for `second_floor_heat_pump_plug`, preventing Zigbee2MQTT from issuing the active availability ping that exposed this failure. During the test, both electrical telemetry and automatic Online/Offline status for that plug are intentionally unavailable or stale. A later failure would show that second-floor measurement polling and availability pings are not required triggers; survival would implicate coordinator traffic to this TS011F device without proving whether the ping caused or merely detected the NCP failure.

On 2026-08-10, another failure at 15:36:56 occurred after about 30 minutes of process uptime. The last operation was again an active `genBasic` availability ping to `second_floor_heat_pump_plug`, ending in `SEND_UNICAST` / `ASH_ERROR_TIMEOUTS` with clean reported ASH error counters. Manual recovery at 21:51 passed with both known OFF relay states.

The Zigbee2MQTT frontend did not expose a separate per-device `availability: false` control on the general Settings page. At 21:58, the attended test instead selected the stronger `disabled` option for `second_floor_heat_pump_plug`, while retaining `measurement_poll_interval: -1`, then restarted Zigbee2MQTT. Startup passed with firmware 8.0.2, bridge online, first-floor availability Online, and no second-floor availability publication. The device list showed the second-floor device as Disabled. This excluded it from availability and other Zigbee2MQTT-managed device activity, so Home Assistant/Zigbee2MQTT state and control for it were intentionally untrusted; the physical relay was known OFF at test start.

The stronger isolation test failed on 2026-08-11 at 06:58:35 after 32,406 seconds, about nine hours. The bridge-health report immediately before failure showed MQTT connected and normal host load. The exception stack directly identified `EmberAdapter.watchdogCounters()` calling `ezspReadAndClearCounters()`; the logged last frame was `SEND_UNICAST`, and the ASH counters again contained no CRC, communication, retry, or ACK-timeout errors. Because the entire second-floor device was disabled throughout this run, neither its measurement polling nor its active availability ping is a required trigger. This also ends the hypothesis that traffic managed for that TS011F device is necessary for the fault. An attended Start at 08:47 resumed firmware 8.0.2, the existing network, MQTT, and both known-OFF cached device states without re-pairing or an observed relay command; only the enabled first-floor device published availability.

After restoring the second-floor device and restarting Zigbee2MQTT, Supervisor Watchdog was enabled for an attended recovery test on 2026-08-11. Five `ASH_ERROR_TIMEOUTS` adapter stops followed at 13:10, 13:21, 13:43, 13:54, and 14:11. The first, third, fourth, and fifth automatic recovery sequences started successfully on their first Supervisor attempt. The 13:21 sequence produced three consecutive `HOST_FATAL_ERROR` EZSP startup failures before its fourth attempt connected at 13:22:51. Across the incident cluster, Supervisor launched eight processes: five reached a running bridge and three failed during startup. The final automatic recovery published the bridge Online at 14:12:12 and remained healthy through at least 22:15, including successful hourly NCP/ASH counter reports from 15:12 through 22:12. Both plugs returned Online after successful starts, and their published relay states remained OFF; startup electrical snapshots remain subject to the normal freshness warning. Watchdog therefore provides useful automatic recovery, but the rapid crash cluster and temporary fatal-start loop mean it is mitigation rather than a root-cause fix.

The next unattended sequence showed that Supervisor Watchdog is not reliable recovery. After about 16 hours of process uptime, the adapter stopped at 06:58:49 on 2026-08-12 with the same `ASH_ERROR_TIMEOUTS` and clean ASH error counters. Five automatic starts failed with `HOST_FATAL_ERROR`; the sixth connected and published the bridge Online at 07:01:37. The adapter failed again at 07:15:01, only about 13 minutes later. Four further automatic starts all ended in `HOST_FATAL_ERROR`, after which Supervisor stopped retrying and Zigbee2MQTT remained stopped from 07:17. The Home Assistant alert correctly reported the recovered interval and the later persistent offline state. This fails unattended-recovery acceptance: Watchdog may shorten some outages but cannot be treated as a bounded self-healing solution for this coordinator fault.

At 11:10 on 2026-08-12, the USB extension cable was removed for a direct-host-port isolation test. Zigbee2MQTT connected to ASH on its first attempt, recognized EmberZNet 8.0.2 build 397, matched the existing network, connected to MQTT, and published both plugs Online. Both cached relay states were OFF and matched the known pre-test condition. Firmware, device settings, and Supervisor Watchdog remain unchanged so that direct connection is the only test variable. Four-hour, 24-hour, and 48-hour stability checkpoints are required; another adapter timeout would rule out both tested extension cables as the necessary cause.

The direct-USB test remained uninterrupted through at least 07:16 on 2026-08-13, just over 20 hours after startup. The 07:10 bridge-health report showed 72,008 seconds of process uptime, MQTT connected, and continuing traffic from both devices. Hourly NCP/ASH counter reads continued successfully, with no `ASH_ERROR_TIMEOUTS`, `HOST_FATAL_ERROR`, or restart in the supplied interval. This passes the four-hour checkpoint but does not yet complete the 24-hour checkpoint at 11:10.

By 10:50 on 2026-08-16, direct USB had reached 344,418 seconds of uninterrupted process uptime, about 95 hours 40 minutes. MQTT remained connected, hourly NCP/ASH counter reads were succeeding, and the retained log contained no coordinator restart or fatal adapter signature. This passes both the 24-hour and 48-hour checkpoints and makes the USB extension path the leading cause of the coordinator instability observed in this installation. It does not identify which electrical or mechanical characteristic of the two tested extension configurations caused the failure.

At 08:35 and 09:02 on 2026-08-16, the second-floor plug separately failed active availability pings, including one failed state read after reconnect. The coordinator remained healthy throughout. The plug recovered Online at 09:07:52 and published fresh state at 09:07:54 and 09:08:15 with LQI 156 and relay state OFF, matching the known physical state. Treat this as a recovered transient endpoint reachability event, not a recurrence of the Ember adapter crash. Repeated endpoint interruptions would require separate radio-placement investigation.

Firmware maintenance gates:

1. verify private Home Assistant, Zigbee2MQTT data-directory, and coordinator backups;
2. keep `permit_join` disabled and record both relay states;
3. stop Zigbee2MQTT and ensure no ZHA or other process owns the coordinator;
4. flash only the verified ZBDongle-E Zigbee Coordinator image through an attended supported tool;
5. retain the prior 7.4.4.0 image and complete backup as the rollback path;
6. start Zigbee2MQTT with `adapter: ember` and `rtscts: false` unchanged;
7. verify firmware identity, existing network/devices, relay states, availability, fresh reports, and no unintended commands;
8. validate at least four counter cycles and 24 hours before enabling Supervisor Watchdog.

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

## Bridge health alerting

The working-tree Home Assistant configuration monitors Zigbee2MQTT's Home Assistant-discovered `binary_sensor.zigbee2mqtt_bridge_connection_state`, backed by the retained `zigbee2mqtt/bridge/state` topic. An offline state must persist for two minutes before one persistent alert is created, avoiding noise from short attended restarts. Recovery produces a separate notice and explicitly requires device availability and fresh post-recovery reports to be verified.

This first reliability increment is observable but not self-healing. It does not call the Supervisor API, restart Zigbee2MQTT, toggle a relay, or authorize automatic Smart Thermal control. The observed `HOST_FATAL_ERROR` restart loop shows that a bounded cooldown and escalation design must be validated before automatic recovery is enabled.

## Backup and recovery

Before firmware, channel, coordinator, or host migration:

1. stop Zigbee2MQTT;
2. create and verify a Home Assistant backup that includes the Zigbee2MQTT app and its data;
3. retain the complete `/config/zigbee2mqtt` data directory through an approved private backup path;
4. keep the backup outside Git and protect it as a secret-bearing artifact;
5. restart Zigbee2MQTT and verify normal operation.

For recovery, restore the complete data set rather than reconstructing only `configuration.yaml`. Keep the existing network key, PAN identifiers, device database, and coordinator backup together. Restore the stable coordinator path, start Zigbee2MQTT, and validate the logs, bridge/device availability, fresh post-recovery telemetry, and ownership state before permitting device joins or enabling EnergyHub automation.

## Pairing gate

Keep `permit_join` disabled except during an attended pairing window. Pair one plug at a time and complete the validation matrix in the [EnergyHub 1.x Development Plan](../roadmap/14-EnergyHub-1.x-Development.md) before any unattended automatic Smart Thermal use is considered.
