# EnergyHub positioning

## Main message

> EnergyHub helps your home make the most of solar energy and lower-cost
> electricity while keeping battery reserve for power outages. It combines
> solar-generation forecasts, weather warnings, household consumption and
> observed grid reliability to decide when to use, preserve or replenish the
> battery.

> It also coordinates selected appliances and heating, protects against
> inverter overload, and explains important decisions through Home Assistant
> dashboards and Telegram reports.

**Economy when conditions allow, preparedness when conditions demand it.**

This is a product aim, not a measured savings claim. The current reserve
controller can require grid charging outside cheap hours. It has one configured
night/normal tariff split for estimated accounting; optimized cheap-slot start
times and electricity export remain future work.

## Homeowner outcomes in the monitored 2.x candidate

| What EnergyHub does | What the homeowner gets |
| --- | --- |
| Combines solar forecast, recent consumption, official weather warnings and grid reliability into one Battery Reserve | Prepare for tomorrow and possible outages without manually interpreting every chart. |
| Offers Manual and guarded Automatic reserve authority | Keep the chosen battery floor or allow recommendations to be applied with evidence checks. |
| Coordinates Solar, Reserve Charging and Grid Hold | Use the available sources according to one understandable reserve policy. |
| Protects against overload and battery discharge during outages | Pause selected flexible appliances when capacity is limited, then restore only with verified conditions and ownership. |
| Integrates supported heat pumps and smart plugs through Home Assistant | Bring connected-home appliances into the energy policy while keeping family temperature and manual OFF choices. |
| Sends Telegram morning reports and important alerts | Read the energy outlook and power-loss/recovery notices in an existing messenger; no extra dedicated monitoring app is required. Home Assistant handles setup and dashboards. |
| Records inverter faults, SOC jumps, freshness and tariff estimates | Understand events and investigate suspicious readings instead of treating every graph as trustworthy. |

The difference to emphasize is coordination across the connected home:
inverter, battery, supported appliances, heating, weather and grid evidence
contribute to one local policy. AI is not part of the current control system.

## What comes next

- **Whole-house evidence and flexible heating (3.x):** validated CO/CO2 and BMS
  inputs, more useful device-health diagnosis, family-controlled and optional
  scheduled heating policies, and cold-weather observations.
- **AI companion and Mission Control (4.x):** an assistant that knows the
  installation, explains decisions, and requests validated settings, schedules
  and device actions. Telegram text in Ukrainian/English comes before voice.
- **Smart EV charging (5.x):** plan energy by departure time from solar and
  approved cheap-grid charging without exhausting the household reserve.
- **Tariff and optional export management (6.x):** multiple fixed cheap periods
  first, dynamic prices later, and contract-specific export/Net Billing only
  with verified export-capable equipment. The aim is to help reduce the monthly
  electricity bill, not promise a universal saving.
- **More installations:** separately verified inverter/device adapters and
  clear capability declarations for each home.

EV charging and tariff/export planning should be visible future benefits on the
public page. Version numbers and sensor implementation detail belong in the
roadmap, rather than the opening message.

## Evidence and scope

EnergyHub 2.4.12 and Family Assistant 2.4.15 were started on 2026-09-29. On
2026-10-01 the homeowner reported the agreed 24-hour monitoring period passed
with normal operation and no new Core/Supervisor errors. Repository regressions
cover the corrective paths; rare failures and extended cold-weather heating
are not all live-tested. Public promotion is prepared separately.

Current verified hardware scope is one PowMr 10.2M / POW-HVM10.2M PI30MAX
installation, with separate optional read-only PV2 Modbus. Household control
requires a mapped, validated Home Assistant bridge. Local operation does not
make forecasts or Telegram independent of their external services.

Do not claim:

- prevention of an external grid outage or guaranteed uninterrupted power;
- measured savings, billing-grade grid import, or dynamic tariff optimization;
- universal inverter compatibility, current EV/export control, or current AI;
- zero grid use for heating from PV/strategy permission alone;
- complete field validation from passing repository tests or routine monitoring.

Competitor comparisons with Tesla Powerwall, SolarAssistant or
Sandisolar/EcoCloud require current primary-source research before publishing
claims. Describe EnergyHub's own capabilities directly until that research is
done. Keep private household diaries, audit inventories and the separate
Threat Monitor outside public EnergyHub promotion.
