import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase
from zoneinfo import ZoneInfo

try:
    import paho.mqtt.client  # noqa: F401
except ModuleNotFoundError:
    paho_module = ModuleType("paho")
    mqtt_module = ModuleType("paho.mqtt")
    mqtt_client_module = ModuleType("paho.mqtt.client")
    mqtt_module.client = mqtt_client_module
    paho_module.mqtt = mqtt_module
    sys.modules["paho"] = paho_module
    sys.modules["paho.mqtt"] = mqtt_module
    sys.modules["paho.mqtt.client"] = mqtt_client_module

from app.mqtt.publisher import publish_weather_buffer, publish_weather_buffer_discovery
from app.services.daily_summary import DailySummaryService
from app.services.weather_buffer import WeatherBufferDryRun as ReservePolicy


TZ = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 9, 5, 5, 0, tzinfo=TZ)


def WeatherBufferDryRun(**kwargs):
    service = ReservePolicy(**kwargs)
    service.update_grid_confidence("normal", service.clock())
    return service


class RecordingClient:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload, retain=False):
        self.messages.append((topic, payload, retain))


def daily(*, baseline=20, solar=10, mode="Dry Run", smart_heating=False):
    return {
        "date": "2026-09-05",
        "observed_at": NOW.isoformat(),
        "mode": mode,
        "baseline_soc": baseline,
        "source_entity": "sensor.solcast_pv_forecast_forecast_today",
        "solar_forecast_kwh": solar,
        "smart_heating_enabled": smart_heating,
    }


def samples(*values):
    return [
        {"date": f"2026-09-0{4-index}", "kwh": value}
        for index, value in enumerate(values)
    ]


def warning(*, severity=2, until="2026-09-05T23:59:59+03:00"):
    return {
        "event_id": f"uhmc1921/5973/{severity}",
        "published_at": "2026-09-05T04:30:00+03:00",
        "valid_from": "2026-09-05T04:30:00+03:00",
        "valid_until": until,
        "severity": severity,
        "severity_color": "orange" if severity == 2 else "yellow",
        "region": "Kyiv/Kyiv region",
        "region_match": True,
        "grid_relevant": True,
        "hazards": ["thunderstorm"],
        "summary": "Гроза, II рівень небезпечності",
        "url": "https://t.me/uhmc1921/5973",
    }


def weather(*warnings, status="fresh"):
    return {
        "observed_at": NOW.isoformat(),
        "source_status": status,
        "source": "uhmc1921",
        "warnings": list(warnings),
    }


class ReservePolicyDryRunTests(TestCase):
    def test_missing_tomorrow_keeps_today_schedule_reserve_at_forty(self):
        for hour, minute in ((21, 0), (23, 55)):
            with self.subTest(hour=hour):
                now = NOW.replace(hour=hour, minute=minute)
                service = WeatherBufferDryRun(path=None, clock=lambda: now)
                inputs = daily(solar=1)
                inputs['observed_at'] = now.isoformat()
                if hour == 23:
                    inputs.update(date=(now.date()+timedelta(days=1)).isoformat(),
                                  forecast_plan_stage='preliminary')
                service.update(inputs, samples(10, 10, 10))
                service.update_grid_confidence('risk', now)
                service.update_schedule(dict(source='alerts_energy', region='kyiv_region',
                    source_status='fresh', validated=True, checked_at=now.isoformat(),
                    dates=[now.date().isoformat()],
                    day_errors={(now.date()+timedelta(days=1)).isoformat(): 'Unconfirmed'}))
                state = service.status_attributes()
                self.assertEqual(40, state['recommended_soc'])
                self.assertEqual('dtek_schedule', state['reserve_planning_source'])
                self.assertEqual(0, state['grid_modifier_percent'])

    def test_schedule_replaces_grid_forecast_modifiers_and_keeps_weather(self):
        current=[NOW]
        service=WeatherBufferDryRun(path=None,clock=lambda:current[0])
        service.update(daily(solar=1),samples(10,10,10))
        service.update_grid_confidence('panic',NOW)
        service.update_weather(weather(warning()))
        self.assertEqual(95,service.status_attributes()['recommended_soc'])
        document=dict(source='bezsvitla',region='kyiv_region',source_status='fresh',validated=True,checked_at=NOW.isoformat(),dates=[NOW.date().isoformat()])
        service.update_schedule(document)
        state=service.status_attributes()
        self.assertEqual(60,state['recommended_soc'])
        self.assertEqual('dtek_schedule',state['reserve_planning_source'])
        self.assertEqual(0,state['grid_modifier_percent'])
        self.assertEqual(0,state['generation_modifier_percent'])
        for source in ('dtek_official','alerts_energy','pro_kyiv','schedule_sources'):
            document['source']=source
            service.update_schedule(document)
            self.assertEqual('dtek_schedule',service.status_attributes()['reserve_planning_source'])
            self.assertEqual(60,service.status_attributes()['recommended_soc'])
        document['checked_at']=(NOW-timedelta(minutes=36)).isoformat()
        service.update_schedule(document)
        self.assertEqual(95,service.status_attributes()['recommended_soc'])
        self.assertEqual('grid_confidence',service.status_attributes()['reserve_planning_source'])

    def test_weather_day_allowance_survives_restart_clear_feed_and_ends_next_day(self):
        current=[NOW]
        with TemporaryDirectory() as temp:
            path=Path(temp)/'reserve.json'
            service=WeatherBufferDryRun(path=path,clock=lambda:current[0])
            service.update(daily(solar=20),samples(10,10,10))
            service.update_weather(weather(warning(until=(NOW+timedelta(minutes=5)).isoformat())))
            restored=WeatherBufferDryRun(path=path,clock=lambda:current[0])
            restored.update_weather(weather())
            self.assertEqual(20,restored.status_attributes()['weather_modifier_percent'])
            current[0]=NOW+timedelta(days=1)
            restored.update_grid_confidence('normal',current[0])
            data=daily(solar=20);data.update(date=current[0].date().isoformat(),observed_at=current[0].isoformat())
            restored.update(data,samples(10,10,10))
            restored.update_weather(dict(weather(),observed_at=current[0].isoformat()))
            self.assertEqual(0,restored.status_attributes()['weather_modifier_percent'])

    def test_weather_levels_add_allowance_independent_of_hazard_type(self):
        for severity in (1, 2, 3):
            for relevant in (False, True):
                with self.subTest(severity=severity, relevant=relevant):
                    service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
                    service.update(daily(solar=20), samples(10, 10, 10))
                    event = warning(severity=severity)
                    event['grid_relevant'] = relevant
                    service.update_weather(weather(event))
                    expected = 20 if severity >= 2 else 0
                    self.assertEqual(expected, service.status_attributes()['weather_modifier_percent'])
                    self.assertEqual(20+expected, service.status_attributes()['recommended_soc'])
                    self.assertEqual(1, len(service.status_attributes()['weather_source_warnings']))

    def test_weather_requires_validity_and_holds_for_the_applicable_day(self):
        current = [NOW]
        service = WeatherBufferDryRun(path=None, clock=lambda: current[0])
        service.update(daily(solar=20), samples(10, 10, 10))
        for value in (None, 'invalid'):
            event = warning(until=value)
            service.update_weather(weather(event))
            self.assertEqual(0, service.status_attributes()['weather_modifier_percent'])
        service.update_weather(weather(warning(until=(NOW+timedelta(seconds=1)).isoformat())))
        self.assertEqual(20, service.status_attributes()['weather_modifier_percent'])
        current[0] = NOW+timedelta(seconds=2)
        service.refresh(current[0])
        self.assertEqual(20, service.status_attributes()['weather_modifier_percent'])
        self.assertEqual(40, service.status_attributes()['recommended_soc'])

    def test_three_day_average_and_deficit_do_not_add_fixed_reserve(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        self.assertTrue(service.update(daily(solar=8), samples(5, 15, 5)))
        attributes = service.status_attributes()
        self.assertEqual(8.33, attributes["consumption_average_kwh"])
        self.assertEqual(3, attributes["consumption_sample_count"])
        self.assertTrue(attributes["forecast_deficit"])
        self.assertEqual(0, attributes["generation_modifier_percent"])
        self.assertEqual(20, attributes["recommended_soc"])
        self.assertFalse(attributes["control_applied"])

    def test_severe_deficit_is_separate_from_br(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        self.assertTrue(service.update(daily(solar=4), samples(10, 10, 10)))
        attributes = service.status_attributes()
        self.assertTrue(attributes["severe_forecast_deficit"])
        self.assertEqual(0, attributes["generation_modifier_percent"])
        self.assertEqual(20, attributes["recommended_soc"])

    def test_heating_does_not_add_reserve_but_grid_risk_still_does(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=20, smart_heating=True), samples(10, 10, 10))
        self.assertEqual(20, service.status_attributes()["recommended_soc"])
        self.assertEqual(0, service.status_attributes()["smart_heating_modifier_percent"])
        service.update_grid_confidence("panic", NOW)
        self.assertEqual(80, service.status_attributes()["recommended_soc"])

    def test_old_heating_and_forecast_modifiers_are_not_restored(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=5, smart_heating=True), samples(10, 10, 10))
        service.decision['smart_heating_modifier_percent'] = 20
        service.decision['recommended_soc'] = 60
        service.refresh(NOW)
        self.assertEqual(20, service.status_attributes()['recommended_soc'])
        self.assertEqual(0, service.status_attributes()['generation_modifier_percent'])
        self.assertEqual(0, service.status_attributes()['smart_heating_modifier_percent'])

    def test_grid_modifiers_are_cumulative_and_cap_at_95(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=5), samples(10, 10, 10))
        service.update_grid_confidence("unstable", NOW)
        self.assertEqual(40, service.status_attributes()["recommended_soc"])
        service.update_grid_confidence("risk", NOW)
        self.assertEqual(60, service.status_attributes()["recommended_soc"])
        service.update_grid_confidence("panic", NOW)
        attributes = service.status_attributes()
        self.assertEqual(80, attributes["recommended_soc"])
        self.assertEqual(60, attributes["grid_modifier_percent"])

    def test_level_two_weather_adds_twenty_independently_of_grid_confidence(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=20), samples(10, 10, 10))
        service.update_weather(weather(warning(severity=2)))
        self.assertEqual(40, service.status_attributes()["recommended_soc"])
        self.assertEqual(20, service.status_attributes()["weather_modifier_percent"])
        service.update_grid_confidence("unstable", NOW)
        attributes = service.status_attributes()
        self.assertEqual(60, attributes["recommended_soc"])
        self.assertEqual(20, attributes["weather_modifier_percent"])
        self.assertEqual(20, attributes["grid_modifier_percent"])

    def test_level_one_is_reportable_but_does_not_change_reserve(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=20), samples(10, 10, 10))
        service.update_weather(weather(warning(severity=1)))
        attributes = service.status_attributes()
        self.assertEqual(20, attributes["recommended_soc"])
        self.assertEqual(1, attributes["latest_weather_event"]["severity"])

    def test_future_warning_is_available_for_immediate_reporting_only(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=20), samples(10, 10, 10))
        tomorrow = warning(
            severity=2,
            until="2026-09-06T23:59:59+03:00",
        )
        tomorrow["valid_from"] = "2026-09-06T00:00:00+03:00"
        service.update_weather(weather(tomorrow))
        attributes = service.status_attributes()
        self.assertEqual([], attributes["weather_warnings"])
        self.assertEqual(1, len(attributes["weather_source_warnings"]))
        self.assertEqual(0, attributes["weather_modifier_percent"])

    def test_invalid_severity_is_not_trusted(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=20), samples(10, 10, 10))
        service.update_weather(weather(warning(severity=9)))
        attributes = service.status_attributes()
        self.assertEqual([], attributes["weather_source_warnings"])
        self.assertEqual(20, attributes["recommended_soc"])

    def test_unknown_source_preserves_warning_until_expiry(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=20), samples(10, 10, 10))
        service.update_weather(weather(warning()))
        service.update_weather(weather(status="unknown"))
        attributes = service.status_attributes()
        self.assertEqual("unknown", attributes["weather_source_status"])
        self.assertEqual(40, attributes["recommended_soc"])
        service.refresh(datetime(2026, 9, 6, 0, 1, tzinfo=TZ))
        self.assertEqual(40, service.status_attributes()["recommended_soc"])
        self.assertIn("weather_source_unknown", service.status_attributes()["evidence_issues"])

    def test_hourly_weather_snapshot_is_fresh_for_seventy_five_minutes(self):
        current = [NOW]
        service = WeatherBufferDryRun(path=None, clock=lambda: current[0])
        service.update(daily(solar=20), samples(10, 10, 10))
        service.update_weather(weather(warning()))
        current[0] = NOW + timedelta(minutes=60)
        service.refresh(current[0])
        self.assertNotIn("weather_source_unknown", service.status_attributes()["evidence_issues"])
        current[0] = NOW + timedelta(minutes=76)
        service.refresh(current[0])
        self.assertIn("weather_source_unknown", service.status_attributes()["evidence_issues"])

    def test_manual_mode_observes_conditions_without_control(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update_weather(weather(warning()))
        service.update_grid_confidence("panic", NOW)
        service.update(daily(solar=1, mode="Manual"), samples(10, 10, 10))
        attributes = service.status_attributes()
        self.assertEqual("manual", attributes["transition"])
        self.assertEqual(95, attributes["recommended_soc"])
        self.assertTrue(attributes["advice_only"])
        self.assertFalse(attributes["control_applied"])

    def test_state_is_persisted_across_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reserve.json"
            first = WeatherBufferDryRun(path=path, clock=lambda: NOW)
            first.update(daily(solar=5), samples(10, 10, 10))
            first.update_weather(weather(warning()))
            restored = WeatherBufferDryRun(path=path, clock=lambda: NOW)
            self.assertEqual(40, restored.status_attributes()["recommended_soc"])

    def test_malformed_persisted_reserve_state_does_not_crash_startup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reserve.json"
            for bad_daily in ("not-an-object", {"date": NOW.date().isoformat()}):
                with self.subTest(bad_daily=bad_daily):
                    path.write_text(json.dumps({
                        "schema_version": 2,
                        "daily_input": bad_daily,
                        "decision": {},
                    }), encoding="utf-8")
                    restored = WeatherBufferDryRun(path=path, clock=lambda: NOW)
                    self.assertIsNone(restored.decision)
                    self.assertIsNone(restored.daily_input)

    def test_invalid_documents_are_rejected(self):
        service = WeatherBufferDryRun(path=None)
        self.assertFalse(service.update("not-json", []))
        self.assertFalse(service.update_weather({"observed_at": NOW.isoformat()}))

    def test_mqtt_status_and_discovery_are_retained(self):
        service = WeatherBufferDryRun(path=None, clock=lambda: NOW)
        service.update(daily(solar=5), samples(10, 10, 10))
        client = RecordingClient()
        publish_weather_buffer_discovery(client)
        publish_weather_buffer(client, service)
        retained = {topic: value for topic, value, retain in client.messages if retain}
        discovery = json.loads(retained["homeassistant/sensor/energyhub_weather_buffer/config"])
        self.assertEqual("Battery Reserve Recommendation", discovery["name"])
        attributes = json.loads(retained["powmr/weather_buffer/attributes"])
        self.assertEqual(20, attributes["recommended_soc"])


class DailyConsumptionHistoryTests(TestCase):
    def test_uses_newest_three_valid_completed_days(self):
        service = DailySummaryService.__new__(DailySummaryService)
        service.history = {
            "2026-08-31": {"house_consumption_kwh": 7},
            "2026-09-01": {"house_consumption_kwh": 0},
            "2026-09-02": {"house_consumption_kwh": 5},
            "2026-09-03": {"house_consumption_kwh": "unavailable"},
            "2026-09-04": {"house_consumption_kwh": 15},
            "2026-09-05": {"house_consumption_kwh": 100},
        }
        self.assertEqual(
            [
                {"date": "2026-09-04", "kwh": 15.0},
                {"date": "2026-09-02", "kwh": 5.0},
                {"date": "2026-08-31", "kwh": 7.0},
            ],
            service.recent_consumption("2026-09-05"),
        )
