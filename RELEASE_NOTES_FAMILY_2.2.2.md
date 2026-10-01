# Family Assistant 2.2.2 and dashboard correction

- Notify stable Autopilot ON/OFF changes in short Ukrainian text.
- Notify overload OFF, ON-but-not-ready, and readiness for eligible devices.
- Require fresh controller snapshot, acknowledgement of requested mode, no fault,
  and at least one eligible device before saying automatic protection is enabled.
- Silent first observation, persisted deduplication, ten-second stable transitions,
  latest queued state per control and revalidation before delivery. Very brief
  toggles between polls are intentionally not an audit trail. Messages can also
  reflect startup disarming; they do not claim who operated a switch.
- Remove the Build Emergency Reserve dashboard button; retain scripts, internal
  emergency logic, entity IDs, manual reserve +/-5% and Battery Reserve Auto.

EH remains 2.2.1. Only Family app and dashboard need deployment. No hardware
control, thresholds, reserve calculations, automations or Threat Monitor changes.
