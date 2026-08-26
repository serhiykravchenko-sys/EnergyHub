# EnergyHub 1.3.13 — Normal-Grid Reserve Hysteresis

EnergyHub 1.3.13 replaces the unconditional morning Solar switch with an
explicit daytime reserve handoff and aligns smart-plug protection with a
trusted, present grid.

## 07:00 ownership handoff

At 07:00, Home Assistant requests a Panic evaluation rather than Solar. The
add-on evaluates fresh SOC, current Grid Confidence, physical grid state, and
any genuine missed AHM target.

When confirmed Hybrid Grid Hold is already `SUB` + `OSO`, EnergyHub transfers
ownership to Panic Grid Hold by persisting the new owner without issuing
redundant inverter commands.

## Normal-grid 20%/30% cycle

With Grid Confidence Normal, grid present, and no active AHM debt:

- Solar at 20% or below enters Panic Grid Hold;
- SOC below 20% uses Panic Charging until the floor is recovered;
- Panic Grid Hold keeps the house grid-backed while OSO permits solar-only
  battery charging;
- SOC reaching 30% releases Solar;
- a later fall to 20% repeats the cycle.

The ten-point hysteresis prevents rapid switching around one SOC value. Solar
release is not attempted while the grid is absent. A genuinely missed AHM
target is still recovered first, and Unstable/Risk/Panic confidence retains
the existing 60/80/95% behavior.

## Trusted-grid smart-plug permission

While Grid Confidence is Normal, grid voltage is present, and EnergyHub
telemetry is fresh, SOC reserve automation does not turn off or reject the
water boiler or any participating heat pump. Remembered lockouts remain
latched underneath and are enforced again if trust is lost.

The basement water pump remains critical infrastructure outside automatic
shedding. EnergyHub does not automatically turn any boiler, heat pump, or
water pump on. Homeowner-selected heat-pump auto-off timers remain separate.

## Validation boundary

Repository tests cover the new ownership transfer, exact threshold behavior,
hysteresis, offline release guard, missed AHM debt, non-Normal preservation,
and no-write transfer. Home Assistant configuration and the affected live
transitions require separate guarded deployment and homeowner observation.
