# Energy Hub 1.3.2

- Learns essential 07:00–12:00 hourly load after subtracting all heat-pump energy.
- Uses a conservative 21-day 75th-percentile profile after three complete samples per interval.
- Plans the morning bridge from aligned hourly load and solar net deficits.
- Requires two consecutive solar-covering hours before takeover.
- Keeps the verified 1.3.1 solar-ramp calculation as the safe fallback.
- Advises one AHM reserve step from three comparable completed mornings and shares the informational result with Home Assistant and Family Assistant.
- Skips a morning observation when the 07:00 SOC is unavailable or Home Assistant restarts during the measurement window.

See `CHANGELOG.md` and `DOCS.md` for complete details.
