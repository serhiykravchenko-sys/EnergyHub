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
from . import house_monitor
from . import co2_monitor
from . import solar_settings
from . import solar_heating_morning
from . import system_log_monitor
from . import household_events
from . import grid_use, hp_summary, outage_schedule, hp_eco
from . import recovery_advice
from . import message_schedule
from . import beacon_recovery, technical_summary
from .bms_evidence import BmsEvidence
from .calendar_service import CalendarError, CalendarService
from .events import (
    confidence_message,
    outage_message,
    peak_load_guard_message,
    recovery_message,
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
    compact_number,
    control_authority_message,
    grid_status_report_lines,
    inverter_report_lines,
    number,
    solar_peak,
    sun_moon_lines,
    useful_solar_window,
    weather_summary,
)
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


def family_quiet_phase(now: datetime, config=None) -> str | None:
    """Return overnight collection or post-report buffer for family delivery."""
    return message_schedule.quiet_phase(now, config)


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
    if str(item.get('kind','')).startswith('reserve_') or item.get('kind') in {'dtek_schedule','dtek_tomorrow','dtek_tomorrow_missing'}:
        return
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
    "hp_eco_change", "hp_manual_transition", "dashboard_control_eco", "dashboard_control_quiet",
    "ha_restart_summary", "soc_anomaly", "uhmc_source_unavailable", "technical_dtek_emergency", "technical_dtek_sources",
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


def recovery_reserve_context(config,client,state=None,now=None):
    if state is not None and now is not None:
        from .reserve_policy_text import context, supply_line
        supply=supply_line(config,client,now)
        return context(config,client,state,now)+('\n'+supply if supply else '')
    reserve=numeric_entity(client,config.ahm_minimum_soc_entity)
    soc=numeric_entity(client,config.battery_soc_entity)
    if reserve is None:
        return ''
    text=f'\n🔋 Мінімальний резерв: <b>{compact_number(reserve)}%</b>.'
    mode=entity_value(client,config.operating_mode_entity)
    if soc is not None and soc<reserve:
        if mode in {'panic','hybrid_charging'}:
            text+=f'\n🔌 Заряджаємо від ДТЕК до резерву <b>{compact_number(reserve)}%</b>; далі зберігатимемо запас до відновлення заряду від сонця.'
        else:
            text+='\nℹ️ Заряд нижчий за резерв; заряджання від ДТЕК поки не підтверджено.'
    if mode=='solar':
        text+='\n🏠 Будинок працює без допомоги ДТЕК.'
    elif mode in {'panic','panic_grid_hold','hybrid_charging','hybrid_grid_hold'}:
        text+='\n🏠 Будинок працює з допомогою ДТЕК.'
    if state is not None and now is not None:
        text+=outage_schedule.recovery_context(config,client,state,now)
    return text


def observe_grid(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime, debounce_seconds: int = 180, *, solar_clock=None) -> bool:
    state.setdefault("pending_notifications", [])
    from . import solar_observation
    solar_now = solar_observation.observe(client, config, state, now, clock=solar_clock)
    from . import soc_interval
    from . import grid_instability
    instability_changed = grid_instability.observe(state, client, now)
    fresh_soc=entity_value(client,config.telemetry_freshness_entity)=='fresh'
    soc_interval.sample(state.get('outage_soc_interval'),now,numeric_entity(client,config.battery_soc_entity),fresh_soc)
    voltage = numeric_entity(client, config.grid_voltage_entity)
    if (voltage is None or not 0 <= voltage <= 300
            or entity_value(client,config.telemetry_freshness_entity) != 'fresh'):
        state['grid_candidate']=None; state['grid_candidate_since']=None
        state.pop('grid_last_observed_at', None)
        return False
    try:
        previous_observation = datetime.fromisoformat(state['grid_last_observed_at'])
        if not 0 <= (now-previous_observation).total_seconds() <= 90:
            state['grid_candidate']=None; state['grid_candidate_since']=None
    except (KeyError, TypeError, ValueError):
        state['grid_candidate']=None; state['grid_candidate_since']=None
    state['grid_last_observed_at'] = now.isoformat()
    confirmed=entity_value(client,'binary_sensor.energyhub_grid_confirmed')
    if confirmed in {'unknown','unavailable'}:
        state['grid_candidate']=None; state['grid_candidate_since']=None
        return False
    row=client.state('binary_sensor.energyhub_grid_confirmed') or {}
    attributes=row.get('attributes') or {}
    confirmation_window=number(attributes.get('confirmation_seconds'))
    confirmation_checked=number(attributes.get('checked_at'))
    trusted_confirmation=(confirmed in {'on','off'} and confirmation_window is not None
                          and confirmation_window >= 180
                          and confirmation_checked is not None
                          and 0 <= now.timestamp()-confirmation_checked <= 90
                          and attributes.get('transition_pending') is False)
    observed_online = confirmed=='on' if trusted_confirmation else voltage > 180
    if trusted_confirmation:
        debounce_seconds=0
    event_time=now
    if trusted_confirmation:
        stamp=number((row.get('attributes') or {}).get('transition_at'))
        if stamp is not None and 0<=now.timestamp()-stamp<=confirmation_window+90:
            event_time=datetime.fromtimestamp(stamp,now.tzinfo)
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
            state["grid_candidate_since"] = event_time.isoformat()
            LOGGER.warning("App started while grid is offline; waiting for debounce")
            return True
        try:
            candidate_since = datetime.fromisoformat(candidate_since_value)
        except (TypeError, ValueError):
            state["grid_candidate_since"] = event_time.isoformat()
            return True
        if (now - candidate_since).total_seconds() < debounce_seconds:
            return False
        state["grid_online"] = False
        state["grid_candidate"] = None
        state["grid_candidate_since"] = None
        state["outage_started_at"] = candidate_since.isoformat()
        state['outage_soc_interval']=soc_interval.begin(now,numeric_entity(client,config.battery_soc_entity))
        queue_notification(state, outage_message(candidate_since,
                           numeric_entity(client, config.battery_soc_entity))+'\n'+solar_observation.line(state,solar_now),
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
        state["grid_candidate_since"] = event_time.isoformat()
        LOGGER.info("Grid transition candidate: %s (%.1f V)", "online" if observed_online else "offline", voltage)
        return True

    candidate_since_value = state.get("grid_candidate_since")
    try:
        candidate_since = datetime.fromisoformat(candidate_since_value)
    except (TypeError, ValueError):
        state["grid_candidate_since"] = event_time.isoformat()
        return True
    if (now - candidate_since).total_seconds() < debounce_seconds:
        return False

    state["grid_online"] = observed_online
    state["grid_candidate"] = None
    state["grid_candidate_since"] = None
    soc = numeric_entity(client, config.battery_soc_entity)
    if observed_online:
        state['grid_restored_at']=candidate_since.isoformat()
        from . import dtek_emergency
        dtek_emergency.restore(state)
        outage_start_value = state.get("outage_started_at")
        try:
            outage_start = datetime.fromisoformat(outage_start_value) if outage_start_value else None
        except ValueError:
            outage_start = None
        interval=state.pop('outage_soc_interval',None)
        rate_line=soc_interval.net_line(interval,now,soc)
        message=recovery_message(candidate_since,outage_start,soc)
        if rate_line:
            message=recovery_message(candidate_since,outage_start,None)+'\n'+rate_line
        solar_line = solar_observation.line(state, solar_now)
        message += '\n'+solar_line
        queue_notification(state, message, "grid_recovered", candidate_since)
        state['pending_notifications'][-1]['restoration_event'] = dict(
            at=candidate_since.isoformat(), outage_start=outage_start.isoformat() if outage_start else None, soc=soc, rate_line=rate_line, solar_line=solar_line)
        state["outage_started_at"] = None
        LOGGER.info("External grid recovered after debounce")
    else:
        state["outage_started_at"] = candidate_since.isoformat()
        state['outage_soc_interval']=soc_interval.begin(now,soc)
        queue_notification(state, outage_message(candidate_since, soc)+'\n'+solar_observation.line(state,solar_now) + outage_schedule.context(state, candidate_since, False, getattr(config, "dtek_dacha_group", "")), "grid_lost", candidate_since)
        LOGGER.warning("External grid lost after debounce")
    return True


def observe_grid_hold(config: Config, client: HomeAssistantClient,
                      state: dict[str, Any], now: datetime,
                      debounce_seconds: int = 10) -> bool:
    """Notify once for confirmed reserve Grid Hold and Solar-return transitions."""
    mode = str(entity_value(client, config.operating_mode_entity) or "").lower()
    voltage = numeric_entity(client, config.grid_voltage_entity)
    grid_use.observe(state, client, now,
        fresh=entity_value(client, config.telemetry_freshness_entity) == 'fresh',
        grid_online=(voltage > 180 if voltage is not None and 0 <= voltage <= 300 else None),
        freshness_entity=config.telemetry_freshness_entity)
    if mode not in {"solar", "panic", "panic_grid_hold", "hybrid_charging",
                    "hybrid_grid_hold", "transitioning", "transition_failed"}:
        return False
    previous = state.get("operating_mode_observed")
    if mode == previous and mode in {'panic', 'hybrid_charging', 'panic_grid_hold', 'hybrid_grid_hold'}:
        grid_use.begin(state, client, now)
    if previous is None:
        state["operating_mode_observed"] = mode
        state["operating_mode_candidate"] = None
        if mode in {'panic', 'hybrid_charging', 'panic_grid_hold', 'hybrid_grid_hold'}:
            grid_use.begin(state, client, now)
        if mode in {"panic_grid_hold", "hybrid_grid_hold"}:
            grid_use.begin(state, client, now)
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
        if mode in {'panic', 'hybrid_charging', 'panic_grid_hold', 'hybrid_grid_hold'}:
            state['operating_mode_candidate']['grid_use_baseline'] = dict(
                sampled_at=now.isoformat(), counters=grid_use.totals(client, now)
                if entity_value(client, config.telemetry_freshness_entity) == 'fresh'
                and (numeric_entity(client, config.grid_voltage_entity) or 0) > 180 else None)
        elif mode == 'solar' and isinstance(state.get('grid_use_episode'), dict):
            state['operating_mode_candidate']['grid_use_end'] = dict(state['grid_use_episode'])
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
    if mode in {'panic', 'hybrid_charging', 'panic_grid_hold', 'hybrid_grid_hold'}:
        voltage = numeric_entity(client, config.grid_voltage_entity)
        if voltage is not None and voltage > 180 and entity_value(client, config.telemetry_freshness_entity) == 'fresh':
            grid_use.begin(state, client, now, started_at=since,
                baseline=candidate.get('grid_use_baseline') or dict(sampled_at=since.isoformat(), counters=None))
            grid_use.observe(state, client, now, fresh=True, grid_online=True,
                             freshness_entity=config.telemetry_freshness_entity)
    preparation = (outage_schedule.active_preparation(client,now)
                   if getattr(config,'dtek_schedule_enabled',False) else None)
    if preparation and mode in {'panic','panic_grid_hold'}:
        state['grid_hold_context']=dict(mode=mode,reserve_soc=preparation['target_soc'],
                                       release_soc=None,outage_preparation=True)
        state['grid_hold_episode_active']=True
        state['grid_hold_episode_reserve_soc']=preparation['target_soc']
        return True
    if mode == "solar":
        grid_lines, grid_episode = grid_use.finish(state, since,
            snapshot=candidate.get('grid_use_end'))
        context = state.pop("grid_hold_context", None)
        state["grid_hold_episode_active"] = False
        state["grid_hold_episode_reserve_soc"] = None
        if not isinstance(context, dict):
            return True
        preparation_now=(client.state(outage_schedule.STATUS_ENTITY) or {}).get('attributes', {})
        try:
            preparation_age=(now-datetime.fromisoformat(preparation_now.get('checked_at',''))).total_seconds()
        except (ValueError, TypeError):
            preparation_age=None
        coverage_release=(preparation_now.get('coverage_release') is True
                          and preparation_now.get('coverage_sufficient') is True
                          and preparation_age is not None and 0 <= preparation_age <= 120)
        if context.get('outage_preparation') and preparation_now.get('outage_not_started') is True:
            return True  # One missed-outage notice owns this explanation.
        voltage = numeric_entity(client, config.grid_voltage_entity)
        if (voltage is None or voltage <= 180
                or entity_value(client, config.telemetry_freshness_entity) != "fresh"):
            return True
        soc = numeric_entity(client, config.battery_soc_entity)
        release = number(context.get("release_soc"))
        if (not coverage_release and not context.get('outage_preparation') and (release is None or soc is None or soc < release)) or soc is None:
            # Solar can also be selected manually or after a failed grid
            # transition; neither is evidence of a reserve-threshold release.
            return True
        if (state.get('grid_candidate') is not None or state.get('grid_online') is False
                or (not coverage_release and any(i.get('kind') in {'grid_lost','grid_recovered'} for i in state.get('pending_notifications',[])))):
            return True
        restored=state.get('grid_restored_at')
        if not coverage_release and restored and abs((since-datetime.fromisoformat(restored)).total_seconds())<=120:
            return True
        lines = ["🏠 <b>Будинок працює без допомоги ДТЕК</b>"]
        lines.append(f"🔋 Поточний заряд: <b>{compact_number(soc)}%</b>.")
        if coverage_release:
            reserve=numeric_entity(client,config.ahm_minimum_soc_entity)
            requirement=number(preparation_now.get('coverage_required_soc'))
            if reserve is not None and requirement is not None and soc >= requirement:
                lines=["☀️ <b>Будинок працює без допомоги ДТЕК</b>",
                       f"🔋 {compact_number(soc)}% — вистачає до кінця планового відключення.",
                       f"Резерв батареї: <b>{compact_number(reserve)}%</b>."]
        queue_notification(state, "\n".join(lines), "grid_hold_released", since)
        state["pending_notifications"][-1].update({
            "soc": soc,
            "release_soc": release,
            "grid_use_episode": grid_episode,
        })
        return True
    if mode == "panic":
        voltage = numeric_entity(client, config.grid_voltage_entity)
        soc = numeric_entity(client, config.battery_soc_entity)
        reserve = numeric_entity(client, config.ahm_minimum_soc_entity)
        if (voltage is not None and voltage > 180
                and entity_value(client, config.telemetry_freshness_entity) == "fresh"
                and soc is not None and reserve is not None and soc < reserve):
            if (state.get('grid_hold_episode_active') is True
                    and number(state.get('grid_hold_episode_reserve_soc'))==reserve):
                LOGGER.info('Suppressed reserve top-up notice within existing grid episode')
                return True
            state['grid_hold_episode_active']=True
            state['grid_hold_episode_reserve_soc']=reserve
            state['grid_hold_context']=dict(mode=mode,reserve_soc=reserve,
                release_soc=min(100,reserve+10) if reserve<95 else None)
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
                "soc": soc,
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
    lines = ["🔌 <b>Будинок підключено до ДТЕК</b>"]
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
        "soc": soc,
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
    issues = state.setdefault('protection_notice_issues', {})
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
        hp1_event = (event.get('key') == 'heat_pump_floor_1' or
                     any(item.get('key') == 'heat_pump_floor_1'
                         for item in (event.get('affected_loads') or []) if isinstance(item, dict)))
        if not (hp1_event and (event.get('reason') in {'battery', 'battery_load_unavailable'} or event.get('protection_source') == 'battery') or event_type == 'hp1_battery_warning'):
            continue
        if event_type == 'battery_reserve_warning' or (event.get('reason') in {'battery', 'battery_load_unavailable'} and not hp1_event and event_type != 'hp1_battery_warning'):
            continue
        key = f"{event.get('stream_id', '')}:{event_id}"
        stream = str(event.get("stream_id") or "")
        sequence = event.get("sequence")
        if not event_id or event_type not in {"shed_recommended", "restore_recommended", "no_candidates",
                "load_shed", "load_restored", "control_complete", "control_attention",
                "load_warning", "load_warning_cleared", "hp1_battery_warning"}:
            continue
        if key in seen or (not event.get("stream_id") and event_id == legacy_id):
            continue
        if stream and isinstance(sequence, int) and sequence <= cursors.get(stream, 0):
            continue
        if stream and isinstance(sequence, int):
            cursor = cursors.get(stream)
            if cursor is not None and sequence > cursor + 1:
                LOGGER.warning("First-floor HP event history gap: %s after %s", sequence, cursor)
            cursors[stream] = sequence
        # Each confirmed restoration already has one message; completion is
        # dashboard/journal bookkeeping, not a second restoration notification.
        if event_type == 'control_attention':
            affected = event.get('affected_loads') or [{'key': 'controller'}]
            new = []
            for item in affected:
                issue = str(item.get('key'))+':'+str(event.get('reason'))
                if issue not in issues:
                    issues[issue] = now.isoformat()
                    new.append(item)
            issues = dict(list(issues.items())[-256:])
            state['protection_notice_issues'] = issues
            if not new:
                seen.append(key)
                changed = True
                continue
            event = dict(event, affected_loads=new)
            cycle_key = str(event.get('cycle_id') or event.get('stream_id') or 'unknown')
            group = attention_pending.setdefault(cycle_key, {
                'first_at': now.isoformat(), 'reasons': [], 'affected_loads': [], 'producer': 'hp1_battery',
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
            if event_type in {'load_shed', 'load_restored'}:
                for item in event.get('affected_loads') or []:
                    for issue in list(issues):
                        if issue.startswith(str(item.get('key'))+':'):
                            issues.pop(issue, None)
            queue_notification(state, peak_load_guard_message(event),
                               f"peak_load_guard_{event_type}", now)
            state["pending_notifications"][-1]["producer"] = "hp1_battery"
        seen.append(key)
        state["peak_load_guard_last_event_id"] = event_id
        LOGGER.info("Observed first-floor HP event: %s cycle=%s", key, event.get("cycle_id"))
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
        state["pending_notifications"][-1]["producer"] = "hp1_battery"
        del attention_pending[cycle_key]
        changed = True
    return changed



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
            state['reserve_recovery_change'] = dict(old=old,new=new,at=now.isoformat())
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
            or weather_warning_quiet_hours(now, config)):
        return True
    pending = state.setdefault("pending_notifications", [])
    if any(x.get("kind") == "uhmc_weather_warning" and x.get("created_at") == now.isoformat() for x in pending):
        return True
    message = (f"🔋 Мін. заряд: <b>{selected:g}%</b>. Рекомендація: <b>{target:g}%</b>.\n"
               f"Причина: {reserve_reason(reserve)}. Рішення за родиною.")
    queue_notification(state, message, "battery_reserve_advice", now)
    state["pending_notifications"][-1]["recommended_soc"] = target
    return True


def weather_warning_quiet_hours(now: datetime, config=None) -> bool:
    return family_quiet_phase(now, config) is not None


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
        if weather_warning_quiet_hours(now, config):
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
        if weather_warning_quiet_hours(now, config):
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
    message = soc_anomaly_message(stored_event, ZoneInfo(config.timezone))
    evidence = state.get('bms_evidence_status') or {}
    if getattr(config, 'bms_entities', ()):
        if 'inverter:' + str(event.get('timestamp')) in evidence.get('event_ids', []):
            message += '\n📋 Дані BMS збережено; збір після події триває 15 хв.'
        else:
            message += '\n⚠️ Запис даних BMS для цієї події не підтверджено.'
    queue_notification(
        state,
        message,
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


def retired_protection_notice(item):
    """Compatibility filter for persisted notices from retired Python plug control."""
    kind = str(item.get('kind', ''))
    return (kind.startswith(('dashboard_control_overload', 'reserve_'))
            or kind == 'peak_load_guard_battery_reserve_warning'
            or (kind.startswith('peak_load_guard_') and
                (item.get('producer') != 'hp1_battery'
                 or 'Захист заряду батареї' in str(item.get('message', '')))))


def observe_reserve_warnings(config, client, state, now):
    """Once per app start; native HA rules own battery-load notifications."""
    queue = state.setdefault('pending_notifications', [])
    kept = [item for item in queue if not retired_protection_notice(item)]
    changed = len(kept) != len(queue)
    state['pending_notifications'] = kept
    for key in ('reserve_warning_offsets', 'reserve_warning_minimum_soc', 'battery_warning_announced'):
        if key in state:
            state.pop(key)
            changed = True
    groups = state.get('peak_load_attention_pending', {})
    for key, group in list(groups.items()):
        if not isinstance(group, dict):
            continue
        if group.get('producer') != 'hp1_battery':
            groups.pop(key)
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
    # Establish an upgrade baseline only when no restoration is waiting to send.
    # Future grid transitions have a new timestamp and require delivery evidence.
    if state.get('grid_notice_order_version') != 1:
        state['grid_notice_order_version'] = 1
        if state.get('grid_restored_at') and not any(x.get('kind') == 'grid_recovered' for x in queue):
            state['grid_recovery_delivered_at'] = state['grid_restored_at']
            changed = True
    index = 0
    while index < len(queue):
        item = queue[index]
        if retired_protection_notice(item):
            queue.pop(index)
            changed = True
            continue
        if item.get('kind') in {'dtek_reminder','dtek_restoration'}:
            from .schedule_context import delivery_gate
            gate=delivery_gate(state,now)
            if gate=='defer':
                index+=1; continue
            if gate=='drop':
                queue.pop(index); changed=True; continue
        if item.get('kind')=='technical_hp_eco_unconfirmed':
            failure=hp_eco.failure(client,now)
            if failure is None or failure['fingerprint']!=item.get('eco_failure'):
                queue.pop(index); changed=True; continue
        if item.get('kind')=='grid_lost' and getattr(config,'dtek_schedule_enabled',False):
            from .schedule_context import loss_context
            try:
                at=datetime.fromisoformat(item['created_at'])
            except (KeyError,TypeError,ValueError):
                at=now
            header='\n'.join(line for line in item['message'].splitlines() if line.startswith(('⚡','🔋','☀️')))
            item['message']=header+loss_context(state,now,config.dtek_dacha_group,'дача',at)
        if (item.get('kind')=='apartment_grid' and item.get('apartment_online') is False
                and getattr(config,'dtek_schedule_enabled',False)):
            from .schedule_context import loss_context
            try:
                at=datetime.fromisoformat(item['created_at'])
            except (KeyError,TypeError,ValueError):
                at=now
            header='\n'.join(item['message'].splitlines()[:2])
            item['message']=header+loss_context(state,now,config.dtek_apartment_group,'квартира',at)+'\nℹ️ За доступністю Xiaomi Hub.'
        from . import restoration_messages
        if client is not None and item.get('kind') in restoration_messages.MODE_EVENTS:
            action = restoration_messages.mode_action(item, config, client, state, now)
            if action == 'drop':
                queue.pop(index); changed=True; continue
            if action == 'defer':
                index += 1; continue
        if client is not None and item.get('kind') == 'grid_recovered':
            try:
                settling = (now-datetime.fromisoformat(item['created_at'])).total_seconds() < 120
            except (KeyError, TypeError, ValueError):
                settling = False
            if state.get('operating_mode_candidate') is not None and settling:
                index += 1; continue
            item['message'] = restoration_messages.house_text(config, client, state, now, item)
        if item.get('kind') == 'dtek_outage_not_started' and client is not None:
            preparation=(client.state(outage_schedule.STATUS_ENTITY) or {}).get('attributes', {})
            if (preparation.get('start') != item.get('start') or preparation.get('outage_not_started') is not True
                    or entity_value(client, config.telemetry_freshness_entity) != 'fresh'
                    or entity_value(client, 'binary_sensor.energyhub_grid_confirmed') != 'on'):
                queue.pop(index); changed=True; continue
        if item.get('kind') == 'hp_eco_change' and client is not None:
            message = hp_eco.refresh(item, client, now)
            if message is None:
                queue.pop(index)
                changed = True
                continue
            item['message'] = message
        if item.get('kind') in {'dtek_schedule','dtek_suspension'}:
            document=state.get('dtek_snapshot') or {}
            lines=outage_schedule.morning_lines(config,state,now,client) if client else []
            if (not lines or document.get('source_status') not in {'fresh','suspended'}
                    or item.get('signature')!=state.get('dtek_signature')
                    or family_quiet_phase(now,config)=='overnight'):
                # The next morning uses the current validated schedule once.
                queue.pop(index)
                changed=True
                continue
            item['message']=(outage_schedule.message(document,[(config.dtek_dacha_group,'дача'),(config.dtek_apartment_group,'квартира')],now,selected_day=now.date().isoformat(),remaining=True)
                             if item.get('kind')=='dtek_schedule' else lines[0])
            if item.get('kind')=='dtek_schedule' and state.get('dtek_schedule_revised'):
                item['message']='📅 <b>Графік відключень оновлено.</b>\n'+item['message']
            if item.get('kind')=='dtek_schedule':
                from .source_policy import status_lines
                status='\n'.join(status_lines(state,now))
                if status:
                    if item['message'].startswith('📅'):
                        first,rest=item['message'].split('\n',1)
                        item['message']=first+'\n'+status+'\n'+rest
                    else:
                        item['message']=status+'\n'+item['message']
        if item.get('kind')=='dtek_restoration':
            text=outage_schedule.restoration_text(config,client,state,now,item) if client else ''
            if not text or family_quiet_phase(now,config)=='overnight':
                queue.pop(index)
                changed=True
                continue
            item['message']=text
        if item.get('kind')=='dtek_reminder':
            text=outage_schedule.reminder_text(config,client,state,now,item) if client else ''
            if not text or family_quiet_phase(now,config)=='overnight':
                queue.pop(index)
                changed=True
                continue
            item['message']=text
        if item.get('kind') in {'dtek_precharge_complete','dtek_solar_bridge'}:
            data=(client.state(outage_schedule.STATUS_ENTITY) or {}).get('attributes',{}) if client else {}
            valid=False
            try:
                valid=(data.get('start')==item.get('start') and now<datetime.fromisoformat(data['start'])
                       and 0 <= (now-datetime.fromisoformat(data['checked_at'])).total_seconds()<=120)
                valid=valid and (data.get('solar_bridge_safe') is True if item['kind']=='dtek_solar_bridge'
                                 else data.get('phase')=='holding' and data.get('acknowledged') is True)
                if item['kind'] == 'dtek_precharge_complete':
                    from .grid_evidence import qualified
                    valid = valid and qualified(config, client, now) is True
            except (ValueError,KeyError,TypeError):
                pass
            if not valid:
                queue.pop(index); changed=True; continue
        if item.get('kind') == 'dtek_preparation':
            from .grid_evidence import qualified
            if client is None or qualified(config, client, now) is not True:
                index += 1
                continue
            restored_at = state.get('grid_restored_at')
            if (any(other.get('kind') == 'grid_recovered' for other in queue)
                    or (restored_at and state.get('grid_recovery_delivered_at') != restored_at)):
                index += 1
                continue
            line=outage_schedule.preparation_for_state(config,client,state,now) if client else ''
            current_start=((client.state(outage_schedule.STATUS_ENTITY) or {}).get('attributes',{}).get('start')
                           if client else None)
            if current_start!=item.get('start') or (client.state(outage_schedule.STATUS_ENTITY) or {}).get('state') not in {'charging', 'holding'}:
                line=''
            if ((client.state(outage_schedule.STATUS_ENTITY) or {}).get('state') == 'holding'
                    and ((client.state(outage_schedule.STATUS_ENTITY) or {}).get('attributes') or {}).get('window_active') is not True):
                line=''
            if not line or family_quiet_phase(now,config)=='overnight':
                queue.pop(index)
                changed=True
                continue
            item['message']=line.strip()
        if item.get('kind') == 'night_charge_decision':
            from .night_charge import snapshot as night_snapshot, decision as night_decision
            data = night_snapshot(client, now) if client else {}
            text = night_decision(config, client, now, data) if client else ''
            if not text or item.get('day') != data.get('day'):
                queue.pop(index); changed=True; continue
            item['message'] = text
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
            item['message'] = restart_message(client, now, current_boot, config=config, state=state)
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
            if (not reserve_recommendation_ready(reserve) or weather_warning_quiet_hours(now, config)
                    or target != item.get('recommended_soc')
                    or target == number(reserve.get('applied_minimum_soc'))):
                queue.pop(index)
                changed = True
                continue
            from .events import reserve_reason
            selected = number(reserve.get('applied_minimum_soc'))
            item['message'] = (f"🔋 Мін. заряд: <b>{selected:g}%</b>. Рекомендація: <b>{target:g}%</b>.\n"
                               f"Причина: {reserve_reason(reserve)}. Рішення за родиною.")
        if item.get('kind') in {'dtek_tomorrow','dtek_tomorrow_missing'}:
            if item.get('kind') == 'dtek_tomorrow_missing':
                queue.pop(index); changed=True; continue
            text=outage_schedule.evening_text(config,client,state,now,item)
            if not text or family_quiet_phase(now,config)=='overnight':
                queue.pop(index); changed=True; continue
            item['message']=text
        policy_events={'battery_reserve_applied','battery_reserve_manual_change','grid_confidence','grid_confidence_change','grid_hold','grid_hold_started','grid_hold_released','battery_reserve_charging'}
        if client is not None and item.get('kind') in policy_events:
            if item.get('kind') in {'grid_hold', 'grid_hold_started', 'battery_reserve_charging'}:
                from .grid_evidence import qualified
                if qualified(config, client, now) is not True:
                    queue.pop(index); changed=True; continue
                night = (client.state('sensor.energyhub_night_charge') or {}).get('attributes') or {}
                if night.get('selected_owner') is True and night.get('acknowledged') is True:
                    try:
                        night_current = 0 <= (now-datetime.fromisoformat(night['checked_at'])).total_seconds() <= 120
                    except (KeyError, TypeError, ValueError):
                        night_current = False
                    if night_current:
                        queue.pop(index); changed=True; continue
            preparation_line = outage_schedule.preparation_for_state(config,client,state,now)
            if (item.get('kind')=='battery_reserve_charging' and preparation_line
                    and (client.state(outage_schedule.STATUS_ENTITY) or {}).get('state')=='charging'):
                # ScheduleMonitor owns the richer per-window start notice.
                queue.pop(index); changed=True; continue
            if (item.get('kind')=='grid_hold_started' and preparation_line
                    and (state.get('precharge_soc_session') or {}).get('key') ==
                        ((client.state(outage_schedule.STATUS_ENTITY) or {}).get('attributes') or {}).get('start')):
                # The confirmed completion notice already explains this hold.
                queue.pop(index); changed=True; continue
            from .reserve_policy_text import context as policy_context
            from .reserve_policy_text import lines as current_policy_lines
            scheduled = any('за графіком' in line for line in current_policy_lines(config,client,state,now))
            if scheduled and item.get('kind') in {'grid_confidence','grid_confidence_change','battery_reserve_applied'}:
                queue.pop(index)
                changed = True
                continue
            header=str(item['message']).split('\n',1)[0]
            if item.get('kind')=='battery_reserve_applied':
                header='🔋 Параметри керування батареєю оновлено.'
            elif item.get('kind')=='battery_reserve_charging':
                header='⚡ ДТЕК підключено для заряджання батареї.'
            if item.get('kind')=='battery_reserve_charging':
                from .reserve_policy_text import reserve_recovery_message
                item['message']=reserve_recovery_message(config,client,state,now)
            elif item.get('kind')=='grid_hold_released':
                base=item.setdefault('policy_base_message',item['message'])
                item['message']=outage_schedule.coverage_release_text(config,client,state,now) or '\n'.join(base.splitlines()[:2])
            else:
                item['message']=header+policy_context(config,client,state,now)
        chat_id = notification_chat(config, str(item.get("kind", "")))
        if item.get('kind')=='pro_notice':
            notice=state.get('pro_notice') or {}
            if (item.get('policy_schema') != 2 or item.get('notice_signature') != notice.get('signature')
                    or item.get('schedule_signature') != notice.get('schedule_signature')):
                queue.pop(index); changed=True; continue
            from .source_policy import notification_text
            item['message']=notification_text(config,state,now)
        quiet_phase = family_quiet_phase(now, config)
        if chat_id == config.destination_chat_id and quiet_phase == "overnight":
            archive_overnight_family_event(state, item)
            if item.get("kind") == "grid_recovered":
                state["grid_recovery_delivered_at"] = state.get("grid_restored_at")
            if client is not None:
                hp_eco.acknowledge_grid(state, item, client, now)
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
        if item.get("kind") == "grid_recovered":
            state["grid_recovery_delivered_at"] = state.get("grid_restored_at")
        if item.get('kind')=='technical_apartment_cloud':
            from .apartment_grid import acknowledge_read_health
            acknowledge_read_health(state,item)
        if client is not None:
            hp_eco.acknowledge_grid(state, item, client, now)
        LOGGER.info("Delivered queued %s notification", item.get("kind", "event"))
        queue.pop(index)
        changed = True
    return changed


def refresh_queued_reserve_warning(config, client, kind):
    """Drop persisted pre-migration warnings, including during an in-flight send."""
    return 'drop', None


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


def fetch_co2_morning_lines(config, client, now=None):
    targets = getattr(config, 'co2_sensors', ())
    if not targets:
        return []
    try:
        entities = {row['entity_id']: row for row in client.states() if row.get('entity_id')}
    except HomeAssistantError as exc:
        LOGGER.warning('Morning CO2 snapshot unavailable: %s', exc)
        entities = {}
    captured_at = now or datetime.now(ZoneInfo(config.timezone))
    maxima = {}
    history = getattr(client, 'import_history', None)
    if callable(history):
        try:
            maxima = co2_monitor.history_maxima(targets,
                history(captured_at-timedelta(hours=24), captured_at,
                        [target.entity for target in targets]), captured_at)
        except (HomeAssistantError, OSError):
            LOGGER.warning('Morning CO2 history unavailable; maximum remains unknown')
    return co2_monitor.morning_lines(targets, entities, captured_at, maxima)


def fetch_solar_heating_morning_lines(client, solar_state, now):
    try:
        policy = entity_value(client, 'input_select.energyhub_climate_policy')
        operation = entity_value(client, 'input_select.energyhub_climate_operation')
        if policy != 'Solar-only' or operation != 'Continuous':
            return []
        family_mode = entity_value(client, 'input_select.energyhub_hp1_family_mode')
        limits = solar_settings.thresholds({key: client.state(key) for key in (solar_settings.START, solar_settings.PAUSE)})
        return solar_heating_morning.morning_lines(policy, operation, family_mode, solar_state, now, limits)
    except HomeAssistantError as exc:
        LOGGER.warning('Morning solar heating status unavailable: %s', exc)
        return []


def create_reports(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> tuple[str | None, list[str]]:
    from . import morning_digest
    now = now.astimezone(ZoneInfo(config.timezone))
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
    energy_outlook = []
    from . import hp_daily_energy
    try:
        energy_outlook.extend(hp_daily_energy.lines(config, client, now.astimezone(timezone), compact=True))
        energy_outlook.extend(hp_daily_energy.hot_water_lines(config, client, now.astimezone(timezone)))
    except HomeAssistantError:
        LOGGER.info('Yesterday HP energy unavailable; omitted')
    from .service_incidents import warning_active
    if warning_active(state):
        energy_outlook.append('ℹ️ Solcast тимчасово не оновлюється; використовуємо останній збережений прогноз із позначеним часом оновлення.')
    from .forecast_quality import collect as collect_forecast_quality
    forecast_accuracy = collect_forecast_quality(client,now)
    from .forecast_quality import weekly as forecast_weekly
    forecast_weekly_lines = forecast_weekly(state, now, forecast_accuracy)
    device_health_lines = data_incidents.morning_lines(state, now) + environment_report_lines(state, now)
    if getattr(config, 'house_monitor_enabled', False):
        device_health_lines = house_monitor.morning_lines(state, now) + device_health_lines
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
        smart_plug_lines = ([] if getattr(config, 'house_monitor_enabled', False)
                            else smart_plug_report_lines(config, client))
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
    current_strategy = ['ℹ️ Живлення будинку ще не підтверджено.']
    current_mode = ""
    try:
        current_mode = str(entity_value(client, config.operating_mode_entity) or "")
        from .reserve_policy_text import supply_line
        supply=supply_line(config,client,now)
        if supply:
            # Grid availability is already in the snapshot. Keep a separate
            # line only when it explains an evidenced charging/preparation action.
            current_strategy=[] if supply.startswith('🏠') else [supply]
        current_strategy = [f'🏠 <b>Стан на {now:%H:%M}</b>', *current_strategy]
    except HomeAssistantError as exc:
        LOGGER.warning("Current strategy description unavailable: %s", exc)
    anomaly_lines = soc_anomaly_report_lines(
        state.get("soc_anomaly_report_events", []),
        timezone,
        history_days=state.get('battery_jump_days', {}),
    )
    from . import co_morning
    from . import solar_outlook
    hp_lines=hp_summary.lines(state,client,now.astimezone(timezone))
    from .night_charge import morning as night_charge_morning
    from .morning_energy import lines as morning_energy_lines_short
    night_summary = night_charge_morning(client, now)
    energy_section = morning_energy_lines_short(consumption=consumption,
        average=consumption_average, sample_count=consumption_sample_count,
        hp_lines=energy_outlook)
    family_report = build_report(
        compact=True,
        solar_outlook_lines=solar_outlook.lines(config,client,now.astimezone(timezone), today=solar_forecast, average=consumption_average),
        solar_forecast_label=solar_outlook.today_label(config,client,now,solar_forecast),
        solar_heating_lines=morning_digest.schedule(config,state,now),
        co2_lines=fetch_co2_morning_lines(config, client)+co_morning.lines(config,client,now,state,compact=True),
        current_strategy_lines=None,
        overnight_event_lines=None,
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
        consumption=None,
        snapshot={},
        night_import=None,
        tariff_import=tariff_import,
        report_date=now.date(),
        current_soc=current_soc,
        solar_average_w=numeric_entity(client, "sensor.energyhub_solar_power_15m_average"),
        energy_section_lines=energy_section,
        energy_outlook_lines=forecast_weekly_lines,
        forecast_accuracy=None,
        ahm_minimum_soc=selected_reserve,
        weather_buffer=weather_buffer,
        control_status_line=None,
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
    if getattr(config, 'bms_entities', ()):
        from . import battery_weekly
        weekly_lines = battery_weekly.lines(state, now.astimezone(timezone))
        if weekly_lines:
            family_report += '\n\n'+'\n'.join(weekly_lines)
    technical_report = technical_summary.build(state, now)
    try:
        technical_summary.archive(config.state_file, core_log, state, now)
    except OSError:
        LOGGER.warning('Private technical archive could not be written')
    fresh = entity_value(client, config.telemetry_freshness_entity) == 'fresh'
    night_report = morning_digest.overnight(config, state, now,
        current_strategy=(current_strategy[1:] if current_strategy[0].startswith('🏠 <b>Стан на') else current_strategy)+hp_lines[:1],
        soc=current_soc, solar_w=numeric_entity(client, 'sensor.energyhub_solar_power_15m_average'),
        grid_voltage=numeric_entity(client, config.grid_voltage_entity),
        telemetry_fresh=fresh, inverter_mode=current_mode, night_summary=night_summary)
    return technical_report, [night_report, family_report]


def create_report(config: Config, client: HomeAssistantClient, state: dict[str, Any], now: datetime) -> str:
    """Compatibility helper returning the family-facing morning report."""
    return '\n\n'.join(create_reports(config, client, state, now)[1])


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
    # Accept the former single-message shape from integrations and persisted
    # outboxes; never regenerate an in-flight report during an upgrade.
    family_messages = [family] if isinstance(family, str) else family
    messages = [*([technical] if technical else []), *family_messages]
    state["morning_report_outbox"] = {
        "date": report_date,
        "message": '\n\n'.join(family_messages),
        "messages": messages,
        "destinations": ([getattr(config, "technical_chat_id", "") or config.destination_chat_id]
                         if technical else []) + [config.destination_chat_id] * len(family_messages),
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
    retire_zigbee_diagnostics(state)
    for name in (
        "soc_snapshots",
        "night_baselines",
        "night_imports",
        "night_observed_modes",
    ):
        state.pop(name, None)


def retire_zigbee_diagnostics(state, config=None):
    """Discard retired diagnostics without fabricating recovery events."""
    for key in ('plug_power_monitor', 'plug_discovered', 'registry_status',
                'registry_check_due', 'data_zigbee_seen'):
        state.pop(key, None)
    retired_entities = {t.entity for t in getattr(config, 'monitored_devices', ())
                        if t.entity.startswith('switch.') or t.parent.endswith('zigbee2mqtt_bridge_connection_state')}
    retired_entities.update(t.entity for t in getattr(config, 'co_alarms', ()))
    def retired(key):
        return (key == 'zigbee' or key.startswith('device:switch.')
                or key.startswith('load_') or 'co_carbon_monoxide' in key
                or key.removeprefix('device:') in retired_entities)
    for name in ('data_incidents', 'current_health', 'data_source_labels'):
        rows=state.get(name)
        if isinstance(rows,dict):
            for key in list(rows):
                if retired(key): rows.pop(key)
    state['data_incident_history']=[r for r in state.get('data_incident_history',[]) if not retired(str(r.get('key','')))]


def observe_safely(observer, *args, **kwargs) -> bool:
    """Keep one malformed entity or observer from blocking report delivery."""
    try:
        return bool(observer(*args, **kwargs))
    except Exception:
        LOGGER.exception("Observation failed: %s", observer.__name__)
        return False


def observe_monitoring(config, client, state, now, bms_evidence=None):
    """One state snapshot, plus bounded registry checks and Beacon recovery."""
    if (config.house_monitor_enabled or bms_evidence is not None or getattr(config, 'co2_sensors', ())
            or getattr(config, 'beacon_recovery_enabled', False)
            or getattr(config, 'log_monitor_enabled', False) or getattr(config, 'co_alarms', ())):
        from types import SimpleNamespace
        snapshot = {row['entity_id']: row for row in client.states()}
        from . import service_incidents
        service_incidents.observe(state, [], now,
            successful_refresh=service_incidents.source_refresh(snapshot, config, now))
        if (getattr(config, 'beacon_recovery_enabled', False)
                and now.timestamp() >= state.get('beacon_check_due', 0)):
            state['beacon_check_due'] = now.timestamp()+60
            try:
                registry, entries = client.registry(), client.config_entries()
                entry = beacon_recovery.isolated_entry(registry, entries)
                transport_error = False
                if entry and entry.get('state') in {'loaded', 'setup_error'}:
                    errors=client.system_log_entries()
                    fault_at=beacon_recovery.recent_control_error(errors, now)
                    if fault_at is not None:
                        state['beacon_control_fault_at']=fault_at
                    transport_error = beacon_recovery.recent_transport_error(errors, now, entry.get('title'))
                beacon_recovery.observe(state, now, registry, entries,
                    snapshot.get(beacon_recovery.LAMP, {}),
                    persist=StateStore(config.state_file).save, reload=client.reload_beacon_entry,
                    control_error=0 <= now.timestamp()-state.get('beacon_control_fault_at', 0) <= 120,
                    transport_error=transport_error)
            except (HomeAssistantError, AttributeError):
                state.setdefault('beacon_recovery', {})['status'] = 'health_unavailable'
        from . import co_cache
        co_cache.observe(state, getattr(config, 'co_alarms', ()), snapshot, now)
        co2_monitor.observe(state, getattr(config, 'co2_sensors', ()), snapshot, now)
        hp_summary.observe(state, snapshot, now)
        from . import battery_weekly
        battery_weekly.observe(state, config, snapshot, now)
        household_events.observe(state, getattr(config, 'co_alarms', ()), snapshot, now, client,
                                 quiet=family_quiet_phase(now, config) is not None)
        if config.house_monitor_enabled:
            recovery_advice.observe(state, snapshot, now)
            from . import hp_connection
            hp_connection.observe(state, snapshot, now)
        if getattr(config, 'log_monitor_enabled', False) and now.timestamp() >= state.get('next_log_check', 0):
            state['next_log_check'] = now.timestamp()+300
            try:
                entries = client.system_log_entries()
                service_incidents.observe(state, entries, now,
                    successful_refresh=service_incidents.source_refresh(snapshot, config, now))
                fault_at=beacon_recovery.recent_control_error(entries, now)
                if fault_at is not None:
                    state['beacon_control_fault_at']=fault_at
                session = (snapshot.get('input_text.energyhub_load_bridge_session') or {}).get('state')
                system_log_monitor.observe(state, entries, now, boot=session)
                if state.get('core_log_status', {}).get('available') is False:
                    LOGGER.info('Structured Core log reads recovered; this does not confirm integration recovery')
                state['core_log_status'] = dict(available=True, checked_at=now.isoformat())
            except HomeAssistantError:
                if state.get('core_log_status', {}).get('available') is not False:
                    LOGGER.warning('Structured Core log read unavailable; retry in five minutes')
                state['core_log_status'] = dict(available=False, checked_at=now.isoformat())
        health = data_incidents.collect(SimpleNamespace(state=snapshot.get), config, state, now)
        if config.house_monitor_enabled:
            health.update(house_monitor.observe_snapshot(config, state, snapshot, now))
        data_incidents.observe(state, health, now)
        state['current_health'], state['current_health_at'] = health, now.isoformat()
        if bms_evidence is not None:
            try:
                bms_evidence.observe(snapshot, {row.label: row.entity for row in config.bms_entities},
                                     config.soc_anomaly_latest_entity, now)
                state['bms_evidence_status'] = dict(saved_at=now.isoformat(),
                    event_ids=[event['id'] for event in bms_evidence.data['events']])
            except (OSError, ValueError, KeyError):
                state['bms_evidence_status'] = dict(error=True)
                LOGGER.exception('BMS evidence capture failed; monitoring continues')
    else:
        health=data_incidents.collect(client, config, state, now)
        data_incidents.observe(state, health, now)
        state['current_health'],state['current_health_at']=health,now.isoformat()


def run() -> None:
    config = load_config()
    if not config.bot_token:
        raise ValueError("bot_token is required")
    if not config.destination_chat_id:
        raise ValueError("destination_chat_id is required; use the family group ID")
    timezone = ZoneInfo(config.timezone)
    store = StateStore(config.state_file)
    state = store.load()
    retire_zigbee_diagnostics(state, config)
    from .schedule_sources import retire_official_state
    retire_official_state(state)
    client = HomeAssistantClient()
    uhmc_source = PublicTelegramSource(config.uhmc_weather_source)
    from . import dtek_emergency
    from . import apartment_grid
    apartment_cloud=apartment_grid.CloudMonitor()
    state['pro_policy_enabled']=True
    state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind') not in {'dtek_emergency','dtek_suspension','technical_facebook'}]
    dtek_monitor = outage_schedule.ScheduleMonitor()
    telegram = TelegramClient(config.bot_token)
    notification_queue = notification_bridge = None
    if config.automation_notifications_enabled:
        try:
            from .automation_notifications import NotificationQueue, MqttNotificationBridge, TelegramAdapter, NotificationDeliveryWorker
            notification_queue = NotificationQueue(config.state_file.with_name('automation-notifications.sqlite3'))
            notification_bridge = MqttNotificationBridge(config, notification_queue)
            notification_bridge.start()
            notification_worker = NotificationDeliveryWorker(notification_queue, notification_bridge,
                TelegramAdapter(TelegramClient(config.bot_token), config.destination_chat_id),
                quiet=lambda: family_quiet_phase(datetime.now(timezone), config) is not None,
                timezone_name=config.timezone)
            notification_worker.start()
            import atexit
            atexit.register(notification_bridge.stop)
            atexit.register(notification_worker.stop)
            LOGGER.info('Native HA notification interface started; Telegram family destination')
        except Exception:
            LOGGER.exception('Native HA notification interface unavailable; household monitoring continues')
    device_health = DeviceHealthMonitor(config)
    bms_evidence = None
    if config.bms_entities:
        try:
            bms_evidence = BmsEvidence(config.state_file.with_name('bms-evidence.json'))
        except (OSError, ValueError, KeyError):
            state['bms_evidence_status'] = dict(error=True)
            LOGGER.exception('BMS evidence unavailable; existing evidence file preserved')
    LOGGER.info("Morning report scheduled for %s; SOC and mode read live at delivery", config.send_time)
    LOGGER.info("Family Telegram quiet hours: %s–%s; independent of HP night window",
                  config.family_quiet_start, config.family_quiet_end)
    LOGGER.info("Pro Kyiv primary (Alerts.energy fallback) enabled=%s; house group=%s; apartment group=%s; source polling=:10/:40; tomorrow=20:00, retries=20:30/21:00 if unavailable; regional notices=Pro Kyiv; reminders checked each monitoring tick",
                config.dtek_schedule_enabled, config.dtek_dacha_group, config.dtek_apartment_group)

    started_at = datetime.now(timezone)
    if not state.get("initialized_at"):
        state["initialized_at"] = started_at.isoformat()
        if started_at.hour * 60 + started_at.minute >= time_minutes(config.send_time):
            state["last_report_date"] = started_at.date().isoformat()
            LOGGER.info("First start is after the morning deadline; the first scheduled report will be tomorrow")
        store.save(state)

    # Upgrade cleanup belongs to startup; delivery also rejects legacy notices.
    if observe_reserve_warnings(config, client, state, started_at):
        store.save(state)

    while True:
        now = datetime.now(timezone)
        changed = False
        try:
            observe_monitoring(config, client, state, now, bms_evidence)
            changed = True
        except (HomeAssistantError, OSError):
            data_incidents.observe(state, {'ha': False}, now)
            grid_use.pause(state)
            household_events.pause(state)
            state.get('host_recovery_advice', {}).update(bad_since=None, pending=None)
            if bms_evidence is not None:
                bms_evidence.pause()
            changed = True
        except Exception:
            LOGGER.exception('Data availability observation failed')
        try:
            changed |= observe_safely(observe_grid, config, client, state, now,
                                      solar_clock=lambda: datetime.now(timezone))
            changed |= observe_safely(apartment_cloud.poll, config, client, state, now)
            changed |= observe_safely(hp_eco.observe, state, client, now)
            changed |= observe_safely(observe_grid_hold, config, client, state, now)
            changed |= observe_safely(observe_grid_confidence, config, client, state, now)
            changed |= observe_safely(observe_restart, client, state, now)
            changed |= observe_safely(observe_controls, client, state, now)
            changed |= observe_safely(observe_soc_anomaly, config, client, state, now)
            changed |= observe_safely(observe_peak_load_guard, config, client, state, now)
            changed |= observe_safely(observe_inverter_strategy_fault,
                config, client, state, now
            )
            changed |= observe_safely(observe_weather_warnings, config, client, state, now)
            changed |= observe_safely(observe_battery_reserve, config, client, state, now)
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
                state['morning_delivered_date'] = now.date().isoformat()
                changed = True
            # Consume completed background reads and reconcile reminders first.
            # Website I/O stays in its worker; an observer failure cannot block
            # independent grid, SOC, CO or report delivery.
            changed |= observe_safely(dtek_monitor.poll,config,client,state,now)
            from .night_charge import observe as observe_night_charge
            changed |= observe_safely(observe_night_charge,config,client,state,now)
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
            # Regional notices were reconciled before dependent delivery.
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
        try:
            changed |= co2_monitor.deliver(state, telegram, config.destination_chat_id,
                datetime.now(timezone), quiet=family_quiet_phase(datetime.now(timezone), config) is not None)
        except (TelegramError, OSError):
            LOGGER.warning('CO2 notification delivery unavailable; will retry')
        try:
            changed |= household_events.deliver(state, telegram, config.destination_chat_id,
                datetime.now(timezone), quiet=family_quiet_phase(datetime.now(timezone), config) is not None,
                technical_chat=config.technical_chat_id)
        except (TelegramError, OSError):
            LOGGER.warning('Household notification delivery unavailable; will retry')
        try:
            technical_now = datetime.now(timezone)
            from . import hp_connection
            changed |= beacon_recovery.deliver(state, telegram, config.technical_chat_id)
            changed |= hp_connection.deliver(state, telegram, config, technical_now)
            from . import service_incidents
            changed |= service_incidents.deliver(state, telegram,
                config.destination_chat_id, technical_now, config)
            technical_destination = config.technical_chat_id or config.destination_chat_id
            if (technical_destination != config.destination_chat_id
                    or family_quiet_phase(technical_now, config) is None):
                changed |= system_log_monitor.deliver(state, telegram,
                    config.technical_chat_id, technical_now)
                changed |= recovery_advice.deliver(state, telegram,
                    technical_destination, technical_now)
        except (TelegramError, OSError, HomeAssistantError):
            # Persist a successfully delivered recovery notice even if HA's
            # acknowledgement failed, so app restart does not resend it.
            store.save(state)
            LOGGER.warning('Technical notification or recovery acknowledgement unavailable; will retry')
        if changed:
            store.save(state)
        time.sleep(30)


if __name__ == "__main__":
    run()
