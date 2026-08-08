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

### Morning bridge

```text
projected_soc_at_07 = max(0, current_soc - 15)

morning_gap_soc =
    hours_from_07_to_first_300W_forecast * 10
```

If the hourly forecast is unavailable, the morning gap falls back to five hours.

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
        20 protected reserve
        + 10 uncertainty margin
        + max(morning_gap_soc, daytime_deficit_soc))
```

Using the maximum avoids counting the pre-solar morning load twice.

### Decision

```text
if projected_soc_at_07 >= target_soc
    remain Solar
    (or restore Solar when taking ownership from Panic)
else if current_soc >= target_soc
    enter Hybrid Grid Hold
else
    enter Hybrid Charging
```

The target and strategy context are persisted. At target, Hybrid Charging changes to Hybrid Grid Hold. Home Assistant requests Solar at 07:00.

![Adaptive Hybrid Mode calculation](../Images/Infographic%234_adaptive_hybrid_v2.png)

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

AHM publishes its evaluated SOC, time, post-07 consumption, post-07 solar, daytime deficit kWh/SOC, morning bridge, final calculation, target, cap, and fallback state.

Panic publishes its decision, reason, phase, effective target, Grid Confidence target, inherited AHM target, and target source.

All decision values are retained so Home Assistant restarts do not erase the explanation.

## Safety priority

`safe_solar` has queue priority when Autopilot is disabled. It cannot be overwritten by AHM, Panic, or manual requests. Invalid or inconsistent inverter state remains observable and is not guessed from telemetry alone.
