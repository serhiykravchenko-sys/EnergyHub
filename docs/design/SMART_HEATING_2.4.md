# Smart Heating 2.4 — first-floor policy

## 2.4.2 night and beacon addendum

While Smart Heating owns the first-floor heat pump, Quiet is selected from 23:00
through 08:00. Turbo is removed. Protection may still turn heating OFF.
Smart Heating OFF remains manual authority and does not rewrite Quiet. The
signalling indicator adds a two-second pulse every 20 seconds only with fresh
telemetry: white for ordinary Smart Heating and yellow when Solar-only Heating is
also enabled. Stale telemetry remains steady white and suppresses the pulse.

The original 2.4.2 addendum above is historical. The 2.4.12 correction below was
deployed on 2026-09-29; the homeowner reported the agreed monitoring window
passed on 2026-10-01. Routine monitoring does not validate every manual/timer
failure or extended cold-weather operation. Dashboard controls default to OFF
on a fresh installation; do not infer current switch states from this document.

## Authority and hardware boundary

Protective priority is overload protection, then battery-discharge protection.
Manual family OFF prevents optional Smart Heating starts. A higher-priority
owner or stale/high load evidence blocks every heating start or setting change.
The first-floor heat pump is controlled through
`climate.first_floor_heat_pump`. Its smart plug remains ON for routine
climate operation and supplies power measurement; protective shedding or
guarded restart restoration may use the plug for electrical isolation. Smart
Heating does not control the second- or third-floor heat pump.

Turning Smart Heating OFF returns the heat pump to manual control without blindly
changing its current state. Solar-only applies only to heating; essential household
loads and inverter protection may still use the grid.

## Battery Reserve interaction

Smart Heating adds a fixed 20 percentage points to the ordinary Battery Reserve
calculation after forecast, Grid Confidence and qualifying weather modifiers. The
combined result is capped at 95%.

The generation tiers are:

- forecast at least recent consumption average: +0 points;
- deficit, but twice the forecast still covers the average: +20 points;
- any forecast generation below the recent consumption average: +20 points,
  without a second severe-deficit tier.

Battery-discharge protection warns at 50%, stops flexible loads at 40%, may restore
the Smart Heating first-floor heat pump in Eco at 50%, and restores the other loads
at 60%. Grid recovery releases the battery block, but restoration remains subject
to overload ownership and sequential verification.

## Heating modes

The family chooses temperature, fan speed, and Super mode. Smart Heating does
not overwrite those settings. It manages native Heat/OFF, Quiet from 23:00
through 08:00, and Eco whenever reliable grid voltage is absent.
At 40% SOC or below it records ownership and turns the native climate entity OFF.
At 50% SOC it restores only that owned pause; an appliance Smart Heating did not
turn off is not restored. Enabling Smart Heating authorizes an initial start.
Once Heat is confirmed, the temporary auto-resume flag is cleared, so a later
remote OFF does not trigger a delayed restart. A family HA OFF request also
revokes optional auto-resume, including when its service call identifies the
climate only in `service_data`. A physical remote OFF while EnergyHub has
already paused the climate may be indistinguishable from the owned pause;
switch Smart Heating OFF for unambiguous manual control in that case.

## Solar-only heating

Solar-only requires the inverter Solar strategy, daylight, current PV >=600 W
to start or >=400 W to continue, and SOC above the calculated Battery Reserve.
A PV-only stop waits for five minutes in the current climate state; battery
protection still stops immediately at 40%. Solar-only changes energy authority,
not the Normal/Quiet/Eco mode
selection, and has no Turbo path.

After HA restart, only remembered family-ON first/second-floor plugs can be
restored. Current guard/load/grid evidence, a five-minute grid-recovery timer,
one candidate at a time, and a five-minute interval between attempts apply.
An automatic protective plug OFF pauses a selected family auto-off timer without
erasing its chosen hours; an eventual ON restarts that full selected duration.
A family HA OFF or a timer expiry clears the selection. This bounds running
time after restoration but does not preserve the original wall-clock deadline.
The three timer automations queue their own plug OFF and helper-change events,
so the expiry run can finish clearing the selected hours before handling its
resulting plug OFF event.

## Evidence and notifications

The first-floor room sensor is
`sensor.example_room_1_temperature`. The bathroom sensor is not used until its
offset is calibrated. The exact first-floor motion entity is not recorded, so the
planned 12-hour automatic occupied/Solar-only selection and 24-hour manual hold are
deliberately not enabled.

The family Telegram bot observes persistent controls and confirmed runtime states.
It sends short messages for Battery Reserve authority changes, confirmed automatic
or manual reserve changes, Smart Heating and Solar-only toggles, and heating mode
transitions. Startup observation is silent; the delayed HA restart summary reports
the reconstructed state once.

## Activation gates

Before activation: deploy with both heating controls OFF, validate all entity IDs
and available Quiet/Eco settings, observe Battery Reserve Auto, perform an attended
native stop/restart test, verify overload/battery ownership in live telemetry, and
review logs after several days. Repository tests do not constitute live hardware
validation.
