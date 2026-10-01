# Telegram Family Assistant 2.4.12 — private candidate

This candidate corrects a false load-protection readiness outage caused by a
30-second Telegram freshness gate against EnergyHub's 60-second unchanged-status
heartbeat. The gate is now 90 seconds; only legacy `control` incident history
from that faulty gate is discarded. Other inverter, Zigbee, and device history
is retained.

Technical warnings distinguish shared input loss from a single unavailable
device. EnergyHub's existing load controller skips unavailable participants and
continues evaluating other eligible loads. The 08:00 family report now includes
confirmed overnight battery-reserve grid hold and return-to-solar transitions,
including the observed times and reserve thresholds.

The companion Home Assistant dashboard patch enlarges the main Autopilot
switch, clarifies Auto/Manual authority labels, shows Solar-only Heating only
under Smart Heating, moves Grid Confidence near the top, and clarifies battery
reserve transition notifications.

This is repository-only preparation. No add-on update, Home Assistant YAML or
dashboard synchronization, Core restart, live validation, private push, or
public release is implied.

Load-control events are already retained in the bounded EnergyHub journal
(`/data/energyhub_peak_load_control.json`, last 64 events). Family Assistant
logs queueing and successful delivery separately; Telegram history remains
the human-readable observation, not the sole diagnostic record.
