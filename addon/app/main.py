import json
import queue
import subprocess
import threading
import time
import traceback
from datetime import datetime

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
    publish_hybrid_decision,
    publish_hybrid_decision_discovery,
    publish_inverter_health,
    publish_inverter_health_discovery,
    publish_inverter_settings,
    publish_inverter_settings_discovery,
    publish_notification_event,
    publish_operating_mode,
    publish_operating_mode_discovery,
    publish_panic_decision,
    publish_panic_decision_discovery,
    publish_system_health,
    publish_system_health_discovery,
    publish_telemetry_freshness,
    publish_telemetry_freshness_discovery,
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
from app.services.hybrid_decision import HybridDecisionEngine
from app.services.inverter_controller import InverterController
from app.services.inverter_health import InverterHealthMonitor
from app.services.panic_decision import PanicDecisionEngine
from app.services.system_health import SystemHealthMonitor
from app.services.telemetry import TelemetryService
from app.services.telemetry_freshness import (
    TelemetryFreshnessMonitor,
)
from app.services.watchdog import CommunicationWatchdog
from app.utils.logger import log


INVERTER_WARNING_INTERVAL_SECONDS = 60
INVERTER_SETTINGS_INTERVAL_SECONDS = 60
PANIC_EVALUATION_INTERVAL_SECONDS = 5 * 60

HYBRID_DEFAULT_TARGET_SOC = 80
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

    inverter = PowMrLocalAdapter(options)
    inverter_controller = InverterController(inverter)

    client = make_client(options)

    telemetry = TelemetryService(client)
    watchdog = CommunicationWatchdog()
    health = HealthMonitor()
    battery_health = BatteryHealthMonitor()
    telemetry_freshness = TelemetryFreshnessMonitor()
    inverter_health = InverterHealthMonitor()
    system_health = SystemHealthMonitor()
    autopilot = AutopilotState()

    grid = GridMonitor()
    history = GridHistoryService()
    grid_import = GridImportService()
    stability = GridStabilityEngine(history)
    daily_summary = DailySummaryService(
        history,
        grid_import,
    )

    # Live decision inputs are kept separate from Daily Summary snapshot
    # inputs. Solcast updates these values throughout the day, while the
    # Daily Summary service should continue to receive only its scheduled
    # snapshot publications.
    decision_inputs = {}

    hybrid_decision = HybridDecisionEngine()
    panic_decision = PanicDecisionEngine()

    hybrid_target_soc = inverter_controller.hybrid_target_soc

    mode_requests = queue.Queue(maxsize=1)
    mode_request_lock = threading.Lock()

    panic_target_soc = (
        inverter_controller.panic_target_soc
        or PANIC_DEFAULT_TARGET_SOC
    )

    last_warning_read = 0
    last_settings_read = 0
    last_panic_evaluation = 0

    hybrid_evaluation_requested = False
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
        nonlocal hybrid_evaluation_requested
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
                "Autopilot disabled during active or unknown "
                "strategy. Performing final safe Solar recovery."
            )

            inverter_controller.restore_solar()
            publish_controller_state()
            return

        if requested_mode == "evaluate_hybrid":
            hybrid_evaluation_requested = True

            log("Hybrid evaluation requested")
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

    def evaluate_hybrid(state):
        nonlocal hybrid_target_soc

        forecast_tomorrow = decision_inputs.get(
            "solar_forecast_tomorrow",
            daily_summary.inputs.get(
                "solar_forecast_tomorrow"
            ),
        )

        consumption_today = daily_summary.inputs.get(
            "daily_house_consumption"
        )

        decision = hybrid_decision.evaluate(
            autopilot_enabled=autopilot.is_enabled(),
            operating_mode=inverter_controller.mode,
            battery_soc=state.battery_soc,
            morning_hours=decision_inputs.get(
                "hybrid_morning_hours"
            ),
            useful_solar_start=decision_inputs.get(
                "hybrid_useful_solar_start"
            ),
            forecast_tomorrow=forecast_tomorrow,
            consumption_today=consumption_today,
            solar_forecast_after_07=decision_inputs.get(
                "hybrid_solar_after_07"
            ),
        )

        if decision.get("target_soc") is not None:
            hybrid_target_soc = decision["target_soc"]
            inverter_controller.set_hybrid_target_soc(
                hybrid_target_soc
            )

        publish_hybrid_decision(
            client,
            hybrid_decision,
        )

        log(
            "Hybrid evaluation: "
            f"status={decision['status']}, "
            f"reason={decision['reason']}"
        )

        requested_mode = decision.get("request")

        if requested_mode is None:
            return

        log(
            "Hybrid decision triggered: "
            f"request={requested_mode}, "
            f"target_soc={hybrid_target_soc:.1f}%, "
            f"useful_solar="
            f"{decision['useful_solar_start']}"
        )

        queue_mode_request(
            requested_mode,
            notification_event={
                "mode": "hybrid",
                "requested_mode": requested_mode,
                "soc": state.battery_soc,
                "forecast": forecast_tomorrow,
                "projected_soc_at_07": (
                    decision["projected_soc_at_07"]
                ),
                "morning_hours": decision["morning_hours"],
                "useful_solar_start": (
                    decision["useful_solar_start"]
                ),
                "target_soc": hybrid_target_soc,
                "target_capped": decision["target_capped"],
                "expected_consumption_after_07": (
                    decision["expected_consumption_after_07"]
                ),
                "solar_forecast_after_07": (
                    decision["solar_forecast_after_07"]
                ),
                "daytime_deficit_kwh": (
                    decision["daytime_deficit_kwh"]
                ),
                "daytime_deficit_soc": (
                    decision["daytime_deficit_soc"]
                ),
                "forecast_fallback": (
                    decision["used_fallback"]
                ),
                "reason": decision["reason"],
            },
        )

    def evaluate_panic(state):
        nonlocal panic_target_soc

        grid_confidence = stability.level()
        evaluation_time = datetime.now().astimezone()
        evaluation_date = evaluation_time.strftime("%Y-%m-%d")
        evaluation_minutes = (
            evaluation_time.hour * 60
            + evaluation_time.minute
        )
        inside_panic_window = (
            7 * 60 <= evaluation_minutes < 23 * 60 + 50
        )

        if (
            inside_panic_window
            and inverter_controller.ahm_debt_date != evaluation_date
        ):
            ahm_debt_target = None

            if (
                hybrid_target_soc is not None
                and state.battery_soc is not None
                and state.battery_soc < hybrid_target_soc
            ):
                ahm_debt_target = hybrid_target_soc

            inverter_controller.set_ahm_debt(
                evaluation_date,
                ahm_debt_target,
            )

            log(
                "AHM morning debt evaluated: "
                f"date={evaluation_date}, "
                f"target={ahm_debt_target}"
            )

        elif (
            inside_panic_window
            and
            inverter_controller.ahm_debt_target_soc is not None
            and state.battery_soc is not None
            and state.battery_soc
            >= inverter_controller.ahm_debt_target_soc
        ):
            inverter_controller.set_ahm_debt(
                evaluation_date,
                None,
            )

            log("AHM morning debt has been recovered")

        decision = panic_decision.evaluate(
            autopilot_enabled=autopilot.is_enabled(),
            operating_mode=inverter_controller.mode,
            grid_confidence=grid_confidence,
            battery_soc=state.battery_soc,
            grid_available=grid.is_available,
            ahm_target_soc=(
                inverter_controller.ahm_debt_target_soc
            ),
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

            log(
                "Subscribed to "
                "energyhub/input/ha/#"
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

        topic = msg.topic
        payload = msg.payload.decode("utf-8")

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

        if key == "adaptive_hybrid_plan":
            try:
                plan = json.loads(payload)
                morning_hours = round(
                    float(plan["morning_hours"]),
                    2,
                )
                useful_solar_start = str(
                    plan["useful_solar_start"]
                ).strip()
                solar_after_07 = plan.get("solar_after_07_kwh")
                if solar_after_07 is not None:
                    solar_after_07 = round(
                        float(solar_after_07),
                        2,
                    )
            except (
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ):
                log(
                    "Decision input ignored invalid "
                    f"adaptive_hybrid_plan: {payload}"
                )
                return

            decision_inputs["hybrid_morning_hours"] = (
                morning_hours
            )
            decision_inputs["hybrid_useful_solar_start"] = (
                useful_solar_start
            )
            if solar_after_07 is not None:
                decision_inputs["hybrid_solar_after_07"] = (
                    solar_after_07
                )

            log(
                "Adaptive Hybrid plan input updated: "
                f"morning_hours={morning_hours}, "
                f"useful_solar_start={useful_solar_start}, "
                f"solar_after_07_kwh={solar_after_07}"
            )
            return

        live_forecast_keys = {
            "solar_forecast_today_live": (
                "solar_forecast_today"
            ),
            "solar_forecast_tomorrow_live": (
                "solar_forecast_tomorrow"
            ),
        }

        if key == "hybrid_useful_solar_start":
            decision_inputs[key] = payload.strip()

            log(
                "Decision input updated: "
                f"{key}={decision_inputs[key]}"
            )
            return

        if key == "hybrid_morning_hours":
            try:
                value = round(float(payload), 2)
            except (TypeError, ValueError):
                log(
                    "Decision input ignored invalid value "
                    f"{key}: {payload}"
                )
                return

            decision_inputs[key] = value

            log(
                "Decision input updated: "
                f"{key}={value}"
            )
            return

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

        if key in {
            "solar_forecast_today",
            "solar_forecast_tomorrow",
        }:
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

    publish_grid_discovery(client)
    publish_grid_import_discovery(client)
    publish_health_discovery(client)
    publish_battery_health_discovery(client)
    publish_telemetry_freshness_discovery(client)
    publish_inverter_health_discovery(client)
    publish_inverter_settings_discovery(client)
    publish_operating_mode_discovery(client)
    publish_hybrid_decision_discovery(client)
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

            telemetry_freshness.update(state)

            publish_telemetry_freshness(
                client,
                telemetry_freshness,
            )

            now = time.monotonic()

            if (
                now - last_warning_read
                >= INVERTER_WARNING_INTERVAL_SECONDS
            ):
                try:
                    warning_data = inverter.read_warnings()

                    inverter_health.update(
                        warning_data
                    )

                except Exception as e:
                    inverter_health.failure()

                    log(
                        "ERROR: QPIWS warning "
                        f"read failed: {e}"
                    )

                publish_inverter_health(
                    client,
                    inverter_health,
                )

                last_warning_read = now

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

                if hybrid_evaluation_requested:
                    evaluate_hybrid(state)
                    hybrid_evaluation_requested = False

                if (
                    autopilot.is_enabled()
                    and inverter_controller.mode
                    == "hybrid_charging"
                    and soc is not None
                    and soc >= (
                        hybrid_target_soc
                        or HYBRID_DEFAULT_TARGET_SOC
                    )
                ):
                    active_hybrid_target = (
                        hybrid_target_soc
                        or HYBRID_DEFAULT_TARGET_SOC
                    )
                    log(
                        "Hybrid target reached: "
                        f"SOC={soc}%, "
                        f"target={active_hybrid_target:.1f}%. "
                        "Switching to Grid Hold."
                    )

                    inverter_controller.enter_hybrid_grid_hold()
                    publish_controller_state()

                if (
                    autopilot.is_enabled()
                    and inverter_controller.mode == "panic"
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

            client.publish(
                INVERTER_AVAILABILITY_TOPIC,
                "offline",
                retain=True,
            )

        except Exception:
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

            client.publish(
                INVERTER_AVAILABILITY_TOPIC,
                "offline",
                retain=True,
            )

        time.sleep(
            int(options["poll_interval"])
        )


if __name__ == "__main__":
    main()
