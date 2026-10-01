# EnergyHub 2.1.2 / Family Assistant 2.1.5 — Manual Reserve Ownership

Private corrective release, 2026-09-06. No automatic reserve controller is enabled.

## Behavior

- One family-owned Battery Reserve setting, 20–95% in five-point steps. The HA
  helper, MQTT input validation and existing Hybrid planner accept that range.
  Changing the helper is not an immediate charge command: the existing strategy
  and its evaluation schedule still govern inverter actions.
- Remove the separate baseline helper and dashboard slider. The observer's
  calculation uses the original fixed 20% policy base, never a manually selected
  override. Its numeric calculated target remains diagnostic, not a manual-mode
  instruction to apply or restore a setting.
- Manual and Advisory/Dry Run both leave ownership with the family. They observe
  weather, grid and forecast conditions. Ukrainian messages describe allowances
  (+20 percentage points, etc.), not repeated additions to a user's chosen value.
- Manual 60% stays 60% through warning expiry/restart. No expiry-based restoration
  command or recommendation replaces that value. Old queued reserve restoration
  notifications are discarded when the new policy is observed.
- Daytime messages are deduplicated by conditions, not manual slider changes.
  Quiet-hour changes are included in the morning report. Existing 05:00 forecast
  capture and incomplete-data safeguards remain in place.
- The old morning evidence collector remains; its competing dashboard advice is
  replaced with an observation-only explanation. Peak Load Guard stays 40/30/20
  Dry Run. Threat Monitor is outside scope.

## Future Automatic contract (not implemented or enabled)

Auto to Manual preserves the applied reserve and transfers ownership to the
family. Manual to Auto explicitly transfers ownership to EnergyHub and applies
its validated calculated target, not the manual override. Activation and reserve
reductions require fresh valid evidence. The actual controller, acknowledgement,
restart ownership and rollback need a separately tested release; the current
Auto indicator remains locked OFF with no command path.

## Deployment scope and checks

Synchronize both app trees and four HA artifacts: `configuration.yaml`,
`automations.yaml`, `.storage/input_number`, `.storage/lovelace.dashboard_powmr1`.
Back up outside the scanned app tree. Homeowner must stop Core before storage
copy, run `ha core check`, start Core and use App-store Reload/Update.

Validate version banners 2.1.2 / 2.1.5, single manual control, unchanged selected
reserve, Auto OFF, fresh participant/weather evidence and condition-only messages.
The earlier 0/3 consumption-history evidence issue is not repaired or hidden by
this release. No history is fabricated or backfilled. No commit/push/publication
is authorized.
