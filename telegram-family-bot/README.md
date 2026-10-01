# Telegram Family Assistant

Version 2.4.15 is the outbound Ukrainian reporting companion to EnergyHub
2.4.12. It informs the household in Telegram without requiring another
monitoring app. Home Assistant remains the configuration and device platform.

## What it reports

- Morning weather, solar-generation forecast, live SOC/mode and reserve context.
- Grid outage/recovery, reserve and load-protection observations.
- SOC anomalies, inverter faults and selected diagnostic warnings.
- Estimated grid import and configured tariff costs where data is available.
- Optional read-only family calendar, environment-sensor and smart-plug status.

Reports explain available evidence and distinguish missing or stale data.
Overnight archived inverter-fault wording uses the current mode at report
delivery. Routine monitoring and an observed outage validated delivery;
rare persistence/retry paths have fixture regression tests, not exhaustive
live fault injection.

## Setup

Install the app after the public release, configure the bot token, destination
and HA access in local app options, and test delivery. Never store real tokens,
chat IDs or private calendar URLs in Git. Optional environment-sensor and
smart-plug lists are empty in the public manifest: populate them with your own
entities. Generic aliases in source/tests are example mappings.

See [configuration and behavior](DOCS.md),
[release notes](../RELEASE_NOTES_FAMILY_2.4.15.md), and
[release evidence](../docs/validation/RELEASE_2.4.12.md).

## Control boundary

This app does not change inverter settings, switch plugs or manage heating.
AI Mission Control, bilingual text requests and later voice interaction are
planned for 4.x, through validated EnergyHub intents. They are not shipped here.
Telegram Threat Monitor is a separate project, not part of EnergyHub promotion.
