# Home Assistant responsibilities

The [reference files](../../homeassistant/README.md) provide the bridge between
EnergyHub and a particular home. They must be adapted, not blindly installed.

## Inputs and control boundary

Home Assistant provides solar forecasts, weather warnings, household demand,
configured reserve preferences, device snapshots and family intents.
EnergyHub evaluates policy and owns guarded inverter transitions and load
ownership. HA executes supported device service calls and returns evidence.
Family Assistant is an outbound reporter, not a second controller.

The current reserve is continuous (20–95%, manual or automatic). Legacy
night-plan entities can remain for compatibility/history; they are not a
second reserve authority. Forecast/weather/grid modifiers are not a promise
of cheap-time-only charging. See [current reserve](../design/BATTERY_RESERVE_CURRENT.md).

Scheduled HA inputs include night/morning reevaluation and daily-summary
snapshots. Review the actual automation times and local timezone in the YAML;
do not interpret scheduling as a general dynamic-tariff optimizer.

## Mapping and commissioning

Map the generic example aliases to your real entities. Verify availability,
power readings, climate capabilities and acknowledgements independently.
No essential or safety-critical load belongs in a shedding list.
Keep automatic device control disabled until attended manual OFF, stale-data,
missing-device, protective OFF and owned-restore tests pass.

Smart Heating manual mode leaves temperature and fan choices to the family.
Supported quiet/Eco changes remain bounded by the documented policy. Family
OFF releases EnergyHub ownership; protective interruptions retain the selected
timer hours. A later ON begins that full duration again, not the original
wall-clock deadline.

## Maintenance

Merge rather than replace manually maintained YAML. Run `ha core check` after
changes, then reload or restart as appropriate. Stop Core before editing or
copying `.storage`; preserve a backup. Ordinary add-on updates do not require
Core to stop. Restart tests and routine operation are distinct evidence.

See [installation](INSTALLATION.md),
[Smart Heating](../design/SMART_HEATING_2.4.md),
[load protection](../design/PEAK_LOAD_CONTROL.md), and
[release evidence](../validation/RELEASE_2.4.12.md).
