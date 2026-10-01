import json
import math
import time
import weakref

import paho.mqtt.client as mqtt

from app.config import (
    BASE_TOPIC,
    ENERGYHUB_AVAILABILITY_TOPIC,
    INVERTER_AVAILABILITY_TOPIC,
    PV2_AVAILABILITY_TOPIC,
    SENSORS,
    TOTAL_PV_AVAILABILITY_TOPIC,
)
from app.utils.presentation import display_text, display_value
from app.utils.logger import log


OUTPUT_SOURCE_PRIORITY_MAP = {
    "Solar Battery Utility": "SBU",
    "Solar Utility Battery": "SUB",
}

HOME_ASSISTANT_STATE_MAX_LENGTH = 255
OPTIONAL_NUMERIC_STATES = {
    "pv2_sample_age_seconds",
    "daily_solar_actual",
    "daily_solar_forecast_error_percent",
}
TELEMETRY_HEARTBEAT_SECONDS = 30
TELEMETRY_DEADBANDS = {
    "ac_output_active_power": 25.0,
    "ac_output_apparent_power": 25.0,
    "pv1_charging_power": 25.0,
    "ac_output_load": 1.0,
    "battery_capacity": 1.0,
    "battery_charging_current": 1.0,
    "battery_discharge_current": 1.0,
    "ac_input_voltage": 0.5,
    "ac_output_voltage": 0.5,
    "battery_voltage": 0.1,
    "battery_voltage_from_scc": 0.1,
    "ac_input_frequency": 0.05,
    "ac_output_frequency": 0.05,
    "inverter_heat_sink_temperature": 1.0,
}
PEAK_GUARD_HEARTBEAT_SECONDS = 60
_PEAK_GUARD_PUBLICATIONS = weakref.WeakKeyDictionary()
_GRID_IMPORT_PUBLICATIONS = weakref.WeakKeyDictionary()


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


def publish_pv2_discovery(client, device_name="PowMr 10.2M"):
    device = {
        "identifiers": ["powmr_10_2m"],
        "name": device_name,
        "manufacturer": "PowMr",
        "model": "10.2M",
    }

    measurements = {
        "pv2_input_voltage": (
            "PV2 Voltage",
            "sensor.powmr_10_2m_pv2_voltage",
            "V",
            "voltage",
            PV2_AVAILABILITY_TOPIC,
        ),
        "pv2_charging_power": (
            "PV2 Power",
            "sensor.powmr_10_2m_pv2_power",
            "W",
            "power",
            PV2_AVAILABILITY_TOPIC,
        ),
        "total_pv_power": (
            "Total PV Power",
            "sensor.powmr_10_2m_total_pv_power",
            "W",
            "power",
            TOTAL_PV_AVAILABILITY_TOPIC,
        ),
    }

    for key, (
        name,
        default_entity_id,
        unit,
        device_class,
        availability_topic,
    ) in measurements.items():
        unique_id = f"powmr_10_2m_{key}"
        payload = {
            "name": name,
            "unique_id": unique_id,
            "default_entity_id": default_entity_id,
            "state_topic": f"{BASE_TOPIC}/{key}/state",
            "unit_of_measurement": unit,
            "device_class": device_class,
            "state_class": "measurement",
            "availability": [
                {"topic": ENERGYHUB_AVAILABILITY_TOPIC},
                {"topic": availability_topic},
            ],
            "availability_mode": "all",
            "device": device,
        }
        client.publish(
            f"homeassistant/sensor/{unique_id}/config",
            json.dumps(payload),
            retain=True,
        )

    diagnostics = {
        "pv2_telemetry_status": (
            "PV2 Telemetry Status",
            None,
            None,
            None,
        ),
        "pv2_telemetry_freshness": (
            "PV2 Telemetry Freshness",
            None,
            None,
            None,
        ),
        "pv2_sample_age_seconds": (
            "PV2 Sample Age",
            "s",
            "duration",
            "measurement",
        ),
    }
    _publish_sensor_discovery(client, _energyhub_device(), diagnostics)

    log("PV2 MQTT discovery published")


def publish_pv2_telemetry(client, pv2_telemetry):
    if pv2_telemetry.last_voltage is not None:
        client.publish(
            f"{BASE_TOPIC}/pv2_input_voltage/state",
            str(pv2_telemetry.last_voltage),
            retain=True,
        )

    if pv2_telemetry.last_power is not None:
        client.publish(
            f"{BASE_TOPIC}/pv2_charging_power/state",
            str(pv2_telemetry.last_power),
            retain=True,
        )

    if pv2_telemetry.last_total_power is not None:
        client.publish(
            f"{BASE_TOPIC}/total_pv_power/state",
            str(pv2_telemetry.last_total_power),
            retain=True,
        )

    for key, value in pv2_telemetry.mqtt_values().items():
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )

    client.publish(
        PV2_AVAILABILITY_TOPIC,
        "online" if pv2_telemetry.pv2_is_fresh() else "offline",
        retain=True,
    )
    client.publish(
        TOTAL_PV_AVAILABILITY_TOPIC,
        "online" if pv2_telemetry.total_is_fresh() else "offline",
        retain=True,
    )


def publish_values(client, data, previous):
    published = 0
    suppressed = 0
    now = time.monotonic()
    published_at = previous.setdefault("__published_at__", {})

    for key in SENSORS:
        if key not in data:
            continue

        value = data.get(key)

        if not is_valid_value(key, value):
            continue

        last_value = previous.get(key)
        last_time = float(published_at.get(key, 0.0))
        deadband = TELEMETRY_DEADBANDS.get(key, 0.0)
        try:
            changed = (
                last_value is None
                or (abs(float(value) - float(last_value)) >= deadband if deadband > 0
                    else float(value) != float(last_value))
            )
        except (TypeError, ValueError):
            changed = value != last_value
        heartbeat_due = now - last_time >= TELEMETRY_HEARTBEAT_SECONDS
        if not changed and not heartbeat_due:
            suppressed += 1
            continue

        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )
        published_at[key] = now
        published += 1

    client.publish(
        INVERTER_AVAILABILITY_TOPIC,
        "online",
        retain=True,
    )

    previous["__last_suppressed__"] = suppressed
    return published


def is_valid_value(key, value):
    if value is None:
        return False

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        log(f"Skip invalid numeric value for {key}: {value!r}")
        return False

    if not math.isfinite(numeric_value):
        log(f"Skip non-finite value for {key}: {value!r}")
        return False

    if key == "battery_capacity":
        if numeric_value < 0 or numeric_value > 100:
            log(f"Skip invalid SOC: {numeric_value}")
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
    now = time.monotonic()
    cache = _GRID_IMPORT_PUBLICATIONS.setdefault(client, {})
    for key, value in grid_import.mqtt_values().items():
        previous = cache.get(key)
        if value is None:
            # Clear any retained state without sending a non-numeric sentinel
            # to Home Assistant energy and monetary sensors.
            if previous is None or previous["value"] is not None:
                client.publish(
                    f"{BASE_TOPIC}/{key}/state",
                    "",
                    retain=True,
                )
                cache[key] = {"value": None, "published_at": now}
            continue
        try:
            numeric = float(value)
            previous_numeric = float(previous["value"]) if previous else None
        except (TypeError, ValueError):
            numeric = previous_numeric = None
        deadband = 25.0 if key == "grid_import_power_estimated" else 0.01
        changed = (
            previous is None
            or (numeric is None and value != previous["value"])
            or (numeric is not None and previous_numeric is None)
            or (numeric is not None and previous_numeric is not None
                and abs(numeric - previous_numeric) >= deadband)
        )
        heartbeat_due = previous is None or now - previous["published_at"] >= 60
        if not changed and not heartbeat_due:
            continue
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            str(value),
            retain=True,
        )
        cache[key] = {"value": value, "published_at": now}


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
        "grid_import_night_today_estimated": (
            "Night Grid Import Today Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_normal_today_estimated": (
            "Normal Grid Import Today Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_night_yesterday_estimated": (
            "Night Grid Import Yesterday Estimated",
            "kWh",
            "energy",
            None,
        ),
        "grid_import_normal_yesterday_estimated": (
            "Normal Grid Import Yesterday Estimated",
            "kWh",
            "energy",
            None,
        ),
        "grid_import_cost_yesterday_estimated": (
            "Grid Import Cost Yesterday Estimated",
            "UAH",
            "monetary",
            None,
        ),
        "grid_import_night_total_estimated": (
            "Night Grid Import Total Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_normal_total_estimated": (
            "Normal Grid Import Total Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_night_month_estimated": (
            "Night Grid Import This Month Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_normal_month_estimated": (
            "Normal Grid Import This Month Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_month_estimated": (
            "Grid Import This Month Estimated",
            "kWh",
            "energy",
            "total_increasing",
        ),
        "grid_import_cost_month_estimated": (
            "Grid Import Cost This Month Estimated",
            "UAH",
            "monetary",
            "total",
        ),
        "grid_import_night_previous_week_estimated": (
            "Night Grid Import Previous Week Estimated", "kWh", "energy", None,
        ),
        "grid_import_normal_previous_week_estimated": (
            "Normal Grid Import Previous Week Estimated", "kWh", "energy", None,
        ),
        "grid_import_previous_week_estimated": (
            "Grid Import Previous Week Estimated", "kWh", "energy", None,
        ),
        "grid_import_cost_previous_week_estimated": (
            "Grid Import Cost Previous Week Estimated", "UAH", "monetary", None,
        ),
        "grid_import_night_previous_month_estimated": (
            "Night Grid Import Previous Month Estimated", "kWh", "energy", None,
        ),
        "grid_import_normal_previous_month_estimated": (
            "Normal Grid Import Previous Month Estimated", "kWh", "energy", None,
        ),
        "grid_import_previous_month_estimated": (
            "Grid Import Previous Month Estimated", "kWh", "energy", None,
        ),
        "grid_import_cost_previous_month_estimated": (
            "Grid Import Cost Previous Month Estimated", "UAH", "monetary", None,
        ),
        "grid_import_night_price": (
            "Night Grid Import Price",
            "UAH/kWh",
            None,
            None,
        ),
        "grid_import_normal_price": (
            "Normal Grid Import Price",
            "UAH/kWh",
            None,
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
        "daily_solar_actual": (
            "Daily Solar Actual", "kWh", "energy", None,
        ),
        "daily_solar_forecast_error_percent": (
            "Daily Solar Forecast Error", "%", None, "measurement",
        ),
        "daily_battery_reached_full": (
            "Daily Battery Reached Full", None, None, None,
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


def publish_soc_anomaly_journal(client, journal):
    values = journal.mqtt_values()

    client.publish(
        f"{BASE_TOPIC}/soc_anomaly_event_count/state",
        str(values["soc_anomaly_event_count"]),
        retain=True,
    )
    client.publish(
        f"{BASE_TOPIC}/soc_anomaly_latest/state",
        str(values["soc_anomaly_latest"]),
        retain=True,
    )
    client.publish(
        f"{BASE_TOPIC}/soc_anomaly_latest/attributes",
        json.dumps(journal.latest_attributes()),
        retain=True,
    )


def publish_soc_anomaly_journal_discovery(client):
    device = _energyhub_device()

    _publish_sensor_discovery(
        client,
        device,
        {
            "soc_anomaly_event_count": (
                "SOC Anomaly Event Count",
                "events",
                None,
                "total_increasing",
            ),
        },
    )

    latest_payload = {
        "name": "Latest SOC Anomaly",
        "unique_id": "energyhub_soc_anomaly_latest",
        "default_entity_id": "sensor.energyhub_soc_anomaly_latest",
        "state_topic": f"{BASE_TOPIC}/soc_anomaly_latest/state",
        "json_attributes_topic": (
            f"{BASE_TOPIC}/soc_anomaly_latest/attributes"
        ),
        "availability_topic": ENERGYHUB_AVAILABILITY_TOPIC,
        "device_class": "timestamp",
        "device": device,
    }
    client.publish(
        "homeassistant/sensor/energyhub_soc_anomaly_latest/config",
        json.dumps(latest_payload),
        retain=True,
    )

    log("SOC Anomaly Journal MQTT discovery published")


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


def publish_inverter_fault_journal(client, journal):
    client.publish(
        f"{BASE_TOPIC}/inverter_fault_current/state",
        journal.current_state()[:HOME_ASSISTANT_STATE_MAX_LENGTH],
        retain=True,
    )
    for position in range(1, 4):
        key = f"inverter_fault_recent_{position}"
        client.publish(
            f"{BASE_TOPIC}/{key}/state",
            journal.event_state(position)[:HOME_ASSISTANT_STATE_MAX_LENGTH],
            retain=True,
        )
        client.publish(
            f"{BASE_TOPIC}/{key}/attributes",
            json.dumps(journal.event_attributes(position)),
            retain=True,
        )


def publish_inverter_fault_journal_discovery(client):
    device = _energyhub_device()
    current = {
        "name": "Current Inverter Message",
        "unique_id": "energyhub_inverter_fault_current",
        "default_entity_id": "sensor.energyhub_inverter_fault_current",
        "state_topic": f"{BASE_TOPIC}/inverter_fault_current/state",
        "icon": "mdi:alert-circle-outline",
        "device": device,
    }
    client.publish(
        "homeassistant/sensor/energyhub_inverter_fault_current/config",
        json.dumps(current),
        retain=True,
    )
    for position in range(1, 4):
        key = f"inverter_fault_recent_{position}"
        payload = {
            "name": f"Recent Inverter Message {position}",
            "unique_id": f"energyhub_{key}",
            "default_entity_id": f"sensor.energyhub_{key}",
            "state_topic": f"{BASE_TOPIC}/{key}/state",
            "json_attributes_topic": f"{BASE_TOPIC}/{key}/attributes",
            "icon": "mdi:history",
            "device": device,
        }
        client.publish(
            f"homeassistant/sensor/energyhub_{key}/config",
            json.dumps(payload),
            retain=True,
        )
    log("Inverter fault journal MQTT discovery published")


def publish_peak_load_guard(client, guard):
    status = guard.status_state()[:HOME_ASSISTANT_STATE_MAX_LENGTH]
    event = guard.event_state()[:HOME_ASSISTANT_STATE_MAX_LENGTH]
    attributes = guard.status_attributes()
    event_attributes = guard.event_attributes()
    cycle = attributes.get("cycle") or {}
    pending = attributes.get("pending") or {}
    fingerprint = json.dumps({
        "status": status,
        "event": event,
        "fault": attributes.get("fault"),
        "automatic_requested": attributes.get("automatic_requested"),
        "pending": {key: pending.get(key) for key in ("command_id", "key", "action", "reason")},
        "cycle": {key: cycle.get(key) for key in ("cycle_id", "owned", "blocked", "shed", "restored", "shedding")},
        "latest_event_id": attributes.get("latest_event_id"),
    }, sort_keys=True, default=str)
    now = time.monotonic()
    previous = _PEAK_GUARD_PUBLICATIONS.get(client, {})
    if (
        previous.get("fingerprint") == fingerprint
        and now - float(previous.get("published_at", 0.0)) < PEAK_GUARD_HEARTBEAT_SECONDS
    ):
        return False
    client.publish(
        f"{BASE_TOPIC}/peak_load_guard/state",
        status,
        retain=True,
    )
    client.publish(
        f"{BASE_TOPIC}/peak_load_guard/attributes",
        json.dumps(attributes),
        retain=True,
    )
    client.publish(
        f"{BASE_TOPIC}/peak_load_guard_event/state",
        event,
        retain=True,
    )
    client.publish(
        f"{BASE_TOPIC}/peak_load_guard_event/attributes",
        json.dumps(event_attributes),
        retain=True,
    )
    _PEAK_GUARD_PUBLICATIONS[client] = {
        "fingerprint": fingerprint,
        "published_at": now,
    }
    return True


def publish_peak_load_guard_discovery(client):
    device = _energyhub_device()
    entities = {
        "peak_load_guard": (
            "Peak Load Guard",
            "mdi:shield-home-outline",
        ),
        "peak_load_guard_event": (
            "Peak Load Guard Event",
            "mdi:shield-alert-outline",
        ),
    }
    for key, (name, icon) in entities.items():
        payload = {
            "name": name,
            "unique_id": f"energyhub_{key}",
            "default_entity_id": f"sensor.energyhub_{key}",
            "state_topic": f"{BASE_TOPIC}/{key}/state",
            "json_attributes_topic": f"{BASE_TOPIC}/{key}/attributes",
            "availability_topic": ENERGYHUB_AVAILABILITY_TOPIC,
            "icon": icon,
            "device": device,
        }
        client.publish(
            f"homeassistant/sensor/energyhub_{key}/config",
            json.dumps(payload),
            retain=True,
        )
    log("Peak Load Guard MQTT discovery published")


def publish_weather_buffer(client, weather_buffer):
    client.publish(
        f"{BASE_TOPIC}/weather_buffer/state",
        weather_buffer.status_state()[:HOME_ASSISTANT_STATE_MAX_LENGTH],
        retain=True,
    )
    client.publish(
        f"{BASE_TOPIC}/weather_buffer/attributes",
        json.dumps(weather_buffer.status_attributes()),
        retain=True,
    )


def publish_weather_buffer_discovery(client):
    payload = {
        "name": "Battery Reserve Recommendation",
        "unique_id": "energyhub_weather_buffer",
        "default_entity_id": "sensor.energyhub_ahm_weather_buffer",
        "state_topic": f"{BASE_TOPIC}/weather_buffer/state",
        "json_attributes_topic": f"{BASE_TOPIC}/weather_buffer/attributes",
        "availability_topic": ENERGYHUB_AVAILABILITY_TOPIC,
        "icon": "mdi:battery-heart-variant",
        "device": _energyhub_device(),
    }
    client.publish(
        "homeassistant/sensor/energyhub_weather_buffer/config",
        json.dumps(payload),
        retain=True,
    )
    log("Battery Reserve Recommendation MQTT discovery published")
    client.publish(
        "homeassistant/binary_sensor/energyhub_battery_reserve_auto/config",
        json.dumps({
            "name": "Battery Reserve Auto",
            "unique_id": "energyhub_battery_reserve_auto",
            "default_entity_id": "binary_sensor.energyhub_battery_reserve_auto",
            "state_topic": f"{BASE_TOPIC}/weather_buffer/attributes",
            "value_template": "{{ 'ON' if value_json.automatic_control_enabled | default(false) else 'OFF' }}",
            "availability_topic": ENERGYHUB_AVAILABILITY_TOPIC,
            "icon": "mdi:battery-lock",
            "device": _energyhub_device(),
        }), retain=True,
    )


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
            "name": display_text(name),
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

        if key in OPTIONAL_NUMERIC_STATES:
            # The retained source may say "unknown" before its first sample.
            # Numeric HA sensors must render None, not that literal string.
            payload["value_template"] = "{{ value | float(none) }}"

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
            display_value(key, value),
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
            display_value(key, value),
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
    }

    _publish_sensor_discovery(
        client,
        device,
        sensors,
    )

    log("Panic Decision MQTT discovery published")


RETIRED_SENSOR_KEYS = (
    "adaptive_hybrid_plan",
    "daily_summary_grid_import",
    "hybrid_calculation",
    "hybrid_decision", "hybrid_decision_reason", "hybrid_evaluated_at",
    "hybrid_evaluated_soc", "hybrid_evaluated_consumption",
    "hybrid_evaluated_forecast", "hybrid_battery_refill_required",
    "hybrid_total_energy_required", "hybrid_projected_soc_at_07",
    "hybrid_minimum_soc", "hybrid_raw_morning_hours", "hybrid_morning_hours",
    "hybrid_useful_solar_start", "hybrid_effective_solar_start",
    "hybrid_ramp_confirmed", "hybrid_ramp_credit_hours",
    "hybrid_ramp_start_power_w", "hybrid_ramp_next_power_w",
    "hybrid_morning_reserve_soc", "hybrid_morning_model_source",
    "hybrid_morning_model_reason", "hybrid_morning_model_samples",
    "hybrid_morning_expected_load_kwh", "hybrid_morning_forecast_solar_kwh",
    "hybrid_morning_net_deficit_kwh", "hybrid_expected_consumption_after_07",
    "hybrid_solar_forecast_after_07", "hybrid_daytime_deficit_kwh",
    "hybrid_daytime_deficit_soc", "hybrid_energy_balance_available",
    "hybrid_target_soc", "hybrid_target_capped", "hybrid_forecast_fallback",
    "hybrid_early_solar_check", "hybrid_early_solar_reason",
    "hybrid_early_solar_evaluated_at", "hybrid_early_solar_live_power_w",
    "hybrid_early_solar_forecast_kwh", "ahm_reserve_advice",
    "ahm_reserve_advice_current_soc", "ahm_reserve_advice_suggested_soc",
    "ahm_reserve_advice_sample_count", "ahm_reserve_advice_reason",
    "panic_grid_target_soc", "panic_ahm_target_soc",
)


def publish_retired_entity_cleanup(client):
    """Remove retained discovery/state and inputs from retired planning models."""
    for key in RETIRED_SENSOR_KEYS:
        client.publish(
            f"homeassistant/sensor/energyhub_{key}/config", b"", retain=True
        )
        client.publish(f"{BASE_TOPIC}/{key}/state", b"", retain=True)
    for topic in (
        "energyhub/input/ha/adaptive_hybrid_plan",
        "energyhub/input/ha/early_solar_check",
        "energyhub/input/ha/morning_load_snapshot",
        "energyhub/input/ha/ahm_reserve_observation",
        "energyhub/input/ha/peak_load_guard_plugs",
    ):
        client.publish(topic, b"", retain=True)
    log("Retired planning MQTT entities and inputs cleared")


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
