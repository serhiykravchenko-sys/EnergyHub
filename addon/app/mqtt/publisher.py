import json

import paho.mqtt.client as mqtt

from app.config import (
    BASE_TOPIC,
    ENERGYHUB_AVAILABILITY_TOPIC,
    INVERTER_AVAILABILITY_TOPIC,
    SENSORS,
)
from app.utils.logger import log


OUTPUT_SOURCE_PRIORITY_MAP = {
    "Solar Battery Utility": "SBU",
    "Solar Utility Battery": "SUB",
}


# Stable entity IDs for fresh Home Assistant installations. Existing entities
# keep their registry IDs; these values are used only when an MQTT entity is
# created for the first time.
POWMR_DEFAULT_ENTITY_IDS = {
    "ac_input_voltage": "sensor.powmr_10_2m_grid_voltage",
    "ac_input_frequency": "sensor.powmr_10_2m_grid_frequency",
    "ac_output_voltage": "sensor.powmr_10_2m_output_voltage",
    "ac_output_frequency": "sensor.powmr_10_2m_output_frequency",
    "ac_output_active_power": "sensor.powmr_10_2m_output_power",
    "ac_output_apparent_power": "sensor.powmr_10_2m_apparent_power",
    "ac_output_load": "sensor.powmr_10_2m_load",
    "bus_voltage": "sensor.powmr_10_2m_bus_voltage",
    "battery_voltage": "sensor.powmr_10_2m_battery_voltage",
    "battery_voltage_from_scc": (
        "sensor.powmr_10_2m_battery_voltage_from_scc"
    ),
    "battery_capacity": "sensor.powmr_10_2m_battery_soc",
    "battery_charging_current": (
        "sensor.powmr_10_2m_battery_charging_current"
    ),
    "battery_discharge_current": (
        "sensor.powmr_10_2m_battery_discharge_current"
    ),
    "pv1_input_voltage": "sensor.powmr_10_2m_pv1_voltage",
    "pv1_input_current": "sensor.powmr_10_2m_pv1_current",
    "pv1_charging_power": "sensor.powmr_10_2m_pv1_power",
    "inverter_heat_sink_temperature": (
        "sensor.powmr_10_2m_temperature"
    ),
}

ENERGYHUB_DEFAULT_ENTITY_ID_OVERRIDES = {
    "grid_available_hours_24h": "sensor.energyhub_grid_available_24h",
    "grid_available_hours_48h": "sensor.energyhub_grid_available_48h",
    "grid_outage_hours_24h": "sensor.energyhub_grid_outage_24h",
    "grid_availability_percent_24h": (
        "sensor.energyhub_grid_availability_24h"
    ),
    "grid_confidence_level": "sensor.energyhub_grid_confidence",
    "house_load_unchanged_minutes": (
        "sensor.energyhub_house_load_unchanged"
    ),
    "daily_grid_import": "sensor.energyhub_daily_summary_grid_import",
}


def make_client(options):
    client = mqtt.Client(client_id="energy_hub_powmr")
    client.username_pw_set(
        options["mqtt_user"],
        options["mqtt_password"],
    )
    client.will_set(
        ENERGYHUB_AVAILABILITY_TOPIC,
        "offline",
        retain=True,
    )
    return client


def publish_discovery(client, device_name):
    device = {
        "identifiers": ["powmr_10_2m"],
        "name": device_name,
        "manufacturer": "PowMr",
        "model": "10.2M",
    }

    for key, (name, unit, device_class, state_class) in SENSORS.items():
        unique_id = f"powmr_10_2m_{key}"

        payload = {
            "name": name,
            "unique_id": unique_id,
            "default_entity_id": POWMR_DEFAULT_ENTITY_IDS[key],
            "state_topic": f"{BASE_TOPIC}/{key}/state",
            "availability": [
                {"topic": ENERGYHUB_AVAILABILITY_TOPIC},
                {"topic": INVERTER_AVAILABILITY_TOPIC},
            ],
            "availability_mode": "all",
            "device": device,
        }

        if unit:
            payload["unit_of_measurement"] = unit

        if device_class:
            payload["device_class"] = device_class

        if state_class:
            payload["state_class"] = state_class

        topic = f"homeassistant/sensor/{unique_id}/config"
        client.publish(
            topic,
            json.dumps(payload),
            retain=True,
        )

    log("MQTT discovery published")


def publish_values(client, data, previous):
    published = 0

    for key in SENSORS:
        if key not in data:
            continue

        value = data.get(key)

        if not is_valid_value(key, value):
            continue

        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )
        published += 1

    client.publish(
        INVERTER_AVAILABILITY_TOPIC,
        "online",
        retain=True,
    )

    return published


def is_valid_value(key, value):
    if value is None:
        return False

    if key == "battery_capacity":
        try:
            soc = float(value)
        except Exception:
            return False

        if soc < 0 or soc > 100:
            log(f"Skip invalid SOC: {soc}")
            return False

    return True


def publish_grid_history(client, history, stability):
    values = {
        "grid_available_hours_24h": history.available_hours(24),
        "grid_available_hours_48h": history.available_hours(48),
        "grid_outage_hours_24h": history.outage_hours(24),
        "grid_availability_percent_24h": history.availability_percent(24),
        "grid_confidence_level": stability.level(),
    }

    for key, value in values.items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_grid_discovery(client):
    device = _energyhub_device()

    sensors = {
        "grid_available_hours_24h": (
            "Grid Available 24h",
            "h",
            None,
            "measurement",
        ),
        "grid_available_hours_48h": (
            "Grid Available 48h",
            "h",
            None,
            "measurement",
        ),
        "grid_outage_hours_24h": (
            "Grid Outage 24h",
            "h",
            None,
            "measurement",
        ),
        "grid_availability_percent_24h": (
            "Grid Availability 24h",
            "%",
            None,
            "measurement",
        ),
        "grid_confidence_level": (
            "Grid Confidence",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Grid MQTT discovery published")


def publish_grid_import(client, grid_import):
    for key, value in grid_import.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_grid_import_discovery(client):
    device = _energyhub_device()

    sensors = {
        "grid_import_power_estimated": (
            "Grid-Supplied House Power Estimated",
            "W",
            "power",
            "measurement",
        ),
        "daily_grid_import_estimated": (
            "Grid Import Today Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_yesterday_estimated": (
            "Grid Import Yesterday Estimated",
            "kWh",
            "energy",
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Grid Import MQTT discovery published")


def publish_health(client, health):
    for key, value in health.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_health_discovery(client):
    device = _energyhub_device()

    sensors = {
        "communication_status": (
            "Communication Status",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Health MQTT discovery published")


def publish_daily_summary(client, daily_summary):
    for key, value in daily_summary.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_daily_summary_discovery(client):
    device = _energyhub_device()

    sensors = {
        "daily_house_consumption": (
            "Daily House Consumption",
            "kWh",
            "energy",
            None,
        ),
        "daily_solar_forecast": (
            "Daily Solar Forecast",
            "kWh",
            "energy",
            None,
        ),
        "daily_solar_surplus_estimated": (
            "Daily Solar Surplus Estimated",
            "kWh",
            "energy",
            None,
        ),
        "daily_grid_import": (
            "Daily Summary Grid Import",
            "kWh",
            "energy",
            None,
        ),
        "daily_grid_availability": (
            "Daily Grid Availability",
            "%",
            None,
            "measurement",
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Daily Summary MQTT discovery published")


def publish_battery_health(client, battery_health):
    for key, value in battery_health.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_battery_health_discovery(client):
    device = _energyhub_device()

    sensors = {
        "battery_health": (
            "Battery Health",
            None,
            None,
            None,
        ),
        "battery_health_reason": (
            "Battery Health Reason",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Battery Health MQTT discovery published")


def publish_telemetry_freshness(client, telemetry_freshness):
    for key, value in telemetry_freshness.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_telemetry_freshness_discovery(client):
    device = _energyhub_device()

    sensors = {
        "telemetry_freshness": (
            "Telemetry Freshness",
            None,
            None,
            None,
        ),
        "telemetry_freshness_reason": (
            "Telemetry Freshness Reason",
            None,
            None,
            None,
        ),
        "house_load_unchanged_minutes": (
            "House Load Unchanged",
            "min",
            None,
            "measurement",
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Telemetry Freshness MQTT discovery published")


def publish_inverter_health(client, inverter_health):
    for key, value in inverter_health.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_inverter_health_discovery(client):
    device = _energyhub_device()

    sensors = {
        "inverter_health": (
            "Inverter Health",
            None,
            None,
            None,
        ),
        "inverter_health_reason": (
            "Inverter Health Reason",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    # Remove the obsolete retained MQTT Discovery entity and its
    # retained state from installations upgraded from an earlier build.
    client.publish(
        "homeassistant/sensor/"
        "energyhub_inverter_warning_raw/config",
        b"",
        retain=True,
    )
    client.publish(
        f"{BASE_TOPIC}/inverter_warning_raw/state",
        b"",
        retain=True,
    )

    log("Inverter Health MQTT discovery published")


def publish_system_health(client, system_health):
    for key, value in system_health.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_system_health_discovery(client):
    device = _energyhub_device()

    sensors = {
        "system_health": (
            "System Health",
            None,
            None,
            None,
        ),
        "system_health_reason": (
            "System Health Reason",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("System Health MQTT discovery published")


def publish_inverter_settings(client, settings):
    raw_output_priority = settings.get(
        "output_source_priority"
    )

    if raw_output_priority is None:
        return

    output_priority = OUTPUT_SOURCE_PRIORITY_MAP.get(
        raw_output_priority,
        raw_output_priority,
    )

    client.publish(
        f"{BASE_TOPIC}/output_source_priority/state",
        str(output_priority),
        retain=True,
    )


def publish_charger_source_priority(client, value):
    client.publish(
        f"{BASE_TOPIC}/charger_source_priority/state",
        str(value),
        retain=True,
    )


def publish_inverter_settings_discovery(client):
    device = _energyhub_device()

    sensors = {
        "output_source_priority": (
            "Output Source Priority",
            None,
            None,
            None,
        ),
        "charger_source_priority": (
            "Charger Source Priority",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Inverter Settings MQTT discovery published")


def publish_autopilot(client, autopilot):
    for key, value in autopilot.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_autopilot_discovery(client):
    device = _energyhub_device()

    sensors = {
        "autopilot_status": (
            "Autopilot Status",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Autopilot MQTT discovery published")


def _energyhub_device():
    return {
        "identifiers": ["energyhub_core"],
        "name": "EnergyHub",
        "manufacturer": "EnergyHub",
        "model": "Core",
    }


def _publish_sensor_discovery(client, device, sensors):
    for key, (
        name,
        unit,
        device_class,
        state_class,
    ) in sensors.items():
        default_entity_id = (
            ENERGYHUB_DEFAULT_ENTITY_ID_OVERRIDES.get(
                key,
                f"sensor.energyhub_{key}",
            )
        )

        payload = {
            "name": name,
            "unique_id": f"energyhub_{key}",
            "default_entity_id": default_entity_id,
            "state_topic": f"{BASE_TOPIC}/{key}/state",
            "availability_topic": ENERGYHUB_AVAILABILITY_TOPIC,
            "device": device,
        }

        if unit:
            payload["unit_of_measurement"] = unit

        if device_class:
            payload["device_class"] = device_class

        if state_class:
            payload["state_class"] = state_class

        topic = (
            f"homeassistant/sensor/"
            f"energyhub_{key}/config"
        )

        client.publish(
            topic,
            json.dumps(payload),
            retain=True,
        )


def publish_operating_mode(client, inverter_controller):
    for key, value in inverter_controller.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_operating_mode_discovery(client):
    device = _energyhub_device()

    sensors = {
        "operating_mode": (
            "Operating Mode",
            None,
            None,
            None,
        ),
        "operating_mode_reason": (
            "Operating Mode Reason",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Operating Mode MQTT discovery published")


def publish_panic_decision(client, panic_decision):
    for key, value in panic_decision.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_panic_decision_discovery(client):
    device = _energyhub_device()

    sensors = {
        "panic_decision": (
            "Panic Decision",
            None,
            None,
            None,
        ),
        "panic_decision_reason": (
            "Panic Decision Reason",
            None,
            None,
            None,
        ),
        "panic_phase": (
            "Panic Phase",
            None,
            None,
            None,
        ),
        "panic_target_source": (
            "Panic Target Source",
            None,
            None,
            None,
        ),
        "panic_target_soc": (
            "Panic Target SOC",
            "%",
            "battery",
            "measurement",
        ),
        "panic_grid_target_soc": (
            "Panic Grid Confidence Target SOC",
            "%",
            "battery",
            "measurement",
        ),
        "panic_ahm_target_soc": (
            "Panic AHM Target SOC",
            "%",
            "battery",
            "measurement",
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Panic Decision MQTT discovery published")


def publish_hybrid_decision(client, hybrid_decision):
    for key, value in hybrid_decision.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )


def publish_hybrid_decision_discovery(client):
    device = _energyhub_device()

    sensors = {
        "hybrid_decision": (
            "Hybrid Decision",
            None,
            None,
            None,
        ),
        "hybrid_decision_reason": (
            "Hybrid Decision Reason",
            None,
            None,
            None,
        ),
        "hybrid_evaluated_at": (
            "Hybrid Evaluated At",
            None,
            None,
            None,
        ),
        "hybrid_calculation": (
            "Hybrid Calculation",
            None,
            None,
            None,
        ),
        "hybrid_evaluated_soc": (
            "Hybrid Evaluated SOC",
            "%",
            "battery",
            "measurement",
        ),
        "hybrid_evaluated_consumption": (
            "Hybrid Evaluated Consumption",
            "kWh",
            "energy",
            None,
        ),
        "hybrid_evaluated_forecast": (
            "Hybrid Evaluated Forecast",
            "kWh",
            "energy",
            None,
        ),
        "hybrid_battery_refill_required": (
            "Hybrid Battery Refill Required",
            "kWh",
            "energy",
            None,
        ),
        "hybrid_total_energy_required": (
            "Hybrid Total Energy Required",
            "kWh",
            "energy",
            None,
        ),
        "hybrid_projected_soc_at_07": (
            "Hybrid Projected SOC at 07:00",
            "%",
            "battery",
            "measurement",
        ),
        "hybrid_morning_hours": (
            "Hybrid Morning Gap",
            "h",
            "duration",
            "measurement",
        ),
        "hybrid_useful_solar_start": (
            "Hybrid Useful Solar Start",
            None,
            None,
            None,
        ),
        "hybrid_morning_reserve_soc": (
            "Hybrid Morning Reserve",
            "%",
            "battery",
            "measurement",
        ),
        "hybrid_expected_consumption_after_07": (
            "Hybrid Expected Consumption after 07:00",
            "kWh",
            "energy",
            None,
        ),
        "hybrid_solar_forecast_after_07": (
            "Hybrid Solar Forecast after 07:00",
            "kWh",
            "energy",
            None,
        ),
        "hybrid_daytime_deficit_kwh": (
            "Hybrid Daytime Deficit",
            "kWh",
            "energy",
            None,
        ),
        "hybrid_daytime_deficit_soc": (
            "Hybrid Daytime Deficit SOC",
            "%",
            "battery",
            "measurement",
        ),
        "hybrid_energy_balance_available": (
            "Hybrid Energy Balance Available",
            None,
            None,
            None,
        ),
        "hybrid_target_soc": (
            "Hybrid Adaptive Target SOC",
            "%",
            "battery",
            "measurement",
        ),
        "hybrid_target_capped": (
            "Hybrid Target Capped",
            None,
            None,
            None,
        ),
        "hybrid_forecast_fallback": (
            "Hybrid Forecast Fallback",
            None,
            None,
            None,
        ),
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Hybrid Decision MQTT discovery published")


def publish_notification_event(client, event):
    client.publish(
        "energyhub/event/notification",
        json.dumps(event),
        retain=False,
    )

    log(
        "Notification event published: "
        f"type={event.get('type')}, "
        f"mode={event.get('mode')}"
    )
