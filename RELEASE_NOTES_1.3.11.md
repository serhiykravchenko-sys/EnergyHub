# EnergyHub 1.3.11 — Tariff-Aware Grid Import Accounting

EnergyHub now divides each new estimated Grid Import increment into the local
calendar day's night and normal tariff periods without changing inverter or
household-load behavior.

## Accounting

- Night: `00:00–07:00` and `23:00–24:00`.
- Normal: `07:00–23:00`.
- Initial prices: 2.50 UAH/kWh at night and 5.00 UAH/kWh at the normal tariff.
- Persisted outputs: current day, completed yesterday, bounded daily history,
  monotonic chart totals, and current-month energy and estimated cost.
- Boundary intervals are divided at 07:00, 23:00, and midnight in the local
  `Europe/Kyiv` timezone.

Existing total Grid Import and Daily Summary reconciliation remain intact.
Schema migration preserves the already accumulated current-day total and
starts the new split at upgrade time; EnergyHub does not guess a tariff for
earlier energy. The first partial deployment day is therefore not published as
a complete previous-day tariff result.

## Home Assistant and Telegram

The existing total Grid Import series remains on Daily Energy Balance. The
renamed Energy Statistics view adds night and normal import to its existing
7-day, 7-week, and 12-month charts and shows a compact current-month summary.

Telegram Family Assistant 0.2.4 adds a finalized previous-calendar-day tariff
summary and current-month totals to the morning message. Its existing
23:00–07:00 operational overnight value remains separate.

## Accuracy and safety

These values are informational estimates, not billing-grade measurements.
The inverter has no verified direct accumulated Grid Import counter, and
simultaneous daytime PV can affect the estimate. Tariff accounting is
observation-only and never influences inverter strategy or load control.

Heat-pump reserve protection also closes a startup/recovery race observed when
battery SOC returned from `unavailable` at a reserve boundary. Both the
one-time shed and critical lockout now require fresh telemetry and revalidate
that the grid is not trusted immediately before any plug command. A Normal,
present grid therefore leaves heat-pump control with the family at every SOC.
