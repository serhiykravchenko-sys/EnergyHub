# EnergyHub Project Positioning

## Current message

> **Adaptive solar planning. Smart tariff use. Outage-ready reserve.**

EnergyHub is a local-first, resilience-aware Home Assistant energy controller for the PowMr 10.2M / POW-HVM10.2M hybrid inverter. It combines tomorrow's hourly solar forecast, expected household demand, battery state, a configured cheap-tariff window, and observed grid reliability to plan economical charging and maintain an adaptive reserve.

EnergyHub 1.3 is validated for one reference hardware and installation architecture. It should not yet claim generic Voltronic, multi-vendor, dynamic-price, Net Billing, automatic EV charging, or full HEMS support.

## Product pillars

### Adaptive solar planning

Adaptive Hybrid Mode uses tomorrow's hourly forecast rather than only a daily total. It aligns expected post-07:00 consumption and solar, applies an independently verified solar-ramp credit to the morning gap, and combines that need with a user-selected 20–50% minimum reserve.

The homeowner chooses the protective reserve. EnergyHub learns the household's essential 07:00–12:00 net energy, then recommends the next safer or more economical setting from comparable completed mornings. It shows the evidence but never changes the preference automatically.

### Smart tariff use

EnergyHub 1.3 uses one configured cheap-tariff window. The durable product concept is a tariff schedule containing one or more eligible periods. Future releases may ingest day-ahead import/export prices and Net Billing rules.

### Outage-ready reserve

Grid Confidence summarizes observed 24-hour and 48-hour availability. Conservative Panic maps that evidence to reserve targets, can remain armed while grid is absent, charges when grid returns, and preserves recovered reserve in Panic Grid Hold.

Grid Confidence does not predict a specific outage, and EnergyHub cannot guarantee uninterrupted power or a reachable target when energy is unavailable.

### Explainable, owned execution

Each strategy transition has one controller owner, a target, a reason, and an observable result. Menu 01 is independently read back. Menu 16 is ACK-confirmed but cannot be independently read back on the reference inverter. Persisted context supports restart reconstruction without guessing from clock time alone.

## Target users

- Home Assistant users with residential solar, battery storage, and hybrid inverters;
- PowMr 10.2M owners who need more than telemetry and isolated YAML rules;
- households with fixed cheap tariffs or future multi-period/day-ahead pricing;
- households in regions where grid availability is not consistently trustworthy;
- advanced users who want visible decisions and bounded local control.

## Why not only Home Assistant automations?

Home Assistant remains the UI, schedule, integration, and notification layer. EnergyHub owns long-lived decision and hardware-transition state that is difficult to reproduce safely as independent automations:

- rolling grid history and Grid Confidence;
- coordinated AHM/Panic ownership;
- adaptive target and morning-debt persistence;
- one writer for inverter transitions;
- transition sequencing and partial-failure recovery;
- restart reconstruction;
- hardware-specific read-back and acknowledgement boundaries.

Future voice or messenger control should submit a time-bounded request to EnergyHub. A conversational assistant must not decide safety. The deterministic override evaluator may allow, shorten, delay, or deny the request according to fresh telemetry, projected reserve, grid availability, load energy, and immutable emergency limits.

The optional Telegram Family Assistant already provides outbound morning plans, grid events, Grid Confidence changes, and AHM reserve advice. This is a useful product surface and a foundation for future interaction, but the current version does not receive or execute commands. Future Telegram text/voice and Home Assistant Assist adapters must translate input into the same authenticated, expiring, auditable intent contract before EnergyHub evaluates it.

## Evidence for public claims

Public releases should provide:

- an AHM calculation example;
- the AHM/Panic ownership timeline;
- a Grid Confidence/Panic flowchart;
- a visible decision-dashboard example;
- Menu 01 read-back versus Menu 16 ACK documentation;
- restart-reconstruction and partial-failure tests;
- sanitized supervised validation results;
- a supported-hardware and firmware matrix;
- known limitations and explicit non-goals.

## Future direction

> EnergyHub should become a capability-based home energy planner that coordinates import, export, storage, EV charging, and flexible loads using forecasts, real prices, and observed grid reliability while preserving local execution, explainability, and bounded hardware control.

Future capability must be introduced progressively through monitoring, shadow planning, attended validation, and only then bounded automatic control.
