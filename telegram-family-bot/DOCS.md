# Telegram Family Assistant

This app is independent from **Telegram Threat Monitor**. It reads Home
Assistant and EnergyHub data and sends one Ukrainian family summary every
morning. Version 1.3.14 is outbound-only: it cannot execute Home Assistant or
inverter commands. The version joins the coordinated public EnergyHub release
train without changing the validated 0.2.4 behavior.

## Schedule

- `23:00`: capture the current daily EnergyHub grid-import estimate.
- During `23:00–07:00`: observe EnergyHub operating modes.
- `07:00`: capture actual battery SOC, Adaptive Hybrid target, and finish the cross-midnight grid-import calculation.
- `08:00`: fetch the latest weather and Solcast forecast and send the report.

## Household sensor health

Version 1.3.14 checks seven configured temperature/humidity sensor pairs every
five minutes. The default registry contains the first floor, second-floor kids'
room, third floor, main entrance, first-floor bathroom, second-floor toilet,
and basement. The six indoor locations share a peer median; the basement is
kept in a separate group.

An explicit `unknown` or `unavailable` reading is reported in the next 08:00
summary. Suspected stale transport requires 24 hours without `last_reported`
(or `last_updated` on older Home Assistant data). A separate suspected-offline
check uses Home Assistant `last_changed`: if both temperature and humidity
remain exactly unchanged for 24 hours, the sensor is reported even when its
integration continues refreshing cached numeric states. A numeric candidate
requires a
temperature difference of 5 °C or humidity difference of 20 percentage points
from the indoor median or the same local hour on the previous day, and it must
persist for 60 minutes. Bathroom and toilet spikes therefore do not warn merely
because of one short event. Recovery is reported once in the next successful
morning summary; multiple recoveries for one physical sensor are collapsed
into one line that names the recovered condition. Unresolved issues repeat
once per morning.
The report bounds active and recovery lines so accumulated diagnostics cannot
grow past Telegram's message limit; omitted active items are counted.

The registry syntax is:

```text
label|temperature_entity|humidity_entity|indoor_or_basement[|battery_entity|pressure_entity]
```

Records are separated with semicolons. Empty optional fields are allowed.
Verified pressure readings are retained as supporting history and are not used
as anomaly thresholds. Missing, stale, or invalid values are never converted
to zero.

The optional `doorbell_battery_entity` is disabled by default. Once its exact
Home Assistant entity is verified, the 08:00 report warns at or below
`device_low_battery_percent` (10% by default), repeats while low, and
distinguishes unavailable or stale telemetry from a real low value.

Snapshots are persisted in `/data`. A Telegram or internet failure does not mark a report as delivered; the app retries after connectivity returns.

## Inverter diagnostics

The morning report reads the three retained EnergyHub inverter-incident
entities and includes incidents whose start time falls on the previous local
calendar day. Each available line identifies the named QPIWS message and its
pre-event load, load percentage, EnergyHub operating mode, grid state, and
observed duration. Missing values are omitted rather than inferred. A cleared
QPIWS message is reported as cleared; it is not called an automatic inverter
restart unless a future verified signal establishes that fact.
The expected overnight `pv_loss_warning` condition is omitted. Durations use
seconds below one minute, minutes and seconds below one hour, and `HH:MM:SS`
from one hour onward.

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

If the advisor has not produced a suggestion, the report labels the displayed
value **current AHM minimum**, not recommended minimum.

Before the morning network call, the app persists an outbox containing the
exact report date and message. A restart retries that same logical message.
Telegram does not accept an idempotency key for `sendMessage`, so this is
at-least-once delivery: a crash after Telegram accepts the request but before
the acknowledgement is saved can still produce a rare duplicate.

## Heat-pump ownership and reserve warnings

The morning report uses current Grid Confidence, physical grid voltage, and
EnergyHub telemetry freshness to state one of two policies:

- `РУЧНЕ КЕРУВАННЯ`: Grid Confidence is Normal, the grid is present, and
  telemetry is fresh (grid input above 180 V); the family controls the heat pumps while EnergyHub
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
- Previous completed night import:
  `sensor.energyhub_grid_import_night_yesterday_estimated`
- Previous completed normal import:
  `sensor.energyhub_grid_import_normal_yesterday_estimated`
- Previous completed estimated cost:
  `sensor.energyhub_grid_import_cost_yesterday_estimated`
- Current-month night, normal, total, and estimated cost:
  `sensor.energyhub_grid_import_night_month_estimated`,
  `sensor.energyhub_grid_import_normal_month_estimated`,
  `sensor.energyhub_grid_import_month_estimated`, and
  `sensor.energyhub_grid_import_cost_month_estimated`

The useful-generation window spans the first through the end of the last Solcast period at or above `300 W`. It is a forecast window and can contain cloudy gaps.

Night import is an EnergyHub estimate, not revenue-grade metering. It is calculated as:

```text
(previous-day final import - previous-day value at 23:00)
+ current-day import at 07:00
```

The value is omitted until the app has observed one complete 23:00–07:00 night. A restart outside the ten-minute snapshot windows can make that day's value unavailable rather than fabricate a number.

The continuous 23:00–07:00 value above remains an operational overnight
metric. The separate tariff section comes from EnergyHub's finalized previous
calendar day, where night includes both `00:00–07:00` and `23:00–24:00`.
It uses initial prices of 2.50 UAH/kWh and 5.00 UAH/kWh and also reports the
current accumulated month. The entire tariff section is omitted if any
required finalized value or price is unavailable. All values are explicitly
identified as estimates, not billing-grade measurements.

## Test mode

On first start of each app version, test mode sends one immediate partial preview. It intentionally omits the 07:00 SOC and night-import lines unless a scheduled report is being sent. Scheduled reports remain visibly labelled while test mode is enabled. Disable test mode after validation.

When the app is installed after the configured morning time, it does not send a second late daily report. The first full scheduled report is sent the next morning.

## Safety

This report is informational. Weather-provider data and solar/grid estimates can be delayed or wrong. The future voice interface must submit requests to EnergyHub's deterministic safety policy rather than directly bypass inverter or smart-load protections.
