# EnergyHub 1.3.3 — Projected-SOC Hybrid Gate

EnergyHub now enters the cheap-night Hybrid strategy only when the projected 07:00 SOC requires support.

- Projected 07:00 SOC at or above target: remain Solar.
- Current SOC at or above target, but projected 07:00 SOC below target: Hybrid Grid Hold.
- Current SOC below target: Hybrid Charging.

AHM remains authoritative at 23:50. If daytime Panic is active but the projected reserve is sufficient, AHM restores Solar.
