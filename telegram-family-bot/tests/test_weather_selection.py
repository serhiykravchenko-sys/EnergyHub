from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.home_assistant import HomeAssistantError
from app.main import fetch_weather


class FakeWeatherClient:
    def states(self):
        return [
            {"entity_id": "weather.forecast_home"},
            {"entity_id": "weather.hourly_provider"},
        ]

    def forecast(self, entity_id, forecast_type):
        if entity_id == "weather.forecast_home" and forecast_type == "hourly":
            raise HomeAssistantError("HTTP 400: hourly is not supported")
        return [{
            "datetime": "2026-08-11T12:00:00+03:00",
            "condition": "sunny",
            "temperature": 25,
        }]

    def state(self, entity_id):
        return {"state": "sunny", "attributes": {"wind_speed_unit": "km/h"}}


class WeatherSelectionTests(unittest.TestCase):
    def test_tries_next_entity_after_unsupported_hourly_forecast(self):
        config = SimpleNamespace(weather_entity="", timezone="Europe/Kyiv", strong_wind_threshold_ms=15)
        now = datetime(2026, 8, 11, 10, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
        lines = fetch_weather(config, FakeWeatherClient(), now)
        self.assertIn("сонячно", lines[0])


if __name__ == "__main__":
    unittest.main()
