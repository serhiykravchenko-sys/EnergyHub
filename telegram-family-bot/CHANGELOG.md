# Changelog

## 1.3.14

- Join the coordinated EnergyHub public release train. This version contains
  the previously validated 0.2.4 outbound reporting behavior with no new
  command, device-control, or inverter-control capability.
- Keep completed-yesterday and current-month estimated tariff summaries,
  inverter diagnostics, household sensor health, and reserve notifications.
- Align trusted-grid ownership with EnergyHub's physical-grid threshold:
  Normal Grid Confidence, fresh telemetry, and voltage above 180 V.
- Persist the exact logical morning report before delivery and retry it after
  restart. Delivery remains at-least-once because Telegram offers no
  idempotency key for the crash-after-acceptance window.
- Add English and Ukrainian metadata for every tariff option and describe an
  unsuggested AHM value as the current minimum rather than a recommendation.
- Remove an unused Home Assistant weather-discovery method.

## 0.2.4

- Add completed previous-calendar-day estimated night/normal Grid Import and
  UAH cost to the morning report.
- Add current-month night, normal, total import, and estimated cost.
- Omit the tariff section when any required finalized sensor is unavailable
  and label all results as informational rather than billing-grade.

## 0.2.3

- Omit the expected overnight `pv_loss_warning` condition from inverter
  morning-report messages while retaining any other message in a mixed event.
- Format incident durations as seconds below one minute, minutes and seconds
  below one hour, and `HH:MM:SS` from one hour onward.

## 0.2.2

- Add previous-day inverter messages from EnergyHub 1.3.10 to the morning
  report, including available load, operating-mode, grid, duration, and clear
  evidence.
- Avoid claiming an automatic inverter restart when only QPIWS clearance is
  observed.

## 0.2.1

- Report a sensor as suspected offline when both its temperature and humidity
  values remain unchanged for the configured 24-hour freshness window, even
  when Home Assistant continues reporting cached numeric states.
- Collapse accumulated recovery events into one line per physical sensor and
  name whether availability, unchanged values, temperature, humidity, or
  battery recovered.

## 0.2.0

- Added five-minute availability and freshness checks for seven configured
  temperature/humidity sensors.
- Added persistent one-hour temperature and humidity outlier candidates using
  the six-sensor indoor median and same-hour previous-day observations; the
  basement remains outside the indoor peer group.
- Added low-battery reporting for verified sensor battery entities and an
  optional Xiaomi doorbell battery entity at or below 10%.
- Added active issues and one-time recovery lines to the 08:00 report without
  granting the Telegram app any control capability.
- Use an explicit blank default for the optional doorbell entity so existing
  installations can upgrade without a missing-option validation error.

## 0.1.9

- Send SOC reserve warnings only while at least one configured heat pump is
  drawing more than the configured 50 W activity threshold.
- Include the floor and current power of every active heat pump in the warning.
- Suppress reserve warnings from 00:00 through 08:01 and defer any already
  queued reserve warning until the daytime delivery window.

## 0.1.8

- State clearly in the morning report whether heat pumps are under family
  manual control or EnergyHub reserve protection.
- Derive heat-pump thresholds from the selected AHM minimum.
- Send persisted downward-crossing SOC warnings at minimum +30, +20, +10,
  and +0 percentage points.
- Rearm each warning only after SOC recovers two percentage points above its
  threshold, avoiding repeated messages near a boundary.

## 0.1.7

- Add today's sunrise and sunset from Home Assistant Sun.
- Show the Moon line only for new moon or full moon.
- Add the expected Solcast peak power and time.
- Show the AHM advisor's suggested minimum and its existing three-morning learning progress.
- Keep wind information conditional on the configured strong-wind warning threshold.

## 0.1.6

- Observe the actual minimum battery SOC from 07:00 through 12:00.
- Show EnergyHub's centralized three-morning AHM reserve advice, including learning progress and one-step increase/decrease suggestions, without changing the slider automatically.
- Distinguish the current partial morning from the previous completed morning in recommendation wording.

## 0.1.5

- Clarify whether grid reliability improved or deteriorated.
- Rename the notification value to the clearer `Цільовий запас батареї вдень` and explain whether EnergyHub retains more reserve or may use more battery.

## 0.1.4

- Notify the family group when external grid power disappears and recovers.
- Include outage start/recovery time, persisted duration, and current SOC when available.
- Notify on valid Grid Confidence transitions and explain the corresponding 20/60/80/95% daytime Panic reserve target.
- Debounce grid voltage for 30 seconds and persist a Telegram retry queue across network failures and restarts.

## 0.1.3

- Format daily minimum and maximum temperatures as clear whole-number bounds: `від +15 до +30 °C`.

## 0.1.2

- Try every available weather entity until one supplies an hourly forecast.
- Fall back to a daily forecast when no provider supports hourly data.
- Include Home Assistant's validation response in weather API error logs.

## 0.1.1

- Replaced the nullable weather-entity default with the explicit `auto` value so Home Assistant configuration validation succeeds.

## 0.1.0

- Initial independent family-assistant app.
- Captures actual battery SOC and EnergyHub target at 07:00.
- Sends a Ukrainian morning report at 08:00.
- Includes weather condition, temperature, precipitation, forecast-derived bad-weather warnings, Solcast forecast, useful-solar window, yesterday's consumption, night mode, and estimated 23:00–07:00 grid import.
- Persists snapshots and retries Telegram delivery after temporary network failures.
