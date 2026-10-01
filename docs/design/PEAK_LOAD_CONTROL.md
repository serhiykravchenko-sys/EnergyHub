# Acknowledged overload control — current 2.4.9 candidate

## 2.4.9 availability and acknowledgement correction

Online availability, reported state, power validity and measurement age are
separate evidence. An unchanged numeric 0/1 W value does not make an online
plug unavailable, while a missing availability field fails closed. A command
is confirmed only by the accepted executor
acknowledgement, matching command context, a bridge snapshot newer than the
command and a target switch/climate observation newer than the command. A fresh
contradictory power reading vetoes OFF confirmation; an old unchanged power
sample is diagnostic and cannot veto a fresh state transition.

The controller retains the episode trigger percentage/reason and the
post-action load separately. Passive first-floor integration attribute refreshes
do not release ownership. Explicit external service intent, a conflicting
state, or an intent revision still releases ownership so EnergyHub never fights
the family or another automation.

## 2.4.2 per-device uncertainty correction

An unavailable, rejected, timed-out, or restart-ambiguous participant is now
blocked only for that participant and protection cycle. The controller continues
with other eligible loads. Ambiguous outcomes never create ownership. During
recovery, only confirmed EnergyHub-owned OFF states are considered; an
unavailable owner remains recorded for later recovery without preventing other
eligible owners from restoring. Fatal persistence corruption or write failure
continues to fail closed globally. This section supersedes the older global-lock
wording below.

## Superseding schema-4 candidate — 2026-09-09

[EH 2.2.5](../../RELEASE_NOTES_2.2.5.md) shares this journal with battery-load
protection. The overload toggle still controls overload actions only; battery
protection remains independent. Both use the same single in-flight command and
owned-state restoration. The older confidence-only restore gate is replaced by
actual grid/battery recovery permission. Existing overload timing remains intact.
Native OFF is preset-independent; restoration requires original settings to be
verified, otherwise it pauses/notifies. Smart Heating remains offline.

Status: prepared locally, NOT deployed or live-validated. This supplements the
inverter's hardware protection; polling cannot guarantee protection against
instantaneous overload, motor starting current, or loss of HA/MQTT.

## Plan and scope

1. Use one controller with automatic or warnings-only operation at 85/75/50.
2. Add an allow-listed HA executor and ownership evidence.
3. Test failure/restart/manual-intervention paths and update Family messages.
4. Synchronize only after separate deployment approval and source comparison.
5. Validate attended behavior before enabling unattended automatic control.

Battery Reserve calculation, its automatic-control lock, inverter settings,
existing reserve safety automations and Threat Monitor are not changed here.

## Gates and sequence

The HA helper `input_boolean.energyhub_load_control_armed` is the single user
mode control: OFF sends warnings only; ON requests automatic control. Device,
telemetry and ownership checks still apply. Core startup disarms the bridge and
creates a new session. The old app flag no longer selects a mode; it is accepted
only as optional saved-options compatibility. Old schema-1/2 snapshots cannot arm
the corrected runtime: the updated schema-3 HA bridge and command are required.
Live participant observations use `energyhub/input/ha/peak_load_control_plugs`;
the historical Dry Run journal/topic is not consumed by the new runtime.

OFF warnings start at 85% (or an explicit inverter overload warning) and clear
below 50% for five minutes. They require fresh inverter readings, not participant
availability. They never claim a device was switched or restored. Retained and
queued trial recommendations are suppressed by Family 2.2.1. ON supersedes a
warning episode without inventing a recovery event. Existing ownership survives
OFF; in-flight acknowledgement/family intervention is still observed.

At native inverter load >=85%, begin one-at-a-time shedding, stopping at <=75%.
The inverter overload flag may also initiate evaluation, but the executor still
requires measured load >75%; a rejected/unconfirmed command requires attention.
Wait for load strictly below 50% for 300 continuous seconds before restoration.
Restore one device, confirm a fresh target-state transition, then wait at least 60 seconds
before the next restoration. Keep observing: any sample >=50%, stale data, or
sample gap over 30 seconds resets the five-minute qualification. A new >=85%
overload can interrupt settling and resume shedding; 50–84.9% after restoration
pauses the next restoration, rather than starting another shedding episode.
Minimum off times and existing reserve permission still apply. These checks take time:
this is not a fast protective relay or a guarantee that the inverter cannot trip.

Order in both directions: water pump, boiler, first-floor heat pump via native
climate control, second-floor heat-pump plug, third-floor heat-pump plug, microwave.
Zero-watt ON loads remain eligible; already-OFF loads are not owned or restored.

## Command and ownership boundary

EH publishes non-retained QoS 0 structured intents, expiring after 20 seconds,
to `energyhub/control/peak_load_guard`. HA maps six fixed keys to local entities;
it accepts no arbitrary target/service from a message. It independently checks
arming, session, expiry, current load age, original state/context, manual-intent
revision and schema. Restore load <50% is checked again by HA immediately before
execution. No mandatory watt allowance or projected surge claim is made.
No raw inverter command or new EH Home Assistant API permission is introduced.
This is not an authentication boundary against a compromised MQTT broker/client.

The separate `/data/energyhub_peak_load_control.json` journal writes intent before
publication. Old Dry Run recommendations are never interpreted as ownership.
An acknowledgement alone is not confirmation: a subsequent target-state
observation with matching context is required. Fresh post-command power above
100 W contradicts and vetoes OFF confirmation; old unchanged watts are not used
as a false failure. This remains limited telemetry evidence, not proof of
mechanical compressor state. Validate actual appliance behavior in the attended
gate.

HA service-call intent revisions catch even OFF while already OFF. Changed state,
context or explicit intent revision releases EH ownership; passive native
attribute refreshes do not. EH does not fight the family. Out-of-band app/remote changes can only be detected when the
integration reports them; a same-state remote action may be unobservable.
If queue pressure evicts a service intent for a pending or owned load, that
participant is quarantined or released immediately; the remaining loads are
not disabled by an unrelated burst.

Pending commands are never retried on timeout/restart. Uncertain outcomes lock
the controller for manual investigation. Confirmed ownership survives app restart;
fresh matching evidence and an armed HA bridge are still required. Core restart
disarms. A manual ownership release blocks the affected cycle, requiring review.
Corrupt/unwritable journals fail closed. Faults are persisted when storage permits.

## Restoration policy and native HP limits

The unused `input_number.energyhub_restart_<key>_watts` compatibility helpers
were removed; schema-5 restoration uses observed live power and device-specific
timing instead. Zero allowances no longer block shedding or restoration. Fresh numeric
zero load is valid; missing/invalid power is not treated as zero. This is an
observed-load, sequential policy, not a verified surge model. A five-minute quiet
period is not proof that a stove will not restart. Confirm motor behavior attended.

Candidate minimum OFF times: 300 seconds for water pump/heat pumps; 60 seconds
for boiler/microwave. These are conservative software defaults, NOT verified
manufacturer restart limits. Appliance-specific constraints are a live gate.
Boiler/heat-pump restoration also requires Grid Confidence Normal to avoid
overriding the existing reserve protections. Other protection remains independent.

First-floor native control is deliberately limited to verified Heat/Off with
normal presets, supported fan values and 16–30 C setpoint. Eco/Quiet/Super/Sleep/
8-degree operation is not eligible in this candidate. EH snapshots settings;
restoration sends only Heat if the settings remain unchanged. No forced 25 C or
fan reset, and no first-floor relay fallback. Verify actual app/remote behavior.
The separate legacy reserve/timer automations can still operate that relay;
this release does not migrate every heat-pump control path.

## Recovery and rollback

Missing inverter readings, bridge snapshots or owned-device power/state evidence
pause restoration. After five minutes while owned OFF loads remain, one persisted
Telegram event lists them and asks the family to check loads before manual restart.
No blind restore after a timeout. On recovery require a new five-minute low-load
window. Notifications require EH, HA/MQTT and Family bot to be running/reachable;
a complete system failure cannot guarantee a message. Inverter exception paths
explicitly tick the missing-data observer. Restarts preserve notification dedup,
ownership and faults, but never carry over a low-load qualification.
Scheduled same-state OFF requests also release ownership, including while inverter
telemetry is missing when the HA ownership snapshot is still fresh.

Turn the HA arming helper OFF to stop further commands. It does not undo an
already-running HA service call and does not automatically re-enable appliances.
Inspect pending/owned/blocked details, physically check each device, and restore
only the devices the family wants ON. Do not clear the ownership journal or force
its version to bypass a fault. Archive/reinitialize it only in a separately
approved, disarmed recovery after all devices are reconciled. There is intentionally
no blind dashboard reset. Keeping the controller disabled is a safe rollback;
preserve its journal if rolling back the app or HA configuration.

## Telegram contract

One short message per confirmed OFF and ON action; completion remains journal/
dashboard-only to avoid a duplicate restoration message. Unknown outcomes say
that a check is required, never that switching succeeded. Notifications are not
part of the electrical safety boundary and cannot guarantee timely delivery.

Battery advice only notifies for a new valid target different from the selected
minimum; repeated/stale evidence is quiet. Morning reports retain a short minimum,
recommendation and manual-control status. Future automatic reserve notifications
require a confirmed applied-change ID; this release does not enable that producer.
Measured night import is reported without inferring exclusive battery supply or
claiming an all-morning energy history. Battery jumps use short neutral wording.
