import math
import time

from app.config import LAST_FILE
from app.models.inverter_state import InverterState
from app.mqtt.publisher import publish_values
from app.utils.json_store import atomic_write_json
from app.utils.logger import log


REQUIRED_FIELDS = [
    "battery_capacity",
    "ac_output_active_power",
    "pv1_charging_power",
    "ac_input_voltage",
]

LAST_SNAPSHOT_SAVE_INTERVAL_SECONDS = 60


def _to_float(value):
    try:
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


class TelemetryService:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.previous = {}
        self.last_snapshot_save_monotonic = None

    def create_state(self, data):
        required = {
            key: _to_float(data.get(key))
            for key in REQUIRED_FIELDS
        }
        valid = all(value is not None for value in required.values())

        battery_soc = required["battery_capacity"]
        if battery_soc is not None and not 0 <= battery_soc <= 100:
            valid = False

        grid_voltage = required["ac_input_voltage"]
        if grid_voltage is not None and grid_voltage < 0:
            valid = False
        if required["ac_output_active_power"] is not None and required["ac_output_active_power"] < 0:
            valid = False
        if required["pv1_charging_power"] is not None and required["pv1_charging_power"] < 0:
            valid = False

        return InverterState(
            valid=valid,
            grid_available=grid_voltage is not None and grid_voltage > 180,
            battery_soc=battery_soc,
            battery_voltage=_to_float(data.get("battery_voltage")),
            battery_current=_to_float(data.get("battery_discharge_current")),
            pv_power=required["pv1_charging_power"],
            load_power=required["ac_output_active_power"],
            raw=data,
        )

    def process(self, data):
        state = self.create_state(data)

        if not state.valid:
            log("Telemetry invalid")
            log(
                "Invalid values | "
                f"SOC={state.battery_soc} | "
                f"PV={state.pv_power} | "
                f"Load={state.load_power} | "
                f"Grid={_to_float(data.get('ac_input_voltage'))}"
            )
            return state

        published = publish_values(self.mqtt_client, data, self.previous)
        self.previous.update(data)

        self._save_last_snapshot(data)

        log(
            "OK | "
            f"SOC={state.battery_soc}% | "
            f"PV1={state.pv_power}W | "
            f"Load={state.load_power}W | "
            f"Grid={'online' if state.grid_available else 'offline'} | "
            f"Published={published} | "
            f"Suppressed={self.previous.get('__last_suppressed__', 0)}"
        )

        return state

    def _save_last_snapshot(self, data):
        now_monotonic = time.monotonic()

        if (
            self.last_snapshot_save_monotonic is not None
            and now_monotonic - self.last_snapshot_save_monotonic
            < LAST_SNAPSHOT_SAVE_INTERVAL_SECONDS
        ):
            return

        try:
            atomic_write_json(
                LAST_FILE,
                data,
                ensure_ascii=False,
                indent=None,
            )
            self.last_snapshot_save_monotonic = now_monotonic

        except Exception as e:
            log(
                "Failed to save last telemetry snapshot: "
                f"{e}"
            )
