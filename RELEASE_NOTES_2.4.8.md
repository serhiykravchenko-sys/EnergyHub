# EnergyHub 2.4.8 / Family Assistant 2.4.10

Private corrective candidate prepared on 2026-09-22.

## Changes

- Apply a level-2/3 official UHMC weather modifier of +20 percentage points for
  every known Grid Confidence state. The forecast, grid, weather, and Smart
  Heating modifiers remain additive and capped at 95%.
- Preserve the established forecast policy: +20 points when forecast
  generation is below recent average consumption, and +40 points when it is
  below half of that consumption.
- Show matching external `Modes & Controls` and `EnergyHub Status` headings,
  larger mission-control buttons, and a prominent Grid Confidence card with
  current level and 24/48-hour availability evidence.
- Color the 08:00 solar forecast orange when it exceeds recent average
  consumption and blue otherwise. Color current 15-minute average generation
  blue below 0.3 kW, yellow from 0.3 to below 1.0 kW, and orange from 1.0 kW.
- Preserve the official validity and impact paragraphs in immediate UHMC
  messages. Level 1 does not discuss Battery Reserve; levels 2/3 show the +20
  weather response and the end of the parsed validity period. Overnight warnings
  become one compact line in the morning report.
- Send one deduplicated Telegram message when DTEK confidence changes. It states
  whether reliability improved or worsened and whether the reserve change was
  confirmed, is pending, or requires manual action. A two-minute fallback avoids
  losing the transition if the reserve evidence does not catch up.
- Pair Zigbee2MQTT bridge notices: the offline alert still requires two
  continuous minutes, and recovery is announced only when the completed `off`
  interval also lasted at least two minutes. Brief interruptions and
  `unavailable` to `on` restoration stay silent. Dismissal of an old persistent
  offline alert remains harmless on every recovery.
- Keep Zigbee health notification-only: no app restart or relay action, and no
  bridge-online state is accepted as proof of fresh plug telemetry.
- Keep speculative cloud-device self-recovery out of this correction. Existing
  private morning log diagnostics remain the observation path; generalized
  online telemetry remediation stays in the 3.x backlog.

## Saved-option cleanup

Five retired Family Assistant option values are removed by re-saving the active
Configuration page after update. They are not restored to the manifest and no
self-modifying migration code is added. See the Home Assistant configuration
operations guide for the exact keys and verification.

## Deployment scope

- Energy Hub add-on 2.4.8;
- Telegram Family Assistant 2.4.10;
- `homeassistant/live/storage/lovelace.dashboard_powmr1`;
- `homeassistant/live/config/automations.yaml`;
- one post-update Family Assistant Configuration save for retired persisted
  options.

The dashboard storage copy requires the homeowner to stop Core before the
guarded synchronization, then run `ha core check` and start Core. App updates
alone do not require a Core stop. No commit, push, deployment, restart, or public
promotion is implied by this prepared candidate.
