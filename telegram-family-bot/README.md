# Telegram Family Assistant — 3.6.37

Ukrainian morning briefings, grid-event messages, planning explanations and
selected diagnostic alerts, paired with EnergyHub 3.6.37. Startup is verified.
The owner reports several days of normal observation and accepts this source
snapshot for public promotion; this is not exhaustive live-event validation.

Features include calendar/weather/solar outlook, outage-source status, SOC/BMS
evidence, optional CO/CO2 and household observations, estimated import/cost and
bounded log/notification queues. Missing data is qualified. Event-time PV uses
a full qualified five-minute observation; delayed delivery must not rewrite it
as current. No exactly-once Telegram guarantee or complete 24-hour log-health
claim is made.

This is not conversational AI Mission Control. It does not directly command the
inverter or shed/restore appliance plugs. Its optional Tuya beacon support can
reload an isolated supported HA integration under bounded checks; this is a
service side effect, not a hardware reboot guarantee. It is disabled by default.
Optional Xiaomi cloud observations reuse an existing HA session rather than
performing a new cloud login, and are also disabled by default.

Set bot credentials/destination locally in app options. The app has read-only
HA configuration mount access, including potentially sensitive existing session
files if optional features are enabled. Review this permission before installation.
Never publish local registries, cloud caches, calendar URLs or chat identifiers.
Optional household/environment/plug lists are empty public defaults. Device
aliases and first/second-site legacy option names are examples/compatibility,
not automatic discovery or a claim of arbitrary regional support.

See [options and boundaries](DOCS.md), [release notes](../RELEASE_NOTES_3.6.37.md)
and [evidence](../docs/validation/RELEASE_3.6.37.md).
Threat Monitor is a separate project and is not included.
