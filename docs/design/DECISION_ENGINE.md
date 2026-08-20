# EnergyHub Decision Engine

## Purpose

The Decision Engine converts household context into requested operating strategies. Decision services never write inverter settings directly; `main.py` queues requests and the Inverter Controller owns verified transitions.

## Inputs

### Physical state

- battery SOC;
- confirmed operating mode;
- current grid availability;
- 48-hour grid history and weighted Grid Confidence.

### Energy context

- today's house consumption;
- tomorrow's total and `detailedHourly` Solcast forecast;
- first tomorrow forecast period at or above 300 W;
- post-07:00 solar sum;
- 16 kWh nominal battery capacity and 90% conservative efficiency.

### Permission and time

- Autopilot state;
- AHM ownership at 23:50;
- one guarded early-Solar evaluation at 06:05;
- Panic window from 07:00 inclusive to 23:50 exclusive;
- Solar handover at 07:00.

## Operating strategies

| Strategy | Menu 01 | Menu 16 | Ownership |
|---|---|---|---|
| Solar | SBU | OSO | Default/recovery |
| Hybrid Charging | SUB | SNU | AHM night plan |
| Hybrid Grid Hold | SUB | OSO | AHM night plan |
| Panic Charging | SUB | SNU | Daytime reserve recovery |
| Panic Grid Hold | SUB | OSO | Daytime reserve preservation |

The physical SUB+SNU and SUB+OSO combinations require persisted strategy context to distinguish AHM from Panic after restart.

## Adaptive Hybrid Mode

AHM evaluates once at 23:50 and is authoritative over any active daytime Panic strategy.

### Preconditions

AHM requires:

- Autopilot enabled;
- operating mode Solar, Unknown, Panic Charging, or Panic Grid Hold;
- valid battery SOC.

### Morning net-energy model

Home Assistant captures cumulative total-house and all three heat-pump energy
values at 07:00, 08:00, 09:00, 10:00, 11:00, and 12:00. EnergyHub derives each
hourly essential-load sample as:

```text
essential_load_kwh =
    max(0, house_energy_delta - heat_pump_energy_delta)
```

It retains 21 days and uses the 75th percentile independently for each
07:00–12:00 interval. The model becomes authoritative only after every interval
has at least three valid samples and tomorrow's aligned hourly solar is complete.

```text
hourly_net_deficit =
    max(0, expected_essential_load - forecast_solar)

morning_deficit_kwh = sum(hourly_net_deficit)

morning_gap_soc =
    morning_deficit_kwh / (16 kWh * 0.90) * 100
```

Solar takeover is confirmed when forecast solar covers expected essential load
for two consecutive hours. This prevents one isolated optimistic hour from
ending the protected bridge.

### Learning and input fallback

Until the learned model is ready, AHM continues to use the verified 1.3.1 ramp
model:

```text
projected_soc_at_07 = max(0, current_soc - 15)

raw_morning_gap =
    hours_from_07_to_first_300W_forecast

if first_300W_hour is followed by an hour >= 600W
    ramp_credit = 1 hour
else
    ramp_credit = 0

effective_morning_gap =
    max(0, raw_morning_gap - ramp_credit)

morning_gap_soc = effective_morning_gap * 10
```

Home Assistant derives the candidate ramp from Solcast hourly data. EnergyHub independently verifies both retained powers before accepting the credit. If the hourly forecast is unavailable, the morning gap falls back to five hours with no credit. Dashboard diagnostics always identify `learned_net_energy` or `verified_ramp_fallback` and explain the fallback reason.

### Aligned daytime energy

Night consumption is excluded because Grid Hold carries the house from cheap grid power.

```text
expected_consumption_after_07 =
    today_consumption * 17 / 24

post_07_energy_deficit_kwh =
    max(0,
        expected_consumption_after_07
        - forecast_solar_after_07)

daytime_deficit_soc =
    post_07_energy_deficit_kwh
    / (16 kWh * 0.90)
    * 100
```

The 17/24 projection is an explicit initial model. A later release may replace it with measured time-of-day load history.

### Target

```text
target_soc =
    min(95,
        selected minimum SOC
        + max(morning_gap_soc, daytime_deficit_soc))
```

The selected minimum is a Home Assistant helper from 20% to 50% in 5% steps. It applies only to AHM; Panic keeps its Grid Confidence targets. Using the maximum avoids counting the pre-solar morning load twice.

### Decision

```text
if projected_soc_at_07 >= target_soc
    remain or restore Solar
else if current_soc >= target_soc
    enter Hybrid Grid Hold
else
    enter Hybrid Charging
```

The conservative projected 07:00 SOC gates initial night-grid use. The target,
strategy context, and date through which the night plan is active are
persisted. At target, Hybrid Charging changes to Hybrid Grid Hold.

### Continuous night enforcement

From the dated 23:50 evaluation until a confirmed non-AHM Solar handover,
EnergyHub reevaluates the existing target on every fresh local telemetry
cycle. It does not recalculate or raise the target:

```text
Solar and SOC > target  → remain Solar
Solar and SOC = target  → Hybrid Grid Hold
Solar and SOC < target  → Hybrid Charging
Grid Hold and SOC < target → resume Hybrid Charging
```

Stale or unavailable SOC and an absent grid produce no inverter request. The
date rejects a retained target from an older night after restart. A confirmed
guarded early-Solar or ordinary 07:00 Solar handover clears the active night
context. Daytime Panic ownership remains unchanged.

### Early Solar handover

Home Assistant publishes the current-day Solcast energy forecast for the
06:00–07:00 interval once at 06:05. EnergyHub, not Home Assistant, applies the
control decision. It requests Solar only when all of these conditions hold:

- Autopilot is enabled and confirmed mode is Hybrid Grid Hold;
- the request date is current and local time is inside 06:00–07:00;
- the persisted Adaptive Hybrid target exists and current SOC meets it;
- inverter telemetry and aligned Total Solar are fresh;
- the grid is currently present;
- live Total Solar is at least 300 W;
- the 06:00–07:00 forecast is at least 1.6 kWh, equivalent to the existing
  conservative 10%-of-16-kWh hourly bridge allowance.

Any failed, missing, stale, or unsupported condition leaves the inverter in
Grid Hold. Hybrid Charging is never released by this check. The ordinary
07:00 Solar handover remains authoritative fallback behavior. The transition
result is confirmed through the existing Inverter Controller and remains
observable if confirmation fails.

![Adaptive Hybrid reserve and early Solar handover](../Images/Infographic%237_adaptive_hybrid_early_solar.png)

## AHM morning debt

At the first Panic evaluation after 07:00, EnergyHub compares actual SOC with the persisted AHM target.

```text
if actual_soc < ahm_target
    ahm_debt = ahm_target
else
    ahm_debt = none
```

The debt is persisted by date so a midday add-on restart cannot manufacture a new debt after normal battery use. It is cleared after the target has been recovered.

## Conservative Panic

Panic is deliberately simpler and more conservative than AHM.

### Grid Confidence target

| Existing Grid Confidence state | Panic target |
|---|---:|
| normal | 20% |
| unstable | 60% |
| risk | 80% |
| panic | 95% |

```text
panic_target = max(Grid Confidence target, active AHM debt)
```

### Evaluation

Panic evaluates every five minutes from 07:00 until 23:50 and immediately after grid transitions.

It requires:

- Autopilot enabled;
- Solar, Panic Charging, or Panic Grid Hold ownership;
- valid SOC and supported Grid Confidence;
- no inverter transition in progress.

Solar forecast and yesterday's consumption are not Panic gates.

### Offline waiting and recovery

```text
if SOC < target and grid offline
    enter/retain Panic Charging strategy
    phase = waiting_for_grid

if SOC < target and grid online
    phase = charging

if SOC >= target
    enter Panic Grid Hold
    preserve reserve until 23:50
```

SUB+SNU can be configured while external grid is absent. The inverter continues to use available solar/battery and begins grid charging when electricity returns. If SOC falls below target during Panic Grid Hold, Panic Charging resumes.

![AHM and Panic coordination](../Images/Infographic%235_ahm_panic_coordination.png)

## Ownership timeline

```text
06:05  If Hybrid Grid Hold passes every early-Solar gate, restore Solar
07:00  Solar handover; calculate any AHM debt
07:00–23:50  Panic owns conservative daytime recovery
23:50  AHM always takes ownership from Panic
23:50–07:00  AHM charges or holds using cheap night electricity
```

## Heat-pump permission

Reserve guards never start heat pumps. A temporary manual-use permission exists only while:

- telemetry is fresh;
- the grid is currently present;
- confirmed mode is Hybrid Charging, Hybrid Grid Hold, Panic Charging, or Panic Grid Hold.

When grid disappears, remembered reserve locks are enforced again.

## MQTT diagnostics

AHM publishes its evaluated SOC, time, selected minimum, active morning model, learning progress, expected essential load, morning forecast solar, net deficit, 300 W threshold time and power, following-hour power, raw gap, independently validated ramp confirmation and credit, effective solar-support time and gap, post-07 consumption, post-07 solar, daytime deficit kWh/SOC, final calculation, target, cap, and fallback state. The early-Solar evaluator separately publishes its status, concise reason, evaluation time, live Total Solar, and 06:00–07:00 forecast energy.

Panic publishes its decision, reason, phase, effective target, Grid Confidence target, inherited AHM target, and target source.

Decision values are retained for Home Assistant presentation. On EnergyHub
restart, the decision state becomes `awaiting_evaluation`; the reason states
whether a target was retained and that the detailed current-process plan is
unavailable until the next 23:50 evaluation. This avoids presenting a stale
night plan as newly calculated.

## Safety priority

`safe_solar` has queue priority when Autopilot is disabled. It cannot be overwritten by AHM, Panic, or manual requests. Invalid or inconsistent inverter state remains observable and is not guessed from telemetry alone.

## AHM reserve advisor

The advisor is observational and never owns the inverter. Home Assistant records the lowest SOC from 07:00 through 12:00 and the AHM minimum selected for that morning. EnergyHub compares only completed mornings recorded at the current slider value. After three comparable mornings it recommends one named step:

Home Assistant marks each morning observation valid only after a trustworthy 07:00 SOC initialization. Missing initialization or a Home Assistant restart before publication invalidates the morning, so partial or restored helper state cannot become recommendation evidence.

- increase when at least two mornings came within five SOC points of the selected reserve;
- decrease only when all three stayed at least 20 SOC points above the reserve;
- otherwise keep the current value.

Changing the slider starts a new comparable window while retained observations remain available. The named recommendation levels are 20, 30, 40, and 50%; custom 5% values move to the next named level in the recommended direction. The dashboard and Family Assistant consume the same retained MQTT result. Panic targets remain independent.
