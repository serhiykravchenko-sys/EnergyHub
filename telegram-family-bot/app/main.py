from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import Config, load_config
from .events import (
    confidence_message,
    heat_pump_management_message,
    outage_message,
    recovery_message,
    reserve_warning_message,
    valid_confidence,
)
from .home_assistant import HomeAssistantClient, HomeAssistantError
from .device_health import (
    DeviceHealthMonitor,
    acknowledge_health_report,
    doorbell_report_line,
    environment_report_lines,
)
from .report import build_report, inverter_report_lines, number, solar_peak, sun_moon_lines, useful_solar_window, weather_summary
from .state import StateStore
from .telegram import TelegramClient, TelegramError


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("telegram-family-assistant")
VERSION = os.environ.get("TELEGRAM_FAMILY_ASSISTANT_VERSION", "development")


def entity_value(client: HomeAssistantClient, entity_id: str) -> Any:
    state = client.state(entity_id)
    return None if not state else state.get("state")


def numeric_entity(client: HomeAssistantClient, entity_id: str) -> float | None:
    return number(entity_value(client, entity_id))


def queue_notification(state: dict[str, Any], message: str, kind: str, when: datetime) -> None:
    state.setdefault("pending_notifications", []).append({
        "kind": kind,
        "message": message,
        "created_at": when.isoformat(),
    })


def observe_grid(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime, debounce_seconds: int = 30) -> bool:
    state.setdefault("pending_notifications", [])
    voltage = numeric_entity(client, config.grid_voltage_entity)
    if voltage is None:
        return False
    observed_online = voltage > 180
    current = state.get("grid_online")
    if current is None:
        state["grid_online"] = observed_online
        state["grid_candidate"] = None
        state["grid_candidate_since"] = None
        if not observed_online and not state.get("outage_started_at"):
            state["outage_started_at"] = now.isoformat()
            LOGGER.warning("App started while grid is offline; outage duration starts at app observation time")
        LOGGER.info("Initialized external grid state: %s (%.1f V)", "online" if observed_online else "offline", voltage)
        return True
    if observed_online == current:
        if state.get("grid_candidate") is not None:
            state["grid_candidate"] = None
            state["grid_candidate_since"] = None
            return True
        return False

    candidate = state.get("grid_candidate")
    if candidate != observed_online:
        state["grid_candidate"] = observed_online
        state["grid_candidate_since"] = now.isoformat()
        LOGGER.info("Grid transition candidate: %s (%.1f V)", "online" if observed_online else "offline", voltage)
        return True

    candidate_since_value = state.get("grid_candidate_since")
    try:
        candidate_since = datetime.fromisoformat(candidate_since_value)
    except (TypeError, ValueError):
        state["grid_candidate_since"] = now.isoformat()
        return True
    if (now - candidate_since).total_seconds() < debounce_seconds:
        return False

    state["grid_online"] = observed_online
    state["grid_candidate"] = None
    state["grid_candidate_since"] = None
    soc = numeric_entity(client, config.battery_soc_entity)
    if observed_online:
        outage_start_value = state.get("outage_started_at")
        try:
            outage_start = datetime.fromisoformat(outage_start_value) if outage_start_value else None
        except ValueError:
            outage_start = None
        queue_notification(state, recovery_message(candidate_since, outage_start, soc), "grid_recovered", candidate_since)
        state["outage_started_at"] = None
        LOGGER.info("External grid recovered after debounce")
    else:
        state["outage_started_at"] = candidate_since.isoformat()
        queue_notification(state, outage_message(candidate_since, soc), "grid_lost", candidate_since)
        LOGGER.warning("External grid lost after debounce")
    return True


def observe_grid_confidence(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> bool:
    state.setdefault("pending_notifications", [])
    observed = valid_confidence(entity_value(client, config.grid_confidence_entity))
    if observed is None:
        return False
    previous = valid_confidence(state.get("grid_confidence"))
    if previous is None:
        state["grid_confidence"] = observed
        LOGGER.info("Initialized Grid Confidence: %s", observed)
        return True
    if observed == previous:
        return False
    state["grid_confidence"] = observed
    queue_notification(state, confidence_message(previous, observed), "grid_confidence", now)
    LOGGER.info("Grid Confidence changed: %s -> %s", previous, observed)
    return True


RESERVE_WARNING_OFFSETS = (30, 20, 10, 0)
RESERVE_WARNING_RESET_MARGIN = 2
RESERVE_WARNING_QUIET_END_MINUTE = 8 * 60 + 1


def reserve_warning_quiet_hours(now: datetime) -> bool:
    return now.hour * 60 + now.minute <= RESERVE_WARNING_QUIET_END_MINUTE


def active_heat_pumps(
    config: Config,
    client: HomeAssistantClient,
) -> list[tuple[str, float]]:
    pumps = (
        ("1-му", config.heat_pump_floor_1_power_entity),
        ("2-му", config.heat_pump_floor_2_power_entity),
        ("3-му", config.heat_pump_floor_3_power_entity),
    )
    active = []
    for floor, entity_id in pumps:
        power_w = numeric_entity(client, entity_id)
        if power_w is not None and power_w > config.heat_pump_active_threshold_w:
            active.append((floor, power_w))
    return active


def observe_reserve_warnings(
    config: Config,
    client: HomeAssistantClient,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    state.setdefault("pending_notifications", [])
    freshness = entity_value(
        client,
        config.telemetry_freshness_entity,
    )
    if str(freshness or "").strip().lower() != "fresh":
        return False

    soc = numeric_entity(client, config.battery_soc_entity)
    minimum = numeric_entity(client, config.ahm_minimum_soc_entity)
    if soc is None or minimum is None:
        return False

    previous_minimum = number(state.get("reserve_warning_minimum_soc"))
    notified = {
        int(value)
        for value in state.get("reserve_warning_offsets", [])
        if number(value) is not None
    }

    if previous_minimum != minimum:
        state["reserve_warning_minimum_soc"] = minimum
        state["reserve_warning_offsets"] = [
            offset
            for offset in RESERVE_WARNING_OFFSETS
            if soc <= minimum + offset
        ]
        LOGGER.info(
            "Initialized reserve warnings for AHM minimum %.1f%% at SOC %.1f%%",
            minimum,
            soc,
        )
        return True

    for offset in tuple(notified):
        if soc >= minimum + offset + RESERVE_WARNING_RESET_MARGIN:
            notified.discard(offset)

    changed = False
    pumps = active_heat_pumps(config, client)
    crossed = []
    if pumps and not reserve_warning_quiet_hours(now):
        crossed = [
            offset
            for offset in RESERVE_WARNING_OFFSETS
            if soc <= minimum + offset and offset not in notified
        ]

    if crossed:
        notified.update(crossed)
        deepest = min(crossed)
        queue_notification(
            state,
            reserve_warning_message(
                soc=soc,
                minimum_soc=minimum,
                offset=deepest,
                confidence=entity_value(
                    client,
                    config.grid_confidence_entity,
                ),
                voltage=entity_value(client, config.grid_voltage_entity),
                freshness=entity_value(
                    client,
                    config.telemetry_freshness_entity,
                ),
                active_heat_pumps=pumps,
            ),
            f"reserve_{deepest}",
            now,
        )
        LOGGER.info(
            "Queued reserve warning: SOC=%.1f%%, AHM minimum=%.1f%%, offset=%d",
            soc,
            minimum,
            deepest,
        )
        changed = True

    normalized = sorted(notified, reverse=True)
    if state.get("reserve_warning_offsets") != normalized:
        state["reserve_warning_offsets"] = normalized
        changed = True
    return changed


def deliver_pending_notifications(
    config: Config,
    telegram: TelegramClient,
    state: dict[str, Any],
    now: datetime | None = None,
    client: HomeAssistantClient | None = None,
) -> bool:
    queue = state.setdefault("pending_notifications", [])
    now = now or datetime.now(ZoneInfo(config.timezone))
    changed = False
    index = 0
    while index < len(queue):
        item = queue[index]
        if (
            str(item.get("kind", "")).startswith("reserve_")
            and reserve_warning_quiet_hours(now)
        ):
            index += 1
            continue
        if str(item.get("kind", "")).startswith("reserve_") and client is not None:
            action, refreshed_message = refresh_queued_reserve_warning(
                config,
                client,
                str(item.get("kind", "")),
            )
            if action == "defer":
                index += 1
                continue
            if action == "drop":
                LOGGER.info("Dropped obsolete queued %s notification", item.get("kind"))
                queue.pop(index)
                changed = True
                continue
            item["message"] = refreshed_message
        telegram.send_message(config.destination_chat_id, str(item["message"]))
        LOGGER.info("Delivered queued %s notification", item.get("kind", "event"))
        queue.pop(index)
        changed = True
    return changed


def refresh_queued_reserve_warning(
    config: Config,
    client: HomeAssistantClient,
    kind: str,
) -> tuple[str, str | None]:
    try:
        offset = int(kind.removeprefix("reserve_"))
    except ValueError:
        return "drop", None
    freshness = entity_value(client, config.telemetry_freshness_entity)
    soc = numeric_entity(client, config.battery_soc_entity)
    minimum = numeric_entity(client, config.ahm_minimum_soc_entity)
    if str(freshness or "").strip().lower() != "fresh" or soc is None or minimum is None:
        return "defer", None
    if soc > min(100, minimum + offset):
        return "drop", None
    pumps = active_heat_pumps(config, client)
    if not pumps:
        return "defer", None
    return "send", reserve_warning_message(
        soc=soc,
        minimum_soc=minimum,
        offset=offset,
        confidence=entity_value(client, config.grid_confidence_entity),
        voltage=entity_value(client, config.grid_voltage_entity),
        freshness=freshness,
        active_heat_pumps=pumps,
    )


def time_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def in_capture_window(now: datetime, configured: str, duration: int = 10) -> bool:
    current = now.hour * 60 + now.minute
    configured_minutes = time_minutes(configured)
    return configured_minutes <= current < configured_minutes + duration


def observe_night_mode(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> bool:
    current = now.hour * 60 + now.minute
    start = time_minutes(config.night_start_time)
    snapshot = time_minutes(config.soc_snapshot_time)
    if current >= start:
        report_date = (now.date() + timedelta(days=1)).isoformat()
    elif current <= snapshot:
        report_date = now.date().isoformat()
    else:
        return False
    mode = str(entity_value(client, config.operating_mode_entity) or "")
    if not mode or mode in {"unknown", "unavailable"}:
        return False
    modes = state.setdefault("night_observed_modes", {}).setdefault(report_date, [])
    if mode in modes:
        return False
    modes.append(mode)
    return True


def summarized_night_mode(modes: list[str]) -> str | None:
    normalized = [mode.lower() for mode in modes]
    if any(mode.startswith("hybrid") for mode in normalized):
        return "hybrid"
    if any(mode.startswith("panic") for mode in normalized):
        return "panic"
    if "solar" in normalized:
        return "solar"
    return modes[-1] if modes else None


def capture_night_baseline(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> bool:
    if not in_capture_window(now, config.night_start_time):
        return False
    key = now.date().isoformat()
    baselines = state.setdefault("night_baselines", {})
    if key in baselines:
        return False
    value = numeric_entity(client, config.daily_grid_import_entity)
    if value is None:
        return False
    baselines[key] = {"value": value, "captured_at": now.isoformat()}
    LOGGER.info("Captured 23:00 grid-import baseline for %s: %.3f kWh", key, value)
    return True


def capture_seven_snapshot(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> bool:
    if not in_capture_window(now, config.soc_snapshot_time):
        return False
    key = now.date().isoformat()
    snapshots = state.setdefault("soc_snapshots", {})
    changed = False
    if key not in snapshots:
        modes = state.setdefault("night_observed_modes", {}).get(key, [])
        snapshots[key] = {
            "soc": numeric_entity(client, config.battery_soc_entity),
            "target_soc": numeric_entity(client, config.target_soc_entity),
            "selected_minimum_soc": numeric_entity(
                client,
                getattr(
                    config,
                    "ahm_minimum_soc_entity",
                    "input_number.ahm_minimum_soc",
                ),
            ),
            "mode": summarized_night_mode(modes) or entity_value(client, config.operating_mode_entity),
            "captured_at": now.isoformat(),
        }
        LOGGER.info("Captured 07:00 SOC snapshot for %s", key)
        changed = True

    imports = state.setdefault("night_imports", {})
    if key not in imports:
        previous_key = (now.date() - timedelta(days=1)).isoformat()
        baseline = state.setdefault("night_baselines", {}).get(previous_key, {}).get("value")
        previous_total = numeric_entity(client, config.yesterday_grid_import_entity)
        current_total = numeric_entity(client, config.daily_grid_import_entity)
        values = [number(baseline), previous_total, current_total]
        if all(value is not None for value in values) and previous_total + 0.001 >= values[0]:
            imports[key] = round(max(0.0, previous_total - values[0]) + max(0.0, current_total), 3)
            LOGGER.info("Calculated 23:00-07:00 grid import for %s: %.3f kWh", key, imports[key])
            changed = True
        else:
            LOGGER.warning("Night import unavailable for %s; a complete 23:00 baseline is required", key)
    return changed


def weather_candidates(config: Config, client: HomeAssistantClient) -> list[str]:
    if config.weather_entity:
        return [config.weather_entity]
    states = client.states()
    candidates = sorted(item["entity_id"] for item in states if str(item.get("entity_id", "")).startswith("weather."))
    if "weather.forecast_home" in candidates:
        candidates.remove("weather.forecast_home")
        candidates.insert(0, "weather.forecast_home")
    return candidates


def fetch_weather(config: Config, client: HomeAssistantClient, now: datetime) -> list[str]:
    candidates = weather_candidates(config, client)
    if not candidates:
        LOGGER.warning("No weather entity found; weather lines will be omitted")
        return []
    LOGGER.info("Weather candidates: %s", ", ".join(candidates))
    failures = []
    for forecast_type in ("hourly", "daily"):
        for entity_id in candidates:
            try:
                forecast = client.forecast(entity_id, forecast_type)
            except HomeAssistantError as exc:
                failures.append(f"{entity_id}/{forecast_type}: {exc}")
                continue
            if not forecast:
                failures.append(f"{entity_id}/{forecast_type}: empty forecast")
                continue
            weather_state = client.state(entity_id) or {}
            attributes = weather_state.get("attributes", {})
            wind_unit = str(attributes.get("wind_speed_unit") or "km/h")
            lines = weather_summary(
                forecast,
                now.date(),
                ZoneInfo(config.timezone),
                wind_unit,
                config.strong_wind_threshold_ms,
                forecast_type,
            )
            if lines:
                LOGGER.info("Weather report uses %s %s forecast", entity_id, forecast_type)
                return lines
            failures.append(f"{entity_id}/{forecast_type}: no periods for today")
    LOGGER.warning("No usable weather forecast; weather lines will be omitted. Attempts: %s", " | ".join(failures))
    return []


def create_report(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime, *, preview: bool = False) -> str:
    weather_lines = fetch_weather(config, client, now)

    solar_state = client.state(config.solar_forecast_entity) or {}
    solar_forecast = number(solar_state.get("state"))
    detailed_hourly = solar_state.get("attributes", {}).get("detailedHourly", [])
    hourly = detailed_hourly if isinstance(detailed_hourly, list) else []
    timezone = ZoneInfo(config.timezone)
    window = useful_solar_window(hourly, now.date(), timezone, config.useful_solar_threshold_w)
    peak = solar_peak(hourly, now.date(), timezone)
    astronomy = sun_moon_lines(
        client.state(config.sun_entity),
        client.state(config.moon_entity),
        now.date(),
        timezone,
    )

    key = now.date().isoformat()
    snapshot = {} if preview else state.setdefault("soc_snapshots", {}).get(key, {})
    night_import = None if preview else number(state.setdefault("night_imports", {}).get(key))
    consumption = numeric_entity(client, config.yesterday_consumption_entity)
    tariff_import = (
        {}
        if preview
        else {
            "yesterday_night_kwh": numeric_entity(
                client, config.yesterday_night_grid_import_entity
            ),
            "yesterday_normal_kwh": numeric_entity(
                client, config.yesterday_normal_grid_import_entity
            ),
            "yesterday_cost_uah": numeric_entity(
                client, config.yesterday_grid_import_cost_entity
            ),
            "month_night_kwh": numeric_entity(
                client, config.month_night_grid_import_entity
            ),
            "month_normal_kwh": numeric_entity(
                client, config.month_normal_grid_import_entity
            ),
            "month_total_kwh": numeric_entity(
                client, config.month_grid_import_entity
            ),
            "month_cost_uah": numeric_entity(
                client, config.month_grid_import_cost_entity
            ),
            "night_price": numeric_entity(
                client, config.night_grid_import_price_entity
            ),
            "normal_price": numeric_entity(
                client, config.normal_grid_import_price_entity
            ),
        }
    )
    reserve_advice = {
        "status": entity_value(client, config.reserve_advice_entity),
        "current_soc": numeric_entity(
            client, config.reserve_advice_current_soc_entity
        ),
        "suggested_soc": numeric_entity(
            client, config.reserve_advice_suggested_soc_entity
        ),
        "sample_count": numeric_entity(
            client, config.reserve_advice_sample_count_entity
        ),
    }
    device_health_lines = environment_report_lines(state, now)
    inverter_lines = inverter_report_lines(
        [
            entity
            for entity_id in config.inverter_message_entities
            if (entity := client.state(entity_id)) is not None
        ],
        now.date() - timedelta(days=1),
        timezone,
    )
    try:
        doorbell_line = doorbell_report_line(config, client, now)
    except HomeAssistantError as exc:
        LOGGER.warning("Doorbell battery check omitted: %s", exc)
        doorbell_line = None
    if doorbell_line:
        device_health_lines.append(doorbell_line)
    return build_report(
        weather_lines=weather_lines,
        astronomy_lines=astronomy,
        solar_forecast=solar_forecast,
        solar_window=window,
        solar_peak_value=peak,
        threshold_w=config.useful_solar_threshold_w,
        consumption=consumption,
        snapshot=snapshot,
        night_import=night_import,
        tariff_import=tariff_import,
        test_mode=config.test_mode,
        reserve_advice=reserve_advice,
        ahm_minimum_soc=numeric_entity(client, config.ahm_minimum_soc_entity),
        heat_pump_management=heat_pump_management_message(
            confidence=entity_value(client, config.grid_confidence_entity),
            voltage=entity_value(client, config.grid_voltage_entity),
            freshness=entity_value(
                client,
                config.telemetry_freshness_entity,
            ),
            minimum_soc=numeric_entity(
                client,
                config.ahm_minimum_soc_entity,
            ),
        ),
        device_health_lines=device_health_lines,
        inverter_lines=inverter_lines,
    )


def due_for_report(config: Config, state: dict[str, Any], now: datetime) -> bool:
    return now.hour * 60 + now.minute >= time_minutes(config.send_time) and state.get("last_report_date") != now.date().isoformat()


def prepare_morning_report_outbox(
    config: Config,
    client: HomeAssistantClient,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    report_date = now.date().isoformat()
    outbox = state.get("morning_report_outbox")
    if (
        isinstance(outbox, dict)
        and outbox.get("date") == report_date
        and isinstance(outbox.get("message"), str)
        and outbox["message"]
    ):
        return False

    state["morning_report_outbox"] = {
        "date": report_date,
        "message": create_report(config, client, state, now),
    }
    return True


def clean_old_state(state: dict[str, Any], now: datetime) -> None:
    cutoff = (now.date() - timedelta(days=14)).isoformat()
    for name in ("soc_snapshots", "night_baselines", "night_imports", "night_observed_modes"):
        values = state.setdefault(name, {})
        for key in list(values):
            if key < cutoff:
                values.pop(key, None)


def run() -> None:
    config = load_config()
    if not config.bot_token:
        raise ValueError("bot_token is required")
    if not config.destination_chat_id:
        raise ValueError("destination_chat_id is required; use the family group ID")
    timezone = ZoneInfo(config.timezone)
    store = StateStore(config.state_file)
    state = store.load()
    client = HomeAssistantClient()
    telegram = TelegramClient(config.bot_token)
    device_health = DeviceHealthMonitor(config)
    LOGGER.info("Morning report scheduled for %s; SOC snapshot at %s", config.send_time, config.soc_snapshot_time)

    started_at = datetime.now(timezone)
    if not state.get("initialized_at"):
        state["initialized_at"] = started_at.isoformat()
        if started_at.hour * 60 + started_at.minute >= time_minutes(config.send_time):
            state["last_report_date"] = started_at.date().isoformat()
            LOGGER.info("First start is after the morning deadline; the first scheduled report will be tomorrow")
        store.save(state)

    if config.test_mode and state.get("test_message_version") != VERSION:
        try:
            try:
                device_health.observe(
                    client,
                    state,
                    datetime.now(timezone),
                    force=True,
                )
            except HomeAssistantError as exc:
                LOGGER.warning("Device-health preview omitted: %s", exc)
            telegram.send_message(config.destination_chat_id, create_report(config, client, state, datetime.now(timezone), preview=True))
        except (HomeAssistantError, TelegramError) as exc:
            LOGGER.warning("Test preview not delivered; will retry: %s", exc)
        else:
            state["test_message_version"] = VERSION
            store.save(state)
            LOGGER.info("One-time test preview delivered")

    while True:
        now = datetime.now(timezone)
        changed = False
        try:
            changed |= observe_grid(config, client, state, now)
            changed |= observe_grid_confidence(config, client, state, now)
            changed |= observe_reserve_warnings(config, client, state, now)
            changed |= observe_night_mode(config, client, state, now)
            changed |= capture_night_baseline(config, client, state, now)
            changed |= capture_seven_snapshot(config, client, state, now)
            report_due = due_for_report(config, state, now)
            try:
                changed |= device_health.observe(
                    client,
                    state,
                    now,
                    force=report_due,
                )
            except HomeAssistantError as exc:
                LOGGER.warning("Device-health check omitted: %s", exc)
            if report_due:
                if prepare_morning_report_outbox(
                    config,
                    client,
                    state,
                    now,
                ):
                    # Persist the exact logical report before the network call.
                    # Telegram has no idempotency key, so a crash after its API
                    # accepts the message can still cause a rare retry duplicate.
                    store.save(state)
                message = state["morning_report_outbox"]["message"]
                telegram.send_message(config.destination_chat_id, message)
                state["last_report_date"] = now.date().isoformat()
                state["morning_report_outbox"] = None
                acknowledge_health_report(state)
                LOGGER.info("Morning report delivered for %s", state["last_report_date"])
                changed = True
            if changed:
                store.save(state)
            changed |= deliver_pending_notifications(
                config,
                telegram,
                state,
                now,
                client,
            )
            clean_old_state(state, now)
        except (HomeAssistantError, TelegramError, OSError) as exc:
            LOGGER.warning("Temporary monitoring/delivery failure; will retry: %s", exc)
        except Exception:
            LOGGER.exception("Unexpected loop failure; will retry")
        if changed:
            store.save(state)
        time.sleep(30)


if __name__ == "__main__":
    run()
