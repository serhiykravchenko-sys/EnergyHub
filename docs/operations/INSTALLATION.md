# Installation and upgrade

This guide covers EnergyHub 2.4.12 / Family Assistant 2.4.15. The candidate has
completed routine household monitoring; see [release evidence](../validation/RELEASE_2.4.12.md).
Publication status is stated in the repository README and GitHub releases.

## Supported reference installation

The verified reference uses Home Assistant OS, a PowMr 10.2M inverter with
PI30MAX over USB serial, and MQTT. Optional PV2 telemetry is a separate,
read-only verified Modbus capability, not generic register-write support.
Other hardware and firmware require their own capability verification.

1. Create a Home Assistant backup.
2. Add `https://github.com/serhiykravchenko-sys/EnergyHub` to the App store's
   repositories after the release is published.
3. Install Energy Hub, configure MQTT and the persistent serial device path,
   and verify the installed hardware/protocol options. Never copy credentials
   or serial identifiers from another installation.
4. Start with load control disabled. Check the version banner, MQTT discovery,
   telemetry freshness, startup reconstruction and inverter settings.
5. Adapt the [Home Assistant examples](../../homeassistant/README.md). Merge
   helpers and automations, map device entities and perform attended checks.
6. Optionally install Telegram Family Assistant. Configure your bot token,
   destination and local HA access in app options, never in Git. Configure
   optional sensor/plug lists for your home; the public defaults are empty.

## Safety and commissioning

Do not connect critical loads to shedding roles. Verify manual OFF authority,
device acknowledgement, missing-device behavior, timer pause/restore and
one-at-a-time protective switching before unattended operation. Family
temperature and fan settings remain authoritative in manual Smart Heating.
Cold-weather commissioning is still needed on each installation.

Menu 16 changes are ACK-confirmed without independent readback. Failed or
uncertain inverter transitions need attended verification; no automatic retry
of an undocumented hardware operation is promised. Grid Import is an estimate,
not a revenue-grade meter. Tariff accounting is not multi-slot optimization.

## Upgrade

Back up first and read the release notes. For app-only changes, reload the App
store, select Update, then inspect build/startup logs and affected entities.
Do not stop Home Assistant Core just for an app update.

For YAML changes, compare and merge with your maintained configuration, run
`ha core check`, and reload YAML or restart Core as the changed integration
requires. For `.storage` changes, stop Core before copying selected files,
preserve backups, check the configuration and start Core. Do not overwrite
your whole dashboard/helper registry with reference storage files.

## Repository checks

Run `python -m unittest discover -s tests -q` inside each of `addon/`,
`telegram-family-bot/` and `homeassistant/`, with the relevant Python dependencies
installed. These tests use fixtures; they do not prove live hardware behavior.

See [HA responsibilities](12-HomeAssistant-Configuration.md),
[verified commands](../hardware/powmr-10-2m-verified-commands.md), and
[positioning](../project/POSITIONING.md).
