# EnergyHub 2.4.11 — private corrective candidate

Prepared as a repository candidate after the 2.4.10 snapshot and logic audit.
Subsequently, the homeowner supplied a 2.4.11 startup banner on 2026-09-27
and reported about 24 hours of normal operation. Exact source/deployed hashes
and attended negative-case validation are not recorded here. The following
describes the 2.4.11 change, not the new 2.4.12 candidate.

- Invalid or missing grid voltage now invalidates the complete control sample.
  This blocks grid-dependent decisions until another valid sample arrives.
- Estimated Grid Import requires physical grid presence and does not integrate
  across a grid-evidence gap. It remains an estimate, not a utility meter.
- Battery Reserve Automatic checks a dated, recently verified recommendation
  from an available EnergyHub entity before writing the selected reserve.
- A QPIWS warning must be recently and validly read before it can trigger a
  warning-based load shed. The Home Assistant executor independently checks its
  current warning sensor; malformed metadata-only replies cannot clear faults.
- Malformed persisted inverter-controller targets no longer abort startup.
- First-floor Smart Heating can start after explicit enable and can resume a
  pause it owns. A later family HA OFF request suspends automatic starts until
  Smart Heating is switched OFF and ON again. Solar-only starts at 600 W and
  remains eligible down to 400 W; short PV fluctuations get a five-minute
  climate-state dwell. Battery protection still stops at 40% immediately.
- Heat-pump plug restart restoration requires current guard/load/grid evidence
  and a five-minute grid recovery period. It attempts one plug at a time, with
  at least five minutes between attempts.

Repository tests and template checks are recorded in the candidate validation
record. HA Core configuration check, actual startup, entity registry and
negative-case behavior require an explicitly authorized deployment and attended
homeowner evidence.
