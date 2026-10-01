# EnergyHub 2.4.10 — private candidate

Prepared in the local repository on 2026-09-26. The add-on source was
synchronized to the Home Assistant local-app directory on 2026-09-26. The
homeowner subsequently reported the 2.4.10 startup banner and initial
telemetry. The separately approved Home Assistant beacon automation was
synchronized with a backup later that day; Automation reload and live color
validation remain open. No commit, push, or public release.

## Changes

- A forecast below the recent valid consumption average adds exactly 20
  reserve points, even for a large shortfall. Other grid, UHMC weather, Smart
  Heating, stale-evidence, and 95% cap rules are retained.
- The Home Assistant beacon is red at or below 40% SOC, yellow from above 40%
  to below 70%, green from 70% to below 95%, and blue from 95% upward. Its
  telemetry fail-safe and emergency pulse remain unchanged.
- Estimated grid-import battery energy no longer counts SOC gained while a
  confirmed SUB+OSO Grid Hold can charge the battery only from solar. A later
  return to grid-charging mode starts from the hold's final SOC.

The orange EV-potential chart series is derived from forecast and daily
consumption, not a measurement of simultaneous surplus. The purple grid-import
series remains an estimate: the house-load component may include solar supply
during SUB, and battery charging in SNU can also have mixed sources. The
candidate does not retrospectively alter saved daily values or claim
billing-grade accuracy.

## Safety and deployment

No new inverter command, relay operation, Zigbee restart, or Home Assistant
service restart was added. The release affects `addon/` and the Home Assistant
beacon automation. Add-on deployment would require a separate authorization;
the automation requires a separately scoped YAML comparison/synchronization
and Home Assistant check/reload or attended restart. Do not stop Core for the
add-on alone.

Live checks must confirm the version banner, unchanged inverter mode/reserve
ownership, forecast-deficit reserve evidence, each beacon boundary, and
estimated import behavior through a real Grid Hold and return. Compare
daytime import with a trusted physical grid meter before any stronger claim.
