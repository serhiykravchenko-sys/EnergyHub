# EnergyHub 2.1.0 — Effective Reserve Dry Run

EnergyHub 2.1.0 adds a separate, observer-only Effective Reserve policy. At
05:00 Home Assistant supplies today's Solcast generation forecast and selected
AHM minimum. EnergyHub compares generation with the average of the newest three
valid completed consumption days, then combines that evidence with current
Grid Confidence and normalized official UHMC warnings.

Telegram Family Assistant 2.1.2 owns the read-only `uhmc1921` preview adapter
and publishes normalized retained warning evidence to EnergyHub. Telegram
Threat Monitor remains the separate 0.1.9 air-threat service and is not part of
this reserve path.

Forecast deficit adds 20 percentage points. Normal/Unstable/Risk/Panic add
0/20/40/60 points cumulatively. An active grid-relevant Kyiv/Kyiv-region UHMC
Level II or III warning adds 20 points only while Grid Confidence is Normal;
Level I remains visible but does not change reserve. The total is capped at
95%. Missing consumption, forecast, or warning evidence is reported as unknown
and never invented.

The official-warning state survives restart and source failure, supports
updates, cancellation and expiry, and preserves active warnings if they leave
Telegram's preview page. The normal 08:00 Ukrainian report includes overnight
warnings and the three-day consumption evidence. New daytime warnings are sent
immediately with the Dry Run recommendation. Morning inverter history omits
`line fail warning` because grid events are already reported during the day.

Mission Control groups the existing Peak Load Guard with Effective Reserve.
The Heat Pumps and Appliances & Water views place their three history periods
in one row and show per-load totals for the current week, month, and year.
These new Utility Meter totals start at deployment and do not backfill.

For a time-bounded household Dry Run, the Peak Load Guard recommendation
profile is temporarily lowered to 40% trigger, 30% relief target, and 20%
restoration. This is intended to exercise the persisted decision, dashboard,
and Ukrainian Telegram path under ordinary load without creating an inverter
overload. It remains observer-only and will be reviewed after one week before
the normal 85/75/60 profile or later automatic-control design is selected.

This release changes no AHM helper value, smart plug, relay, or inverter
setting. Automatic reserve authority remains unavailable pending two to three
weeks of Dry Run evidence.
