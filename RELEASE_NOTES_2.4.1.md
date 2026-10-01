# EnergyHub 2.4.1 — continuous Battery Reserve

Private corrective candidate. Family Assistant remains 2.4.0.

## Changed

- The applied Battery Reserve is the sole inverter reserve target, 24 hours a
  day.
- Grid-available behavior charges or holds at the applied reserve and releases
  Solar at reserve +10 points. The 95% cap remains held until policy decreases.
- The 23:52 preliminary forecast and 05:00 revision change only the forecast
  allowance. Live grid and weather changes remain immediate.
- The former 23:50 Low-Tariff Plan, 06:05 Early Solar check, 07:00 ownership
  handoff, morning debt, and learned morning-reserve observations are retired.
- Persisted legacy Hybrid modes are still recognized and transferred safely to
  Battery Reserve ownership. New legacy Hybrid/Early Solar commands are ignored
  or redirected.
- The detailed legacy decision panel and its duplicate compact replacement are
  hidden. Current strategy and reserve remain in Modes & Controls; overnight
  grid-use and 07:00 SOC reporting are retained.

## Safety and rollout

The reviewed add-on, automation, and dashboard files were synchronized and
EnergyHub 2.4.1 started at 18:03 on 2026-09-12. Startup reconstructed Solar
(`SBU`/`OSO`) without inverter writes; Automatic Battery Reserve evaluated the
applied 20% floor at SOC 46% on a Normal grid and correctly took no action.
Scheduled-time and reserve-boundary monitoring remain open. Smart Heating
remains OFF. The release is not committed, pushed, or publicly released.
