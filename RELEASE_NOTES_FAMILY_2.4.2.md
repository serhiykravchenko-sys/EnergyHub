# Family Assistant 2.4.2 private corrective candidate

Family Assistant 2.4.2 is prepared in the repository but is not committed,
pushed, synchronized, installed, started, or live-validated.

## Corrections

- `technical_chat_id` is now a truly optional Home Assistant app option: it is
  retained in the optional schema but omitted from default options. This avoids
  Supervisor materializing a new missing value as invalid `null` during an
  upgrade. Technical delivery still falls back to the family destination when
  the option is absent or empty.
- When the minimum Battery Reserve moves the house to confirmed Grid Hold, the
  family message reports the current SOC, applied reserve, and the dynamic
  `reserve + 10` return threshold.
- When that hold later returns to confirmed Solar with fresh telemetry and the
  grid still available, a second family message reports the current SOC and the
  stored return threshold. A Solar transition caused by grid loss is silent in
  this observer because the separate outage message explains that event.

## Security and deployment note

The supplied Supervisor diagnostic exposed live secrets. Rotate the Telegram
bot token and private calendar URL before starting the app, and keep replacement
values only in Home Assistant app options. No secret belongs in Git.
