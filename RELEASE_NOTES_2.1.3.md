# EnergyHub 2.1.3 / Family Assistant 2.1.6 — Clear strategy names

Prepared privately on 2026-09-06. Not synchronized, rebuilt, deployed, committed,
pushed or published. The homeowner previously confirmed EH 2.1.2 / Family 2.1.5
startup. Threat Monitor is outside this release.

## Display contract

| Existing internal value/name | English display | Ukrainian family wording |
| --- | --- | --- |
| AHM minimum | Battery Reserve | Запас батареї |
| solar | Solar First | Пріоритет сонця |
| hybrid_charging | Low-Tariff Charging | Заряджання за нічним/денним тарифом |
| hybrid_grid_hold | Grid Hold | Будинок живиться від мережі, батарея чекає сонця |
| panic | Reserve Protection | Захист резерву батареї |
| panic_grid_hold | Reserve Hold | Будинок живиться від мережі, резерв батареї зберігається |
| Start Panic | Build Emergency Reserve | Existing structured command, unchanged |
| grid confidence panic | Critical | Критична |

The dashboard separates strategy, the installed low-tariff window (23:00–07:00),
and battery target. Family messages use the current local tariff period, not
the mode name, when explaining charging. These names do not add configurable
or dynamic tariffs; the installed accounting window remains unchanged.

The overnight aggregate `hybrid` means use of the tariff plan, not necessarily
charging. The morning report keeps this historical summary and adds a separately
timestamped current-strategy description from read-only HA observations. Grid
hold and charging are distinguished; stale telemetry or missing grid voltage
prevents a positive grid-supply claim. The selected charging mode is not a
measurement of instantaneous charging current. Reserve Protection does not
promise to wait for sunlight after its target is reached.

## Compatibility and safety

- Entity IDs, discovery unique IDs, MQTT topics, enums, command payloads,
  persistence and numeric settings remain unchanged. Display names and selected
  human-readable explanation strings change; technical logs/raw states may
  retain the old terms. Existing user-customized entity names may override
  MQTT-discovered friendly names.
- Reserve ownership remains manual/advisory. Automatic stays unavailable.
- Peak Load Guard remains Dry Run at 40/30/20, with unchanged recovery timing,
  cycle identity, event journal and Telegram deduplication. No plug writes added.
- Forecast evaluation, reserve arithmetic, weather qualification and quiet hours
  are unchanged. The unresolved consumption-history 0/3 observation is separate.
- Existing queued notifications are not rewritten or replayed. They may retain
  older wording once. No new daytime strategy notification stream is introduced.

## Deployment handoff — separate approval required

Scope: `addon/`, `telegram-family-bot/`, HA `automations.yaml`, `scripts.yaml`,
and `.storage/lovelace.dashboard_powmr1`. No `configuration.yaml`, helper storage
or Threat Monitor synchronization is needed for this naming increment.

Follow the standard workflow (private development record). Compare
live files first and preserve outside-scope manual changes; back up outside the
local-app discovery tree. Dashboard storage requires homeowner Core stop before
copying, then Core check/start. Apps require App-store Reload/Update and startup
verification. Do not stop Core for app updates alone.

Prefer finishing the agreed September 7/8 morning observations before deployment.
If deployed sooner, record the boundary: app restart interrupts observation and
resets recovery confirmation, although persisted Dry Run cycle data remains.
Confirm EH 2.1.3 / Family 2.1.6 startup, MQTT, unchanged entity IDs and manual
reserve, Auto OFF, Peak Load Guard 40/30/20 and the next Ukrainian report.

See repository validation (private development record).
