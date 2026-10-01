from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import Config, load_config
from .control_notifications import observe_controls, queued_control_is_current
from .restart_summary import observe_restart, boot_id, summary as restart_message
from . import data_incidents
from .calendar_service import CalendarError, CalendarService
from .events import (
    manual_reserve_advice,
    confidence_message,
    heat_pump_restart_restored_message,
    outage_message,
    peak_load_guard_message,
    recovery_message,
    reserve_warning_message,
    soc_anomaly_event_id,
    soc_anomaly_message,
    soc_anomaly_report_lines,
    valid_confidence,
    weather_warning_event_id,
    weather_warning_message,
    weather_warning_report_lines,
    weather_reserve_restoration_message,
    weather_reserve_restoration_report_lines,
)
from .home_assistant import HomeAssistantClient, HomeAssistantError
from .log_digest import system_digest_lines
from .device_health import (
    DeviceHealthMonitor,
    acknowledge_health_report,
    doorbell_report_line,
    environment_report_lines,
    smart_plug_report_lines,
)
from .report import (
    build_report,
    build_technical_report,
    compact_number,
    control_authority_message,
    grid_status_report_lines,
    inverter_report_lines,
    morning_energy_lines,
    number,
    overnight_family_event_lines,
    solar_peak,
    sun_moon_lines,
    useful_solar_window,
    weather_summary,
)
from .presentation import strategy_lines
from .state import StateStore
from .telegram import TelegramClient, TelegramError
from .uhmc_source import PublicTelegramSource
from .uhmc_morning import morning_status
from .weather_warning import build_warning_snapshot, unavailable_warning_snapshot


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("telegram-family-assistant")


def publish_uhmc_weather_snapshot(
    config: Config,
    client: HomeAssistantClient,
    source: PublicTelegramSource,
    state: dict[str, Any],
    now: datetime,
    refresh_seconds: int = 300,
) -> bool:
    previous = state.get("uhmc_active_warnings", [])
    try:
        snapshot = build_warning_snapshot(
            source.fetch(),
            now,
            previous if isinstance(previous, list) else [],
            config.timezone,
        )
    except (RuntimeError, OSError) as exc:
        LOGGER.warning("UHMC Telegram source unavailable: %s", exc)
        snapshot = unavailable_warning_snapshot(now)

    signature = json.dumps(
        {
            "source_status": snapshot.get("source_status"),
            "warnings": snapshot.get("warnings", []),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        last_published = datetime.fromisoformat(
            str(state.get("uhmc_last_published_at"))
        )
    except (TypeError, ValueError):
        last_published = None
    due = (
        state.get("uhmc_snapshot_signature") != signature
        or last_published is None
        or (now - last_published).total_seconds() >= refresh_seconds
    )
    # Latest source evidence must remain visible even if MQTT fails/throttles.
    state["uhmc_last_snapshot"] = snapshot
    if not due:
        return False
    client.publish_mqtt(config.uhmc_weather_mqtt_topic, snapshot, retain=True)
    if snapshot.get("source_status") == "fresh":
        state["uhmc_active_warnings"] = snapshot.get("warnings", [])
        archived = {item["event_id"]: item for item in state.get("uhmc_superseded_warnings", [])
                    if isinstance(item, dict) and item.get("event_id")}
        archived.update({item["event_id"]: item for item in snapshot.get("superseded_warnings", [])})
        state["uhmc_superseded_warnings"] = list(archived.values())[-100:]
    state["uhmc_snapshot_signature"] = signature
    state["uhmc_last_published_at"] = now.isoformat()
    LOGGER.info(
        "Published UHMC warning evidence: status=%s, active=%d",
        snapshot.get("source_status"),
        len(snapshot.get("warnings", [])),
    )
    return True


def poll_uhmc_weather(
    config: Config,
    client: HomeAssistantClient,
    source: PublicTelegramSource,
    state: dict[str, Any],
    now: datetime,
    interval_seconds: int = 3600,
    retry_seconds: int = 300,
) -> bool:
    """Poll hourly; retry one failed read after five minutes and warn once."""
    due_value = state.get("uhmc_next_check_at")
    try:
        due = datetime.fromisoformat(str(due_value)) if due_value else None
    except ValueError:
        due = None
    if due is not None and now < due:
        return False

    retrying = bool(state.get("uhmc_retry_pending"))
    published = publish_uhmc_weather_snapshot(
        config, client, source, state, now, refresh_seconds=interval_seconds
    )
    fresh = (state.get("uhmc_last_snapshot") or {}).get("source_status") == "fresh"
    if fresh:
        state["uhmc_retry_pending"] = False
        state["uhmc_source_warning_active"] = False
        state["uhmc_next_check_at"] = (now + timedelta(seconds=interval_seconds)).isoformat()
        return True

    if not retrying:
        state["uhmc_retry_pending"] = True
        state["uhmc_next_check_at"] = (now + timedelta(seconds=retry_seconds)).isoformat()
        return True

    state["uhmc_retry_pending"] = False
    state["uhmc_next_check_at"] = (now + timedelta(seconds=interval_seconds)).isoformat()
    if not state.get("uhmc_source_warning_active"):
        queue_notification(
            state,
            "⚠️ УГМЦ: дані про погодні попередження тимчасово недоступні.",
            "uhmc_source_unavailable",
            now,
        )
        state["uhmc_source_warning_active"] = True
        LOGGER.warning("UHMC source failed twice; queued one family warning")
    return True


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


FAMILY_QUIET_START_MINUTE = 23 * 60
FAMILY_MORNING_REPORT_MINUTE = 8 * 60
FAMILY_QUIET_END_MINUTE = 8 * 60 + 1


def family_quiet_phase(now: datetime) -> str | None:
    """Return overnight collection or post-report buffer for family delivery."""
    minutes = now.hour * 60 + now.minute
    if minutes >= FAMILY_QUIET_START_MINUTE or minutes < FAMILY_MORNING_REPORT_MINUTE:
        return "overnight"
    if minutes <= FAMILY_QUIET_END_MINUTE:
        return "morning_buffer"
    return None


def overnight_family_event_id(event: dict[str, Any]) -> str:
    return "|".join((
        str(event.get("kind") or "event"),
        str(event.get("created_at") or ""),
        str(event.get("message") or ""),
    ))


def archive_overnight_family_event(
    state: dict[str, Any],
    item: dict[str, Any],
) -> None:
    events = state.setdefault("overnight_family_events", [])
    event_id = overnight_family_event_id(item)
    if any(
        isinstance(event, dict)
        and overnight_family_event_id(event) == event_id
        for event in events
    ):
        return
    events.append(dict(item))
    state["overnight_family_events"] = events[-50:]


TECHNICAL_NOTIFICATION_KINDS = {
    "ha_restart_summary", "soc_anomaly", "uhmc_source_unavailable",
}


def notification_chat(config: Config, kind: str) -> str:
    """Keep household operations in the family chat and diagnostics private."""
    technical = (
        kind in TECHNICAL_NOTIFICATION_KINDS
        or kind == "peak_load_guard_control_attention"
        or kind.startswith("technical_")
    )
    if technical:
        return getattr(config, "technical_chat_id", "") or config.destination_chat_id
    return config.destination_chat_id


def observe_grid(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime, debounce_seconds: int = 60) -> bool:
    state.setdefault("pending_notifications", [])
    voltage = numeric_entity(client, config.grid_voltage_entity)
    if voltage is None:
        return False
    observed_online = voltage > 180
    current = state.get("grid_online")
    if current is None:
        if observed_online:
            state["grid_online"] = True
            state["grid_candidate"] = None
            state["grid_candidate_since"] = None
            LOGGER.info("Initialized external grid state: online (%.1f V)", voltage)
            return True
        candidate_since_value = state.get("grid_candidate_since")
        if state.get("grid_candidate") is not False or not candidate_since_value:
            state["grid_candidate"] = False
            state["grid_candidate_since"] = now.isoformat()
            LOGGER.warning("App started while grid is offline; waiting for debounce")
            return True
        try:
            candidate_since = datetime.fromisoformat(candidate_since_value)
        except (TypeError, ValueError):
            state["grid_candidate_since"] = now.isoformat()
            return True
        if (now - candidate_since).total_seconds() < debounce_seconds:
            return False
        state["grid_online"] = False
        state["grid_candidate"] = None
        state["grid_candidate_since"] = None
        state["outage_started_at"] = candidate_since.isoformat()
        queue_notification(state, outage_message(candidate_since,
                           numeric_entity(client, config.battery_soc_entity)),
                           "grid_lost", candidate_since)
        LOGGER.warning("Confirmed external grid offline after startup debounce")
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


def observe_grid_hold(config: Config, client: HomeAssistantClient,
                      state: dict[str, Any], now: datetime,
                      debounce_seconds: int = 10) -> bool:
    """Notify once for confirmed reserve Grid Hold and Solar-return transitions."""
    mode = str(entity_value(client, config.operating_mode_entity) or "").lower()
    if mode not in {"solar", "panic", "panic_grid_hold", "hybrid_charging",
                    "hybrid_grid_hold", "transitioning", "transition_failed"}:
        return False
    previous = state.get("operating_mode_observed")
    if previous is None:
        state["operating_mode_observed"] = mode
        state["operating_mode_candidate"] = None
        if mode in {"panic_grid_hold", "hybrid_grid_hold"}:
            reserve = numeric_entity(client, config.ahm_minimum_soc_entity)
            state["grid_hold_context"] = {
                "mode": mode,
                "reserve_soc": reserve,
                "release_soc": (
                    min(100, reserve + 10)
                    if reserve is not None and 20 <= reserve < 95 else None
                ),
            }
            state["grid_hold_episode_active"] = True
            state["grid_hold_episode_reserve_soc"] = reserve
        return True
    if mode == previous:
        migrated = False
        if (
            mode in {"panic_grid_hold", "hybrid_grid_hold"}
            and "grid_hold_episode_active" not in state
        ):
            context = state.get("grid_hold_context")
            reserve = (
                number(context.get("reserve_soc"))
                if isinstance(context, dict)
                else numeric_entity(client, config.ahm_minimum_soc_entity)
            )
            state["grid_hold_episode_active"] = True
            state["grid_hold_episode_reserve_soc"] = reserve
            migrated = True
        if state.get("operating_mode_candidate") is not None:
            state["operating_mode_candidate"] = None
            return True
        return migrated
    candidate = state.get("operating_mode_candidate") or {}
    if candidate.get("mode") != mode:
        state["operating_mode_candidate"] = {"mode": mode, "since": now.isoformat()}
        return True
    try:
        since = datetime.fromisoformat(candidate["since"])
    except (KeyError, TypeError, ValueError):
        state["operating_mode_candidate"] = {"mode": mode, "since": now.isoformat()}
        return True
    if (now - since).total_seconds() < debounce_seconds:
        return False
    state["operating_mode_observed"] = mode
    state["operating_mode_candidate"] = None
    if mode == "solar":
        context = state.pop("grid_hold_context", None)
        state["grid_hold_episode_active"] = False
        state["grid_hold_episode_reserve_soc"] = None
        if not isinstance(context, dict):
            return True
        voltage = numeric_entity(client, config.grid_voltage_entity)
        if (voltage is None or voltage <= 180
                or entity_value(client, config.telemetry_freshness_entity) != "fresh"):
            return True
        soc = numeric_entity(client, config.battery_soc_entity)
        release = number(context.get("release_soc"))
        if release is None or soc is None or soc < release:
            # Solar can also be selected manually or after a failed grid
            # transition; neither is evidence of a reserve-threshold release.
            return True
        lines = ["☀️ <b>Будинок повернувся до пріоритету сонця</b>"]
        lines.append(f"🔋 Поточний заряд: <b>{compact_number(soc)}%</b>.")
        lines.append(f"Досягнуто порогу повернення <b>{compact_number(release)}%</b>.")
        queue_notification(state, "\n".join(lines), "grid_hold_released", since)
        state["pending_notifications"][-1].update({
            "soc": soc,
            "release_soc": release,
        })
        return True
    if mode == "panic":
        voltage = numeric_entity(client, config.grid_voltage_entity)
        soc = numeric_entity(client, config.battery_soc_entity)
        reserve = numeric_entity(client, config.ahm_minimum_soc_entity)
        if (voltage is not None and voltage > 180
                and entity_value(client, config.telemetry_freshness_entity) == "fresh"
                and soc is not None and reserve is not None and soc < reserve):
            next_step = (
                " Далі батарею заряджатиме лише сонце; повернення до "
                f"пріоритету сонця при <b>{compact_number(reserve + 10)}%</b>."
                if 20 <= reserve < 95 else ""
            )
            queue_notification(
                state,
                f"🔋 Заряд <b>{compact_number(soc)}%</b>, нижче резерву "
                f"<b>{compact_number(reserve)}%</b>. ДТЕК підключено для "
                f"заряджання батареї до <b>{compact_number(reserve)}%</b>.{next_step}",
                "battery_reserve_charging", since,
            )
            state["pending_notifications"][-1].update({
                "reserve_soc": reserve,
                "release_soc": min(100, reserve + 10) if reserve < 95 else None,
            })
        return True
    if mode not in {"panic_grid_hold", "hybrid_grid_hold"}:
        return True
    voltage = numeric_entity(client, config.grid_voltage_entity)
    if (voltage is None or voltage <= 180
            or entity_value(client, config.telemetry_freshness_entity) != "fresh"):
        return True
    soc = numeric_entity(client, config.battery_soc_entity)
    reserve = numeric_entity(client, config.ahm_minimum_soc_entity)
    release = (
        min(100, reserve + 10)
        if reserve is not None and 20 <= reserve < 95 else None
    )
    state["grid_hold_context"] = {
        "mode": mode,
        "reserve_soc": reserve,
        "release_soc": release,
    }
    same_episode = (
        state.get("grid_hold_episode_active") is True
        and number(state.get("grid_hold_episode_reserve_soc")) == reserve
    )
    state["grid_hold_episode_active"] = True
    state["grid_hold_episode_reserve_soc"] = reserve
    if same_episode:
        LOGGER.info(
            "Suppressed duplicate Grid Hold notification within reserve episode"
        )
        return True
    lines = ["🔌 <b>Будинок перейшов у режим сонце + ДТЕК</b>"]
    if reserve is not None and 20 <= reserve <= 95:
        if reserve < 95:
            lines.append(
                f"Резерв <b>{compact_number(reserve)}%</b> досягнуто. "
                "Батарею заряджає лише сонце; повернення до пріоритету "
                f"сонця при <b>{compact_number(release)}%</b>."
            )
        else:
            lines.append(
                "EnergyHub зберігає резерв <b>95%</b>; повернення до "
                "пріоритету сонця очікує зниження вибраного резерву."
            )
    queue_notification(state, "\n".join(lines), "grid_hold_started", since)
    state["pending_notifications"][-1].update({
        "reserve_soc": reserve,
        "release_soc": release,
    })
    return True


def observe_grid_confidence(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> bool:
    state.setdefault("pending_notifications", [])
    observed = valid_confidence(entity_value(client, config.grid_confidence_entity))
    if observed is None:
        return False
    reserve_entity = client.state(config.weather_buffer_entity) or {}
    reserve = reserve_entity.get("attributes") or {}
    if not isinstance(reserve, dict):
        reserve = {}
    selected = number(reserve.get("applied_minimum_soc"))
    previous = valid_confidence(state.get("grid_confidence"))
    if previous is None:
        state["grid_confidence"] = observed
        state["grid_confidence_reserve_soc"] = selected
        LOGGER.info("Initialized Grid Confidence: %s", observed)
        return True
    changed = False
    if observed != previous:
        state["grid_confidence"] = observed
        state["grid_confidence_pending"] = {
            "previous": previous,
            "current": observed,
            "previous_reserve": state.get("grid_confidence_reserve_soc"),
            "observed_at": now.isoformat(),
        }
        LOGGER.info("Grid Confidence changed: %s -> %s; awaiting reserve reaction", previous, observed)
        changed = True

    pending = state.get("grid_confidence_pending")
    if isinstance(pending, dict) and pending.get("current") == observed:
        reserve_confidence = valid_confidence(reserve.get("grid_confidence"))
        try:
            pending_since = datetime.fromisoformat(str(pending.get("observed_at")))
            if pending_since.tzinfo is None:
                pending_since = pending_since.replace(tzinfo=now.tzinfo)
            reaction_timeout = (now - pending_since).total_seconds() >= 120
        except (TypeError, ValueError):
            reaction_timeout = True
        if reserve_confidence == observed or reaction_timeout:
            message_reserve = reserve
            if reaction_timeout and reserve_confidence != observed:
                message_reserve = dict(reserve)
                message_reserve.update({
                    "control_applied": False,
                    "applied_minimum_soc": None,
                    "recommended_soc": None,
                })
            queue_notification(
                state,
                confidence_message(
                    str(pending["previous"]),
                    observed,
                    message_reserve,
                    pending.get("previous_reserve"),
                ),
                "grid_confidence",
                now,
            )
            state["grid_confidence_pending"] = None
            state["grid_confidence_reserve_soc"] = selected
            if reaction_timeout and reserve_confidence != observed:
                LOGGER.warning(
                    "Grid Confidence reserve reaction timed out: confidence=%s reserve_confidence=%s",
                    observed,
                    reserve_confidence,
                )
            LOGGER.info("Grid Confidence reaction queued: %s", observed)
            return True
    elif selected is not None:
        state["grid_confidence_reserve_soc"] = selected
    return changed


def observe_peak_load_guard(
    config: Config,
    client: HomeAssistantClient,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    entity = client.state(config.peak_load_guard_event_entity)
    if not entity:
        return False
    attributes = entity.get("attributes") or {}
    events = attributes.get("events")
    if not isinstance(events, list):
        events = [attributes.get("event")]
    seen = list(state.get("peak_load_guard_seen_ids") or [])
    cursors = dict(state.get("peak_load_guard_cursors") or {})
    legacy_id = state.get("peak_load_guard_last_event_id")
    attention_pending = state.setdefault("peak_load_attention_pending", {})
    # On upgrade, start after the already observed legacy event, not at the
    # beginning of retained history. Subsequent reads drain every new event.
    if not seen and legacy_id:
        for index, event in enumerate(events):
            if isinstance(event, dict) and event.get("event_id") == legacy_id:
                seen.extend(f"{item.get('stream_id', '')}:{item.get('event_id', '')}"
                            for item in events[:index + 1] if isinstance(item, dict))
                events = events[index + 1:]
                break
    changed = False
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "")
        event_type = event.get("type")
        key = f"{event.get('stream_id', '')}:{event_id}"
        stream = str(event.get("stream_id") or "")
        sequence = event.get("sequence")
        if not event_id or event_type not in {"shed_recommended", "restore_recommended", "no_candidates",
                "load_shed", "load_restored", "control_complete", "control_attention",
                "load_warning", "load_warning_cleared", "battery_reserve_warning"}:
            continue
        if key in seen or (not event.get("stream_id") and event_id == legacy_id):
            continue
        if stream and isinstance(sequence, int) and sequence <= cursors.get(stream, 0):
            continue
        if stream and isinstance(sequence, int):
            cursor = cursors.get(stream)
            if cursor is not None and sequence > cursor + 1:
                LOGGER.warning("Peak Load Guard event history gap: %s after %s", sequence, cursor)
            cursors[stream] = sequence
        # Each confirmed restoration already has one message; completion is
        # dashboard/journal bookkeeping, not a second restoration notification.
        if event_type == 'control_attention':
            cycle_key = str(event.get('cycle_id') or event.get('stream_id') or 'unknown')
            group = attention_pending.setdefault(cycle_key, {
                'first_at': now.isoformat(), 'reasons': [], 'affected_loads': [],
                'load_percent': event.get('load_percent'),
            })
            reason = event.get('reason')
            if reason and reason not in group['reasons']:
                group['reasons'].append(reason)
            known = {item.get('key') for item in group['affected_loads'] if isinstance(item, dict)}
            for item in event.get('affected_loads') or []:
                if isinstance(item, dict) and item.get('key') not in known:
                    group['affected_loads'].append({'key': item.get('key')})
                    known.add(item.get('key'))
            group['load_percent'] = event.get('load_percent')
        elif event_type not in {'control_complete', 'shed_recommended', 'restore_recommended', 'no_candidates'}:
            queue_notification(state, peak_load_guard_message(event),
                               f"peak_load_guard_{event_type}", now)
        seen.append(key)
        state["peak_load_guard_last_event_id"] = event_id
        LOGGER.info("Queued Peak Load Guard event: %s cycle=%s", key, event.get("cycle_id"))
        changed = True
    state["peak_load_guard_seen_ids"] = seen[-128:]
    state["peak_load_guard_cursors"] = dict(list(cursors.items())[-8:])
    for cycle_key, group in list(attention_pending.items()):
        try:
            age = (now-datetime.fromisoformat(group['first_at'])).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = 60
        if age < 60:
            continue
        event = dict(type='control_attention', mode='automatic', cycle_id=cycle_key,
                     reasons=group.get('reasons') or [],
                     affected_loads=group.get('affected_loads') or [],
                     load_percent=group.get('load_percent'))
        queue_notification(state, peak_load_guard_message(event),
                           "peak_load_guard_control_attention", now)
        del attention_pending[cycle_key]
        changed = True
    return changed


def observe_heat_pump_restart_restore(
    config: Config,
    client: HomeAssistantClient,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    """Queue one family message for each new HA restart-restore report."""
    entity = client.state(config.heat_pump_restart_event_entity)
    raw = (entity or {}).get("state")
    if not raw or raw in {"unknown", "unavailable"}:
        return False
    try:
        event = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(event, dict):
        return False
    event_id = str(event.get("id") or "")
    if not event_id or event_id == state.get("heat_pump_restart_event_id"):
        return False
    try:
        message = heat_pump_restart_restored_message(event)
    except ValueError:
        return False
    queue_notification(state, message, "heat_pump_restart_restored", now)
    state["heat_pump_restart_event_id"] = event_id
    LOGGER.info("Queued heat-pump restart restoration report: %s", event_id)
    return True


def observe_inverter_strategy_fault(
    config: Config,
    client: HomeAssistantClient,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    """Report an unconfirmed inverter strategy once, including after restart."""
    mode = entity_value(client, config.operating_mode_entity)
    if mode in {"transition_failed", "inconsistent"}:
        if state.get("inverter_strategy_fault_reported"):
            return False
        queue_notification(
            state,
            "⚠️ <b>EnergyHub не підтвердив режим інвертора.</b> "
            "Автоматичне керування резервом призупинене. "
            "Перевірте стан інвертора та журнал EnergyHub; "
            "потрібна перевірка людиною.",
            "technical_inverter_strategy_fault",
            now,
        )
        state["inverter_strategy_fault_reported"] = True
        return True
    if mode in {"solar", "panic", "panic_grid_hold", "hybrid_charging", "hybrid_grid_hold"}:
        if state.pop("inverter_strategy_fault_reported", None):
            return True
    return False


def observe_battery_reserve(config, client, state, now):
    """New actionable advice only; manual changes never authorize a write."""
    from .events import reserve_change_reason, reserve_recommendation_ready, reserve_reason
    reserve = (client.state(config.weather_buffer_entity) or {}).get("attributes") or {}
    changed = False
    selected = number(reserve.get("applied_minimum_soc"))
    previous_selected = number(state.get("reserve_selected_observed"))
    selected_changed = False
    if selected is not None and 20 <= selected <= 95:
        if previous_selected is None:
            state["reserve_selected_observed"] = selected
            changed = True
        elif selected != previous_selected:
            state["reserve_selected_observed"] = selected
            selected_changed = True
            changed = True
            if reserve.get("management_mode") != "automatic":
                state.setdefault("pending_notifications", [])[:] = [
                    item for item in state.get("pending_notifications", [])
                    if item.get("kind") != "battery_reserve_advice"
                ]
                queue_notification(
                    state,
                    f"🔋 Мін. заряд змінено вручну: <b>{previous_selected:g}% → {selected:g}%</b>.",
                    "battery_reserve_manual_change",
                    now,
                )
    if not state.get("reserve_notifications_v2"):
        obsolete = {"battery_reserve_recommendation", "battery_reserve_conditions",
                    "uhmc_weather_reserve_restored"}
        state["pending_notifications"] = [x for x in state.get("pending_notifications", [])
                                          if x.get("kind") not in obsolete]
        state["weather_reserve_restoration_events"] = []
        state["reserve_notifications_v2"] = True
        changed = True
    # Future automatic control must supply an explicit acknowledged change.
    if reserve.get("management_mode") == "automatic":
        change_id = reserve.get("applied_change_id")
        old = number(reserve.get("previous_applied_soc"))
        new = number(reserve.get("applied_minimum_soc"))
        if (reserve.get("applied_change_confirmed") is True and change_id
                and old is not None and new is not None and 20 <= old <= 95
                and 20 <= new <= 95 and old != new
                and change_id != state.get("reserve_applied_change_id")):
            state["reserve_applied_change_id"] = change_id
            queue_notification(state,
                f"🔋 Мін. заряд: <b>{old:g}% → {new:g}%</b> — "
                f"{reserve_change_reason(reserve, old, new)}.",
                "battery_reserve_applied", now)
            return True
        return changed
    if not reserve_recommendation_ready(reserve):
        return changed
    target = number(reserve.get("recommended_soc"))
    selected = number(reserve.get("applied_minimum_soc"))
    previous = state.get("reserve_last_valid_recommendation")
    if previous == target:
        return changed
    state["reserve_last_valid_recommendation"] = target
    if (previous is None or target == selected or selected_changed
            or weather_warning_quiet_hours(now)):
        return True
    pending = state.setdefault("pending_notifications", [])
    if any(x.get("kind") == "uhmc_weather_warning" and x.get("created_at") == now.isoformat() for x in pending):
        return True
    message = (f"🔋 Мін. заряд: <b>{selected:g}%</b>. Рекомендація: <b>{target:g}%</b>.\n"
               f"Причина: {reserve_reason(reserve)}. Рішення за родиною.")
    queue_notification(state, message, "battery_reserve_advice", now)
    state["pending_notifications"][-1]["recommended_soc"] = target
    return True


def weather_warning_quiet_hours(now: datetime) -> bool:
    minutes = now.hour * 60 + now.minute
    return minutes >= 23 * 60 or minutes <= 8 * 60 + 1


def observe_weather_warnings(
    config: Config,
    client: HomeAssistantClient,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    entity = client.state(config.weather_buffer_entity)
    if not entity:
        return False
    reserve = entity.get("attributes") or {}
    if not isinstance(reserve, dict):
        return False
    warnings = (
        reserve.get("weather_source_warnings")
        or reserve.get("weather_warnings")
        or []
    )
    if not isinstance(warnings, list):
        return False

    current_modifier = number(reserve.get("weather_modifier_percent")) or 0
    current_recommended = number(reserve.get("recommended_soc"))
    previous_modifier = number(state.get("weather_reserve_modifier"))
    previous_recommended = number(state.get("weather_reserve_recommended_soc"))

    seen = list(state.setdefault("weather_warning_seen_event_ids", []))
    seen_set = set(seen)
    report_events = state.setdefault("weather_warning_report_events", [])
    changed = False
    superseded_ids = {item.get("event_id") for item in state.get("uhmc_superseded_warnings", [])
                      if isinstance(item, dict)}
    current_report = [item for item in report_events if item.get("event_id") not in superseded_ids]
    if current_report != report_events:
        report_events = current_report
        state["weather_warning_report_events"] = report_events
        changed = True
    if previous_modifier is None:
        state["weather_reserve_modifier"] = current_modifier
        state["weather_reserve_recommended_soc"] = current_recommended
        changed = True
    elif (
        previous_modifier > 0
        and not reserve.get("advice_only")
        and current_modifier == 0
        and bool(reserve.get("dry_run"))
        and previous_recommended is not None
        and current_recommended is not None
        and current_recommended < previous_recommended
    ):
        restoration = {
            "event_id": str(reserve.get("evaluation_signature") or reserve.get("evaluated_at") or now.isoformat()),
            "previous_recommended_soc": previous_recommended,
            "recommended_soc": current_recommended,
        }
        if weather_warning_quiet_hours(now):
            restorations = state.setdefault("weather_reserve_restoration_events", [])
            restorations.append(restoration)
            state["weather_reserve_restoration_events"] = restorations[-20:]
            LOGGER.info("Saved weather-reserve restoration for morning report")
        else:
            queue_notification(
                state,
                weather_reserve_restoration_message(restoration),
                "uhmc_weather_reserve_restored",
                now,
            )
            LOGGER.info("Queued daytime weather-reserve restoration")
        changed = True
    if (
        state.get("weather_reserve_modifier") != current_modifier
        or state.get("weather_reserve_recommended_soc") != current_recommended
    ):
        state["weather_reserve_modifier"] = current_modifier
        state["weather_reserve_recommended_soc"] = current_recommended
        changed = True
    for event in warnings:
        if not isinstance(event, dict):
            continue
        event_id = weather_warning_event_id(event)
        if event_id is None or event_id in seen_set or event_id in superseded_ids:
            continue
        stored = dict(event)
        stored["event_id"] = event_id
        if weather_warning_quiet_hours(now):
            report_events.append(stored)
            state["weather_warning_report_events"] = report_events[-50:]
            LOGGER.info("Saved overnight UHMC warning for morning report: %s", event_id)
        else:
            queue_notification(
                state,
                weather_warning_message(stored, reserve),
                "uhmc_weather_warning",
                now,
            )
            LOGGER.info("Queued daytime UHMC warning: %s", event_id)
        seen.append(event_id)
        seen_set.add(event_id)
        changed = True
    state["weather_warning_seen_event_ids"] = seen[-200:]
    return changed


def observe_soc_anomaly(
    config: Config,
    client: HomeAssistantClient,
    state: dict[str, Any],
    now: datetime,
) -> bool:
    entity = client.state(config.soc_anomaly_latest_entity)
    if not entity:
        return False
    attributes = entity.get("attributes") or {}
    if not isinstance(attributes, dict):
        return False
    event = attributes.get("latest_event")
    if not isinstance(event, dict):
        return False
    event_id = soc_anomaly_event_id(event)
    if event_id is None:
        return False

    # Keep independent day evidence after morning-report events are acknowledged.
    try:
        day = datetime.fromisoformat(str(event['timestamp'])).astimezone(ZoneInfo(config.timezone)).date()
        if 0 <= (now.date()-day).days <= 30:
            days = state.setdefault('battery_jump_days', {})
            days[day.isoformat()] = True
            cutoff = (now.date()-timedelta(days=30)).isoformat()
            state['battery_jump_days'] = {k:v for k,v in days.items() if k >= cutoff}
    except (ValueError, TypeError, KeyError):
        pass

    event_count = number(attributes.get("event_count"))
    if not state.get("soc_anomaly_initialized"):
        state["soc_anomaly_initialized"] = True
        state["soc_anomaly_last_event_id"] = event_id
        state["soc_anomaly_last_event_count"] = event_count
        LOGGER.info("Initialized SOC anomaly observation at %s", event_id)
        return True
    if state.get("soc_anomaly_last_event_id") == event_id:
        return False

    stored_event = dict(event)
    stored_event["event_id"] = event_id
    queue_notification(
        state,
        soc_anomaly_message(stored_event, ZoneInfo(config.timezone)),
        "soc_anomaly",
        now,
    )
    report_events = state.setdefault("soc_anomaly_report_events", [])
    report_events.append(stored_event)
    state["soc_anomaly_report_events"] = report_events[-100:]
    previous_count = number(state.get("soc_anomaly_last_event_count"))
    if (
        event_count is not None
        and previous_count is not None
        and event_count > previous_count + 1
    ):
        LOGGER.warning(
            "SOC anomaly journal advanced by %.0f events between bot polls; "
            "only the latest event details are available",
            event_count - previous_count,
        )
    state["soc_anomaly_last_event_id"] = event_id
    state["soc_anomaly_last_event_count"] = event_count
    LOGGER.info("Queued SOC anomaly notification: %s", event_id)
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
    attributes = (client.state('sensor.energyhub_peak_load_guard') or {}).get('attributes') or {}
    if attributes.get('control_schema') in (4, 5):
        # The shared controller reports confirmed actions, not the retired
        # reserve+30/+20 prediction messages from the independent relay guards.
        pending = state['pending_notifications']
        kept = [x for x in pending if not str(x.get('kind', '')).startswith('reserve_')]
        state['pending_notifications'] = kept
        return len(kept) != len(pending)
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
    # Reserve warnings are outage messages.  Reuse the grid observer's
    # persisted one-minute confirmation instead of reacting to one low or
    # invalid inverter sample.
    if (
        state.get("grid_online") is False
        and pumps
        and not reserve_warning_quiet_hours(now)
    ):
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
        if item.get('kind') == 'technical_inverter_strategy_fault':
            if client is None:
                index += 1
                continue
            mode = entity_value(client, config.operating_mode_entity)
            if mode in {"solar", "panic", "panic_grid_hold",
                        "hybrid_charging", "hybrid_grid_hold"}:
                item['message'] = (
                    "⚠️ <b>EnergyHub раніше не підтвердив режим інвертора.</b> "
                    f"Подія: {item.get('created_at', 'час невідомий')}. "
                    f"Зараз підтверджений режим: {mode}. "
                    "Перевірте журнал EnergyHub."
                )
            elif mode in {"transition_failed", "inconsistent"}:
                item['message'] = (
                    "⚠️ <b>EnergyHub не підтвердив режим інвертора.</b> "
                    "Автоматичне керування резервом призупинене. "
                    "Перевірте стан інвертора та журнал EnergyHub; "
                    "потрібна перевірка людиною."
                )
            else:
                index += 1
                continue
        if item.get('kind') == 'ha_restart_summary':
            current_boot = boot_id(client) if client is not None else None
            if current_boot is None:
                index += 1
                continue
            if current_boot != item.get('boot_id'):
                queue.pop(index)
                changed = True
                continue
            item['message'] = restart_message(client, now, current_boot)
        if str(item.get('kind', '')).startswith('dashboard_control_'):
            if state.get('restart_summary_pending'):
                index += 1
                continue
            if not queued_control_is_current(client, item, now):
                queue.pop(index)
                changed = True
                continue
        # Old retained/queued trial advice must not be re-delivered after upgrade.
        if item.get('kind') in {'peak_load_guard_shed_recommended',
                                'peak_load_guard_restore_recommended',
                                'peak_load_guard_no_candidates'}:
            queue.pop(index)
            changed = True
            continue
        if item.get('kind') == 'battery_reserve_advice':
            if client is None:
                index += 1
                continue
            from .events import reserve_recommendation_ready
            reserve = (client.state(config.weather_buffer_entity) or {}).get('attributes') or {}
            target = number(reserve.get('recommended_soc'))
            if (not reserve_recommendation_ready(reserve) or weather_warning_quiet_hours(now)
                    or target != item.get('recommended_soc')
                    or target == number(reserve.get('applied_minimum_soc'))):
                queue.pop(index)
                changed = True
                continue
            from .events import reserve_reason
            selected = number(reserve.get('applied_minimum_soc'))
            item['message'] = (f"🔋 Мін. заряд: <b>{selected:g}%</b>. Рекомендація: <b>{target:g}%</b>.\n"
                               f"Причина: {reserve_reason(reserve)}. Рішення за родиною.")
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
        chat_id = notification_chat(config, str(item.get("kind", "")))
        quiet_phase = family_quiet_phase(now)
        if chat_id == config.destination_chat_id and quiet_phase == "overnight":
            archive_overnight_family_event(state, item)
            LOGGER.info(
                "Archived overnight %s notification for the morning report",
                item.get("kind", "event"),
            )
            queue.pop(index)
            changed = True
            continue
        if chat_id == config.destination_chat_id and quiet_phase == "morning_buffer":
            index += 1
            continue
        telegram.send_message(chat_id, str(item["message"]))
        LOGGER.info("Delivered queued %s notification", item.get("kind", "event"))
        queue.pop(index)
        changed = True
    return changed


def refresh_queued_reserve_warning(
    config: Config,
    client: HomeAssistantClient,
    kind: str,
) -> tuple[str, str | None]:
    attributes = (client.state('sensor.energyhub_peak_load_guard') or {}).get('attributes') or {}
    if attributes.get('control_schema') in (4, 5):
        return 'drop', None
    try:
        offset = int(kind.removeprefix("reserve_"))
    except ValueError:
        return "drop", None
    freshness = entity_value(client, config.telemetry_freshness_entity)
    soc = numeric_entity(client, config.battery_soc_entity)
    minimum = numeric_entity(client, config.ahm_minimum_soc_entity)
    if str(freshness or "").strip().lower() != "fresh" or soc is None or minimum is None:
        return "defer", None
    voltage = numeric_entity(client, config.grid_voltage_entity)
    if voltage is None:
        return "defer", None
    if voltage > 180:
        return "drop", None
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
                getattr(config, "weather_humidity_low_percent", 30),
                getattr(config, "weather_humidity_high_percent", 80),
                getattr(config, "weather_humidity_change_percent", 25),
            )
            if lines:
                LOGGER.info("Weather report uses %s %s forecast", entity_id, forecast_type)
                return lines
            failures.append(f"{entity_id}/{forecast_type}: no periods for today")
    LOGGER.warning("No usable weather forecast; weather lines will be omitted. Attempts: %s", " | ".join(failures))
    return []


def create_reports(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> tuple[str | None, str]:
    weather_lines = fetch_weather(config, client, now)

    calendar_lines: list[str] = []
    if config.family_calendar_ical_url:
        try:
            calendar_lines = CalendarService(
                config.family_calendar_ical_url,
                ZoneInfo(config.timezone),
            ).digest_lines(now.date())
        except CalendarError as exc:
            LOGGER.warning("Family calendar omitted from morning report: %s", exc)

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

    consumption = numeric_entity(client, config.yesterday_consumption_entity)
    tariff_import = {
            "week_night_kwh": numeric_entity(client, "sensor.energyhub_grid_import_night_previous_week_estimated"),
            "week_normal_kwh": numeric_entity(client, "sensor.energyhub_grid_import_normal_previous_week_estimated"),
            "week_total_kwh": numeric_entity(client, "sensor.energyhub_grid_import_previous_week_estimated"),
            "week_cost_uah": numeric_entity(client, "sensor.energyhub_grid_import_cost_previous_week_estimated"),
            "previous_month_night_kwh": numeric_entity(client, "sensor.energyhub_grid_import_night_previous_month_estimated"),
            "previous_month_normal_kwh": numeric_entity(client, "sensor.energyhub_grid_import_normal_previous_month_estimated"),
            "previous_month_total_kwh": numeric_entity(client, "sensor.energyhub_grid_import_previous_month_estimated"),
            "previous_month_cost_uah": numeric_entity(client, "sensor.energyhub_grid_import_cost_previous_month_estimated"),
            "night_price": numeric_entity(
                client, config.night_grid_import_price_entity
            ),
            "normal_price": numeric_entity(
                client, config.normal_grid_import_price_entity
            ),
    }
    weather_buffer_entity = client.state(config.weather_buffer_entity) or {}
    weather_buffer_attributes = weather_buffer_entity.get("attributes", {})
    weather_buffer = (
        weather_buffer_attributes
        if isinstance(weather_buffer_attributes, dict)
        and weather_buffer_attributes.get("date") == now.date().isoformat()
        else None
    )
    def helper_mode(entity_id, *, enabled="EH", disabled="вручну"):
        value = entity_value(client, entity_id)
        if value == "on":
            return enabled
        if value == "off":
            return disabled
        return "уточнюється"

    reserve_mode = str(
        weather_buffer_attributes.get("management_mode") or ""
    ).lower()
    if reserve_mode == "automatic":
        reserve_owner = "EH"
    elif reserve_mode == "manual":
        reserve_owner = "вручну"
    else:
        reserve_owner = "уточнюється"
    control_status = control_authority_message(
        inverter=helper_mode('input_boolean.energyhub_autopilot'),
        reserve=reserve_owner,
        overload=helper_mode(
            'input_boolean.energyhub_load_control_armed',
            disabled='вручну',
        ),
        smart_heating=entity_value(
            client,
            'input_boolean.energyhub_smart_heating',
        ),
    )
    consumption_average = number(
        (weather_buffer or {}).get("consumption_average_kwh")
    )
    consumption_sample_count = int(
        number((weather_buffer or {}).get("consumption_sample_count")) or 0
    )
    current_soc = numeric_entity(client, config.battery_soc_entity)
    selected_reserve = numeric_entity(client, config.ahm_minimum_soc_entity)
    energy_outlook = morning_energy_lines(
        forecast=solar_forecast,
        consumption_average=consumption_average,
        soc=current_soc,
        reserve_soc=selected_reserve,
        battery_capacity_kwh=config.battery_capacity_kwh,
        battery_voltage_v=config.battery_nominal_voltage_v,
        battery_charge_current_a=config.battery_grid_charge_current_a,
        battery_efficiency=config.battery_charge_efficiency,
        house_reference_current_a=config.house_grid_reference_current_a,
    )
    full_state = entity_value(client, "sensor.energyhub_daily_battery_reached_full")
    forecast_accuracy = {
        "actual_kwh": numeric_entity(client, "sensor.energyhub_daily_solar_actual"),
        "forecast_kwh": numeric_entity(client, "sensor.energyhub_daily_solar_forecast"),
        "error_percent": numeric_entity(client, "sensor.energyhub_daily_solar_forecast_error_percent"),
        "battery_full": full_state == "on" if full_state in {"on", "off"} else None,
    }
    device_health_lines = data_incidents.morning_lines(state, now) + environment_report_lines(state, now)
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
    try:
        smart_plug_lines = smart_plug_report_lines(config, client)
    except HomeAssistantError as exc:
        LOGGER.warning("Smart-plug availability check omitted: %s", exc)
        smart_plug_lines = []
    core_log = supervisor_log = None
    unavailable_logs = []
    try:
        core_log = client.error_log()
    except HomeAssistantError as exc:
        LOGGER.warning("HA Core log digest unavailable: %s", exc)
        unavailable_logs.append("Core")
    # Supervisor logs require the broad manager role. Do not grant that
    # privilege to a Telegram app solely for a morning digest.
    log_digest_lines = system_digest_lines(core_log, supervisor_log, now)
    if unavailable_logs:
        log_digest_lines.append("ℹ️ Недоступний журнал: " + ", ".join(unavailable_logs))
    log_digest_lines.append("ℹ️ Supervisor не перевіряється: потрібні розширені права.")
    current_strategy = []
    current_mode = ""
    try:
        current_mode = str(entity_value(client, config.operating_mode_entity) or "")
        voltage = numeric_entity(client, config.grid_voltage_entity)
        current_strategy = strategy_lines(current_mode,
            selected_reserve, now=now.astimezone(timezone),
            fresh=entity_value(client, config.telemetry_freshness_entity) == "fresh",
            grid_online=voltage is not None and voltage > 180)
    except HomeAssistantError as exc:
        LOGGER.warning("Current strategy description unavailable: %s", exc)
    anomaly_lines = soc_anomaly_report_lines(
        state.get("soc_anomaly_report_events", []),
        timezone,
        history_days=state.get('battery_jump_days', {}),
    )
    overnight_lines = overnight_family_event_lines(
        [
            event
            for event in state.get("overnight_family_events", [])
            if isinstance(event, dict)
        ],
        inverter_mode=current_mode,
        mode_observed_at=now,
    )
    family_report = build_report(
        current_strategy_lines=current_strategy,
        overnight_event_lines=overnight_lines,
        calendar_lines=calendar_lines,
        weather_lines=[
            line
            for line in [
                *weather_lines,
                morning_status(
                    state.get("uhmc_last_snapshot"),
                    now.astimezone(timezone),
                ),
            ]
            if line
        ],
        astronomy_lines=astronomy,
        solar_forecast=solar_forecast,
        solar_window=window,
        solar_peak_value=peak,
        threshold_w=config.useful_solar_threshold_w,
        consumption=consumption,
        snapshot={},
        night_import=None,
        tariff_import=tariff_import,
        report_date=now.date(),
        current_soc=current_soc,
        solar_average_w=numeric_entity(client, "sensor.energyhub_solar_power_15m_average"),
        energy_outlook_lines=energy_outlook,
        forecast_accuracy=forecast_accuracy,
        ahm_minimum_soc=selected_reserve,
        weather_buffer=weather_buffer,
        control_status_line=control_status,
        consumption_average=consumption_average,
        consumption_sample_count=consumption_sample_count,
        weather_warning_lines=weather_warning_report_lines(
            state.get("weather_warning_report_events", []), now
        ),
        weather_restoration_lines=weather_reserve_restoration_report_lines(
            state.get("weather_reserve_restoration_events", [])
        ),
        heat_pump_management=None,
        device_health_lines=device_health_lines,
        smart_plug_lines=smart_plug_lines,
        inverter_lines=inverter_lines,
        grid_status_lines=grid_status_report_lines(
            entity_value(client, config.grid_confidence_entity),
            numeric_entity(client, config.grid_available_24h_entity),
            numeric_entity(client, config.grid_outage_24h_entity),
        ),
        soc_anomaly_lines=[],
    )
    technical_report = build_technical_report(
        log_digest_lines=log_digest_lines,
        soc_anomaly_lines=anomaly_lines,
        device_health_lines=device_health_lines,
        smart_plug_lines=smart_plug_lines,
        inverter_lines=inverter_lines,
    )
    return technical_report, family_report


def create_report(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> str:
    """Compatibility helper returning the family-facing morning report."""
    return create_reports(config, client, state, now)[1]


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

    technical, family = create_reports(config, client, state, now)
    messages = [message for message in (technical, family) if message]
    state["morning_report_outbox"] = {
        "date": report_date,
        "message": family,
        "messages": messages,
        "destinations": [
            (getattr(config, "technical_chat_id", "") or config.destination_chat_id)
            if technical and message == technical else config.destination_chat_id
            for message in messages
        ],
        "next_message_index": 0,
        "soc_anomaly_event_ids": [
            event_id
            for event in state.get("soc_anomaly_report_events", [])
            if isinstance(event, dict)
            and (event_id := soc_anomaly_event_id(event)) is not None
        ],
        "weather_warning_event_ids": [
            event_id
            for event in state.get("weather_warning_report_events", [])
            if isinstance(event, dict)
            and (event_id := weather_warning_event_id(event)) is not None
        ],
        "weather_restoration_event_ids": [
            str(event.get("event_id"))
            for event in state.get("weather_reserve_restoration_events", [])
            if isinstance(event, dict) and event.get("event_id")
        ],
        "overnight_family_event_ids": [
            overnight_family_event_id(event)
            for event in state.get("overnight_family_events", [])
            if isinstance(event, dict)
        ],
    }
    return True


def acknowledge_soc_anomaly_report(
    state: dict[str, Any],
    event_ids: list[str],
) -> None:
    acknowledged = set(event_ids)
    state["soc_anomaly_report_events"] = [
        event
        for event in state.get("soc_anomaly_report_events", [])
        if not isinstance(event, dict)
        or soc_anomaly_event_id(event) not in acknowledged
    ]


def acknowledge_weather_warning_report(
    state: dict[str, Any],
    event_ids: list[str],
) -> None:
    acknowledged = set(event_ids)
    state["weather_warning_report_events"] = [
        event
        for event in state.get("weather_warning_report_events", [])
        if not isinstance(event, dict)
        or weather_warning_event_id(event) not in acknowledged
    ]


def acknowledge_weather_restoration_report(
    state: dict[str, Any],
    event_ids: list[str],
) -> None:
    acknowledged = set(event_ids)
    state["weather_reserve_restoration_events"] = [
        event
        for event in state.get("weather_reserve_restoration_events", [])
        if not isinstance(event, dict)
        or str(event.get("event_id")) not in acknowledged
    ]


def acknowledge_overnight_family_events(
    state: dict[str, Any],
    event_ids: list[str],
) -> None:
    acknowledged = set(event_ids)
    state["overnight_family_events"] = [
        event
        for event in state.get("overnight_family_events", [])
        if not isinstance(event, dict)
        or overnight_family_event_id(event) not in acknowledged
    ]


def clean_old_state(state: dict[str, Any], _now: datetime) -> None:
    for name in (
        "soc_snapshots",
        "night_baselines",
        "night_imports",
        "night_observed_modes",
    ):
        state.pop(name, None)


def observe_safely(observer, *args) -> bool:
    """Keep one malformed entity or observer from blocking report delivery."""
    try:
        return bool(observer(*args))
    except Exception:
        LOGGER.exception("Observation failed: %s", observer.__name__)
        return False


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
    uhmc_source = PublicTelegramSource(config.uhmc_weather_source)
    telegram = TelegramClient(config.bot_token)
    device_health = DeviceHealthMonitor(config)
    LOGGER.info("Morning report scheduled for %s; SOC and mode read live at delivery", config.send_time)

    started_at = datetime.now(timezone)
    if not state.get("initialized_at"):
        state["initialized_at"] = started_at.isoformat()
        if started_at.hour * 60 + started_at.minute >= time_minutes(config.send_time):
            state["last_report_date"] = started_at.date().isoformat()
            LOGGER.info("First start is after the morning deadline; the first scheduled report will be tomorrow")
        store.save(state)

    while True:
        now = datetime.now(timezone)
        changed = False
        try:
            data_incidents.observe(state, data_incidents.collect(client, config, state, now), now)
            changed = True
        except Exception:
            LOGGER.exception('Data availability observation failed')
        try:
            changed |= observe_safely(observe_grid, config, client, state, now)
            changed |= observe_safely(observe_grid_hold, config, client, state, now)
            changed |= observe_safely(observe_grid_confidence, config, client, state, now)
            changed |= observe_safely(observe_restart, client, state, now)
            changed |= observe_safely(observe_controls, client, state, now)
            changed |= observe_safely(observe_soc_anomaly, config, client, state, now)
            changed |= observe_safely(observe_peak_load_guard, config, client, state, now)
            changed |= observe_safely(observe_heat_pump_restart_restore,
                config, client, state, now
            )
            changed |= observe_safely(observe_inverter_strategy_fault,
                config, client, state, now
            )
            changed |= observe_safely(observe_weather_warnings, config, client, state, now)
            changed |= observe_safely(observe_battery_reserve, config, client, state, now)
            changed |= observe_safely(observe_reserve_warnings, config, client, state, now)
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
                outbox = state["morning_report_outbox"]
                messages = outbox.get("messages") or [outbox["message"]]
                destinations = outbox.get("destinations") or [config.destination_chat_id] * len(messages)
                index = int(outbox.get("next_message_index") or 0)
                while index < len(messages):
                    telegram.send_message(destinations[index], messages[index])
                    index += 1
                    outbox["next_message_index"] = index
                    store.save(state)
                state["last_report_date"] = now.date().isoformat()
                acknowledge_soc_anomaly_report(
                    state,
                    outbox.get("soc_anomaly_event_ids", []),
                )
                acknowledge_weather_warning_report(
                    state,
                    outbox.get("weather_warning_event_ids", []),
                )
                acknowledge_weather_restoration_report(
                    state,
                    outbox.get("weather_restoration_event_ids", []),
                )
                acknowledge_overnight_family_events(
                    state,
                    outbox.get("overnight_family_event_ids", []),
                )
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
            # Keep the external public-preview read after safety and family
            # notifications so a slow source cannot delay a grid/SOC message
            # or the scheduled morning report.
            changed |= poll_uhmc_weather(
                config,
                client,
                uhmc_source,
                state,
                now,
            )
            clean_old_state(state, now)
        except (HomeAssistantError, TelegramError, OSError) as exc:
            LOGGER.warning("Temporary monitoring/delivery failure; will retry: %s", exc)
        except Exception:
            LOGGER.exception("Unexpected loop failure; will retry")
        # Keep warning delivery outside the HA-dependent block, so HA downtime
        # cannot suppress its own notification. Telegram/network outages can.
        try:
            changed |= data_incidents.deliver(state, telegram, config,
                                              datetime.now(timezone), client)
        except (HomeAssistantError, TelegramError, OSError):
            LOGGER.warning('Data incident notification delivery unavailable; will retry')
        if changed:
            store.save(state)
        time.sleep(30)


if __name__ == "__main__":
    run()
