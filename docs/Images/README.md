# Current visual specification

Start with [the illustrated family guide](family/README.md). The owner-selected
lead picture is [A battery reserve, plus a plan](family/family-battery-and-charging.png).

These eight technical pairs describe the current **monolithic 3.6.37 snapshot**,
not a Core/Custom split. Each PNG has an editable SVG with the same basename.

| Topic | Image |
| --- | --- |
| System and component responsibilities | [Architecture](system-architecture-current.png) |
| Distinct EH, HA and human authorities | [Control boundaries](control-boundaries-current.png) |
| Reserve formula and application | [Battery Reserve](battery-reserve-current.png) |
| Night and scheduled-outage targets | [Charging preparation](charging-planning-current.png) |
| Native group OFF and ordered recovery | [Overload](overload-protection-current.png) |
| Four-plug 40/50 and separate fridge 20/30 | [Outage preservation](outage-preservation-current.png) |
| EH/HA supported HP1 management | [Heating](smart-heating-load-protection.png) |
| Freshness, persistence and message meaning | [Evidence](telemetry-resilience-current.png) |

Illustrations were checked against the current runtime, native HA packages and
regressions. In particular: overload is no longer Python shed-to-75%; reserve
has no forecast-deficit/Smart Heating +20 term; native plug restoration is not
a universal family-OFF guarantee; native notices are not physical ACKs.

Edit the SVG before rendering its PNG. The family images are generated raster
illustrations with [saved prompts](family/PROMPTS.md), not SVGs. Historical review
images and private generators/audit inventories are excluded. See the public
[release evidence](../validation/RELEASE_3.6.37.md) for field-validation limits.
