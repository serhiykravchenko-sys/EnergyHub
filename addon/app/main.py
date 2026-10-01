import json
import queue
import subprocess
import threading
import time
import traceback
from datetime import date, datetime

from app.adapters.powmr import PowMrLocalAdapter
from app.config import (
    ENERGYHUB_AVAILABILITY_TOPIC,
    INVERTER_AVAILABILITY_TOPIC,
    load_options,
)
from app.mqtt.publisher import (
    make_client,
    publish_autopilot,
    publish_autopilot_discovery,
    publish_battery_health,
    publish_battery_health_discovery,
    publish_charger_source_priority,
    publish_daily_summary,
    publish_daily_summary_discovery,
    publish_discovery,
    publish_grid_discovery,
    publish_grid_history,
    publish_grid_import,
    publish_grid_import_discovery,
    publish_health,
    publish_health_discovery,
    publish_inverter_health,
    publish_inverter_health_discovery,
    publish_inverter_fault_journal,
    publish_inverter_fault_journal_discovery,
    publish_inverter_settings,
    publish_inverter_settings_discovery,
    publish_notification_event,
    publish_operating_mode,
    publish_operating_mode_discovery,
    publish_panic_decision,
    publish_panic_decision_discovery,
    publish_peak_load_guard,
    publish_peak_load_guard_discovery,
    publish_pv2_discovery,
    publish_pv2_telemetry,
    publish_retired_entity_cleanup,
    publish_soc_anomaly_journal,
    publish_soc_anomaly_journal_discovery,
    publish_system_health,
    publish_system_health_discovery,
    publish_telemetry_freshness,
    publish_telemetry_freshness_discovery,
    publish_weather_buffer,
    publish_weather_buffer_discovery,
)
from app.services.autopilot import AutopilotState
from app.services.battery_health import BatteryHealthMonitor
from app.services.daily_summary import DailySummaryService
from app.services.event_bus import EventBus
from app.services.grid_history import GridHistoryService
from app.services.grid_import import GridImportService
from app.services.grid_monitor import GridMonitor
from app.services.grid_stability import GridStabilityEngine
from app.services.health_monitor import HealthMonitor
from app.services.inverter_controller import InverterController
from app.services.inverter_health import InverterHealthMonitor
from app.services.inverter_fault_journal import InverterFaultJournal, valid_qpiws_response
from app.services.panic_decision import PanicDecisionEngine
from app.services.peak_load_control import PeakLoadGuardController, COMMAND_TOPIC
from app.services.pv2_telemetry import PV2TelemetryService
from app.services.soc_anomaly_journal import SocAnomalyJournal
from app.services.system_health import SystemHealthMonitor
from app.services.telemetry import TelemetryService
from app.services.telemetry_freshness import (
    TelemetryFreshnessMonitor,
)
from app.services.watchdog import CommunicationWatchdog
from app.services.weather_buffer import WeatherBufferDryRun
from app.utils.logger import log


INVERTER_WARNING_INTERVAL_SECONDS = 60
INVERTER_SETTINGS_INTERVAL_SECONDS = 60
PANIC_EVALUATION_INTERVAL_SECONDS = 5 * 60

PANIC_DEFAULT_TARGET_SOC = 95

MENU_01_QPIRI_MAP = {
    "Solar Battery Utility": "SBU",
    "Solar Utility Battery": "SUB",
}

AUTOPILOT_SAFE_RECOVERY_MODES = {
    "unknown",
    "inconsistent",
    "hybrid_charging",
    "hybrid_grid_hold",
    "panic",
    "panic_grid_hold",
    "transitioning",
    "transition_failed",
}


def main():
    options = load_options()

    if not options.get("powmr_enabled", True):
        log("PowMr module disabled. Sleeping forever.")

        while True:
            time.sleep(3600)

    log("Options loaded")
    log(
        f"MQTT: "
        f"{options['mqtt_host']}:"
        f"{options['mqtt_port']}"
    )
    log(f"Serial: {options['serial_port']}")
    log(f"Protocol: {options['protocol']}")
    log(
        f"Poll interval: "
        f"{options['poll_interval']} sec"
    )
    log(
        "PV2 Modbus telemetry: "
        f"{'enabled' if options.get('pv2_modbus_enabled', False) else 'disabled'}"
    )
    if options.get("pv2_modbus_enabled", False):
        log(
            "PV2 poll interval: "
            f"{options.get('pv2_poll_interval', 30)} sec"
        )

    inverter = PowMrLocalAdapter(options)
    inverter_controller = InverterController(inverter)

    client = make_client(options)

    telemetry = TelemetryService(client)
    pv2_telemetry = PV2TelemetryService(
        enabled=options.get("pv2_modbus_enabled", False),
        poll_interval=options.get("pv2_poll_interval", 30),
    )
    watchdog = CommunicationWatchdog()
    health = HealthMonitor()
    battery_health = BatteryHealthMonitor()
    telemetry_freshness = TelemetryFreshnessMonitor()
    inverter_health = InverterHealthMonitor()
    inverter_fault_journal = InverterFaultJournal()
    def publish_load_intent(command):
        # One non-retained QoS 0 intent: never replay a retained hardware command.
        result = client.publish(COMMAND_TOPIC, json.dumps(command), qos=0, retain=False)
        if result.rc != 0:
            raise RuntimeError('Load command delivery uncertain')

    # One dashboard switch selects automatic control vs warnings-only. The old
    # app flag is accepted for saved-options compatibility, not a second mode.
    peak_load_guard = PeakLoadGuardController(publish_load_intent)
    log('Overload protection: 85/75/50%; recovery 5 minutes, sequential restore at least 60 seconds; dashboard automatic/warnings-only')
    weather_buffer = WeatherBufferDryRun(
        timezone_name=options.get("timezone", "Europe/Kyiv")
    )
    system_health = SystemHealthMonitor()
    autopilot = AutopilotState()

    grid = GridMonitor()
    history = GridHistoryService()
    grid_import = GridImportService(
        timezone_name=options.get("timezone", "Europe/Kyiv")
    )
    stability = GridStabilityEngine(history)
    daily_summary = DailySummaryService(
        history,
        grid_import,
        timezone_name=options.get("timezone", "Europe/Kyiv"),
    )
    soc_anomaly_journal = SocAnomalyJournal()

    # Live decision inputs are kept separate from Daily Summary snapshot
    # inputs. Solcast updates these values throughout the day, while the
    # Daily Summary service should continue to receive only its scheduled
    # snapshot publications.
    decision_inputs = {}

    panic_decision = PanicDecisionEngine()

    mode_requests = queue.Queue(maxsize=1)
    mode_request_lock = threading.Lock()

    panic_target_soc = (
        inverter_controller.panic_target_soc
        or PANIC_DEFAULT_TARGET_SOC
    )

    last_warning_read = 0
    last_warning_success = None
    last_reserve_publish = 0
    last_settings_read = 0
    last_panic_evaluation = 0
    communication_interrupted = False

    panic_evaluation_requested = False

    startup_reconstruction_complete = False
    autopilot_state_received = False
    startup_recovery_decided = False

    bus = EventBus()
    bus.subscribe(grid.handle_inverter_state)

    def publish_all_health():
        system_health.update(
            health,
            battery_health,
            telemetry_freshness,
            inverter_health,
        )

        publish_system_health(
            client,
            system_health,
        )

    def publish_controller_state():
        publish_charger_source_priority(
            client,
            inverter_controller.known_charger_priority,
        )

        publish_operating_mode(
            client,
            inverter_controller,
        )

    def reconcile_grid_import_finalizations():
        daily_summary_changed = False

        for (
            completed_date,
            final_energy_kwh,
        ) in grid_import.get_pending_day_finalizations():
            result = daily_summary.finalize_grid_import(
                completed_date,
                final_energy_kwh,
            )

            if result == "invalid":
                log(
                    "Grid import finalization remains pending: "
                    f"{completed_date}"
                )
                continue

            if result == "updated":
                daily_summary_changed = True

            grid_import.mark_day_finalization_handled(
                completed_date
            )

        return daily_summary_changed

    def queue_mode_request(
        requested_mode,
        notification_event=None,
        target_soc=None,
    ):
        # MQTT callbacks run in the Paho network thread while requests are
        # consumed in the main loop. The lock makes the read/replace/write
        # operation atomic and prevents an ordinary request from replacing
        # a pending safe Solar recovery.
        request = {
            "mode": requested_mode,
            "notification_event": notification_event,
            "target_soc": target_soc,
        }

        with mode_request_lock:
            try:
                pending_request = mode_requests.get_nowait()
            except queue.Empty:
                pending_request = None

            pending_mode = (
                pending_request.get("mode")
                if isinstance(pending_request, dict)
                else pending_request
            )

            if (
                pending_mode == "safe_solar"
                and requested_mode != "safe_solar"
            ):
                mode_requests.put_nowait(pending_request)

                log(
                    "Preserved pending safe Solar recovery; "
                    "ignored inverter mode request: "
                    f"{requested_mode}"
                )
                return False

            mode_requests.put_nowait(request)

        if requested_mode == "safe_solar":
            log(
                "Safe Solar recovery queued with priority"
            )
        else:
            log(
                "Inverter mode request queued: "
                f"{requested_mode}"
            )

        return True

    def maybe_handle_startup_recovery():
        nonlocal startup_recovery_decided

        if startup_recovery_decided:
            return

        if not startup_reconstruction_complete:
            return

        if not autopilot_state_received:
            return

        if inverter_controller.mode not in {
            "unknown",
            "inconsistent",
        }:
            startup_recovery_decided = True

            log(
                "Startup reconstruction accepted without inverter writes: "
                f"mode={inverter_controller.mode}"
            )
            return

        if inverter_controller.transition_pending:
            startup_recovery_decided = True
            log(
                "Startup transition journal is uncertain. Automatic Solar "
                "recovery is suspended; attended inverter verification is required."
            )
            return

        if autopilot.is_enabled():
            startup_recovery_decided = True

            log(
                "Startup reconstruction is incomplete while Autopilot is "
                "enabled. Queueing one safe Solar recovery."
            )
            queue_mode_request("safe_solar")
            return

        startup_recovery_decided = True

        log(
            "Startup reconstruction is incomplete and Autopilot is "
            "disabled. Inverter settings will not be changed automatically."
        )

    def process_mode_request():
        nonlocal panic_target_soc
        nonlocal panic_evaluation_requested

        with mode_request_lock:
            try:
                request = mode_requests.get_nowait()
            except queue.Empty:
                return

        if isinstance(request, dict):
            requested_mode = request.get("mode")
            requested_target_soc = request.get("target_soc")
            notification_event = request.get(
                "notification_event"
            )
        else:
            # Backward-compatible handling for any request queued before
            # this process version became active.
            requested_mode = request
            requested_target_soc = None
            notification_event = None

        if requested_mode == "safe_solar":
            if inverter_controller.transition_pending:
                log(
                    "Autopilot safe Solar recovery blocked: inverter transition "
                    "journal is uncertain and requires attended verification"
                )
                publish_controller_state()
                return
            if (
                inverter_controller.mode
                not in AUTOPILOT_SAFE_RECOVERY_MODES
            ):
                log(
                    "Autopilot safe Solar recovery not required: "
                    f"current mode={inverter_controller.mode}"
                )
                return

            log(
                "Autopilot requires a confirmed strategy. "
                "Attempting one safe Solar recovery."
            )

            recovered = inverter_controller.restore_solar()
            if not recovered:
                log(
                    "ATTENTION: Safe Solar recovery failed; inverter strategy "
                    "is unconfirmed and automatic reserve control is suspended. "
                    "Attended verification is required."
                )
            publish_controller_state()
            return

        if requested_mode == "evaluate_hybrid":
            panic_evaluation_requested = True

            log(
                "Legacy Hybrid evaluation request redirected to the "
                "24/7 Battery Reserve controller"
            )
            return

        if requested_mode == "evaluate_panic":
            panic_evaluation_requested = True

            log("Panic evaluation requested")
            return

        if requested_mode in {"hybrid", "hybrid_grid_hold"}:
            panic_evaluation_requested = True
            log(
                f"Retired inverter request {requested_mode} ignored; "
                "the 24/7 Battery Reserve controller will reevaluate"
            )
            return

        if not autopilot.is_enabled():
            log(
                "Ignore inverter mode request "
                f"{requested_mode}: "
                "Autopilot disabled"
            )
            return

        log(
            "Processing inverter mode request: "
            f"{requested_mode}"
        )

        if requested_mode in {"panic_80", "panic_95"}:
            requested_target_soc = int(
                requested_mode.split("_")[1]
            )
            requested_mode = "panic"

            log(
                "Mapped legacy automatic Panic request to "
                f"target SOC={requested_target_soc}%"
            )

        transition_succeeded = False

        if requested_mode == "hybrid":
            transition_succeeded = (
                inverter_controller.enter_hybrid()
            )

        elif requested_mode == "hybrid_grid_hold":
            transition_succeeded = (
                inverter_controller.enter_hybrid_grid_hold()
            )

        elif requested_mode == "solar":
            transition_succeeded = (
                inverter_controller.restore_solar()
            )

        elif requested_mode == "panic":
            panic_target_soc = round(float(
                requested_target_soc
                or PANIC_DEFAULT_TARGET_SOC
            ), 2)
            inverter_controller.set_panic_target_soc(
                panic_target_soc
            )

            log(
                "Panic requested: "
                f"target SOC={panic_target_soc}%"
            )

            if inverter_controller.mode == "panic":
                transition_succeeded = True
            elif inverter_controller.mode == "hybrid_charging":
                transition_succeeded = (
                    inverter_controller.transfer_hybrid_charging_to_panic()
                )
            else:
                transition_succeeded = (
                    inverter_controller.enter_panic()
                )

        elif requested_mode == "panic_grid_hold":
            if requested_target_soc is not None:
                panic_target_soc = round(
                    float(requested_target_soc),
                    2,
                )
                inverter_controller.set_panic_target_soc(
                    panic_target_soc
                )

            if inverter_controller.mode == "hybrid_grid_hold":
                transition_succeeded = (
                    inverter_controller.transfer_hybrid_hold_to_panic()
                )
            else:
                transition_succeeded = (
                    inverter_controller.enter_panic_grid_hold()
                )

        else:
            log(
                "Ignore unsupported inverter mode request: "
                f"{requested_mode}"
            )
            return

        publish_controller_state()

        if notification_event is not None:
            event = dict(notification_event)

            if transition_succeeded:
                event["type"] = "automatic_mode_activation"

                publish_notification_event(
                    client,
                    event,
                )

            else:
                event["type"] = (
                    "automatic_mode_activation_failed"
                )
                event["error"] = (
                    inverter_controller.last_error
                    or (
                        "The requested inverter transition was not "
                        "confirmed"
                    )
                )
                event["current_mode"] = (
                    inverter_controller.mode
                )

                publish_notification_event(
                    client,
                    event,
                )

        if inverter_controller.mode == "solar":
            panic_evaluation_requested = True

            log(
                "Automatic Panic reevaluation requested "
                "after Solar confirmation"
            )

    def evaluate_panic(state):
        nonlocal panic_target_soc

        grid_confidence = stability.level()

        decision = panic_decision.evaluate(
            manual_reserve_soc=decision_inputs.get("ahm_minimum_soc"),
            autopilot_enabled=autopilot.is_enabled(),
            operating_mode=inverter_controller.mode,
            grid_confidence=grid_confidence,
            battery_soc=state.battery_soc,
            grid_available=grid.is_available,
        )

        if (
            decision.get("target_soc") is not None
            and inverter_controller.mode
            in {"panic", "panic_grid_hold"}
        ):
            panic_target_soc = round(
                float(decision["target_soc"]),
                2,
            )
            inverter_controller.set_panic_target_soc(
                panic_target_soc
            )

        publish_panic_decision(
            client,
            panic_decision,
        )

        log(
            "Automatic Panic evaluation: "
            f"status={decision['status']}, "
            f"reason={decision['reason']}"
        )

        requested_mode = decision.get("request")

        if requested_mode is None:
            return

        log(
            "Automatic Panic triggered: "
            f"request={requested_mode}, "
            f"target={decision['target_soc']}%"
        )

        queue_mode_request(
            requested_mode,
            target_soc=decision["target_soc"],
            notification_event={
                "mode": "panic",
                "soc": state.battery_soc,
                "grid_confidence": grid_confidence,
                "phase": decision["phase"],
                "requested_mode": requested_mode,
                "target_source": decision["target_source"],
                "target_soc": decision["target_soc"],
                "reason": decision["reason"],
            },
        )

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            log("MQTT connected")

            client.subscribe(
                "energyhub/input/ha/#"
            )

            client.subscribe(
                "energyhub/input/weather/uhmc"
            )

            log(
                "Subscribed to "
                "energyhub/input/ha/# and energyhub/input/weather/uhmc"
            )

            client.publish(
                ENERGYHUB_AVAILABILITY_TOPIC,
                "online",
                retain=True,
            )

            # A new or restored MQTT connection does not prove that the
            # inverter is readable. The next valid telemetry response
            # will publish inverter availability as online.
            client.publish(
                INVERTER_AVAILABILITY_TOPIC,
                "offline",
                retain=True,
            )

        else:
            log(
                "MQTT connection failed "
                f"with code {rc}"
            )

    def on_message(client, userdata, msg):
        nonlocal autopilot_state_received
        nonlocal panic_evaluation_requested

        topic = msg.topic
        payload = msg.payload.decode("utf-8")

        if topic == "energyhub/input/weather/uhmc":
            if weather_buffer.update_weather(payload):
                publish_weather_buffer(client, weather_buffer)
                log("Official UHMC weather-warning snapshot updated")
            else:
                log("Reserve Policy ignored an invalid UHMC snapshot")
            return

        prefix = "energyhub/input/ha/"
        if not topic.startswith(prefix):
            return

        key = topic.replace(prefix, "")

        if key == "autopilot":
            was_enabled = autopilot.is_enabled()

            if autopilot.update(payload):
                autopilot_state_received = True

                publish_autopilot(
                    client,
                    autopilot,
                )

                if (
                    was_enabled
                    and not autopilot.is_enabled()
                ):
                    queue_mode_request("safe_solar")

                elif (
                    not was_enabled
                    and autopilot.is_enabled()
                    and startup_reconstruction_complete
                    and startup_recovery_decided
                    and inverter_controller.mode
                    in {"unknown", "inconsistent"}
                ):
                    log(
                        "Autopilot enabled while inverter strategy is "
                        "unconfirmed. Queueing safe Solar recovery."
                    )
                    queue_mode_request("safe_solar")

                maybe_handle_startup_recovery()

            return

        if key == "inverter_mode":
            requested_mode = payload.strip().lower()
            queue_mode_request(requested_mode)
            return

        if key == "peak_load_control_plugs":
            if peak_load_guard.update_load_snapshot(payload):
                publish_peak_load_guard(client, peak_load_guard)
                log("Peak Load Guard participant snapshot updated")
            else:
                log("Peak Load Guard ignored an invalid participant snapshot")
            return

        if key == 'peak_load_guard_ack' and isinstance(peak_load_guard, PeakLoadGuardController):
            peak_load_guard.update_ack(payload)
            return
        if key == 'peak_load_guard_intent' and isinstance(peak_load_guard, PeakLoadGuardController):
            peak_load_guard.update_intent(payload)
            return

        if key == "weather_buffer_forecast":
            try:
                evaluation_date = date.fromisoformat(
                    str(json.loads(payload)["date"])
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                evaluation_date = None
            consumption_samples = (
                daily_summary.recent_consumption(evaluation_date, limit=3, require_final=True)
                if evaluation_date is not None
                else []
            )
            if weather_buffer.update(payload, consumption_samples):
                publish_weather_buffer(client, weather_buffer)
                attributes = weather_buffer.status_attributes()
                log(
                    "Battery Reserve evaluated: "
                    f"date={attributes.get('date')}, "
                    f"plan={attributes.get('forecast_plan_stage')}, "
                    f"transition={attributes.get('transition')}, "
                    f"baseline={attributes.get('baseline_soc')}%, "
                    f"consumption_average={attributes.get('consumption_average_kwh')} kWh, "
                    f"recommended={attributes.get('recommended_soc')}%"
                )
            else:
                log("Battery Reserve Policy ignored invalid daily inputs")
            return

        if key == "ahm_minimum_soc":
            try:
                value = round(float(payload), 1)
            except (TypeError, ValueError):
                log(
                    "Decision input ignored invalid AHM minimum SOC: "
                    f"{payload}"
                )
                return

            if (
                not 20 <= value <= 95
                or value % 5 != 0
            ):
                log(
                    "Decision input ignored out-of-range AHM "
                    f"minimum SOC: {value}"
                )
                return

            # Process the family setting on the next valid telemetry loop;
            # MQTT callbacks must never issue inverter commands directly.
            if decision_inputs.get("ahm_minimum_soc") != value:
                panic_evaluation_requested = True
            decision_inputs["ahm_minimum_soc"] = value

            log(f"AHM minimum SOC updated: {value}%")
            return

        live_forecast_keys = {
            "solar_forecast_today_live": (
                "solar_forecast_today"
            ),
            "solar_forecast_tomorrow_live": (
                "solar_forecast_tomorrow"
            ),
        }

        if key in live_forecast_keys:
            decision_key = live_forecast_keys[key]

            try:
                value = round(float(payload), 2)
            except (TypeError, ValueError):
                log(
                    "Decision input ignored invalid value "
                    f"{decision_key}: {payload}"
                )
                return

            decision_inputs[decision_key] = value

            log(
                "Decision input updated: "
                f"{decision_key}={value}"
            )
            return

        if key == "daily_summary_snapshot":
            if daily_summary.update_snapshot(payload):
                publish_daily_summary(
                    client,
                    daily_summary,
                )
            return

        daily_summary_keys = {
            "daily_house_consumption",
            "solar_forecast_today",
            "solar_forecast_tomorrow",
            "daily_solar_surplus_estimated",
        }

        if key not in daily_summary_keys:
            return

        if key in {"solar_forecast_today", "solar_forecast_tomorrow"}:
            try:
                decision_inputs[key] = round(
                    float(payload),
                    2,
                )
            except (TypeError, ValueError):
                pass

        daily_summary.update_input(
            key,
            payload,
        )

    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            log("Connecting to MQTT...")

            client.connect(
                options["mqtt_host"],
                int(options["mqtt_port"]),
                60,
            )

            break

        except Exception as e:
            log(
                "MQTT connection failed: "
                f"{e}"
            )

            time.sleep(10)

    client.loop_start()

    publish_discovery(
        client,
        options["device_name"],
    )
    publish_pv2_discovery(client, options["device_name"])
    publish_pv2_telemetry(client, pv2_telemetry)

    publish_grid_discovery(client)
    publish_grid_import_discovery(client)
    publish_health_discovery(client)
    publish_battery_health_discovery(client)
    publish_telemetry_freshness_discovery(client)
    publish_inverter_health_discovery(client)
    publish_inverter_fault_journal_discovery(client)
    publish_inverter_fault_journal(client, inverter_fault_journal)
    publish_peak_load_guard_discovery(client)
    publish_peak_load_guard(client, peak_load_guard)
    publish_weather_buffer_discovery(client)
    publish_weather_buffer(client, weather_buffer)
    publish_inverter_settings_discovery(client)
    publish_operating_mode_discovery(client)
    publish_retired_entity_cleanup(client)
    publish_soc_anomaly_journal_discovery(client)
    publish_soc_anomaly_journal(client, soc_anomaly_journal)
    publish_panic_decision_discovery(client)
    publish_autopilot_discovery(client)
    publish_system_health_discovery(client)
    publish_daily_summary_discovery(client)

    reconcile_grid_import_finalizations()

    publish_daily_summary(
        client,
        daily_summary,
    )

    publish_grid_import(
        client,
        grid_import,
    )

    publish_autopilot(
        client,
        autopilot,
    )

    publish_panic_decision(
        client,
        panic_decision,
    )

    publish_charger_source_priority(
        client,
        inverter_controller.known_charger_priority,
    )

    publish_operating_mode(
        client,
        inverter_controller,
    )

    client.publish(
        ENERGYHUB_AVAILABILITY_TOPIC,
        "online",
        retain=True,
    )

    # Raw inverter telemetry remains unavailable until the first valid
    # telemetry response confirms communication.
    client.publish(
        INVERTER_AVAILABILITY_TOPIC,
        "offline",
        retain=True,
    )

    while True:
        try:
            process_mode_request()

            data = inverter.read_telemetry()
            state = telemetry.process(data)
            pv1_sample_time = time.monotonic()

            if state.valid and pv2_telemetry.due(pv1_sample_time):
                pv2_succeeded = pv2_telemetry.poll(
                    inverter,
                    state.pv_power,
                    pv1_sample_time,
                )

                if pv2_succeeded:
                    log(
                        "PV2 OK | "
                        f"Voltage={pv2_telemetry.last_voltage}V | "
                        f"Power={pv2_telemetry.last_power}W | "
                        f"Total={pv2_telemetry.last_total_power}W"
                    )
                else:
                    log(
                        "PV2 telemetry unavailable: "
                        f"{pv2_telemetry.status}"
                    )

            pv2_telemetry.refresh()
            publish_pv2_telemetry(client, pv2_telemetry)

            telemetry_freshness.update(state)

            publish_telemetry_freshness(
                client,
                telemetry_freshness,
            )

            communication_recovered = (
                state.valid and communication_interrupted
            )
            anomaly_created = soc_anomaly_journal.observe(
                valid=state.valid,
                soc=state.battery_soc,
                battery_voltage=state.battery_voltage,
                charging_current=(state.raw or {}).get(
                    "battery_charging_current"
                ),
                discharging_current=(state.raw or {}).get(
                    "battery_discharge_current"
                ),
                pv1_power=state.pv_power,
                pv2_power=(
                    pv2_telemetry.last_power
                    if pv2_telemetry.pv2_is_fresh()
                    else None
                ),
                total_pv_power=(
                    pv2_telemetry.last_total_power
                    if pv2_telemetry.total_is_fresh()
                    else None
                ),
                house_load=state.load_power,
                grid_available=state.grid_available,
                grid_voltage=(state.raw or {}).get(
                    "ac_input_voltage"
                ),
                operating_mode=inverter_controller.mode,
                telemetry_freshness=telemetry_freshness.status,
                communication_recovered=communication_recovered,
            )
            communication_interrupted = not state.valid

            inverter_fault_journal.observe_telemetry(
                valid=state.valid,
                load_w=state.load_power,
                load_percent=(state.raw or {}).get("ac_output_load"),
                battery_soc=state.battery_soc,
                battery_voltage=state.battery_voltage,
                battery_charging_current=(state.raw or {}).get(
                    "battery_charging_current"
                ),
                battery_discharging_current=(state.raw or {}).get(
                    "battery_discharge_current"
                ),
                pv1_power=state.pv_power,
                pv2_power=(
                    pv2_telemetry.last_power
                    if pv2_telemetry.pv2_is_fresh()
                    else None
                ),
                total_pv_power=(
                    pv2_telemetry.last_total_power
                    if pv2_telemetry.total_is_fresh()
                    else None
                ),
                grid_available=state.grid_available,
                grid_voltage=(state.raw or {}).get("ac_input_voltage"),
                operating_mode=inverter_controller.mode,
                telemetry_freshness=telemetry_freshness.status,
            )

            if anomaly_created:
                publish_soc_anomaly_journal(
                    client,
                    soc_anomaly_journal,
                )

            now = time.monotonic()

            if (
                now - last_warning_read
                >= INVERTER_WARNING_INTERVAL_SECONDS
            ):
                fault_changed = False
                try:
                    warning_data = inverter.read_warnings()

                    inverter_health.update(
                        warning_data
                    )
                    if valid_qpiws_response(warning_data):
                        last_warning_success = time.monotonic()
                    else:
                        last_warning_success = None
                    fault_changed = inverter_fault_journal.observe_qpiws(
                        warning_data
                    )

                except Exception as e:
                    inverter_health.failure()
                    last_warning_success = None

                    log(
                        "ERROR: QPIWS warning "
                        f"read failed: {e}"
                    )

                publish_inverter_health(
                    client,
                    inverter_health,
                )
                if fault_changed:
                    publish_inverter_fault_journal(
                        client,
                        inverter_fault_journal,
                    )

                last_warning_read = now

            peak_load_guard.evaluate(
                telemetry_valid=state.valid,
                battery_soc=state.battery_soc,
                telemetry_freshness=telemetry_freshness.status,
                load_percent=(state.raw or {}).get("ac_output_load"),
                load_w=state.load_power,
                load_va=(state.raw or {}).get("ac_output_apparent_power"),
                grid_available=state.grid_available,
                operating_mode=inverter_controller.mode,
                overload_warning=(
                    last_warning_success is not None
                    and 0 <= time.monotonic() - last_warning_success <= 90
                    and (
                        "over_load" in inverter_fault_journal.active_messages
                        or "overload" in inverter_fault_journal.active_messages
                    )
                ),
            )
            publish_peak_load_guard(client, peak_load_guard)

            if (
                now - last_settings_read
                >= INVERTER_SETTINGS_INTERVAL_SECONDS
            ):
                try:
                    settings_data = inverter.read_settings()

                    publish_inverter_settings(
                        client,
                        settings_data,
                    )

                    raw_menu_01 = settings_data.get(
                        "output_source_priority"
                    )

                    menu_01 = MENU_01_QPIRI_MAP.get(
                        raw_menu_01,
                        "unknown",
                    )

                    menu_16 = (
                        inverter_controller
                        .known_charger_priority
                    )

                    log(
                        "Inverter settings updated: "
                        f"Menu 01={menu_01}, "
                        f"Menu 16={menu_16}"
                    )

                    if (
                        not startup_reconstruction_complete
                        and menu_01 != "unknown"
                    ):
                        inverter_controller.reconstruct_mode(
                            menu_01
                        )

                        startup_reconstruction_complete = True
                        panic_target_soc = (
                            inverter_controller.panic_target_soc
                            or PANIC_DEFAULT_TARGET_SOC
                        )

                        publish_controller_state()
                        maybe_handle_startup_recovery()

                except Exception as e:
                    log(
                        "ERROR: QPIRI settings "
                        f"read failed: {e}"
                    )

                last_settings_read = now

            if not state.valid:
                watchdog.failure()
                health.update(watchdog)

                publish_health(
                    client,
                    health,
                )

                publish_all_health()

                client.publish(
                    INVERTER_AVAILABILITY_TOPIC,
                    "offline",
                    retain=True,
                )

            else:
                watchdog.success()
                health.update(watchdog)

                publish_health(
                    client,
                    health,
                )

                battery_health.update(state)

                publish_battery_health(
                    client,
                    battery_health,
                )

                soc = state.battery_soc

                bus.publish(state)
                grid_state_changed = history.update(
                    grid.is_available
                )

                reserve_policy_changed = weather_buffer.update_grid_confidence(
                    stability.level(),
                    datetime.now().astimezone(),
                )
                reserve_policy_changed |= weather_buffer.refresh(
                    datetime.now().astimezone()
                )
                if reserve_policy_changed or now - last_reserve_publish >= 30:
                    publish_weather_buffer(client, weather_buffer)
                    last_reserve_publish = now
                if reserve_policy_changed:
                    attributes = weather_buffer.status_attributes()
                    log(
                        "Battery Reserve reevaluated: "
                        f"grid={attributes.get('grid_confidence')}, "
                        f"recommended={attributes.get('recommended_soc')}%"
                    )

                if grid_state_changed:
                    panic_evaluation_requested = True

                    log(
                        "Automatic Panic reevaluation requested "
                        "after grid state change"
                    )

                grid_import.update(
                    operating_mode=inverter_controller.mode,
                    output_power_w=state.load_power,
                    battery_soc=state.battery_soc,
                    grid_available=state.grid_available,
                )

                if reconcile_grid_import_finalizations():
                    publish_daily_summary(
                        client,
                        daily_summary,
                    )

                publish_grid_import(
                    client,
                    grid_import,
                )

                if panic_decision.requires_immediate_evaluation(
                    manual_reserve_soc=decision_inputs.get("ahm_minimum_soc"),
                    operating_mode=inverter_controller.mode,
                    grid_confidence=stability.level(),
                    battery_soc=soc,
                    grid_available=grid.is_available,
                ):
                    if not panic_evaluation_requested:
                        log(
                            "Immediate Normal-grid reserve evaluation "
                            "requested at the selected reserve boundary"
                        )
                    panic_evaluation_requested = True

                if (
                    autopilot.is_enabled()
                    and inverter_controller.mode == "panic"
                    and not panic_evaluation_requested
                    and soc is not None
                    and soc >= panic_target_soc
                ):
                    log(
                        "Panic target reached: "
                        f"SOC={soc}%, "
                        f"target={panic_target_soc}%. "
                        "Switching to Panic Grid Hold."
                    )

                    hold_entered = (
                        inverter_controller.enter_panic_grid_hold()
                    )

                    publish_controller_state()

                    if not hold_entered:
                        log(
                            "Panic Grid Hold transition failed"
                        )

                if (
                    autopilot.is_enabled()
                    and inverter_controller.mode == "panic_grid_hold"
                    and not panic_evaluation_requested
                    and soc is not None
                    and soc < panic_target_soc
                ):
                    log(
                        "Panic reserve fell below target: "
                        f"SOC={soc}%, target={panic_target_soc}%. "
                        "Returning to Panic Charging."
                    )

                    inverter_controller.enter_panic()
                    publish_controller_state()

                if (
                    panic_evaluation_requested
                    or (
                        now - last_panic_evaluation
                        >= PANIC_EVALUATION_INTERVAL_SECONDS
                    )
                ):
                    evaluate_panic(state)

                    last_panic_evaluation = now
                    panic_evaluation_requested = False

                publish_all_health()

                client.publish(
                    INVERTER_AVAILABILITY_TOPIC,
                    "online",
                    retain=True,
                )

                publish_grid_history(
                    client,
                    history,
                    stability,
                )

        except subprocess.TimeoutExpired:
            communication_interrupted = True
            client.publish(
                INVERTER_AVAILABILITY_TOPIC,
                "offline",
                retain=True,
            )
            peak_load_guard.evaluate(telemetry_valid=False, telemetry_freshness='stale',
                                     load_percent=None, load_w=None)
            publish_peak_load_guard(client, peak_load_guard)
            pv2_telemetry.refresh()
            publish_pv2_telemetry(client, pv2_telemetry)

            telemetry_freshness.update_status()

            publish_telemetry_freshness(
                client,
                telemetry_freshness,
            )

            watchdog.failure()
            health.update(watchdog)

            publish_health(
                client,
                health,
            )

            publish_all_health()

            log("ERROR: mpp-solar timeout")

        except Exception:
            communication_interrupted = True
            client.publish(
                INVERTER_AVAILABILITY_TOPIC,
                "offline",
                retain=True,
            )
            pv2_telemetry.refresh()
            peak_load_guard.evaluate(telemetry_valid=False, telemetry_freshness='stale',
                                     load_percent=None, load_w=None)
            publish_peak_load_guard(client, peak_load_guard)
            publish_pv2_telemetry(client, pv2_telemetry)

            telemetry_freshness.update_status()

            publish_telemetry_freshness(
                client,
                telemetry_freshness,
            )

            watchdog.failure()
            health.update(watchdog)

            publish_health(
                client,
                health,
            )

            publish_all_health()

            log("ERROR:")
            log(traceback.format_exc())

        time.sleep(
            int(options["poll_interval"])
        )


if __name__ == "__main__":
    main()
