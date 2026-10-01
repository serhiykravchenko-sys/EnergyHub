# EnergyHub 2.2.5 / Family Assistant 2.2.6 — private candidate

Prepared 2026-09-09. Not deployed, committed, pushed or published.

- One shared command/ownership journal for overload and battery-load protection.
- Actual grid outage (even with Normal reliability): soft stop at 50%, manual ON
  permitted until 40%, then latched lockout until recovery. Pump, boiler and three
  HPs participate; microwave is excluded from battery protection, not overload.
- First-floor HP always uses native OFF in this protection path, including Eco
  and Turbo; the plug stays powered. Old independent reserve relay writers removed.
- No battery shedding with actual grid present. Restoration needs 60% charge or
  at least 60 seconds of observed grid availability plus a confirmed grid-support
  strategy. Also require five continuous minutes below 50% inverter load and with
  battery recovery permission, sequential restoration at least one minute apart,
  device minimum-off times, fresh data and unchanged family/schedule ownership.
- A critical battery lock remains latched through a partial rebound (e.g. 55%).
- Charging recommendations do not shift these thresholds. The current manual
  slider is an explicit family floor: above the default boundaries it is protected
  with soft=max(50,floor), critical=max(40,floor), recovery=min(100,max(60,floor+10)).
  A future automatic charging target must NOT be wired into this hard-floor input.
- Invalid battery evidence blocks protected-load restoration, not otherwise valid
  overload shutdown. Unknown device outcomes are never replayed automatically.
- Native OFF can reset presets. If original settings no longer match, restoration
  pauses with one attention event; no unverified preset write or relay fallback.
- Family distinguishes battery preservation from overload, and suppresses retired
  reserve-offset relay warnings when the schema-4 controller is observed.
- Dashboard replaces obsolete confidence-based manual-authority descriptions.

## Companion deployment — separately authorized only

Requires reviewed EH app, Family app, HA automations.yaml and dashboard together.
configuration.yaml helper history is retained; existing critical lockouts are
imported once into the durable shared journal. Old helpers are not subsequently
used to relatch cleared locks. Schema 4 rejects old retained schema-3 snapshots/commands.
Never deploy only the removed legacy writers or only the new controller expecting
protection to remain available through the transition. Plan an attended low-load
maintenance window, backup and compare the live files, then follow the standard
Core stop/check/start and app rebuild procedures. No such operation was performed.

Before promotion, verify OFF/native settings behaviour and restoration on actual
hardware, startup reconstruction, a manual override, telemetry loss, grid return
and confirmation messages. Keep Battery Reserve automatic application disabled.

## Offline Smart Heating 2.4

Occupied heating: fixed 40% stop (or higher explicit family floor), Eco whenever
grid is absent, including solar supply. Calculated house requirements remain
diagnostics/estimated endurance, not a moving stopping threshold. A deficit is
visible; 40% is not a guarantee of overnight household endurance.
Solar-only: at least the ordinary 50% soft boundary, and earlier if the solar
recharge budget requires it. No restart merely because grid returned.
The shared policy exposes the occupied-HP exception, but runtime 2.2.5 never
enables it. Future adapters must coordinate current heating demand, all owners,
mode changes and confirmed native preset restoration before deployment.
