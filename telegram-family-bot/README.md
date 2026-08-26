# Telegram Family Assistant

Home Assistant app that sends a Ukrainian weather, energy, and heat-pump
ownership summary to a private family Telegram group every morning and warns
when SOC crosses reserve-relative thresholds.

It can recommend increasing the user-selected AHM reserve when the observed 07:00–12:00 SOC minimum approaches that reserve. Recommendations are informational and never change Home Assistant controls.

Version 1.3.14 remains outbound-only and joins the coordinated EnergyHub public
release train. It reports whether the family or
EnergyHub protection currently governs heat-pump use. Reserve warnings require
an active configured heat pump, include its floor and observed power, and are
kept quiet through 08:01. The 08:00 report also includes persistent health
issues for seven configured temperature/humidity sensors and an optional
doorbell low-battery warning. It treats an unchanged temperature/humidity pair
for 24 hours as suspected offline and collapses duplicate recovery history per
sensor. The app never switches a device or sends an
inverter command. The morning report also summarizes up to three EnergyHub
inverter incidents from the previous day and distinguishes a cleared message
from an unverified inverter restart. The report also shows the finalized
previous-calendar-day night/normal estimated Grid Import and cost, followed by
current-month totals, when every required EnergyHub sensor is available.

The app persists the exact logical morning report before calling Telegram and
retries that outbox after a restart. Telegram `sendMessage` has no idempotency
key, so delivery is at-least-once: a crash after Telegram accepts a message but
before the local acknowledgement is saved can still cause a rare duplicate.

See `DOCS.md` for installation and data semantics.
