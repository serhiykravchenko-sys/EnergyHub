# Telegram Family Assistant

Home Assistant app that sends a Ukrainian weather, energy, and heat-pump
ownership summary to a private family Telegram group every morning and warns
when SOC crosses reserve-relative thresholds.

It can recommend increasing the user-selected AHM reserve when the observed 07:00–12:00 SOC minimum approaches that reserve. Recommendations are informational and never change Home Assistant controls.

Version 0.1.9 remains outbound-only. It reports whether the family or
EnergyHub protection currently governs heat-pump use. Reserve warnings require
an active configured heat pump, include its floor and observed power, and are
kept quiet through 08:01. The app never switches a device or sends an inverter
command.

See `DOCS.md` for installation and data semantics.
