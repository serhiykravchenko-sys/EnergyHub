# Telegram Family Assistant

This app is independent from **Telegram Threat Monitor**. It reads Home Assistant and EnergyHub data and sends one Ukrainian family summary every morning. Version 0.1.9 is outbound-only: it cannot execute Home Assistant commands.

## Schedule

- `23:00`: capture the current daily EnergyHub grid-import estimate.
- During `23:00–07:00`: observe EnergyHub operating modes.
- `07:00`: capture actual battery SOC, Adaptive Hybrid target, and finish the cross-midnight grid-import calculation.
- `08:00`: fetch the latest weather and Solcast forecast and send the report.

Snapshots are persisted in `/data`. A Telegram or internet failure does not mark a report as delivered; the app retries after connectivity returns.

## Grid event notifications

The app watches `sensor.powmr_10_2m_grid_voltage`. A value above 180 V means the external grid is present. A change must remain stable for 30 seconds before notification, filtering brief inverter telemetry noise.

On grid loss it sends the confirmed start time and current SOC. On recovery it sends the recovery time, outage duration, and current SOC. The outage start and unsent notifications are persisted across app restarts and temporary Wi-Fi/Telegram failures. If the app itself starts while the grid is already absent, it cannot know the earlier exact outage time and begins duration tracking when it first observes the outage.

The app also watches `sensor.energyhub_grid_confidence`. Valid transitions explain the corresponding **daytime Panic reserve target**:

| Grid Confidence | Daytime Panic reserve target |
|---|---:|
| Normal | 20% |
| Unstable | 60% |
| Risk | 80% |
| Panic | 95% |

This is not the user-selected 20–50% AHM minimum SOC. Grid Confidence does not automatically change the separate night AHM minimum.

The morning report displays EnergyHub's centralized AHM reserve advice. EnergyHub observes completed 07:00–12:00 mornings at the current slider value. It suggests one safer named step when at least two of the latest three mornings came within five SOC points of the reserve, and one more economical step only when all three stayed at least 20 points above it. Changing the slider starts a new comparable three-morning window. This is advice only; neither app changes the slider automatically.

## Heat-pump ownership and reserve warnings

The morning report uses current Grid Confidence, physical grid voltage, and
EnergyHub telemetry freshness to state one of two policies:

- `РУЧНЕ КЕРУВАННЯ`: Grid Confidence is Normal, the grid is present, and
  telemetry is fresh; the family controls the heat pumps while EnergyHub
  monitors reserve;
- `ЗАХИСТ ENERGYHUB`: one or more trust gates are missing, so Home Assistant's
  reserve-relative heat-pump protection applies.

The app observes the selected AHM minimum `S` and sends one warning on each
downward crossing of `S+30`, `S+20`, `S+10`, and `S`. For `S=20%`, those are
50%, 40%, 30%, and 20%. Each warning names the active ownership policy. A
warning rearms only after SOC recovers two percentage points above its
threshold. State is persisted, so an app restart does not replay every already
crossed warning.

Reserve warnings are relevant only while a heat pump is operating. The app
reads the configured first-, second-, and third-floor power entities and queues
a warning only when at least one reports more than `heat_pump_active_threshold_w`
(50 W by default). The warning names every active floor and its observed power.
Reserve warnings are not delivered from 00:00 through 08:01 local time. Before
retrying an already queued warning after the quiet period, the app rechecks SOC,
telemetry freshness, and current heat-pump power. It refreshes the floor/watt
lines, waits while every pump is idle, and drops the warning if SOC has recovered
above its threshold. Grid-loss, grid-recovery, and Grid Confidence notifications
are not subject to this reserve-warning quiet period.

These messages report policy and observed SOC. The app itself performs no
control action.

Notifications say whether reliability improved or deteriorated and describe this value as the `Цільовий запас батареї вдень`. The wording avoids presenting the target as a hard battery shutdown floor. An active missed AHM target can make the effective daytime target higher than the Grid Confidence target alone.


## Telegram setup

The app only calls Telegram `sendMessage`, so it may temporarily reuse an existing bot token and private family group. Enter the destination's negative chat ID only in the Home Assistant app configuration; do not commit it with the repository.

A separate Telegram bot identity can be introduced before inbound commands/voice proxy work. Only one process should consume `getUpdates` for a bot token.

## Weather

Set `weather_entity` to the desired `weather.*` entity, or keep the default `auto`. Auto-selection prefers `weather.forecast_home` and otherwise selects the first available weather entity.

In `auto` mode the app tests all weather entities for an hourly forecast. If none supports hourly data, it uses the first usable daily forecast; precipitation timing is then reported as `протягом дня` instead of inventing an hour.

The app requests the provider's hourly forecast and only prints fields actually supplied:

- dominant daytime condition and min/max temperature;
- precipitation time window, total millimetres, and maximum probability;
- rain, snow, mixed rain/snow, or hail;
- inferred warnings for thunderstorm, heavy rain, hail, fog, or wind/gusts above the configured threshold.

These are forecast-derived warnings, not official government weather alerts. Snow precipitation in millimetres is labelled as water equivalent, not snow depth.

Minimum and maximum temperatures are rounded to whole degrees and written explicitly as `від +15 до +30 °C`.

## Energy data

Default entity IDs match this EnergyHub installation. Every ID remains configurable.

- Actual SOC: `sensor.powmr_10_2m_battery_soc`
- Adaptive target: `sensor.energyhub_hybrid_target_soc`
- Mode: `sensor.energyhub_operating_mode`
- Completed previous-day consumption: `sensor.energyhub_daily_house_consumption`
- Today's forecast and `detailedHourly`: `sensor.solcast_pv_forecast_forecast_today`
- Current daily import: `sensor.energyhub_daily_grid_import_estimated`
- Previous completed import: `sensor.energyhub_grid_import_yesterday_estimated`

The useful-generation window spans the first through the end of the last Solcast period at or above `300 W`. It is a forecast window and can contain cloudy gaps.

Night import is an EnergyHub estimate, not revenue-grade metering. It is calculated as:

```text
(previous-day final import - previous-day value at 23:00)
+ current-day import at 07:00
```

The value is omitted until the app has observed one complete 23:00–07:00 night. A restart outside the ten-minute snapshot windows can make that day's value unavailable rather than fabricate a number.

## Test mode

On first start of each app version, test mode sends one immediate partial preview. It intentionally omits the 07:00 SOC and night-import lines unless a scheduled report is being sent. Scheduled reports remain visibly labelled while test mode is enabled. Disable test mode after validation.

When the app is installed after the configured morning time, it does not send a second late daily report. The first full scheduled report is sent the next morning.

## Safety

This report is informational. Weather-provider data and solar/grid estimates can be delayed or wrong. The future voice interface must submit requests to EnergyHub's deterministic safety policy rather than directly bypass inverter or smart-load protections.
