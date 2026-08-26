# EnergyHub 1.3.9 — SOC Anomaly Journal

EnergyHub 1.3.9 preserves the 1.3.8 inverter and flexible-load control policy
and adds diagnostic evidence only.

## SOC anomaly evidence

Consecutive valid SOC samples create an event when they differ by at least
five percentage points within five minutes. EnergyHub retains the latest 100
events plus a lifetime count. Each event records SOC, elapsed time, battery
voltage, separate charge/discharge current, PV1, fresh PV2 and aligned Total
PV, house load, grid availability/voltage, mode, freshness, EnergyHub uptime,
SOC region, startup context, and communication recovery.

Home Assistant receives:

- `sensor.energyhub_soc_anomaly_event_count`;
- `sensor.energyhub_soc_anomaly_latest`, with the full latest event as
  attributes.

The journal does not reject telemetry, influence System Health, inhibit a
decision, change inverter mode, switch a household load, or send Telegram.

## Household sensor health

Telegram Family Assistant 0.2.1 checks seven configured Xiaomi
temperature/humidity sensor pairs every five minutes. Six indoor sensors use
the indoor median; the basement uses only its own same-hour previous-day
baseline. Temperature differences of 5 °C and humidity differences of 20
percentage points must persist for 60 minutes. Explicit unavailable states,
24-hour staleness, active anomalies, recoveries, and verified low sensor
batteries appear in the existing 08:00 report.

If Home Assistant continues refreshing a cached numeric state, a sensor is
also reported as suspected offline when both temperature and humidity remain
unchanged for 24 hours. Recovery history is collapsed to one detailed line per
physical sensor.

An optional doorbell battery entity warns at or below 10%, repeats once each
morning while unresolved, and distinguishes stale/unavailable data from a real
low value. The option remains empty until the exact entity ID is verified.

All companion messages remain outbound-only and informational. Environmental
data and device batteries are not EnergyHub control inputs.
