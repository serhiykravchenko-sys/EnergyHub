# EnergyHub House Model

## Overview

The current EnergyHub installation manages a three-floor country house. The model separates physical assets and capabilities from decision policy.

```text
House Model = assets + sensors + controllable loads + capabilities
Decision Policy = rules for using those capabilities
```

## Energy assets

### Solar PV

- LONGi Hi-MO X10 LR7-54HVH-490M panels;
- Field 1: 7 × 490 W = 3.43 kWp, tilt 35°;
- Field 2: 8 × 490 W = 3.92 kWp, tilt 65°;
- approximate azimuth: 130°;
- modeled total of the two documented fields: 7.35 kWp;
- PI30MAX exposes reliable PV1 telemetry only;
- Solcast supplies whole-system Today and Tomorrow forecasts.

### Inverter

- PowMr 10.2M;
- PI30MAX;
- USB-RS232;
- Menu 01 and Menu 16 strategy control.

### Battery

- LiFePO4;
- 16 kWh nominal capacity;
- primary reserve and time-shifting buffer.

### Grid

- utility connection;
- cheap night tariff;
- voltage stabilizer before the inverter;
- inverter normally sees approximately 220 V when the grid exists and 0 V when absent;
- planned and unexpected outages are possible;
- historical availability contributes to Grid Confidence.

## Building and comfort

### Basement

- inverter and energy equipment;
- water system;
- basement water pump connected through the Xiaomi device named `Basement Water Smart Power`;
- 40 L electric boiler;
- boiler heating from approximately 10°C to 70°C requires roughly 3 kWh and is a future flexible-load candidate.

The boiler is connected through an existing Xiaomi device named `2nd floor water Boiler Smart Power`; confirm whether that name reflects its physical location before changing the house model. The verified dashboard entities are:

| Capability | Boiler | Basement pump |
|---|---|---|
| Switch | `switch.chuangmi_212a01_c91f_switch` | `switch.chuangmi_212a01_ac48_switch` |
| Live power | `sensor.chuangmi_212a01_c91f_electric_power` | `sensor.chuangmi_212a01_ac48_electric_power` |
| Energy today | `sensor.chuangmi_212a01_c91f_power_cost_today` | `sensor.chuangmi_212a01_ac48_power_cost_today` |
| Energy month | `sensor.chuangmi_212a01_c91f_power_cost_month` | `sensor.chuangmi_212a01_ac48_power_cost_month` |
| Current | `sensor.chuangmi_212a01_c91f_electric_current` | `sensor.chuangmi_212a01_ac48_electric_current` |
| Plug temperature | `sensor.chuangmi_212a01_c91f_temperature` | `sensor.chuangmi_212a01_ac48_temperature` |

Availability is represented by these entities becoming `unavailable`; there is no separate verified availability sensor. Boiler/plug ratings, pump/motor ratings and starting surge, power-outage behavior, and load suitability must be recorded before unattended switching. The pump remains a critical non-sheddable load unless a later explicit safety review changes that classification.

### 1st Floor

| Capability | Entity |
|---|---|
| Temperature | `sensor.miaomiaoce_t2_e515_temperature` |
| Humidity | `sensor.miaomiaoce_t2_e515_relative_humidity` |
| Heat-pump plug | `switch.first_floor_heat_pump_plug` |
| Heat-pump power | `sensor.first_floor_heat_pump_plug_power` |
| Auto-off duration | `input_number.input_number_floor1_heat_pump_timer_hours` |
| Remaining time | `timer.floor_1_heat_pump_auto_off` |

### 2nd Floor · Kids Room

| Capability | Entity |
|---|---|
| Temperature | `sensor.miaomiaoce_t2_1bf2_temperature` |
| Humidity | `sensor.miaomiaoce_t2_1bf2_relative_humidity` |
| Heat-pump plug | `switch.second_floor_heat_pump_plug` |
| Heat-pump power | `sensor.second_floor_heat_pump_plug_power` |
| Auto-off duration | `input_number.input_number_floor2_heat_pump_timer_hours` |
| Remaining time | `timer.floor_2_heat_pump_auto_off` |

### 3rd Floor

| Capability | Entity |
|---|---|
| Temperature | `sensor.lumi_weather_v1_b318_temperature` |
| Humidity | `sensor.lumi_weather_v1_b318_relative_humidity` |
| Heat-pump plug | `switch.chuangmi_212a01_ea40_switch` |
| Heat-pump power | `sensor.chuangmi_212a01_ea40_electric_power` |
| Auto-off duration | `input_number.input_number_floor3_heat_pump_timer_hours` |
| Remaining time | `timer.floor_3_heat_pump_auto_off` |

All three floors use the same Home Assistant auto-off behavior. Duration `0 h` means manual mode: cancel the countdown but leave the heat pump in its current state. When a non-zero duration expires, HA switches the corresponding plug off and resets the duration to zero. Switching a plug off also cancels its timer and resets its duration.

## Current EnergyHub-controlled capability

In 1.0 EnergyHub directly controls only inverter strategy. Heat-pump controls shown on the dashboard are Home Assistant household controls, not EnergyHub automatic strategy outputs.

EnergyHub 1.1 implements reserve-only OFF protection in Home Assistant. The boiler is requested OFF once at 50%, may be manually or motion-restored from 41–50%, locks OFF at 40%, and unlocks at 60%. Heat pumps use a fully trusted-grid policy of all-floor OFF/lock at 50% and unlock at 60%. Every degraded or unknown grid state uses the conservative policy: all floors OFF once at 80%, floor 2 again at 70%, floor 1 at 60%, and floor 3 plus every floor OFF/locked at 50%, with unlock at 90%. No recovery threshold turns a load on. The basement pump is never shed.

Confirmed Hybrid Charging or Hybrid Grid Hold with fresh telemetry and currently present grid power temporarily permits manual heat-pump requests. The SOC latch remains remembered underneath and is re-enforced when that permission ends. This permission never starts a heat pump and does not introduce Smart Thermal ownership.

## Current strategies

### Solar

```text
Menu 01 = SBU
Menu 16 = OSO
```

### Hybrid Charging

```text
Menu 01 = SUB
Menu 16 = SNU
Target SOC = adaptive 30-95%
```

At 23:50, Adaptive Night Hybrid projects SOC at 07:00 using a conservative
15-point overnight allowance. It finds the first tomorrow Solcast hourly
estimate at or above 300 W and adds 10 SOC points for each hour from 07:00
to that useful-solar time. The target is a 20% protected reserve plus that
morning gap plus a 10% forecast/ramp margin, capped at 95%.

If projected SOC already covers the target, EnergyHub remains in Solar. If
current SOC covers the target but the projection does not, it enters Hybrid
Grid Hold immediately. Otherwise it enters Hybrid Charging immediately and
changes to Grid Hold when the adaptive target is reached.

### Hybrid Grid Hold

```text
Menu 01 = SUB
Menu 16 = OSO
Exit = 07:00 Solar request
```

### Panic

```text
Menu 01 = SUB
Menu 16 = SNU
Target SOC = 80% or 95%
```

## Removed experimental capability

The old Away Mode first-floor heat-pump automation and helpers are not part of 1.0. They were removed because energy-to-comfort optimization should not depend on occupancy. The current per-floor auto-off timers are manual Home Assistant household controls, not a revival of Away Mode or automatic EnergyHub load policy.

## Future Smart Thermal Energy

EnergyHub 1.5 introduces the first automatic Smart Thermal controller. EnergyHub 1.1 provides device, dashboard, measurement, and reserve-protection groundwork only.

Smart Thermal will model thermal loads as capabilities:

- controllable plug;
- measured or expected power;
- room temperature/humidity;
- heating/cooling role;
- comfort band;
- minimum runtime and cooldown;
- ownership state;
- load priority.

It may use:

- surplus solar;
- cheap night electricity;
- battery reserve;
- forecast;
- Grid Confidence;
- seasonal comfort goals.

## Flexible-load candidates

- 1st-floor heat pump;
- future 2nd-floor heat pump plug;
- 3rd-floor heat pump;
- electric boiler;
- future EV charger.

## Measurements

### Measured

- grid voltage/frequency;
- output power/load;
- battery SOC/voltage/current;
- PV1 power/voltage/current;
- inverter temperature;
- floor temperatures/humidity;
- selected smart-plug power.

### Derived

- grid availability and history;
- Grid Confidence;
- Daily Summary;
- estimated solar surplus;
- estimated Grid Import;
- health states;
- operating strategy and decision reason.

## Model principle

Physical assets change slowly. Policies change more quickly. Device entities should be mapped into stable capabilities, while strategy rules remain replaceable and configurable.
