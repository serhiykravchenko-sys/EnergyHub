# EnergyHub 1.3.9

EnergyHub 1.3.9 adds a strictly read-only SOC Anomaly Journal. It records a
suspicious event when two consecutive valid SOC samples differ by at least
five percentage points and are no more than five minutes apart.

Each retained event includes:

- previous/current SOC, delta, and elapsed seconds;
- battery voltage and separate charge/discharge current;
- PV1, fresh PV2, fresh aligned Total PV, and house load;
- grid availability and voltage;
- operating mode and telemetry freshness;
- EnergyHub start time and uptime;
- whether the event followed EnergyHub startup or communication recovery;
- low, mid-range, or top-of-charge SOC context.

The journal persists its latest 100 events in `/data`, while a lifetime count
continues beyond the rolling history. Home Assistant receives
`sensor.energyhub_soc_anomaly_event_count` and
`sensor.energyhub_soc_anomaly_latest`; the latest-event entity exposes the full
record as attributes.

This observer does not reject or quarantine SOC, modify an EnergyHub decision,
send an inverter command, switch a household load, inhibit control, or produce
a Telegram alarm. A journal persistence failure is logged and isolated from
telemetry and control.

The coordinated Telegram Family Assistant 0.2.0 update checks seven configured
temperature/humidity sensors every five minutes and adds active issues to the
08:00 report. Six indoor sensors use the current indoor median and the same
local hour from the previous day. The basement uses only its own previous-day
baseline. Temperature deviations of 5 °C and humidity deviations of 20
percentage points must persist for 60 minutes. Explicit unavailable states and
24-hour stale data are reported directly. The app also reports verified sensor
batteries and an optional configured doorbell battery at or below 10%.

The doorbell battery entity remains disabled until its exact Home Assistant
entity ID is verified and entered in the companion app settings.
