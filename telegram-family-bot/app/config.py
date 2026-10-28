from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .device_health import (
    EnvironmentSensor,
    SmartPlug,
    parse_environment_sensors,
    parse_smart_plugs,
)
from .house_monitor import parse_targets, DeviceTarget, DEFAULT_DEVICES
from .bms_evidence import parse_mapping as parse_bms_mapping


DEFAULT_OPTIONS_FILE = Path("/data/options.json")


@dataclass(frozen=True)
class Config:
    bot_token: str
    destination_chat_id: str
    technical_chat_id: str
    weather_entity: str
    uhmc_weather_source: str
    uhmc_weather_mqtt_topic: str
    family_calendar_ical_url: str
    send_time: str
    timezone: str
    useful_solar_threshold_w: int
    battery_capacity_kwh: float
    battery_nominal_voltage_v: float
    battery_grid_charge_current_a: float
    battery_charge_efficiency: float
    house_grid_reference_current_a: float
    strong_wind_threshold_ms: float
    weather_humidity_low_percent: float
    weather_humidity_high_percent: float
    weather_humidity_change_percent: float
    battery_soc_entity: str
    ahm_minimum_soc_entity: str
    operating_mode_entity: str
    yesterday_consumption_entity: str
    solar_forecast_entity: str
    sun_entity: str
    moon_entity: str
    daily_grid_import_entity: str
    yesterday_grid_import_entity: str
    yesterday_night_grid_import_entity: str
    yesterday_normal_grid_import_entity: str
    yesterday_grid_import_cost_entity: str
    month_night_grid_import_entity: str
    month_normal_grid_import_entity: str
    month_grid_import_entity: str
    month_grid_import_cost_entity: str
    night_grid_import_price_entity: str
    normal_grid_import_price_entity: str
    grid_voltage_entity: str
    grid_confidence_entity: str
    grid_available_24h_entity: str
    grid_outage_24h_entity: str
    telemetry_freshness_entity: str
    soc_anomaly_latest_entity: str
    peak_load_guard_event_entity: str
    weather_buffer_entity: str
    inverter_message_entities: tuple[str, ...]
    heat_pump_active_threshold_w: float
    heat_pump_floor_1_power_entity: str
    heat_pump_floor_2_power_entity: str
    heat_pump_floor_3_power_entity: str
    environment_sensors: tuple[EnvironmentSensor, ...]
    environment_stale_hours: float
    environment_temperature_deviation_c: float
    environment_humidity_deviation_percent: float
    environment_persistence_minutes: int
    device_low_battery_percent: float
    doorbell_battery_entity: str
    smart_plugs: tuple[SmartPlug, ...]
    state_file: Path
    heat_pump_floor_1_energy_entity: str = 'sensor.first_floor_heat_pump_plug_energy'
    heat_pump_floor_2_energy_entity: str = 'sensor.second_floor_heat_pump_plug_energy'
    water_boiler_energy_entity: str = 'sensor.water_boiler_energy_calculated'
    heat_pump_floor_3_energy_entity: str = 'sensor.third_floor_heat_pump_energy_calculated'
    house_monitor_enabled: bool = True
    monitored_devices: tuple[DeviceTarget, ...] = ()
    bms_entities: tuple[DeviceTarget, ...] = ()
    co2_sensors: tuple[DeviceTarget, ...] = ()
    log_monitor_enabled: bool = False
    solcast_last_success_entity: str = ''
    co_alarms: tuple[DeviceTarget, ...] = ()
    family_quiet_start: str = '23:00'
    family_quiet_end: str = '08:01'
    apartment_grid_proxy_entity: str = ''
    apartment_grid_cloud_enabled: bool = True
    dtek_schedule_enabled: bool = False
    dtek_dacha_group: str = ''
    dtek_apartment_group: str = ''
    dtek_dacha_district: str = ''
    dtek_apartment_district: str = ''
    dtek_solar_forecast_tomorrow_entity: str = 'sensor.solcast_pv_forecast_forecast_tomorrow'
    solar_forecast_day3_entity: str = 'sensor.solcast_pv_forecast_forecast_day_3'
    beacon_recovery_enabled: bool = True
    automation_notifications_enabled: bool = False
    notification_mqtt_host: str = 'core-mosquitto'
    notification_mqtt_port: int = 1883
    notification_mqtt_user: str = ''
    notification_mqtt_password: str = ''


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
        automation_notifications_enabled=options.get('automation_notifications_enabled') is True,
        notification_mqtt_host=str(options.get('notification_mqtt_host') or 'core-mosquitto').strip(),
        notification_mqtt_port=int(options.get('notification_mqtt_port', 1883)),
        notification_mqtt_user=str(options.get('notification_mqtt_user') or ''),
        notification_mqtt_password=str(options.get('notification_mqtt_password') or ''),
        bot_token=str(options.get("bot_token") or "").strip(),
        destination_chat_id=str(options.get("destination_chat_id") or "").strip(),
        technical_chat_id=str(options.get("technical_chat_id") or "").strip(),
        weather_entity=(
            ""
            if str(options.get("weather_entity") or "auto").strip().lower() == "auto"
            else str(options.get("weather_entity") or "").strip()
        ),
        uhmc_weather_source=str(
            options.get("uhmc_weather_source") or "uhmc1921"
        ).strip().lstrip("@"),
        uhmc_weather_mqtt_topic=str(
            options.get("uhmc_weather_mqtt_topic")
            or "energyhub/input/weather/uhmc"
        ).strip(),
        family_calendar_ical_url=str(options.get("family_calendar_ical_url") or "").strip(),
        send_time=_time(options.get("send_time"), "08:00"),
        family_quiet_start=_time(options.get('family_quiet_start'), '23:00'),
        family_quiet_end=_time(options.get('family_quiet_end'), '08:01'),
        timezone=str(options.get("timezone") or "Europe/Kyiv"),
        useful_solar_threshold_w=max(50, int(options.get("useful_solar_threshold_w", 300))),
        battery_capacity_kwh=max(1.0, float(options.get("battery_capacity_kwh", 16))),
        battery_nominal_voltage_v=max(12.0, float(options.get("battery_nominal_voltage_v", 51.2))),
        battery_grid_charge_current_a=max(1.0, float(options.get("battery_grid_charge_current_a", 30))),
        battery_charge_efficiency=max(0.5, min(1.0, float(options.get("battery_charge_efficiency", 0.9)))),
        house_grid_reference_current_a=max(1.0, float(options.get("house_grid_reference_current_a", 16))),
        strong_wind_threshold_ms=max(5.0, float(options.get("strong_wind_threshold_ms", 15))),
        weather_humidity_low_percent=max(
            0.0,
            min(100.0, float(
                30
                if options.get("weather_humidity_low_percent") is None
                else options["weather_humidity_low_percent"]
            )),
        ),
        weather_humidity_high_percent=max(
            0.0,
            min(100.0, float(
                80
                if options.get("weather_humidity_high_percent") is None
                else options["weather_humidity_high_percent"]
            )),
        ),
        weather_humidity_change_percent=max(
            1.0,
            min(100.0, float(
                25
                if options.get("weather_humidity_change_percent") is None
                else options["weather_humidity_change_percent"]
            )),
        ),
        battery_soc_entity=str(options.get("battery_soc_entity") or "sensor.powmr_10_2m_battery_soc"),
        ahm_minimum_soc_entity=str(options.get("ahm_minimum_soc_entity") or "input_number.ahm_minimum_soc"),
        operating_mode_entity=str(options.get("operating_mode_entity") or "sensor.energyhub_operating_mode"),
        yesterday_consumption_entity=str(options.get("yesterday_consumption_entity") or "sensor.energyhub_daily_house_consumption"),
        solar_forecast_entity=str(options.get("solar_forecast_entity") or "sensor.solcast_pv_forecast_forecast_today"),
        sun_entity=str(options.get("sun_entity") or "sun.sun"),
        moon_entity=str(options.get("moon_entity") or "moon.moon"),
        daily_grid_import_entity=str(options.get("daily_grid_import_entity") or "sensor.energyhub_daily_grid_import_estimated"),
        yesterday_grid_import_entity=str(options.get("yesterday_grid_import_entity") or "sensor.energyhub_grid_import_yesterday_estimated"),
        yesterday_night_grid_import_entity=str(options.get("yesterday_night_grid_import_entity") or "sensor.energyhub_grid_import_night_yesterday_estimated"),
        yesterday_normal_grid_import_entity=str(options.get("yesterday_normal_grid_import_entity") or "sensor.energyhub_grid_import_normal_yesterday_estimated"),
        yesterday_grid_import_cost_entity=str(options.get("yesterday_grid_import_cost_entity") or "sensor.energyhub_grid_import_cost_yesterday_estimated"),
        month_night_grid_import_entity=str(options.get("month_night_grid_import_entity") or "sensor.energyhub_grid_import_night_month_estimated"),
        month_normal_grid_import_entity=str(options.get("month_normal_grid_import_entity") or "sensor.energyhub_grid_import_normal_month_estimated"),
        month_grid_import_entity=str(options.get("month_grid_import_entity") or "sensor.energyhub_grid_import_month_estimated"),
        month_grid_import_cost_entity=str(options.get("month_grid_import_cost_entity") or "sensor.energyhub_grid_import_cost_month_estimated"),
        night_grid_import_price_entity=str(options.get("night_grid_import_price_entity") or "sensor.energyhub_grid_import_night_price"),
        normal_grid_import_price_entity=str(options.get("normal_grid_import_price_entity") or "sensor.energyhub_grid_import_normal_price"),
        grid_voltage_entity=str(options.get("grid_voltage_entity") or "sensor.powmr_10_2m_grid_voltage"),
        grid_confidence_entity=str(options.get("grid_confidence_entity") or "sensor.energyhub_grid_confidence"),
        grid_available_24h_entity=str(options.get("grid_available_24h_entity") or "sensor.energyhub_grid_available_24h"),
        grid_outage_24h_entity=str(options.get("grid_outage_24h_entity") or "sensor.energyhub_grid_outage_24h"),
        telemetry_freshness_entity=str(options.get("telemetry_freshness_entity") or "sensor.energyhub_telemetry_freshness"),
        soc_anomaly_latest_entity=str(
            options.get("soc_anomaly_latest_entity")
            or "sensor.energyhub_soc_anomaly_latest"
        ),
        peak_load_guard_event_entity=str(
            options.get("peak_load_guard_event_entity")
            or "sensor.energyhub_peak_load_guard_event"
        ),
        weather_buffer_entity=str(
            options.get("weather_buffer_entity")
            or "sensor.energyhub_ahm_weather_buffer"
        ),
        inverter_message_entities=tuple(
            item.strip()
            for item in str(
                options.get("inverter_message_entities")
                or "sensor.energyhub_inverter_fault_recent_1;"
                "sensor.energyhub_inverter_fault_recent_2;"
                "sensor.energyhub_inverter_fault_recent_3"
            ).split(";")
            if item.strip()
        ),
        heat_pump_active_threshold_w=max(0.0, float(options.get("heat_pump_active_threshold_w", 50))),
        heat_pump_floor_1_power_entity=str(options.get("heat_pump_floor_1_power_entity") or "sensor.first_floor_heat_pump_plug_power"),
        heat_pump_floor_2_power_entity=str(options.get("heat_pump_floor_2_power_entity") or "sensor.second_floor_heat_pump_plug_power"),
        heat_pump_floor_3_power_entity=str(options.get("heat_pump_floor_3_power_entity") or "sensor.third_floor_heat_pump_plug_electric_power"),
        heat_pump_floor_1_energy_entity=str(options.get('heat_pump_floor_1_energy_entity') or 'sensor.first_floor_heat_pump_plug_energy'),
        heat_pump_floor_2_energy_entity=str(options.get('heat_pump_floor_2_energy_entity') or 'sensor.second_floor_heat_pump_plug_energy'),
        water_boiler_energy_entity=str(options.get('water_boiler_energy_entity', 'sensor.water_boiler_energy_calculated')),
        heat_pump_floor_3_energy_entity=str(options.get('heat_pump_floor_3_energy_entity') or 'sensor.third_floor_heat_pump_energy_calculated'),
        environment_sensors=parse_environment_sensors(
            options.get("environment_sensor_entities", "")
        ),
        environment_stale_hours=max(
            1.0,
            float(options.get("environment_stale_hours", 24)),
        ),
        environment_temperature_deviation_c=max(
            0.5,
            float(options.get("environment_temperature_deviation_c", 5)),
        ),
        environment_humidity_deviation_percent=max(
            1.0,
            float(options.get("environment_humidity_deviation_percent", 20)),
        ),
        environment_persistence_minutes=max(
            0,
            int(options.get("environment_persistence_minutes", 60)),
        ),
        device_low_battery_percent=max(
            1.0,
            min(100.0, float(options.get("device_low_battery_percent", 10))),
        ),
        doorbell_battery_entity=str(
            options.get("doorbell_battery_entity") or ""
        ).strip(),
        smart_plugs=parse_smart_plugs(options.get("smart_plug_entities", "")),
        beacon_recovery_enabled=options.get('beacon_recovery_enabled', True) is True,
        solcast_last_success_entity=str(options.get('solcast_last_success_entity', '') or 'sensor.solcast_pv_forecast_api_last_polled'),
        solar_forecast_day3_entity=str(options.get('solar_forecast_day3_entity') or 'sensor.solcast_pv_forecast_forecast_day_3'),
        state_file=Path(os.environ.get("STATE_FILE", "/data/telegram-family-assistant-state.json")),
        house_monitor_enabled=bool(options.get('house_monitor_enabled', True)),
        monitored_devices=parse_targets(options.get('monitored_device_entities', DEFAULT_DEVICES)),
        bms_entities=parse_bms_mapping(options.get('bms_entity_mapping', '')),
        co2_sensors=parse_targets(options.get('co2_sensor_entities', '')),
        log_monitor_enabled=bool(options.get('log_monitor_enabled', False)),
        co_alarms=parse_targets(options.get('co_alarm_entities', '')),
        apartment_grid_proxy_entity=str(options.get('apartment_grid_proxy_entity') or '').strip(),
        apartment_grid_cloud_enabled=options.get('apartment_grid_cloud_enabled',True) is True,
        dtek_schedule_enabled=options.get('dtek_schedule_enabled') is True,
        dtek_dacha_group=str(options.get('dtek_dacha_group') or '').strip(),
        dtek_apartment_group=str(options.get('dtek_apartment_group') or '').strip(),
        dtek_dacha_district=str(options.get('dtek_dacha_district') or '').strip(),
        dtek_apartment_district=str(options.get('dtek_apartment_district') or '').strip(),
        dtek_solar_forecast_tomorrow_entity=str(options.get('dtek_solar_forecast_tomorrow_entity') or '').strip(),
    )
