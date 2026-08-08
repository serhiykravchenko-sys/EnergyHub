# EnergyHub Design Philosophy

## Human first

EnergyHub is built for a household, not only for an engineer. The family-facing interface should present:

- current strategy;
- battery reserve;
- grid availability;
- important decisions;
- simple controls.

Technical details remain available in deeper views and logs.

## Reduce cognitive load

The objective is not to expose every inverter parameter. It is to remove repetitive decisions:

```text
Should I charge tonight?
Should I preserve the battery?
Should I build reserve before an outage?
```

EnergyHub should answer these automatically and explain the result.

## Calm technology

Normal operation should be quiet. Notifications are reserved for meaningful transitions, failures, or conditions that require attention.

A successful automatic transition is reported only after the Inverter Controller confirms it. A failed transition produces a failure notification rather than a false activation message.

## Default to Solar

Solar is the normal strategy and the safe recovery target. Automatic strategies are temporary deviations with explicit targets and exits.

## Explainable decisions

A decision should include:

- input values used;
- rule or comparison applied;
- selected target;
- resulting request;
- transition result.

The dashboard displays concise explanations. Logs preserve technical detail.

## Separate decision from execution

Decision services answer **what should happen**.

The Inverter Controller answers **how to change the hardware safely**.

This boundary prevents policy code from writing inverter settings directly and makes future hardware adapters possible.

## Honest certainty

EnergyHub distinguishes between:

- measured telemetry;
- calculated state;
- estimated energy;
- read-back verified settings;
- ACK-confirmed but unreadable settings;
- remembered context.

Examples:

- Menu 01 is independently read back through QPIRI.
- Menu 16 is ACK-confirmed and persisted because the inverter has no supported read-back command.
- Grid Import is estimated and not billing-grade.

## Local first

Core telemetry, decisions, persistence, and inverter control run locally. Solcast is an external forecast input, not the owner of strategy execution.

## Safe and bounded recovery

EnergyHub prefers one understandable recovery action over indefinite retries.

- writes have bounded retries;
- partial Hybrid/Panic failures attempt Solar recovery;
- Grid Hold failure attempts one Solar recovery;
- safe Solar queue requests cannot be overwritten by ordinary requests;
- the inverter is never restarted automatically.

## Progressive automation

A feature should move through clear stages:

1. observe;
2. display;
3. recommend;
4. automate with explicit permission;
5. verify and explain;
6. generalize only after real-system evidence.

The experimental Away Mode was removed because it encoded one narrow use case. The broader future feature is Smart Thermal Energy: convert surplus solar or cheap-tariff electricity into heating or cooling, independent of occupancy.

## No fake controls

A planned feature may appear as a labelled future card, but an active switch must not exist before a real service owns the action.

## Preserve manual control

Autopilot controls automatic inverter strategy changes. Turning it off returns active or unknown automatic strategies to Solar once, then stops automatic changes.

Manual household controls, such as heat-pump smart plugs, remain available.

## Ownership for flexible loads

Future flexible-load services must stop a device only when EnergyHub started it. This protects manual household actions from automation cleanup.

## Progressive disclosure

EnergyHub uses two levels of communication:

### Family layer

- simple Autopilot infographic;
- current strategy;
- main charts;
- grid online/offline;
- floor comfort controls.

### Technical layer

- architecture infographic;
- health reasons;
- decision inputs;
- MQTT state;
- persistence;
- transition and recovery logs.

## Design goal

```text
Simple outside
Explicit inside
Safe at the hardware boundary
```
