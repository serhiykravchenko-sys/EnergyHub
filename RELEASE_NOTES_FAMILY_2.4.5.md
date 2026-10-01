# Family Assistant 2.4.5 overnight digest and tariff detail

Private corrective candidate. EnergyHub remains 2.4.2.

## Family delivery

- Keep the family chat silent from 23:00 until the scheduled 08:00 morning
  report. The report is the only 08:00 exception; ordinary delivery resumes at
  08:02.
- Persist and condense overnight family events into the morning report. A Grid
  Hold entry is summarized as its time, reserve, and Solar-return SOC.
- Keep private technical-chat diagnostics immediate during family quiet hours.

## Grid Hold clarity

- Show the current Grid Hold strategy as one compact line: grid, preserved
  reserve, and Solar-return threshold.
- Persist one reserve-episode latch and suppress another Grid Hold notification
  until a confirmed Solar return closes that episode. Existing 2.4.4 state is
  migrated without replaying a message after update.
- This is notification hysteresis only. EnergyHub inverter decisions and the
  established reserve plus ten-point Solar-return rule are unchanged.

## Monthly import

- Add current-month night and normal tariff energy/cost rows before the combined
  monthly total. These remain EnergyHub estimates, not billing measurements.

## Deployment boundary

Synchronize only Family Assistant 2.4.5. The homeowner reloads the Home
Assistant App store, selects Update, and verifies the 2.4.5 startup banner.
Home Assistant Core restart and public promotion are not included.
