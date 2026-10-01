# EnergyHub visual specification

The current system should be understandable from these five diagrams:

1. [System Architecture](system-architecture-current.png) — physical inputs,
   local core, guarded execution, Home Assistant, Telegram, and future Mission
   Control.
2. [Control Ownership and Safety Boundaries](control-boundaries-current.png) —
   authority order and the separate inverter, household-load, and native-climate
   execution paths.
3. [Battery Reserve](battery-reserve-current.png) — manual/automatic authority,
   recommendation inputs, and continuous inverter behavior.
4. [Smart Heating and Load Protection](smart-heating-load-protection.png) —
   overload, outage-battery, Smart Heating, and family/manual behavior.
5. [Telemetry, Memory and Recovery](telemetry-resilience-current.png) — validated
   acquisition, derived evidence, persistence, diagnostics, and conservative
   failure handling.

Every current PNG has a matching editable SVG source. Update the SVG first and
render the PNG for GitHub/documentation use.

Superseded diagrams are excluded from this public release. These five diagrams describe the current operating contract.
