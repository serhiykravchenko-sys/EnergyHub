# Family configuration and limits

Use the app manifest's schema for available options. Enter real bot token,
destination, MQTT credentials and private calendar URL only in local options.
`technical_chat_id` can separate technical warnings; routing, quiet hours,
bounded retry/expiry and fallback are report-specific rather than universal.

Public household/environment/plug lists are empty; populate them with your
verified entities. Optional CO/CO2/BMS mappings are evidence readers, not
life-safety certification or BMS parameter control. Forecast/weather/outage
providers are independently fallible. Primary accepted data is not invalidated
merely because a backup cannot confirm tomorrow. Unknown is not zero/no outage.

Optional Xiaomi cloud observation and isolated Tuya integration-reload support
are disabled in public defaults. Read [the permission boundary](README.md)
before enabling them. Local configuration mount access must be considered
sensitive. Public example aliases do not change installed firmware capabilities.

Native HA can opt into the Telegram notification gateway through configured
MQTT transport and the matching HA notify integration/settings. Do not alter
customer automations automatically. Send confirmation is not device ACK, and
Telegram acceptance before durable local ACK can still lead to duplicate retry.

The active policy and current startup/regression evidence are described in
[release notes](../RELEASE_NOTES_3.6.37.md) and
[validation](../docs/validation/RELEASE_3.6.37.md). No HA deployment/restart is
performed by preparing these source files.
