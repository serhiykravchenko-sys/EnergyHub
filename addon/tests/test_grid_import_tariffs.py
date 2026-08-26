from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.services.grid_import import GridImportService


class GridImportTariffTests(unittest.TestCase):
    def make_service(self, path: Path, now: datetime) -> GridImportService:
        return GridImportService(
            path=path,
            clock=lambda: now,
            timezone_name="Europe/Kyiv",
        )

    def integrate(self, service, start, end, power_w=3600, soc=50):
        service.update(
            operating_mode="hybrid_grid_hold",
            output_power_w=power_w,
            battery_soc=soc,
            now=start,
        )
        service.last_update_monotonic = 100.0
        service.last_update_at = start
        with patch(
            "app.services.grid_import.time.monotonic",
            side_effect=[120.0] * 8,
        ):
            service.update(
                operating_mode="hybrid_grid_hold",
                output_power_w=power_w,
                battery_soc=soc,
                now=end,
            )

    def test_2300_boundary_splits_one_interval_between_tariffs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid_import.json"
            service = self.make_service(
                path, datetime.fromisoformat("2026-08-22T22:59:50+03:00")
            )
            self.integrate(
                service,
                datetime.fromisoformat("2026-08-22T22:59:50+03:00"),
                datetime.fromisoformat("2026-08-22T23:00:10+03:00"),
            )

            self.assertAlmostEqual(0.01, service.normal_energy_kwh, places=6)
            self.assertAlmostEqual(0.01, service.night_energy_kwh, places=6)
            self.assertAlmostEqual(0.075, service.daily_cost_uah, places=6)

    def test_midnight_closes_previous_calendar_day_and_keeps_0000_night(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid_import.json"
            service = self.make_service(
                path, datetime.fromisoformat("2026-08-22T23:59:50+03:00")
            )
            self.integrate(
                service,
                datetime.fromisoformat("2026-08-22T23:59:50+03:00"),
                datetime.fromisoformat("2026-08-23T00:00:10+03:00"),
            )

            self.assertEqual("2026-08-23", service.date)
            self.assertAlmostEqual(
                0.01,
                service.daily_tariff_history["2026-08-22"]["night_kwh"],
                places=6,
            )
            self.assertAlmostEqual(0.01, service.night_energy_kwh, places=6)
            self.assertAlmostEqual(0.01, service.yesterday_energy_kwh, places=6)
            self.assertEqual(
                "unknown",
                service.mqtt_values()["grid_import_night_yesterday_estimated"],
            )
            self.assertIn(
                ("2026-08-22", 0.01),
                service.get_pending_day_finalizations(),
            )

    def test_full_day_started_at_midnight_publishes_completed_tariffs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid_import.json"
            service = self.make_service(
                path, datetime.fromisoformat("2026-08-22T00:00:00+03:00")
            )
            self.integrate(
                service,
                datetime.fromisoformat("2026-08-22T23:59:50+03:00"),
                datetime.fromisoformat("2026-08-23T00:00:10+03:00"),
            )
            self.assertAlmostEqual(
                0.01, service.yesterday_night_energy_kwh, places=6
            )
            self.assertAlmostEqual(0.025, service.yesterday_cost_uah, places=6)

    def test_restart_restores_tariff_totals_and_month_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid_import.json"
            now = datetime.fromisoformat("2026-08-22T06:00:00+03:00")
            service = self.make_service(path, now)
            service.house_energy_kwh = 3.0
            service._add_tariff_energy("night", "house", 3.0)
            service.daily_tariff_history["2026-08-21"] = {
                "night_kwh": 2.0,
                "normal_kwh": 1.0,
                "night_cost_uah": 5.0,
                "normal_cost_uah": 5.0,
            }
            service.save()

            restored = self.make_service(path, now)
            month = restored.month_to_date()
            self.assertAlmostEqual(3.0, restored.night_energy_kwh)
            self.assertAlmostEqual(5.0, month["night_kwh"])
            self.assertAlmostEqual(1.0, month["normal_kwh"])
            self.assertAlmostEqual(17.5, month["cost_uah"])

    def test_schema_two_migration_preserves_existing_total_without_guessing_tariff(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid_import.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "date": "2026-08-22",
                        "house_energy_kwh": 4.0,
                        "battery_energy_kwh": 1.0,
                    }
                ),
                encoding="utf-8",
            )
            service = self.make_service(
                path, datetime.fromisoformat("2026-08-22T12:00:00+03:00")
            )

            self.assertEqual(5.0, service.daily_energy_kwh)
            self.assertEqual(0.0, service.night_energy_kwh)
            self.assertEqual(0.0, service.normal_energy_kwh)

    def test_battery_soc_gain_uses_tariff_at_observation_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid_import.json"
            service = self.make_service(
                path, datetime.fromisoformat("2026-08-22T06:00:00+03:00")
            )
            service.update(
                operating_mode="hybrid_charging",
                output_power_w=0,
                battery_soc=50,
                now=datetime.fromisoformat("2026-08-22T06:00:00+03:00"),
            )
            service.update(
                operating_mode="hybrid_charging",
                output_power_w=0,
                battery_soc=55,
                now=datetime.fromisoformat("2026-08-22T06:00:10+03:00"),
            )
            self.assertAlmostEqual(0.8, service.night_energy_kwh)
            self.assertAlmostEqual(2.0, service.daily_cost_uah)

    def test_both_fall_back_ambiguous_hours_remain_night_tariff(self):
        with tempfile.TemporaryDirectory() as directory:
            timezone = ZoneInfo("Europe/Kyiv")
            service = self.make_service(
                Path(directory) / "grid_import.json",
                datetime(2026, 10, 25, 3, 30, tzinfo=timezone),
            )

            first = datetime(2026, 10, 25, 3, 30, tzinfo=timezone, fold=0)
            second = datetime(2026, 10, 25, 3, 30, tzinfo=timezone, fold=1)

            self.assertEqual("night", service._tariff_for(first))
            self.assertEqual("night", service._tariff_for(second))

    def test_spring_clock_jump_uses_monotonic_poll_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            timezone = ZoneInfo("Europe/Kyiv")
            path = Path(directory) / "grid_import.json"
            before = datetime(2026, 3, 29, 2, 59, 50, tzinfo=timezone)
            after = datetime(2026, 3, 29, 4, 0, 10, tzinfo=timezone)
            service = self.make_service(path, before)

            service.update(
                operating_mode="hybrid_grid_hold",
                output_power_w=3600,
                battery_soc=50,
                now=before,
            )
            service.last_update_monotonic = 100.0
            service.last_update_at = before
            with patch(
                "app.services.grid_import.time.monotonic",
                side_effect=[120.0] * 8,
            ):
                service.update(
                    operating_mode="hybrid_grid_hold",
                    output_power_w=3600,
                    battery_soc=50,
                    now=after,
                )

            self.assertAlmostEqual(0.02, service.night_energy_kwh, places=6)


if __name__ == "__main__":
    unittest.main()
