# Family Assistant 2.2.5 — quieter data incidents

Prepared privately, not deployed. Family add-on only; EH remains 2.2.4. No Core
configuration, dashboard, Threat Monitor or Smart Heating changes required.

Policy: record short interruptions silently; one alert at the first observation
at/after 180 seconds continuously missing. Recovery requires 300 seconds of healthy
observations; observation gaps above 90 seconds restart recovery qualification.
Warned flaps stay in one incident. Send recovery only for an actually delivered
warning. Group sources maturing in the same observation; persistent incidents do
not send reminders. Other source failures can generate a later, distinct warning.
Initial unavailable data also qualifies; do not fabricate a formerly healthy state.

Scope: HA API availability, inverter freshness and valid charge/grid readings,
PV2 when present/previously seen, load bridge, six participant power/state readings,
overload readiness, configured forecast value, reserve evidence and UHMC snapshot.
This is not a watchdog for every HA entity. Whole HA loss masks child observations;
it does not falsely recover them. Semantic freshness relies on EH/provider flags;
a plausible frozen numeric forecast without a stale flag is not detected.

Protection reacts on its existing timing, not these notification delays. The bot
does not change switches or restart equipment. Recovery messages describe current
overload readiness and do not turn manual controls on. Operational overload action,
fault/owned-OFF attention messages remain distinct and are not suppressed by the
data-notification timer. Readiness-only ON/ready chatter is suppressed.

Morning: yesterday's actual missing intervals, count, total and longest duration;
include any interval >=3 minutes or >=3 interruptions/source. At most four detail
lines plus an additional-source count. Five-minute recovery wait is not downtime.
History retained up to 14 days/500 closed records, active intervals bounded to 2000.
Battery recurrence counts distinct observed dates in the last 30 days independently
of morning acknowledgement. Highlight consecutive days or affected days in a
ten-day window. No diagnosis and no invented pre-upgrade history. Existing immediate
battery-jump messages remain short and unchanged.

No notification is possible if the Family app itself is stopped, Telegram/network
is unavailable or the polling loop cannot execute. Threshold delivery is approximate
(30-second loop plus IO), not a real-time guarantee. Save/send crashes can cause a
rare duplicate; Telegram has no exactly-once delivery contract.

Deploy only after separate authorization using the standard Family sync/Update
workflow, with a backup outside app discovery and live-source comparison. No Core
stop/restart required. Observe real interruptions or replay fixtures; do not disable
hardware safety or deliberately overload the inverter to test messaging.
