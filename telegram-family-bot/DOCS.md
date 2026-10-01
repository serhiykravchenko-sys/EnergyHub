# Telegram Family Assistant

Current local candidate: **2.4.15**. A malformed non-object heat-pump restart
event cannot suppress unrelated reports and alerts; observer failures are
isolated. A `transition_failed` EnergyHub operating mode generates one technical
warning per failure episode, including after a bot restart. This version is not
deployed or observed in Telegram; see
[release notes](../RELEASE_NOTES_FAMILY_2.4.15.md). The homeowner reported
2.4.14 running from 2026-09-27.

## Prior versions

The 2.4.13 messages separate confirmed
grid charging below the selected reserve, grid hold with solar-only battery
charging, and the return to solar priority at reserve +10. The 08:00 recap
retains confirmed reserve-change reasons, reports actual versus forecast
generation only when the battery is confirmed not to have reached 100%, and
summarizes active official weather hazards. Daytime official weather messages
use the warning section of the source post. Core warnings/errors come from
the accessible Core current-session error log, filtered to at most 24 hours;
Supervisor is explicitly unmonitored because its log needs broader privileges.
No current-session log can prove the whole preceding 24 hours were clean.
The earlier 2.4.11 update corrected the 08:00 technical health model and
overload evidence. Availability comes from HA/bridge/device state rather than
unchanged watt age. The report covers the rolling 24 hours ending at delivery,
masks child attribution during parent outages, merges short poll flaps, and
uses separate HA, inverter and Zigbee duration thresholds. Core and Supervisor
warnings/errors are deduplicated in the private technical report. Overload
messages separate trigger load from post-action load and consolidate translated
attention reasons for one minute. Version 2.4.10 added compact forecast/current-PV color markers,
preserves actionable official wording in immediate UHMC alerts, keeps overnight
UHMC recap to one line, and combines each DTEK confidence transition with the
confirmed, pending, or manual Battery Reserve reaction. The private 08:00 digest
of distinct Home Assistant Core warnings/errors remains unchanged. Retired
Hybrid and three-morning reserve-advisor configuration paths remain removed.
`technical_chat_id` optionally separates SOC anomalies,
data-source and device availability incidents, command-attention events, restart
diagnostics, and the morning technical report from family operational messages.
If it is empty, delivery falls back to `destination_chat_id`. Store the real
numeric ID only in local app options. The HA restart summary waits for current-boot state,
up to five minutes, and marks any unresolved protection explicitly. Battery
Reserve messages support Manual and Automatic
authority, and outage protection reports warning 50%, disconnect 40% and
recovery 60%. UHMC is checked hourly with one retry after five minutes;
two failed attempts produce one family warning until a successful check. Morning
diagnostics are sent first as a separate message, then the family weather/energy
report. The restart summary includes both battery-discharge and overload protection.
See [release notes](../RELEASE_NOTES_FAMILY_2.2.7.md).

## Current shared data incidents

Warn after two minutes for the Zigbee bridge, five minutes for inverter/load-
bridge telemetry, and three minutes for other directly observed sources; send
recovery only after five healthy minutes and only for a delivered warning.
Quietly log shorter interruptions and group simultaneous sources. The morning
report uses a rolling 24-hour window, merges gaps below two minutes and reports
only sources crossing their duration threshold. Parent outages pause child
attribution; specifically, a Zigbee bridge outage suppresses separate outage
attribution for its two heat-pump plugs. Persist timers and distinct
battery-jump days across restart.
Summarize meaningful interruptions and recurring battery jumps in the morning.
Readiness-only overload messages are replaced by this policy, not layered on top.
Actual device-action/attention notifications remain. See [scope and limitations](../RELEASE_NOTES_FAMILY_2.2.5.md).

## HA restart summary — prepared 2.2.4

Read the existing HA-start bridge session; wait 60 seconds, then queue one summary
of strategy/Autopilot, selected minimum/authority and overload readiness. Persist
boot identity; consolidate startup control notifications and refresh queued content
before sending. Bot-only restart on an old boot is silent. Missing native/controller
data is not labelled ready. No Smart Heating status is invented while it is offline.

## 2.2.4 morning UHMC status — prepared, not deployed

Only an active official warning is shown in the family morning message. Level I
still counts as a warning; tomorrow-only, expired and cancelled warnings do not.
Missing, malformed or stale source evidence is handled by private diagnostics
rather than a routine family line. Night warning details
and daytime delivery are unchanged. Source snapshots are retained in bot state.

## 2.2.3 recovery correction — prepared

Overload messages explain five continuous minutes below 50% before restoration
and at least one minute between devices. A dedicated short notice after five
minutes without usable restoration evidence lists EH-owned OFF devices and asks
the family to check loads before manual action. Notifications cannot guarantee
delivery if EH/HA/MQTT or Telegram is unavailable. No blind automatic restoration.

## 2.2.1 overload correction — prepared, not deployed

Warnings-only 85/75/60 overload episodes are short Ukrainian messages, distinct
from confirmed automatic actions. Historical trial events and queued trial
recommendations are consumed/dropped, never replayed to the family. Battery
Reserve and weather messages remain unchanged. See [release notes](../RELEASE_NOTES_2.2.1.md).

## 2.2.0 candidate messaging

Short confirmed overload actions, valid changed reserve advice only, compact
morning and battery-jump wording. No new reserve-control authority. See
[release notes](../RELEASE_NOTES_2.2.0.md). Not deployed by preparation.

## 2.1.8 warning replacement

A newer same-source/region warning supersedes an older one only if its hazard
set includes the old hazards, severity is not lower, and validity covers the
remaining older interval. Added hazards or increased severity are updates;
unchanged reposts retain the existing deduplication behavior. The active count
excludes superseded records; the last 100 are persisted separately for history.
Replaced overnight items are removed from the pending morning digest. Already
sent messages and rendered delivery retries are not rewritten. Unrelated,
shorter-period or weaker warnings do not erase existing protection evidence.
EnergyHub reserve policy is unchanged; it receives the consolidated active list.

## 2.1.7 compact UHMC warnings

Daytime warnings use severity/hazards, actual manual reserve plus a concise
advisory result, and source link. Incomplete evidence explicitly means insufficient
data. Higher family selections are preserved. Warning detection, quiet-hour
queues and morning-report behavior are unchanged; already queued message text
is not rewritten. The bot performs no battery-control writes.

## 2.1.6 strategy wording

The morning report separates its saved overnight strategy from a timestamped
current strategy read from HA. Charging names follow the installed 23:00–07:00
tariff window; Grid Hold waits for solar, Reserve Hold preserves outage reserve.
Stale telemetry or missing grid evidence suppresses supply claims. This does not
change schedules or add automatic reserve control. See the coordinated
[display contract](../RELEASE_NOTES_2.1.3.md).

## 2.1.5 manual reserve advice

New EnergyHub `advice_only` evidence produces Ukrainian condition explanations,
not new manual targets or restoration instructions. Manual value changes do not
repeat advice. Quiet hours remain unchanged. Old-server payloads retain legacy
formatting for upgrade compatibility.

## Compact messages (2.1.3)

Daytime UHMC notifications omit the forecast excerpt and retain severity,
location/hazard, reserve guidance, dry-run status and source. Morning weather
remains unchanged. Monthly grid import is labeled `З мережі за місяць`, uses
`≈` for estimated cost, and is omitted at zero kWh. Morning SOC anomalies show
the largest transition and local HH:MM in one informational line, without a
recovery promise. Manual heat-pump ownership and AHM recommendations use shorter
wording; no reserve decision or hardware-control behavior changes. Existing
three-morning advisor logic and its concluding line await a separate audit.

This app is independent from **Telegram Threat Monitor**. It reads Home
Assistant and EnergyHub data and sends one Ukrainian family summary every
morning. Version 2.1.2 can publish only normalized UHMC warning evidence through
Home Assistant MQTT; it cannot change AHM, switch loads, or issue inverter
commands.

## SOC anomaly observation

The app reads `soc_anomaly_latest_entity`, which defaults to
`sensor.energyhub_soc_anomaly_latest`. The first valid retained event after the
2.1.1 upgrade establishes a silent baseline, so an old journal entry is not
replayed. Each later event receives an immediate Ukrainian message containing
the SOC transition, elapsed time, and available battery, PV, load, operating
mode, freshness, restart, and communication-recovery context.

The last event ID, queued message, and events awaiting the morning summary are
persisted. The next successfully delivered morning report shows the number of
new anomalies and the largest transition; events arriving while that report is
being delivered remain for the following report. EnergyHub currently records
SOC anomalies for diagnosis only. Neither EnergyHub nor this bot filters the
reported SOC value in 2.1.1, and the bot performs no control action.

## Battery Reserve weather and forecast evidence

The Family Assistant reads the public official `uhmc1921` Telegram preview,
normalizes active Kyiv/Kyiv-region infrastructure warnings, and publishes the
retained document to `energyhub/input/weather/uhmc`. It handles duplicates,
edited posts, cancellations, expiry, restart, and preview pagination. If the
source cannot be read, it publishes Unknown rather than Clear and preserves its
last known active set locally. Explicit validity is used when present;
otherwise the warning receives a conservative 12-hour TTL. Road ice is
included; fog, heat, ordinary cold, and other regions are excluded.

The scheduled 08:00 report reads the current Battery Reserve policy through
`weather_buffer_entity` only when `date`
matches the local report date. It shows yesterday's consumption, EnergyHub's
average of up to three newest valid completed days, today's generation
forecast, forecast/Grid/weather modifiers, and recommended reserve. One or two
valid days are used with the sample count shown; no valid days remain Unknown.

New official UHMC warnings observed from 08:01 until 22:59 produce an immediate
Ukrainian message that preserves up to two actionable official paragraphs.
Warnings observed from 23:00 through 08:00 are queued as one compact line in
the morning report. Level I is forwarded without Battery Reserve advice.
Relevant Level II–III warnings explain the independent +20-point weather
modifier, the current applied/recommended response, and the parsed validity end.
The weather and Grid Confidence modifiers are additive for every known grid
state and the resulting recommendation remains capped at 95%.
If expiry or cancellation lowers the recommendation, daytime restoration is
sent immediately; an overnight restoration is preserved for the morning report.

Family messages report the recommendation and whether Manual or Automatic
Battery Reserve owns the applied value. The app does not evaluate the policy
or publish the 23:52/05:00 forecast inputs; EnergyHub owns the persisted
decision. `line fail warning` is omitted from the morning inverter history
because immediate grid-loss/recovery reporting already covers it.

## Overload and battery load protection

The app reads the configured `peak_load_guard_event_entity` every polling
cycle. It sends a Ukrainian notification only when the retained EnergyHub
`event_id` changes. Family messages name only appliances whose OFF or restore
action EnergyHub confirmed. Technical messages report unavailable, rejected,
or unconfirmed participants without stopping the remaining protection cycle.
The event ID and pending notification queue survive app restart. The Family
Assistant never operates a smart plug itself; Home Assistant executes only
structured, guarded EnergyHub intents.

## Schedule

- `23:00`: capture the current daily EnergyHub grid-import estimate.
- During `23:00–07:00`: observe EnergyHub operating mode and grid supply.
- `07:00`: capture actual battery SOC and finish the cross-midnight grid-import calculation.
- `08:00`: fetch the Family Calendar, latest weather, and Solcast forecast and
  send the report.

## Read-only Family Calendar

The optional `family_calendar_ical_url` setting accepts Google Calendar's
**Secret address in iCal format**. Leave it empty to omit the calendar section.
In Google Calendar on the web, open **Settings for my calendars → Family →
Integrate calendar**, then copy the secret iCal address into the add-on option.
Do not paste the address into chat, Git, logs, or documentation: anyone who has
it can read the calendar. If it is ever exposed, reset the secret address in
Google Calendar and update the add-on option.

Home Assistant renders this option as a masked password and stores its real
value only in the local add-on configuration. No private URL, calendar ID,
OAuth client, or refresh token belongs in this repository.

The app performs one HTTPS GET and parses only the returned iCalendar feed for
the period from local midnight today through local midnight tomorrow.
RFC 5545 recurrence rules, exclusions, and edited occurrences are expanded by
pinned parser libraries before events are normalized and sorted. The feed is
read-only; the app has no code path or credential for creating, updating, or
deleting an event. Calendar responses are limited to 5 MiB, and failures are
logged without the secret URL.

The 08:00 digest shows every event occurring today and reproduces its title
exactly after Telegram HTML escaping. Timed events receive a local `HH:MM`
prefix. All-day events show only their title, without `Увесь день`. The app
does not inspect tomorrow and does not infer birthdays, anniversaries, or any
other event category. If calendar retrieval or parsing fails, the failure is
logged without the secret URL and the remaining morning digest is still sent.

## Household sensor health

Version 2.0.0 checks seven configured temperature/humidity sensor pairs every
five minutes. The default registry contains the first floor, second-floor kids'
room, third floor, main entrance, first-floor bathroom, second-floor toilet,
and basement. The retained indoor/basement registry field is configuration
metadata only; rooms are not compared with one another.

An explicit `unknown` or `unavailable` reading is reported in the next 08:00
summary. Suspected stale transport requires 24 hours without `last_reported`
(or `last_updated` on older Home Assistant data). A separate suspected-offline
check uses Home Assistant `last_changed`: if both temperature and humidity
remain exactly unchanged for 24 hours, the sensor is reported even when its
integration continues refreshing cached numeric states. A numeric candidate
requires a temperature change of 5 °C or humidity change of 20 percentage
points relative to the same sensor at approximately the same local hour on the
previous day, and it must persist for 60 minutes. The morning line states the
old value, new value, direction, and difference. It is sent once and does not
describe either value as normal or abnormal. Numeric changes do not create a
recovery message. Availability, stale/unchanged transport, and low-battery
issues remain separate; connectivity recovery is reported once after fresh
data resumes. Unresolved connectivity issues repeat once per morning.
The report bounds active and recovery lines so accumulated diagnostics cannot
grow past Telegram's message limit; omitted active items are counted.

## Smart-plug availability

`smart_plug_entities` is a semicolon-separated registry of
`label|switch_entity` records. Version 2.0.0 contains the verified switch
entities for all three heat pumps, the basement water pump, water boiler, and
microwave.

At 08:00, the app reports a configured plug only when its switch entity is
missing, `unknown`, or `unavailable`. An available `on` or `off` state is
healthy; zero watts is not treated as offline, and an unchanged switch state
does not become stale merely because it remains unchanged. If the Home
Assistant API request itself fails, the entire plug section is omitted rather
than incorrectly calling every plug offline. The check is read-only and never
issues a plug command.

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

The app watches `sensor.powmr_10_2m_grid_voltage`. A value above 180 V means the external grid is present. A change must remain stable for 60 seconds before notification, filtering brief inverter telemetry noise.

On grid loss it sends the confirmed start time and current SOC. On recovery it sends the recovery time, outage duration, and current SOC. The outage start and unsent notifications are persisted across app restarts and temporary Wi-Fi/Telegram failures. If the app itself starts while the grid is already absent, it cannot know the earlier exact outage time and begins duration tracking when it first observes the outage.

The app also watches `sensor.energyhub_grid_confidence`. A valid transition
produces one deduplicated family message naming the old and new DTEK confidence
levels. The app briefly waits for `sensor.energyhub_ahm_weather_buffer` to show
the matching evaluation, then reports a confirmed Automatic reserve change, a
pending Automatic application, or a Manual recommendation. After two minutes,
missing or lagging evidence is stated as unconfirmed instead of suppressing the
transition. Grid Confidence contributes 0/20/40/60 percentage points to the
single additive Battery Reserve calculation; it is not a separate day/night
target.

Before the morning network call, the app persists an outbox containing the
exact report date and message. A restart retries that same logical message.
Telegram does not accept an idempotency key for `sendMessage`, so this is
at-least-once delivery: a crash after Telegram accepts the request but before
the acknowledgement is saved can still produce a rare duplicate.
An archived overnight inverter fault states when its mode was observed during
report creation. If delivery is delayed, the saved report still refers to that
time rather than claiming the inverter has the same mode at delivery.

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

Reserve warnings are relevant only during a confirmed external-grid outage and
while a heat pump is operating. The same persisted 60-second grid confirmation
used by the outage message must finish first; a single low-voltage sample cannot
create a reserve warning. The app
reads the configured first-, second-, and third-floor power entities and queues
a warning only when at least one reports more than `heat_pump_active_threshold_w`
(50 W by default). The warning names every active floor and its observed power.
The family chat is silent from 23:00 until its scheduled 08:00 report. Family
events observed during that interval are persisted and condensed into a short
`Події за ніч` section in the report. The report itself is the only 08:00
exception; newly queued family events wait through 08:01 and resume normal
delivery at 08:02. Private technical-chat diagnostics remain immediate.

Before a queued reserve warning is archived or delivered, the app rechecks SOC,
telemetry freshness, grid voltage, and current heat-pump power. It refreshes the
floor/watt lines, waits while every pump is idle, and drops the warning if SOC
has recovered above its threshold or grid voltage has returned above 180 V.
The Grid Hold transition message is emitted once per persisted reserve episode;
short internal mode movements around the reserve floor do not replay it. A
confirmed Solar return closes the episode.

These messages report policy and observed SOC. The app itself performs no
control action.

Home Assistant separately remembers explicit user ON/OFF choices for the two
Zigbee heat-pump plugs. After a restart it waits for a stable bridge session,
fresh telemetry, grid voltage above 180 V, available plug states and no active
EnergyHub ownership. It may then restore only a remembered-ON plug that returned
OFF. One minute later it writes a compact result to the configured
`heat_pump_restart_event_entity`; the Family Assistant reports confirmed watts.
The bot remains read-only and never operates the plug itself.

Notifications say whether reliability improved or deteriorated and describe this value as the `Цільовий запас батареї вдень`. The wording avoids presenting the target as a hard battery shutdown floor. An active missed AHM target can make the effective daytime target higher than the Grid Confidence target alone.


## Telegram setup

For Telegram delivery the app only calls `sendMessage`, so it may temporarily
reuse an existing bot token and private family group. Its separate Home
Assistant API use is restricted to publishing normalized UHMC evidence to
MQTT. Enter the destination's negative chat ID only in the Home Assistant app
configuration; do not commit it with the repository.

A separate Telegram bot identity can be introduced before inbound commands/voice proxy work. Only one process should consume `getUpdates` for a bot token.

## Weather

Set `weather_entity` to the desired `weather.*` entity, or keep the default `auto`. Auto-selection prefers `weather.forecast_home` and otherwise selects the first available weather entity.

`uhmc_weather_source` defaults to the official public channel `uhmc1921`.
`uhmc_weather_mqtt_topic` defaults to `energyhub/input/weather/uhmc`; it must
match the EnergyHub subscription and normally should not be changed.

In `auto` mode the app tests all weather entities for an hourly forecast. If none supports hourly data, it uses the first usable daily forecast; precipitation timing is then reported as `протягом дня` instead of inventing an hour.

The app requests the provider's hourly forecast and only prints fields actually supplied:

- dominant daytime condition and min/max temperature;
- precipitation time window, total millimetres, and maximum probability;
- rain, snow, mixed rain/snow, or hail;
- inferred warnings for thunderstorm, heavy rain, hail, fog, or wind/gusts above the configured threshold;
- forecast humidity only when it is at or below 30%, at or above 80%, or spans
  at least 25 percentage points during the day.

These are forecast-derived warnings, not official government weather alerts. Snow precipitation in millimetres is labelled as water equivalent, not snow depth.

Minimum and maximum temperatures are rounded to whole degrees and written explicitly as `від +15 до +30 °C`.

## Energy data

Default entity IDs match this EnergyHub installation. Every ID remains configurable.

- Actual SOC: `sensor.powmr_10_2m_battery_soc`
- Applied reserve: `input_number.ahm_minimum_soc`
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

The value is omitted until the app has observed one complete 23:00–07:00 night,
and a measured zero is also omitted from the family message. A restart outside
the ten-minute snapshot windows can make that day's value unavailable rather
than fabricate a number.

The continuous 23:00–07:00 value above remains an operational overnight
metric. The separate tariff section comes from EnergyHub's finalized previous
calendar day, where night includes both `00:00–07:00` and `23:00–24:00`.
It uses initial prices of 2.50 UAH/kWh and 5.00 UAH/kWh. Zero-value tariff rows
are omitted, and the whole previous-day block is omitted when yesterday's
import was zero. The current month is split into night and normal energy/cost
rows followed by the combined total. If component data is unavailable, the
month total can still be shown independently. The previous-day portion is
omitted when its finalized values or prices are unavailable. All values are
explicitly identified as estimates, not billing-grade measurements.

## Conditional attention lines

The report adds a factual grid-availability line whenever rolling 24-hour grid
availability is below 24 hours. Unstable Grid Confidence is highlighted in
yellow; Risk and Panic are red. Today's forecast is orange when it exceeds the
recent one-to-three-day consumption average and blue otherwise. Current
15-minute average generation is blue below 0.3 kW, yellow from 0.3 to below
1.0 kW, and orange from 1.0 kW. Retained inverter messages are headed in red
after the expected overnight PV-loss condition has been filtered out.

Version 2.0.0 has no test mode, per-version preview, or test label.

When the app is installed after the configured morning time, it does not send a second late daily report. The first full scheduled report is sent the next morning.

## Safety

This report is informational. Weather-provider data and solar/grid estimates can be delayed or wrong. The future voice interface must submit requests to EnergyHub's deterministic safety policy rather than directly bypass inverter or smart-load protections.
## 2.1.4 Dry Run hardening

This candidate preserves 2.1.3 presentation, consumes the EH event journal,
and reports one Battery Reserve recommendation. Overnight reserve changes are
left for 08:00; daytime changes explicitly say no setting was changed.
Ambiguous UHMC region/severity and missing timestamps are unknown evidence.
No hardware command, automatic reserve control or Threat Monitor change is
included. See [release notes](../RELEASE_NOTES_2.1.1.md).
# Dashboard controls — 2.2.2

The read-only observer uses the existing EnergyHub Autopilot and overload helpers.
It announces stable changes after ten seconds and checks overload readiness before
claiming enabled control. Initial observations are silent; state is persisted and
queued messages are revalidated. OFF does not claim that owned loads were restored.
Notifications are operational information, not a safety interlock or an audit of
every rapid click. Missing helpers are ignored. No new settings are required.
# Prepared 2.2.6 battery-protection messages

With EH schema 4, confirmed shared-controller events replace legacy reserve-offset
relay predictions. Battery shutdown messages state the observed battery charge
and affected devices; they are not labelled inverter overload. Existing startup
session messages indicate an observed bridge-session change, not a restart cause.
This candidate does not change HA or restart detection. Not deployed.
