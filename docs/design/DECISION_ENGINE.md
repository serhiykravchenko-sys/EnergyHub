# EnergyHub Decision Engine

> Historical design reference for the retired Low-Tariff Plan and daytime
> Panic/AHM handoff. The current 2.4 policy is documented in
> [Battery Reserve](BATTERY_RESERVE_CURRENT.md) and
> [System Architecture](05-System-Architecture.md). The legacy timelines,
> thresholds, and ownership rules below must not be used for deployment.

> **Current 2.4.1 candidate:** Battery Reserve is the sole 24/7 reserve
> controller. Its applied floor already includes forecast, live grid, weather,
> and Smart Heating allowances. It holds/charges at that floor and releases
> Solar at floor +10 (except the held 95% cap). The former 23:50 Low-Tariff
> Plan, 06:05 Early Solar check, 07:00 ownership handoff, morning debt, and
> learned morning target are retired. The detailed legacy design below is kept
> only as historical and restart-compatibility context.

Reviewed terminology for 2.1.3. The live controllers below are separate from the
[new Battery Reserve advisory policy](BATTERY_RESERVE_CURRENT.md). Raw MQTT keys
and code identifiers retain their old names. No automatic reserve ownership is
introduced by this documentation update.

## Purpose

The Decision Engine converts household context into requested operating strategies. Decision services never write inverter settings directly; `main.py` queues requests and the Inverter Controller owns verified transitions.

## Inputs

### Physical state

- battery SOC;
- confirmed operating mode;
- current grid availability;
- 48-hour grid history and weighted Grid Reliability.

### Energy context

- today's house consumption;
- tomorrow's total and `detailedHourly` Solcast forecast;
- first tomorrow forecast period at or above 300 W;
- post-07:00 solar sum;
- 16 kWh nominal battery capacity and 90% conservative efficiency.

### Permission and time

- Autopilot state;
- Low-Tariff Plan ownership at 23:50;
- one guarded early-Solar evaluation at 06:05;
- Reserve Protection window from 07:00 inclusive to 23:50 exclusive;
- Reserve Protection ownership evaluation at 07:00.

## Operating strategies

| Strategy | Menu 01 | Menu 16 | Ownership |
|---|---|---|---|
| Solar | SBU | OSO | Default/recovery |
| Low-Tariff Charging | SUB | SNU | Low-Tariff Plan night plan |
| Grid Hold | SUB | OSO | Low-Tariff Plan night plan |
| Reserve Protection | SUB | SNU | Daytime reserve recovery |
| Reserve Hold | SUB | OSO | Daytime reserve preservation |

The physical SUB+SNU and SUB+OSO combinations require persisted strategy context to distinguish Low-Tariff Plan from Reserve Protection after restart.

## Low-Tariff Planning

Low-Tariff Plan evaluates once at 23:50 and is authoritative over any active daytime Reserve Protection strategy.

### Preconditions

Low-Tariff Plan requires:

- Autopilot enabled;
- operating mode Solar, Unknown, Reserve Protection, or Reserve Hold;
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

Until the learned model is ready, Low-Tariff Plan continues to use the verified 1.3.1 ramp
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

The selected minimum is a Home Assistant helper from 20% to 95% in 5% steps. It applies only to Low-Tariff Plan; Reserve Protection keeps its Grid Reliability targets. Using the maximum avoids counting the pre-solar morning load twice.

### Decision

```text
if projected_soc_at_07 >= target_soc
    remain or restore Solar
else if current_soc >= target_soc
    enter Grid Hold
else
    enter Low-Tariff Charging
```

The conservative projected 07:00 SOC gates initial night-grid use. The target,
strategy context, and date through which the night plan is active are
persisted. At target, Low-Tariff Charging changes to Grid Hold.

### Continuous night enforcement

From the dated 23:50 evaluation until a confirmed non-Low-Tariff Plan Solar handover,
EnergyHub reevaluates the existing target on every fresh local telemetry
cycle. It does not recalculate or raise the target:

```text
Solar and SOC > target  → remain Solar
Solar and SOC = target  → Grid Hold
Solar and SOC < target  → Low-Tariff Charging
Grid Hold and SOC < target → resume Low-Tariff Charging
```

Stale or unavailable SOC and an absent grid produce no inverter request. The
date rejects a retained target from an older night after restart. A confirmed
guarded early-Solar handover clears the active night context. At 07:00, Reserve Protection
evaluates the current Hybrid owner and takes daytime ownership; the context
clears when a later confirmed Solar transition occurs or the next Low-Tariff Plan
evaluation replaces it.

### Early Solar handover

Home Assistant publishes the current-day Solcast energy forecast for the
06:00–07:00 interval once at 06:05. EnergyHub, not Home Assistant, applies the
control decision. It requests Solar only when all of these conditions hold:

- Autopilot is enabled and confirmed mode is Grid Hold;
- the request date is current and local time is inside 06:00–07:00;
- the persisted Low-Tariff Plan target exists and current SOC meets it;
- inverter telemetry and aligned Total Solar are fresh;
- the grid is currently present;
- live Total Solar is at least 300 W;
- the 06:00–07:00 forecast is at least 1.6 kWh, equivalent to the existing
  conservative 10%-of-16-kWh hourly bridge allowance.

Any failed, missing, stale, or unsupported condition leaves the inverter in
Grid Hold. Low-Tariff Charging is never released by this check. The ordinary
07:00 Reserve Protection ownership evaluation remains authoritative fallback behavior. The transition
result is confirmed through the existing Inverter Controller and remains
observable if confirmation fails.

![Continuous Battery Reserve](../Images/battery-reserve-current.png)

## Low-Tariff Plan morning debt

At the first Reserve Protection evaluation after 07:00, EnergyHub compares actual SOC with the persisted Low-Tariff Plan target.

```text
if actual_soc < ahm_target
    ahm_debt = ahm_target
else
    ahm_debt = none
```

The debt is persisted by date so a midday add-on restart cannot manufacture a new debt after normal battery use. It is cleared after the target has been recovered.

## Conservative Reserve Protection

Reserve Protection is deliberately simpler and more conservative than Low-Tariff Plan.

### Grid Reliability target

| Existing Grid Reliability state | Reserve Protection target |
|---|---:|
| normal | 20% |
| unstable | 60% |
| risk | 80% |
| panic | 95% |

```text
panic_target = max(Grid Reliability target, active Low-Tariff Plan debt)
```

### Evaluation

Reserve Protection evaluates every five minutes from 07:00 until 23:50, immediately after
grid transitions, and on the Home Assistant 07:00 ownership request.

It requires:

- Autopilot enabled;
- Solar, Low-Tariff Charging/Grid Hold at the daytime handoff, or Reserve Protection ownership;
- valid SOC and supported Grid Reliability;
- no inverter transition in progress.

Solar forecast and yesterday's consumption are not Reserve Protection gates.

### Normal-grid hysteresis

When Grid Reliability is Normal, the physical grid is present, and no missed
Low-Tariff Plan debt remains, Reserve Protection uses two thresholds:

```text
Solar and SOC <= 20%        → Reserve Hold
SOC < 20%                   → Reserve Protection until 20%
Reserve Hold, SOC < 30%  → remain Grid Hold
Reserve Hold, SOC >= 30% → Solar
```

The 20% floor and 30% release prevent rapid mode oscillation. Grid Hold uses
`SUB` + `OSO`, so the grid supports the house while solar-only charging can
raise SOC. Solar is not released while the physical grid is absent. A genuine
Low-Tariff Plan debt disables this Normal-grid release cycle until the debt is recovered.

### Offline waiting and recovery

```text
if SOC < target and grid offline
    enter/retain Reserve Protection strategy
    phase = waiting_for_grid

if SOC < target and grid online
    phase = charging

if SOC >= target and Grid Reliability is not Normal
    enter Reserve Hold
    preserve reserve until 23:50
```

SUB+SNU can be configured while external grid is absent. The inverter continues to use available solar/battery and begins grid charging when electricity returns. If SOC falls below target during Reserve Hold, Reserve Protection resumes.

See [current reserve ownership and limits](BATTERY_RESERVE_CURRENT.md).

## Ownership timeline

```text
06:05  If Grid Hold passes every early-Solar gate, restore Solar
07:00  Reserve Protection evaluates and takes daytime ownership; calculate any Low-Tariff Plan debt
07:00–23:50  Reserve Protection owns conservative daytime recovery
23:50  Low-Tariff Plan always takes ownership from Reserve Protection
23:50–07:00  Low-Tariff Plan charges or holds using cheap night electricity
```

## Heat-pump permission

Reserve guards never start heat pumps. Calculated Normal grid reliability keeps
heat pumps and boiler under family reserve authority. Instantaneous grid loss,
mode changes or telemetry transitions cannot alone revoke that authority.
Outside Normal, separate existing reserve guards may act on fresh evidence.
Manual auto-off timers remain independent. Peak Load Guard is observer-only.
See the [current load boundary](BATTERY_RESERVE_CURRENT.md#loads-and-monitoring).

## MQTT diagnostics

Low-Tariff Plan publishes its evaluated SOC, time, selected minimum, active morning model, learning progress, expected essential load, morning forecast solar, net deficit, 300 W threshold time and power, following-hour power, raw gap, independently validated ramp confirmation and credit, effective solar-support time and gap, post-07 consumption, post-07 solar, daytime deficit kWh/SOC, target, cap, and fallback state. The verbose legacy calculation string is not published. The early-Solar evaluator separately publishes its status, concise reason, evaluation time, live Total Solar, and 06:00–07:00 forecast energy.

Reserve Protection publishes its decision, reason, phase, effective target, Grid Reliability target, inherited Low-Tariff Plan target, and target source.

Decision values are retained for Home Assistant presentation. On EnergyHub
restart, the decision state becomes `awaiting_evaluation`; the reason states
whether a target was retained and that the detailed current-process plan is
unavailable until the next 23:50 evaluation. This avoids presenting a stale
night plan as newly calculated.

## Safety priority

`safe_solar` has queue priority when Autopilot is disabled. It cannot be overwritten by Low-Tariff Plan, Reserve Protection, or manual requests. Invalid or inconsistent inverter state remains observable and is not guessed from telemetry alone.
An unfinished persisted inverter transition is an exception: the controller
does not attempt automatic Solar recovery until attended verification.

## Morning reserve observation (legacy diagnostic)

This retained diagnostic is observational and never owns the inverter or
changes the additive Battery Reserve recommendation. Home Assistant records the
lowest SOC from 07:00 through 12:00 and the selected minimum for that morning.
Its historical comparison remains available for later validation and Smart
Heating development; Family Assistant suppresses its older competing advice.

The legacy comparison classified three comparable mornings as follows:

Home Assistant marks each morning observation valid only after a trustworthy 07:00 SOC initialization. Missing initialization or a Home Assistant restart before publication invalidates the morning, so partial or restored helper state cannot become recommendation evidence.

- increase when at least two mornings came within five SOC points of the selected reserve;
- decrease only when all three stayed at least 20 SOC points above the reserve;
- otherwise keep the current value.

Changing the slider starts a new comparable window while retained observations remain available. The named recommendation levels are 20, 30, 40, and 50%; custom 5% values move to the next named level in the recommended direction. The observation remains useful diagnostic evidence. Family Assistant suppresses
this older competing advice when the new reserve policy is available. Daytime
targets remain independent. This is not the three-day whole-house consumption
average used by the new observer.
