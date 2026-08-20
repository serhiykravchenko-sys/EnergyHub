# EnergyHub 1.3.5 - PV2 and Total PV Telemetry

EnergyHub 1.3.5 adds an optional, strictly read-only telemetry layer for the
second PV input on the installed PowMr POW-HVM10.2M.

## Added

- PV2 voltage from Modbus holding register 4563, scaled by 0.1 V;
- PV2 power from Modbus holding register 4564 in watts;
- Total PV power derived from aligned, fresh PV1 and PV2 samples;
- PV2 status, freshness, sample age, and dedicated MQTT availability;
- regression tests for protocol decoding, failures, freshness, alignment,
  restart behavior, and PI30MAX continuity.

## Safety boundary

- Modbus is disabled by default and polls conservatively when enabled.
- All PI30MAX and Modbus operations use one adapter-owned serial lock.
- The implementation can issue only one fixed function-03 read for registers
  4563-4564. It contains no Modbus write or generic register interface.
- Bad CRC, timeout, malformed response, invalid range, unsupported firmware,
  and other PV2 failures do not invalidate or stop PI30MAX polling.
- Retained PV2 values are marked unavailable when stale and are not
  reconstructed as fresh after restart.
- Total PV requires no more than 15 seconds between the component samples and
  expires when either component exceeds its freshness limit.
- PV2 and Total PV do not participate in AHM, Panic, Hybrid, or inverter
  control decisions in 1.3.5.

## Validation status

The verified high-production and curtailed-production Modbus frames are covered
by 80 passing add-on tests. Python compilation also passes. The 1.3.5 app built,
updated, and started successfully on Home Assistant on 2026-08-14.
`ha core check` completed successfully. The first two nighttime PV2 polls
returned valid frames with 0.0 V and 1 W while PI30MAX continued to report PV1
at 0 W; Total PV correctly published 1 W. MQTT Discovery created the PV2
voltage/power, Total PV, status, freshness, and sample-age entities. Solar mode
was reconstructed without inverter writes and EnergyHub health reached online.

The PV1, PV2, and Total PV 24-hour chart was then deployed and inspected under
daylight production. The three series rendered correctly and Total PV tracked
the combined component series. This chart result is homeowner-observed; the
retained validation evidence does not contain a numeric daylight sample.

A 2–3-day private monitoring period remains required before public promotion.

## Acknowledgements

Power Forum users `tistructor` and `lismulder` documented the `QPIGS2`
limitation and the Modbus PV2 register lead. `odya` and contributors to
`esphome-powmr-hybrid-inverter` published useful PowMr Modbus, byte-order, and
register-map research. These were research leads; EnergyHub independently
verified registers 4563 and 4564 on the installed inverter and implemented its
own bounded read-only integration.
