# Home Assistant Configuration

This directory contains the versioned Home Assistant part of EnergyHub.

For full behavior, see [`docs/operations/12-HomeAssistant-Configuration.md`](../docs/operations/12-HomeAssistant-Configuration.md).

## Directory structure

```text
homeassistant/
  live/
    config/
      configuration.yaml
      automations.yaml
      scripts.yaml
      scenes.yaml
    storage/
      input_boolean
      input_number
      timer
      lovelace.dashboard_powmr1
      lovelace_dashboards
      lovelace_resources
```

## What is versioned

- EnergyHub YAML automations and scripts;
- selected helpers;
- the EnergyHub dashboard;
- required dashboard resources.

## What is not versioned

- secrets;
- entity registry exports;
- recorder database;
- tokens;
- unrelated `.storage` state;
- temporary backups.

## Current HA-owned functions

- Autopilot helper;
- Adaptive Night Hybrid schedule at 23:50 and Solar restoration at 07:00;
- live Solcast publication, including the first tomorrow hourly forecast at
  or above 300 W for the adaptive morning-gap target;
- atomic Daily Summary publication;
- manual Panic script;
- transition notifications;
- beacon;
- first-, second-, and third-floor heat-pump auto-off controls;
- a compact Heat Pumps view with switch, live power, 0–12 h auto-off, absolute turn-off time, and consumption history for all three floors;
- a compact Mission Control view without duplicated floor cards;
- separate Heat Pumps and Water Systems views for compact manual control and daily/weekly/monthly locally recorded consumption history.
- temporary manual heat-pump permission during confirmed grid-backed Hybrid; it never starts a heat pump and preserves the remembered SOC lockout underneath.

## Current EnergyHub-owned functions

- telemetry and health;
- history and Grid Confidence;
- Hybrid/Panic decisions;
- inverter transitions and verification;
- Grid Import and Daily Summary persistence;
- restart reconstruction;
- MQTT state;
- reserve-only OFF guards for the boiler and heat pumps, with no automatic starts.

## Synchronize live HA to Git

```powershell
.\tools\dev\sync-from-ha.ps1
```

Review all changes before committing. Do not commit `core.entity_registry` or CSV exports created for audits.

## Deploy Git to HA

The deployment entry point supports separate scopes. Its default remains the historical add-on-only workflow:

```powershell
.\tools\dev\deploy-to-ha.ps1
```

This mirrors `addon/` only. Rebuild and restart the local Energy Hub add-on, then inspect its logs.

Deploy selected Home Assistant YAML while HA Core is running:

```powershell
.\tools\dev\deploy-to-ha.ps1 `
    -Scope HomeAssistant `
    -ConfigFiles automations.yaml
```

Reload only Automations afterward. Use the matching YAML reload for scripts or scenes; a `configuration.yaml` change requires a configuration check and HA Core restart.

Deploy YAML plus selected `.storage` objects:

```powershell
.\tools\dev\deploy-to-ha.ps1 `
    -Scope HomeAssistant `
    -ConfigFiles automations.yaml `
    -StorageFiles input_number,timer,lovelace.dashboard_powmr1 `
    -HomeAssistantStopped
```

HA Core must already be stopped. The script backs up every replaced target under `\\homeassistant\config\energyhub-deploy-backups\<timestamp>`. After the copy, run `ha core check`, start HA Core, and inspect the logs. Startup loads both YAML and `.storage`, so no separate YAML reload is needed.

Preview either workflow without contacting or changing Home Assistant by adding `-DryRun`.

`sync-to-ha.ps1` remains the proven lower-level add-on mirror used by the add-on deployment scope. Prefer `deploy-to-ha.ps1` as the normal entry point because it selects the correct workflow and prints the required rebuild, restart, or reload actions.

## Editing safety

- Edit dashboards/helpers through HA UI where possible.
- Do not overwrite live `.storage` files while HA is running.
- `-HomeAssistantStopped` is an explicit operator assertion; the script cannot stop or verify HA Core remotely.
- Replace YAML files as complete files, then reload automations/scripts.
- A conditional dashboard card displays all branches in edit mode; test the final view outside edit mode.

## Current dashboard dependencies

- ApexCharts Card custom resource;
- MQTT integration;
- Solcast entities;
- listed room sensors and smart plugs.

## Security

The repository must not contain real passwords or tokens. Published add-on defaults still require hardening before external release.
