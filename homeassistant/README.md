# Home Assistant integration examples

EnergyHub 2.4.12 / Family Assistant 2.4.15 use Home Assistant for household
inputs, device service calls, acknowledgements, helpers and dashboards.
These files are reference examples, not a drop-in configuration for every home.

## Installation boundary

Back up your installation. Merge the required helpers and automations instead
of replacing your complete configuration. Map every entity to your actual
device and test its availability and service behavior before enabling control.
The example load roles are water pump, water boiler, first-floor native heat
pump, second-/third-floor heat pumps and microwave. Battery protection excludes
the microwave; overload protection has a separate ordered list. Never map an
essential, medical or safety-critical load to a controllable role.

Family Assistant's optional environment-sensor and smart-plug lists are empty
by default in the public manifest. Populate them with your own entity IDs.
Generic aliases in this directory and tests are examples, not discovered devices.

## Responsibilities

- EnergyHub evaluates reserve, grid, overload and heating policies and requests
  structured actions. It owns inverter control and load ownership.
- Home Assistant supplies fresh inputs and executes supported device actions.
  Acknowledgements and fresh snapshots are required; a sent request is not
  proof that a device switched.
- Family Assistant sends Ukrainian reports and alerts. It does not control
  Home Assistant, plugs or the inverter.

Keep load control off until attended checks pass: family manual OFF, missing
devices, stale snapshots, timers, shedding and owned-load restoration.
Three family heat-pump auto-off timers retain the selected hours across a
protective OFF; a later ON starts that full duration again, rather than preserving
the original wall-clock deadline. Smart Heating
preserves family temperature and fan choices, using quiet mode at night
(23:00–08:00) and Eco when supported on battery.

## Configuration changes

After merging YAML, run `ha core check` and perform the appropriate YAML reload
or configuration restart. Stop Core before replacing any `.storage` file;
do not copy another home's storage files indiscriminately. An app-only update
does not require a Core stop/start.

See [installation](../docs/operations/INSTALLATION.md),
[HA configuration](../docs/operations/12-HomeAssistant-Configuration.md),
[reserve policy](../docs/design/BATTERY_RESERVE_CURRENT.md), and
[release evidence](../docs/validation/RELEASE_2.4.12.md).
