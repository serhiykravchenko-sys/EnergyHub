# EnergyHub Installation and Upgrade

This document covers EnergyHub 1.1.0.

## Supported environment

EnergyHub 1.1.0 requires:

- Home Assistant OS with Supervisor/Apps;
- `aarch64` hardware;
- PowMr 10.2M using PI30MAX;
- FTDI USB-RS232 communication with the inverter;
- an MQTT broker reachable as `core-mosquitto` or another configured host;
- Home Assistant MQTT integration.

The release was validated on Raspberry Pi 4. Other `aarch64` Home Assistant OS hardware may work but has not been validated.

## Before installation

Create a Home Assistant backup and store a copy outside the Home Assistant device.

Confirm that the inverter USB-RS232 adapter is connected. A Zigbee coordinator may remain connected; EnergyHub identifies the inverter by its persistent FTDI device path rather than `/dev/ttyUSB0` or `/dev/ttyUSB1`.

## Installation from the GitHub app repository

1. In Home Assistant, open **Settings → Apps → App store**.
2. Open the top-right menu and choose **Repositories**.
3. Add the EnergyHub repository URL.
4. Refresh the App store.
5. Open **Energy Hub** and install it.
6. Do not start it until MQTT credentials and the serial path are configured.

EnergyHub can also be installed as a local development app by copying the repository's `addon/` directory to:

```text
/addons/local/energy_hub
```

After copying a local app, reload the App store so Home Assistant discovers the app or its changed manifest.

## Find the persistent inverter serial path

Open Terminal & SSH or the Studio Code Server terminal and run:

```bash
ha hardware info
```

Find the FTDI adapter used by the inverter. Use its `by_id` value, for example:

```text
/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_REPLACE_WITH_YOUR_ID-if00-port0
```

Do not configure EnergyHub with `/dev/ttyUSB0` or `/dev/ttyUSB1`. Those names may change after a restart or when another USB serial device is connected.

A SONOFF Zigbee coordinator normally has a different persistent path, for example:

```text
/dev/serial/by-id/usb-Itead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_V2_...-if00-port0
```

Do not select the Itead/Sonoff path for EnergyHub.

## Configure the app

Open **Settings → Apps → Energy Hub → Configuration**.

Required values:

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

Save the configuration.

The app manifest enables:

```yaml
uart: true
udev: true
```

No Docker-style host/container device mapping is required.

## First start

Start Energy Hub and open its log.

A healthy startup includes lines similar to:

```text
[Energy Hub] Starting...
[Energy Hub] Version 1.1.0
Serial: /dev/serial/by-id/usb-FTDI_...
MQTT connected
OK | SOC=... | PV1=... | Load=... | Grid=online | Published=17
Inverter settings updated: Menu 01=SBU, Menu 16=OSO
Startup strategy reconstructed: mode=solar, Menu 01=SBU, Menu 16=OSO
Startup reconstruction accepted without inverter writes: mode=solar
EnergyHub health: Communication starting -> online
```

The exact operating mode may differ if EnergyHub was intentionally stopped during Hybrid or Panic.

## Home Assistant configuration

EnergyHub depends on selected Home Assistant helpers, automations, scripts, MQTT inputs, and dashboards stored under:

```text
homeassistant/live/
```

The repository includes synchronized examples from the reference installation, but they are not a complete Home Assistant backup and may contain installation-specific entity IDs.

Review the files before copying them to another Home Assistant installation. The architectural boundary and current entity set are documented in [12-HomeAssistant-Configuration.md](12-HomeAssistant-Configuration.md).

## Local development deployment

The reference add-on development workflow uses:

```powershell
.\tools\dev\deploy-to-ha.ps1 -Scope Addon
```

The deployment script mirrors the local repository's `addon/` directory into the Home Assistant local app directory. After deployment:

1. stop Energy Hub;
2. rebuild it;
3. start it;
4. inspect the app log.

The Docker build runs all release tests. A failed test stops the rebuild.

Home Assistant YAML and selected `.storage` deployment is a separate scope. See [Home Assistant Configuration](12-HomeAssistant-Configuration.md#development-deployment) for guarded commands and post-deploy actions. Never copy `.storage` while HA Core is running.

## Watching the build log

Open:

```text
Settings → System → Logs
```

Select **Supervisor** as the source. A successful rebuild ends with:

```text
Build local/aarch64-addon-energy_hub:1.1.0 done
App 'local_energy_hub' successfully rebuilt
```

The test stage contains:

```text
Ran 24 tests in ...
OK
```

## Upgrade from an earlier local build

1. Create a Home Assistant backup.
2. Stop Energy Hub.
3. Replace the app files while preserving the `addon/` directory structure.
4. Keep the existing Home Assistant app options unless a migration explicitly requires a change.
5. Confirm that `serial_port` uses the persistent FTDI `by-id` path.
6. Reload the App store when `config.yaml` changed.
7. Rebuild Energy Hub.
8. Start it and verify MQTT, telemetry, operating mode, and health.
9. Perform a Home Assistant host restart when validating USB persistence.

The app's `/data` directory is managed by Home Assistant and is not part of the source-code replacement. Do not delete it during a normal upgrade.

## Zigbee coordinator coexistence

EnergyHub does not configure or control a Zigbee coordinator.

A SONOFF ZBDongle-E may remain connected during EnergyHub operation. The reference 1.1 installation assigns its own persistent `by-id` path exclusively to Zigbee2MQTT; ZHA must not claim the same coordinator. See [Zigbee2MQTT with SONOFF ZBDongle-E](hardware/zigbee2mqtt-zbdongle-e.md).

For radio reliability, a USB 2.0 port or USB extension cable is generally preferable for a 2.4 GHz Zigbee coordinator. This placement does not affect EnergyHub's FTDI serial selection.

## Troubleshooting

### `can't open file '/publisher.py'`

The app entry point must run:

```text
/app/publisher.py
```

The current `run.sh` already uses this path. Rebuild the image after replacing files.

### `Permission denied` or serial device unavailable

Confirm:

- `uart: true` and `udev: true` exist in `addon/config.yaml`;
- the configured path belongs to the FTDI inverter adapter;
- the device is physically connected;
- the path still appears in `ha hardware info`.

### EnergyHub opens the wrong USB device

Replace any `/dev/ttyUSB*` configuration with the FTDI `/dev/serial/by-id/...` path.

### App rebuild fails at the test stage

Open Supervisor logs and copy the first `FAIL` or `ERROR` section. Do not remove the Dockerfile test gate merely to complete the build.

### MQTT does not connect

Confirm the broker is running and that the configured username/password are valid. EnergyHub does not ship usable public credentials.

### Old MQTT entities remain

They may be retained MQTT Discovery topics from an older build. Confirm the current build is running before clearing only the obsolete retained topics. Do not delete current EnergyHub Discovery topics indiscriminately.

## Safety notes

- EnergyHub must never automatically restart the inverter.
- Manual inverter control remains available.
- Menu 16 is ACK-confirmed, not read-back verified.
- Grid Import is informational, not billing-grade.
- Do not use an unreviewed Home Assistant configuration from another installation without checking entity IDs.
