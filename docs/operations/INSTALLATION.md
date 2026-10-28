# Installation and upgrade — 3.6.37

This source snapshot is not a new tagged public release. Read [validation](../validation/RELEASE_3.6.37.md)
and [the reference HA guide](../../homeassistant/README.md) before installation.

The verified reference is Home Assistant OS on aarch64 with PowMr 10.2M PI30MAX
serial, MQTT and individually mapped devices. Optional PV2 is a separate verified
read-only Modbus operation. Do not assume another inverter/firmware is compatible.

1. Back up HA. Use the public repository URL
   `https://github.com/serhiykravchenko-sys/EnergyHub` for the App store after the
   intended version's publication/acceptance is confirmed.
2. Set local MQTT credentials and a persistent serial path in app options.
   Never place tokens, addresses or device credentials in Git. Optional control
   inputs are not supplied merely by installing an app.
3. Review and merge HA helpers/packages/automations rather than replacing your
   whole home. Map every generic entity alias, validate device capabilities and
   required dashboard cards. Keep Autopilot/load/heating control off until
   commissioning; inspect initialization rules before merging the reference.
4. Start and check version banners, MQTT, telemetry freshness, inverter settings
   and reconstruction. Menu 01 has readback; Menu 16 is ACK-confirmed only.
5. Commission family OFF, missing/stale input, restart, native saved states and
   interlocks in attended tests. Do not shed essential loads. A configuration
   check does not prove physical switching. Never inject faults just for wording.
6. Configure optional Family reporting and validate the intended destination.
   Public environment/plug/household lists are empty. Xiaomi cloud observation
   and the bounded Tuya reload aid are disabled; explicitly assess credentials,
   permissions and compatible integration isolation before any opt-in.

App-only upgrades do not require Core stop/start. Reload the App store, Update,
then check build/startup evidence. For YAML, compare/merge, run `ha core check`
and reload/restart as required. Stop Core before any selected `.storage` copy,
preserve rollback, check and start. Reference storage is not a portable registry:
do not copy another home's live entity/device/config-entry registries.

There is no universal plug-and-play installer, AI control, arbitrary tariff-slot
optimizer or hardware recovery guarantee. Monitor naturally occurring events and
scheduled reports before unattended operation or public release acceptance.
