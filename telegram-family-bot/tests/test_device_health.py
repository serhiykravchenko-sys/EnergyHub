from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from app.device_health import (
    DeviceHealthMonitor,
    acknowledge_health_report,
    doorbell_report_line,
    environment_report_lines,
    parse_environment_sensors,
    parse_smart_plugs,
    smart_plug_report_lines,
)


TIMEZONE = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 8, 20, 8, 0, tzinfo=TIMEZONE)


def entity(entity_id, value, updated=NOW):
    return {
        "entity_id": entity_id,
        "state": str(value),
        "last_changed": updated.isoformat(),
        "last_updated": updated.isoformat(),
        "attributes": {},
    }


class FakeClient:
    def __init__(self, values):
        self.values = values

    def states(self):
        return list(self.values.values())

    def state(self, entity_id):
        return self.values.get(entity_id)


class DeviceHealthTests(unittest.TestCase):
    def setUp(self):
        sensors = parse_environment_sensors(
            "Room A|sensor.a_temperature|sensor.a_humidity|indoor;"
            "Room B|sensor.b_temperature|sensor.b_humidity|indoor;"
            "Room C|sensor.c_temperature|sensor.c_humidity|indoor;"
            "Basement|sensor.d_temperature|sensor.d_humidity|basement|sensor.d_battery"
        )
        self.config = SimpleNamespace(
            environment_sensors=sensors,
            environment_stale_hours=24,
            environment_temperature_deviation_c=5,
            environment_humidity_deviation_percent=20,
            environment_persistence_minutes=60,
            device_low_battery_percent=10,
            doorbell_battery_entity="sensor.doorbell_battery",
        )
        self.monitor = DeviceHealthMonitor(self.config)
        self.values = {
            "sensor.a_temperature": entity("sensor.a_temperature", 30),
            "sensor.a_humidity": entity("sensor.a_humidity", 50),
            "sensor.b_temperature": entity("sensor.b_temperature", 20),
            "sensor.b_humidity": entity("sensor.b_humidity", 50),
            "sensor.c_temperature": entity("sensor.c_temperature", 20),
            "sensor.c_humidity": entity("sensor.c_humidity", 50),
            "sensor.d_temperature": entity("sensor.d_temperature", 12),
            "sensor.d_humidity": entity("sensor.d_humidity", 80),
            "sensor.d_battery": entity("sensor.d_battery", 9),
        }
        self.client = FakeClient(self.values)
        self.state = {}

    def test_smart_plugs_report_only_unavailable_unknown_or_missing(self):
        config = SimpleNamespace(smart_plugs=parse_smart_plugs(
            "Heat pump 1|switch.hp1;"
            "Heat pump 2|switch.hp2;"
            "Boiler|switch.boiler;"
            "Pump|switch.pump"
        ))
        client = FakeClient({
            "switch.hp1": entity("switch.hp1", "on"),
            "switch.hp2": entity("switch.hp2", "off"),
            "switch.boiler": entity("switch.boiler", "unavailable"),
        })

        self.assertEqual(
            ["⚠️ Недоступна: Boiler", "⚠️ Недоступна: Pump"],
            smart_plug_report_lines(config, client),
        )

    def test_smart_plug_labels_are_escaped_for_telegram_html(self):
        config = SimpleNamespace(
            smart_plugs=parse_smart_plugs("Pump <critical>|switch.pump")
        )
        self.assertEqual(
            ["⚠️ Недоступна: Pump &lt;critical&gt;"],
            smart_plug_report_lines(config, FakeClient({})),
        )

    def test_each_sensor_uses_only_its_own_previous_day_reading(self):
        self.state["environment_hourly_snapshots"] = {
            "2026-08-19T08": {
                "a": {"temperature": 20, "humidity": 50},
                "d": {"temperature": 20, "humidity": 80},
            }
        }
        self.monitor.observe(self.client, self.state, NOW, force=True)
        self.assertNotIn("a:temperature", self.state["environment_active"])
        self.assertIn("a:temperature", self.state["environment_candidates"])
        self.assertIn("d:temperature", self.state["environment_candidates"])

        later = NOW + timedelta(minutes=60)
        for item in self.values.values():
            item["last_updated"] = later.isoformat()
        self.monitor.observe(self.client, self.state, later, force=True)

        for key in ("a:temperature", "d:temperature"):
            issue = self.state["environment_active"][key]
            self.assertEqual("change", issue["kind"])
            self.assertEqual(60, issue["duration_minutes"])
            self.assertNotIn("peer", issue)

    def test_unavailable_is_immediate_and_recovery_is_reported(self):
        self.values["sensor.b_humidity"]["state"] = "unavailable"
        self.monitor.observe(self.client, self.state, NOW, force=True)
        self.assertEqual(
            "unavailable",
            self.state["environment_active"]["b:availability"]["kind"],
        )

        recovered = NOW + timedelta(minutes=5)
        self.values["sensor.b_humidity"] = entity(
            "sensor.b_humidity", 50, recovered
        )
        self.monitor.observe(self.client, self.state, recovered, force=True)
        lines = environment_report_lines(self.state, recovered)
        self.assertTrue(any(
            "✅ Room B: датчик знову передає актуальні дані." == line
            for line in lines
        ))

    def test_stale_pair_is_not_treated_as_a_numeric_peer(self):
        old = NOW - timedelta(hours=25)
        self.values["sensor.c_temperature"]["last_updated"] = old.isoformat()
        self.values["sensor.c_humidity"]["last_updated"] = old.isoformat()
        self.monitor.observe(self.client, self.state, NOW, force=True)
        issue = self.state["environment_active"]["c:availability"]
        self.assertEqual("stale", issue["kind"])
        self.assertGreaterEqual(issue["age_hours"], 25)

    def test_last_reported_prevents_false_stale_for_unchanged_value(self):
        old = NOW - timedelta(hours=25)
        recent = NOW - timedelta(minutes=5)
        self.values["sensor.c_temperature"]["last_updated"] = old.isoformat()
        self.values["sensor.c_humidity"]["last_updated"] = old.isoformat()
        self.values["sensor.c_temperature"]["last_changed"] = recent.isoformat()
        self.values["sensor.c_humidity"]["last_changed"] = recent.isoformat()
        self.values["sensor.c_temperature"]["last_reported"] = recent.isoformat()
        self.values["sensor.c_humidity"]["last_reported"] = recent.isoformat()

        self.monitor.observe(self.client, self.state, NOW, force=True)

        self.assertNotIn("c:availability", self.state["environment_active"])

    def test_unchanged_pair_is_suspected_offline_despite_recent_reports(self):
        old = NOW - timedelta(hours=24)
        recent = NOW - timedelta(minutes=5)
        for entity_id in ("sensor.d_temperature", "sensor.d_humidity"):
            self.values[entity_id]["last_changed"] = old.isoformat()
            self.values[entity_id]["last_reported"] = recent.isoformat()
            self.values[entity_id]["last_updated"] = recent.isoformat()

        self.monitor.observe(self.client, self.state, NOW, force=True)

        issue = self.state["environment_active"]["d:availability"]
        self.assertEqual("unchanged", issue["kind"])
        self.assertGreaterEqual(issue["age_hours"], 24)
        self.assertTrue(any(
            "Basement" in line and "можливий офлайн" in line
            for line in environment_report_lines(self.state, NOW)
        ))

    def test_one_changing_metric_prevents_unchanged_pair_warning(self):
        old = NOW - timedelta(hours=25)
        recent = NOW - timedelta(minutes=5)
        self.values["sensor.d_temperature"]["last_changed"] = old.isoformat()
        self.values["sensor.d_humidity"]["last_changed"] = recent.isoformat()

        self.monitor.observe(self.client, self.state, NOW, force=True)

        self.assertNotIn("d:availability", self.state["environment_active"])

    def test_numeric_changes_do_not_create_recovery_messages(self):
        self.state["environment_recoveries"] = [
            {"label": "Bathroom", "kind": "change", "metric": "temperature"},
            {"label": "Bathroom", "kind": "change", "metric": "humidity"},
        ]
        self.assertFalse(any(
            "Bathroom" in line
            for line in environment_report_lines(self.state, NOW)
        ))

    def test_legacy_recoveries_without_metrics_are_also_collapsed(self):
        self.state["environment_recoveries"] = [
            {"label": "Bathroom", "kind": "unavailable"},
            {"label": "Bathroom", "kind": "unavailable"},
        ]

        lines = environment_report_lines(self.state, NOW)

        self.assertEqual(1, len([line for line in lines if "Bathroom" in line]))

    def test_change_report_shows_values_direction_and_is_acknowledged_once(self):
        self.state["environment_active"] = {
            "d:humidity": {
                "kind": "change",
                "label": "Basement",
                "metric": "humidity",
                "yesterday": 58,
                "value": 81,
                "yesterday_deviation": 23,
            },
            "a:temperature": {
                "kind": "change",
                "label": "Room A",
                "metric": "temperature",
                "yesterday": 23,
                "value": 17,
                "yesterday_deviation": -6,
            },
        }
        lines = environment_report_lines(self.state, NOW)
        self.assertTrue(any(
            "зросла з 58% до 81% (+23 п.п. порівняно з учора)" in line
            for line in lines
        ))
        self.assertTrue(any(
            "знизилась з 23°C до 17°C (-6°C порівняно з учора)" in line
            for line in lines
        ))

        acknowledge_health_report(self.state)
        self.assertEqual([], environment_report_lines(self.state, NOW))

    def test_previous_day_same_hour_detects_basement_change(self):
        self.state["environment_hourly_snapshots"] = {
            "2026-08-19T08": {
                "d": {"temperature": 20, "humidity": 80}
            }
        }
        self.monitor.observe(self.client, self.state, NOW, force=True)
        self.assertIn("d:temperature", self.state["environment_candidates"])
        self.assertNotIn("d:temperature", self.state["environment_active"])

    def test_known_sensor_battery_warning_is_immediate(self):
        self.monitor.observe(self.client, self.state, NOW, force=True)
        issue = self.state["environment_active"]["d:battery"]
        self.assertEqual(9, issue["battery"])

    def test_doorbell_warns_at_ten_percent_and_distinguishes_unavailable(self):
        self.values["sensor.doorbell_battery"] = entity(
            "sensor.doorbell_battery", 10
        )
        self.assertIn(
            "10%",
            doorbell_report_line(self.config, self.client, NOW),
        )
        self.values["sensor.doorbell_battery"]["state"] = "unavailable"
        self.assertIn(
            "недоступні",
            doorbell_report_line(self.config, self.client, NOW),
        )

    def test_parser_rejects_invalid_group(self):
        with self.assertRaises(ValueError):
            parse_environment_sensors(
                "Room|sensor.t|sensor.h|outside"
            )


if __name__ == "__main__":
    unittest.main()
