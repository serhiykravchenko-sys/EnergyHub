# PowMr 10.2M Modbus Telemetry

## Status

Read-only Modbus RTU telemetry was verified on the installed PowMr 10.2M on
2026-08-14. This is a separate capability layer from the PI30MAX interface used
by EnergyHub 1.3.4.

EnergyHub 1.3.5 now implements the optional production reader in the repository.
All 80 add-on tests pass. EnergyHub 1.3.5 was packaged, deployed, and
nighttime-validated on 2026-08-14. The evidence proves that this specific
inverter exposes the registers; it does not establish a register map for every
PowMr 10.2M firmware version.

## Verified transport

- physical path: the same FTDI USB-RS232 adapter used by PI30MAX;
- baud rate: 2400;
- data format: 8 data bits, no parity, one stop bit;
- Modbus slave address: `5`;
- function: `03` (read holding registers);
- register values: 16-bit words with byte-swapped payload values;
- writes performed during verification: none.

Only one process may own the serial port. The EnergyHub app was stopped for the
bounded probe and restarted immediately afterward.

## Live evidence

The first request used known register 4502 to validate transport and byte order:

```text
Request:  05 03 11 96 00 01 60 9E
Response: 05 03 02 9C 08 21 42
Decoded:  2204 -> 220.4 V grid voltage
```

The PV2 request read registers 4563 and 4564 together:

```text
Request:  05 03 11 D3 00 02 31 4A
Response: 05 03 04 C6 0D 8A 0D B4 1D
Decoded:  register 4563 = 3526 -> 352.6 V
          register 4564 = 3466 -> 3466 W
```

Both responses had valid Modbus CRC values. The PV2 values were plausible for
the current solar conditions. The existing PI30MAX loop resumed after restart
with fresh PV1, SOC, load, grid, settings, and decision telemetry. Startup
reconstruction explicitly reported that it did not write inverter settings.

### Full-battery / curtailed-production sample

The same bounded read-only probe was repeated on 2026-08-14 at approximately
12:10 after the battery had reached 100% in Home Assistant. The validation read
returned 218.9 V grid voltage. The PV2 response was:

```text
Request:  05 03 11 D3 00 02 31 4A
Response: 05 03 04 78 0F FB 00 D4 60
Decoded:  register 4563 = 3960 -> 396.0 V
          register 4564 = 251  -> 251 W
```

After EnergyHub restarted, fresh PI30MAX telemetry reported SOC 99%, PV1
552 W, house load 309 W, and Solar mode. The provisional fresh-sample total was
therefore approximately 803 W. Compared with the earlier PV2 sample of 352.6 V
and 3466 W, the sharply lower power and higher string voltage are consistent
with curtailed/low-current PV operation and demonstrate that registers 4563 and
4564 are live rather than frozen values.

The low/nighttime, high-production, and full-battery curtailed-production
observations are complete. A separate medium-production point would add useful
diagnostic evidence but is not a release blocker because the live registers
have already varied plausibly across the validated operating range.

### EnergyHub 1.3.5 supervised deployment

The Home Assistant app updated and started as version 1.3.5 on 2026-08-14 with
PV2 polling enabled at 30 seconds. `ha core check` completed successfully.

At 22:43 local time, two consecutive nighttime polls returned PV2 0.0 V and
1 W while PI30MAX reported PV1 0 W. EnergyHub published Total PV as 1 W. PI30MAX
telemetry continued between Modbus polls, communication health became online,
Solar mode reconstructed without inverter writes, and no timeout, CRC,
malformed-response, serial-contention, or decision error was observed.

Home Assistant MQTT Discovery created PV2 Voltage, PV2 Power, Total PV Power,
PV2 Telemetry Status, PV2 Telemetry Freshness, and PV2 Sample Age. The PV1,
PV2, and Total PV 24-hour chart was subsequently deployed and visually checked
under daylight production. The user observed all three series rendering and
Total PV tracking the combined component series; no numeric daylight snapshot
was retained in the repository evidence. Longer private monitoring remains
pending.

## Why the community frame looked unusual

The reported frame `05 03 04 67 0C 0A 00 66 24` is a response, not a request:

- `05` - slave address;
- `03` - read holding registers;
- `04` - four data bytes;
- `67 0C` and `0A 00` - two byte-swapped register values;
- `66 24` - CRC.

The decoded values are 3175 and 10. A correct request for decimal registers
4563-4564 is `05 03 11 D3 00 02 31 4A`.

## EnergyHub 1.3.5 integration

The repository implementation:

1. keeps PI30MAX and Modbus behind one adapter-owned serial lock;
2. polls PV2 conservatively and never overlaps an `mpp-solar` process;
3. validates slave, function, byte count, CRC, byte-swapped ranges, and freshness;
4. retains the last valid measurement only behind explicit stale/offline availability;
5. defaults Modbus to disabled so unsupported firmware cannot degrade PI30MAX;
6. publishes Total PV only when PV1 and PV2 samples are within 15 seconds and both remain fresh;
7. starts with PV2 and Total PV unavailable after restart until a new valid sample arrives;
8. covers timeout, CRC, malformed response, unsupported exception, invalid range, stale data, restart, and PI30MAX continuation in regression tests;
9. exposes no generic Modbus register operation and no Modbus write path.

Suggested entities:

- PV1 voltage and power - existing PI30MAX values;
- PV2 voltage and power - Modbus registers 4563 and 4564;
- total PV power - derived from fresh PV1 plus fresh PV2 only;
- PV2 telemetry health/freshness;
- optional per-string anomaly signal after sufficient history exists (deferred).

## Dual-output boundary

The PowMr 8.2/10.2 kW manual confirms a dual-output feature and documents:

- menu 41 - enable/disable dual output;
- menu 42 - dual-output exit voltage and load-percentage thresholds;
- maximum second load in battery mode: 3400 W for the 10.2 kW model.

The available sources do not provide a trustworthy Modbus write-register map
for those settings. EnergyHub must not infer write addresses from adjacent
registers or another model.

Future second-output work should therefore proceed in stages:

1. identify read-only state/setting registers from a captured official app or
   display interaction;
2. verify those reads on the installed firmware;
3. define the Home Assistant intent and hardware limits in shadow mode;
4. perform an attended single-setting write only after the exact frame,
   accepted range, read-back, rollback, and power limits are independently
   verified;
5. never expose a raw Modbus-write service to Home Assistant, messaging, voice,
   or an AI agent.

## Research sources

### Community acknowledgement

Power Forum users `tistructor` and `lismulder` documented the `QPIGS2`
limitation and the Modbus PV2 register lead. `odya` and contributors to
`esphome-powmr-hybrid-inverter` published useful open PowMr Modbus, byte-order,
and register-map research. These contributions supplied research leads;
EnergyHub independently verified registers 4563 and 4564 on the installed
inverter and implemented its own bounded read-only reader.

- [PowMr manual download page](https://powmr.com/pages/powmr-user-manual)
- [Community POW-HVM10.2M PV2 report](https://powerforum.co.za/topic/29426-powmr-pow-hvm102m-unable-to-read-pigs2-nak/)
- [Community ESPHome Modbus implementation](https://github.com/odya/esphome-powmr-hybrid-inverter)
- [Community register map for the related 2.4 kW model](https://github.com/odya/esphome-powmr-hybrid-inverter/blob/main/docs/registers-map.md)

Community material is a research lead, not a compatibility guarantee. The live
read-only result above is authoritative only for the installed inverter.
