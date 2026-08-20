# EnergyHub 1.3.4 — Safer Controls and Clearer Diagnostics

- Replaces the exposed AHM slider with confirmed 5% decrease/increase controls.
- Highlights and groups the active reserve, explanation, and recommendation as one management control.
- Publishes a short Hybrid Decision Reason that Home Assistant can store reliably.
- Keeps the detailed calculation and notification explanation separately.
- Shows `None` when Panic has no inherited AHM target.
- Renames the temporary morning model to `verified_ramp_fallback` and clarifies that learned energy values appear after 3/3 samples.
