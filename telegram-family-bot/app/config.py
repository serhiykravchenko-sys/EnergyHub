from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_OPTIONS_FILE = Path("/data/options.json")


@dataclass(frozen=True)
class Config:
    bot_token: str
    destination_chat_id: str
    weather_entity: str
    send_time: str
    soc_snapshot_time: str
    night_start_time: str
    timezone: str
    useful_solar_threshold_w: int
    strong_wind_threshold_ms: float
    test_mode: bool
    battery_soc_entity: str
    target_soc_entity: str
    ahm_minimum_soc_entity: str
    reserve_advice_entity: str
    reserve_advice_current_soc_entity: str
    reserve_advice_suggested_soc_entity: str
    reserve_advice_sample_count_entity: str
    operating_mode_entity: str
    yesterday_consumption_entity: str
    solar_forecast_entity: str
    sun_entity: str
    moon_entity: str
    daily_grid_import_entity: str
    yesterday_grid_import_entity: str
    grid_voltage_entity: str
    grid_confidence_entity: str
    telemetry_freshness_entity: str
    heat_pump_active_threshold_w: float
    heat_pump_floor_1_power_entity: str
    heat_pump_floor_2_power_entity: str
    heat_pump_floor_3_power_entity: str
    state_file: Path


def _time(value: object, fallback: str) -> str:
    candidate = str(value or fallback).strip()
    parts = candidate.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time {candidate!r}; expected HH:MM")
    hour, minute = (int(part) for part in parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time {candidate!r}; expected HH:MM")
    return f"{hour:02d}:{minute:02d}"


def load_config(path: Path | None = None) -> Config:
    options_file = path or Path(os.environ.get("OPTIONS_FILE", DEFAULT_OPTIONS_FILE))
    with options_file.open("r", encoding="utf-8") as handle:
        options = json.load(handle)

    return Config(
        bot_token=str(options.get("bot_token") or "").strip(),
        destination_chat_id=str(options.get("destination_chat_id") or "").strip(),
        weather_entity=(
            ""
            if str(options.get("weather_entity") or "auto").strip().lower() == "auto"
            else str(options.get("weather_entity") or "").strip()
        ),
        send_time=_time(options.get("send_time"), "08:00"),
        soc_snapshot_time=_time(options.get("soc_snapshot_time"), "07:00"),
        night_start_time=_time(options.get("night_start_time"), "23:00"),
        timezone=str(options.get("timezone") or "Europe/Kyiv"),
        useful_solar_threshold_w=max(50, int(options.get("useful_solar_threshold_w", 300))),
        strong_wind_threshold_ms=max(5.0, float(options.get("strong_wind_threshold_ms", 15))),
        test_mode=bool(options.get("test_mode", True)),
        battery_soc_entity=str(options.get("battery_soc_entity") or "sensor.powmr_10_2m_battery_soc"),
        target_soc_entity=str(options.get("target_soc_entity") or "sensor.energyhub_hybrid_target_soc"),
        ahm_minimum_soc_entity=str(options.get("ahm_minimum_soc_entity") or "input_number.ahm_minimum_soc"),
        reserve_advice_entity=str(options.get("reserve_advice_entity") or "sensor.energyhub_ahm_reserve_advice"),
        reserve_advice_current_soc_entity=str(options.get("reserve_advice_current_soc_entity") or "sensor.energyhub_ahm_reserve_advice_current_soc"),
        reserve_advice_suggested_soc_entity=str(options.get("reserve_advice_suggested_soc_entity") or "sensor.energyhub_ahm_reserve_advice_suggested_soc"),
        reserve_advice_sample_count_entity=str(options.get("reserve_advice_sample_count_entity") or "sensor.energyhub_ahm_reserve_advice_sample_count"),
        operating_mode_entity=str(options.get("operating_mode_entity") or "sensor.energyhub_operating_mode"),
        yesterday_consumption_entity=str(options.get("yesterday_consumption_entity") or "sensor.energyhub_daily_house_consumption"),
        solar_forecast_entity=str(options.get("solar_forecast_entity") or "sensor.solcast_pv_forecast_forecast_today"),
        sun_entity=str(options.get("sun_entity") or "sun.sun"),
        moon_entity=str(options.get("moon_entity") or "moon.moon"),
        daily_grid_import_entity=str(options.get("daily_grid_import_entity") or "sensor.energyhub_daily_grid_import_estimated"),
        yesterday_grid_import_entity=str(options.get("yesterday_grid_import_entity") or "sensor.energyhub_grid_import_yesterday_estimated"),
        grid_voltage_entity=str(options.get("grid_voltage_entity") or "sensor.powmr_10_2m_grid_voltage"),
        grid_confidence_entity=str(options.get("grid_confidence_entity") or "sensor.energyhub_grid_confidence"),
        telemetry_freshness_entity=str(options.get("telemetry_freshness_entity") or "sensor.energyhub_telemetry_freshness"),
        heat_pump_active_threshold_w=max(0.0, float(options.get("heat_pump_active_threshold_w", 50))),
        heat_pump_floor_1_power_entity=str(options.get("heat_pump_floor_1_power_entity") or "sensor.first_floor_heat_pump_plug_power"),
        heat_pump_floor_2_power_entity=str(options.get("heat_pump_floor_2_power_entity") or "sensor.second_floor_heat_pump_plug_power"),
        heat_pump_floor_3_power_entity=str(options.get("heat_pump_floor_3_power_entity") or "sensor.chuangmi_212a01_ea40_electric_power"),
        state_file=Path(os.environ.get("STATE_FILE", "/data/telegram-family-assistant-state.json")),
    )
