from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2 import Environment
import yaml


ROOT = Path(__file__).resolve().parents[2]
AUTOMATIONS = ROOT / "homeassistant/live/config/automations.yaml"


class ZigbeeBridgeNotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        automations = yaml.safe_load(AUTOMATIONS.read_text(encoding="utf-8"))
        cls.offline = next(item for item in automations if item["id"] == "1786100000101")
        cls.recovery = next(item for item in automations if item["id"] == "1786100000102")
        cls.recovery_gate = cls.recovery["actions"][1]
        condition = cls.recovery_gate["if"][0]["value_template"]
        cls.template = Environment().from_string(condition)

    def recovery_notice(self, from_value, to_value, duration_seconds):
        started = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
        trigger = SimpleNamespace(
            from_state=(
                None
                if from_value is None
                else SimpleNamespace(state=from_value, last_changed=started)
            ),
            to_state=(
                None
                if to_value is None
                else SimpleNamespace(
                    state=to_value,
                    last_changed=started + timedelta(seconds=duration_seconds),
                )
            ),
        )
        strict_transition = from_value == "off" and to_value == "on"
        rendered = self.template.render(
            trigger=trigger,
            as_timestamp=lambda value: value.timestamp(),
        ).strip().lower()
        return strict_transition and rendered == "true"

    def offline_notice(self, duration_seconds):
        trigger = self.offline["triggers"][0]
        hours, minutes, seconds = (int(part) for part in trigger["for"].split(":"))
        threshold = hours * 3600 + minutes * 60 + seconds
        return duration_seconds >= threshold

    def test_brief_eleven_second_interruption_is_silent(self):
        self.assertFalse(self.offline_notice(11))
        self.assertFalse(self.recovery_notice("off", "on", 11))

    def test_brief_thirty_six_second_interruption_is_silent(self):
        self.assertFalse(self.offline_notice(36))
        self.assertFalse(self.recovery_notice("off", "on", 36))

    def test_interruption_over_two_minutes_has_paired_notices(self):
        self.assertTrue(self.offline_notice(348))
        self.assertTrue(self.recovery_notice("off", "on", 348))

    def test_startup_or_entity_restoration_does_not_report_recovery(self):
        self.assertFalse(self.recovery_notice("unavailable", "on", 348))
        self.assertFalse(self.recovery_notice(None, "on", 348))

    def test_dismiss_always_precedes_conditional_recovery_notice(self):
        dismiss, conditional = self.recovery["actions"]
        self.assertEqual("persistent_notification.dismiss", dismiss["action"])
        self.assertEqual(
            "energyhub_zigbee2mqtt_bridge_offline",
            dismiss["data"]["notification_id"],
        )
        self.assertIn("if", conditional)
        self.assertEqual(
            "persistent_notification.create",
            conditional["then"][0]["action"],
        )

    def test_health_automations_never_restart_or_toggle_devices(self):
        text = yaml.safe_dump([self.offline, self.recovery]).lower()
        self.assertNotIn("hassio.addon_restart", text)
        self.assertNotIn("switch.turn_", text)
        self.assertNotIn("homeassistant.restart", text)
        self.assertIn("fresh post-recovery telemetry", text)


if __name__ == "__main__":
    unittest.main()
