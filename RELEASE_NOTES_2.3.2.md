# EnergyHub 2.3.2

Prepared 2026-09-12 as a private candidate.

## Two-stage forecast plan

- At 23:52, after the completed 23:51 Daily Summary snapshot, calculate a
  preliminary Battery Reserve forecast allowance for tomorrow and apply it in
  Automatic mode while the low-tariff window is available.
- At 05:00, replace that forecast component using the updated forecast for
  today. The forecast allowance is +0 or +20 percentage points and never
  accumulates across evaluations.
- If the 05:00 forecast is unavailable, retain the safe preliminary forecast
  allowance. After a valid morning capture, ordinary intraday forecast changes
  do not replace it.
- Grid Confidence and qualifying UHMC warning allowances continue to update
  throughout the day.

## Dashboard

- Hide the manual +/-5% controls while Battery Reserve Automatic is enabled.
- Remove the duplicate Recommendations entity card.
- In Automatic mode show one current reserve; in Manual mode show the selected
  reserve and EH recommendation separately.
- Name every allowance condition and show whether the forecast plan is
  preliminary or the 05:00 morning revision.

## Deployment scope

EnergyHub add-on, `automations.yaml`, and the dashboard `.storage` file. Family
Assistant is unchanged at 2.3.1. Core stop/check/start is required for the
reviewed Home Assistant files.
