# Dashboard implementation sources

## 3.6.36 presentation refinement

Mission Control keeps daily status/controls; Settings and Diagnostics separate
configuration from evidence. BMS uses the installed Apex card threshold gradient
for signed current, integer twenty-amp-aligned bounds and zero reference; SOC/current
widths remain 3/2px. `render_balance_3636.cjs` exercises the installed card using
synthetic mixed/positive/negative/zero/gap data at narrow/wide widths. Other
energy-history generators and forecast definitions are unchanged.


## 3.6.35 canonical daily balance

energy_history.js is the readable source embedded in the card async generators. It queries HA recorder daily change statistics in kWh and HA timezone, sums matching tariff buckets, and overrides only current consumption with the same live meter as the raw header. Missing history is null; no recorder backfill/write. Rendering fixtures use synthetic data.
