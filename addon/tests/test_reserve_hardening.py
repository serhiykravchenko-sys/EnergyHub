from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zoneinfo import ZoneInfo

from tests.test_weather_buffer import NOW, daily, samples, weather, warning
from app.services.weather_buffer import WeatherBufferDryRun
from app.services.daily_summary import DailySummaryService


class ReserveHardeningTests(TestCase):
    def setUp(self):
        self.now = NOW
        self.policy = WeatherBufferDryRun(path=None, clock=lambda: self.now)
        self.policy.update_grid_confidence("normal", self.now)
        self.policy.update_weather(weather())

    def update(self, solar=1, **extra):
        payload = daily(solar=solar)
        payload.update(date=self.now.date().isoformat(), observed_at=self.now.isoformat(), **extra)
        return self.policy.update(payload, samples(5, 5, 5))

    def test_intraday_forecast_and_applied_slider_do_not_stack(self):
        self.update()
        self.now += timedelta(hours=1)
        self.update(solar=30, applied_minimum_soc=40)
        state = self.policy.status_attributes()
        self.assertEqual(40, state["recommended_soc"])
        self.assertEqual(20, state["baseline_soc"])
        self.assertEqual(40, state["applied_minimum_soc"])
        self.assertEqual(1, state["solar_forecast_kwh"])

    def test_missing_forecast_next_day_holds_deficit(self):
        self.update()
        self.now += timedelta(days=1)
        self.update(solar=None)
        self.assertEqual(40, self.policy.status_attributes()["recommended_soc"])
        self.assertIn("forecast_unknown", self.policy.status_attributes()["evidence_issues"])

    def test_stale_retained_input_rejected(self):
        self.now += timedelta(days=1)
        self.assertFalse(self.policy.update(daily(), samples(5, 5, 5)))

    def test_source_failure_and_expiry_do_not_authorize_lowering(self):
        self.update(solar=30)
        self.policy.update_weather(weather(warning()))
        self.now += timedelta(days=1)
        self.policy.refresh(self.now)
        state = self.policy.status_attributes()
        self.assertEqual(40, state["recommended_soc"])
        self.assertEqual("unknown", state["weather_source_status"])
        self.assertFalse(state["daily_plan_fresh"])

    def test_fresh_clear_source_releases_weather_buffer(self):
        self.update(solar=30)
        self.policy.update_weather(weather(warning()))
        self.policy.update_weather(weather())
        self.assertEqual(20, self.policy.status_attributes()["recommended_soc"])

    def test_automatic_path_requires_complete_evidence_and_matching_applied_value(self):
        self.update(mode="Automatic", automatic_control_enabled=True)
        state = self.policy.status_attributes()
        self.assertTrue(state["automatic_control_enabled"])
        self.assertTrue(state["automatic_control_available"])
        self.assertFalse(state["control_applied"])
        self.update(mode="Automatic", applied_minimum_soc=40)
        state = self.policy.status_attributes()
        self.assertTrue(state["control_applied"])
        self.assertTrue(state["applied_change_confirmed"])
        self.assertEqual(20, state["previous_applied_soc"])
        self.assertTrue(state["applied_change_id"])

    def test_pre_five_recovery_captures_and_restart_preserves_plan(self):
        self.now -= timedelta(hours=1)
        self.update()
        self.assertIsNotNone(self.policy.status_attributes()["forecast_captured_at"])
        self.assertEqual("preliminary", self.policy.status_attributes()["forecast_plan_stage"])
        self.now += timedelta(hours=1)
        self.update(forecast_plan_stage="morning")
        with TemporaryDirectory() as directory:
            self.policy.path = Path(directory) / "reserve.json"
            self.policy._save()
            self.policy = WeatherBufferDryRun(path=self.policy.path, clock=lambda: self.now)
            self.update(solar=30)
            self.assertEqual(1, self.policy.status_attributes()["solar_forecast_kwh"])

    def test_preliminary_next_day_plan_is_active_then_morning_replaces_it(self):
        self.now = datetime.fromisoformat("2026-09-05T23:52:00+03:00")
        self.policy.update_grid_confidence("normal", self.now)
        preliminary = {
            "date": "2026-09-06",
            "observed_at": self.now.isoformat(),
            "mode": "Automatic",
            "applied_minimum_soc": 20,
            "forecast_plan_stage": "preliminary",
            "solar_forecast_kwh": 4,
        }
        completed = [{"date": "2026-09-05", "kwh": 10, "complete": True}]
        self.assertTrue(self.policy.update(preliminary, completed))
        state = self.policy.status_attributes()
        self.assertTrue(state["daily_plan_fresh"])
        self.assertEqual("preliminary", state["forecast_plan_stage"])
        self.assertEqual(40, state["recommended_soc"])

        refresh = dict(preliminary, observed_at=self.now.isoformat(),
                       forecast_plan_stage="refresh", applied_minimum_soc=40,
                       solar_forecast_kwh=30)
        self.assertTrue(self.policy.update(refresh, completed))
        state = self.policy.status_attributes()
        self.assertEqual("preliminary", state["forecast_plan_stage"])
        self.assertEqual(4, state["solar_forecast_kwh"])
        self.assertEqual(40, state["recommended_soc"])

        self.now = datetime.fromisoformat("2026-09-06T05:00:00+03:00")
        self.policy.update_grid_confidence("normal", self.now)
        morning = dict(preliminary, observed_at=self.now.isoformat(),
                       forecast_plan_stage="morning", solar_forecast_kwh=20)
        self.assertTrue(self.policy.update(morning, completed))
        state = self.policy.status_attributes()
        self.assertEqual("morning", state["forecast_plan_stage"])
        self.assertEqual("morning_captured", state["forecast_revision_status"])
        self.assertEqual(20, state["recommended_soc"])

    def test_missing_morning_revision_retains_preliminary_allowance(self):
        self.now = datetime.fromisoformat("2026-09-05T23:52:00+03:00")
        preliminary = {
            "date": "2026-09-06",
            "observed_at": self.now.isoformat(),
            "mode": "Automatic",
            "applied_minimum_soc": 40,
            "forecast_plan_stage": "preliminary",
            "solar_forecast_kwh": 4,
        }
        completed = [{"date": "2026-09-05", "kwh": 10, "complete": True}]
        self.policy.update(preliminary, completed)
        self.now = datetime.fromisoformat("2026-09-06T05:00:00+03:00")
        morning = dict(preliminary, observed_at=self.now.isoformat(),
                       forecast_plan_stage="morning", solar_forecast_kwh=None)
        self.policy.update(morning, completed)
        state = self.policy.status_attributes()
        self.assertEqual(4, state["solar_forecast_kwh"])
        self.assertEqual(40, state["recommended_soc"])
        self.assertEqual("morning_unavailable_preliminary_retained",
                         state["forecast_revision_status"])

    def test_incomplete_or_old_consumption_not_a_zero_deficit(self):
        self.update()
        self.now += timedelta(days=1)
        payload = daily(solar=30)
        payload.update(date=self.now.date().isoformat(), observed_at=self.now.isoformat())
        self.policy.update(payload, [{"date": "2026-09-05", "kwh": 2, "complete": False}])
        self.assertEqual(40, self.policy.status_attributes()["recommended_soc"])
        self.assertIn("consumption_history_incomplete", self.policy.status_attributes()["evidence_issues"])

    def test_final_daily_samples_require_end_of_day_evidence(self):
        service = DailySummaryService.__new__(DailySummaryService)
        service.timezone = ZoneInfo("Europe/Kyiv")
        service.history = {
            "2026-09-04": {"house_consumption_kwh": 5, "source_timestamp": "2026-09-04T23:51:00+03:00"},
            "2026-09-03": {"house_consumption_kwh": 2, "source_timestamp": "2026-09-03T12:00:00+03:00"},
            "2026-09-02": {"house_consumption_kwh": 8},
        }
        selected = service.recent_consumption(NOW.date(), require_final=True)
        self.assertEqual(["2026-09-04"], [item["date"] for item in selected])

    def test_final_daily_samples_accept_ha_unix_timestamp(self):
        service = DailySummaryService.__new__(DailySummaryService)
        service.timezone = ZoneInfo("Europe/Kyiv")
        captured = datetime.fromisoformat("2026-09-04T23:51:00+03:00").timestamp()
        service.history = {
            "2026-09-04": {
                "house_consumption_kwh": 5.9,
                "source_timestamp": str(int(captured)),
            },
        }
        selected = service.recent_consumption(NOW.date(), require_final=True)
        self.assertEqual(
            [{"date": "2026-09-04", "kwh": 5.9, "complete": True}],
            selected,
        )
