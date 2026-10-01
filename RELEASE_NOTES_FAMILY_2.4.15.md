# Telegram Family Assistant 2.4.15 — monitored companion release

Deployed and started on 2026-09-29, paired with EnergyHub 2.4.12. The homeowner
reported the agreed monitoring period passed on 2026-10-01; supplied Telegram
evidence confirms grid-outage/recovery messages. Rare strategy-failure and
delayed-delivery scenarios remain covered by repository regressions rather than
forced live failures. Included with the EnergyHub 2.4.12 public release.

- Ignore a heat-pump restart event that is valid JSON but not an object.
- Isolate event observers so a malformed entity or observer exception does not
  suppress unrelated queued alerts or the scheduled morning report.
- Report a `transition_failed` or unreconstructed `inconsistent` inverter strategy once per fault
  episode to the configured technical destination, with the existing family
  chat fallback. Clear the deduplication latch only after a recognized healthy
  strategy returns.
- Recheck a queued strategy warning before delivery. If Telegram recovers
  after the inverter mode has recovered, describe the failure as a past event
  and show the currently confirmed mode instead of reporting suspended control.
- When a technical warning falls back to the family chat overnight, the morning
  digest checks the current inverter mode before describing that archived
  event. The mode is labeled with the report's observation time so a delayed
  Telegram retry does not present the saved status as current. Unknown mode is
  reported as needing verification.

The bot remains outbound-only. It does not retry inverter commands, change HA
helpers, or restore loads. New installations must verify delivery and the
intended Telegram destination. Morning briefings and alerts provide everyday
information in Telegram; Home Assistant remains the configuration platform.
