import json
import time
from datetime import datetime
from pathlib import Path

from app.utils.json_store import atomic_write_json
from app.utils.logger import log


GRID_IMPORT_FILE = Path("/data/grid_import.json")
SCHEMA_VERSION = 2
BATTERY_CAPACITY_KWH = 16.0
PERSIST_INTERVAL_SECONDS = 60

SUB_OPERATING_MODES = {
    "hybrid_charging",
    "hybrid_grid_hold",
    "panic",
    "panic_grid_hold",
}


class GridImportService:
    def __init__(self):
        self.date = datetime.now().strftime("%Y-%m-%d")

        self.house_energy_kwh = 0.0
        self.battery_energy_kwh = 0.0
        self.current_power_w = 0.0
        self.yesterday_energy_kwh = 0.0

        self.sub_active = False
        self.sub_start_soc = None
        self.sub_max_soc = None
        self.sub_battery_accounted_kwh = 0.0

        self.last_update_monotonic = None
        self.last_save_monotonic = None

        # Completed-day totals wait here until Daily Summary has reconciled
        # its historical record. Keeping this queue in Grid Import persistence
        # makes the hand-off survive an add-on restart immediately after
        # midnight.
        self.pending_day_finalizations = {}

        self.load()

    @property
    def daily_energy_kwh(self):
        return self.house_energy_kwh + self.battery_energy_kwh

    def load(self):
        if not GRID_IMPORT_FILE.exists():
            log(
                "Grid import history not found. "
                "Starting from 0 kWh."
            )
            return

        try:
            data = json.loads(
                GRID_IMPORT_FILE.read_text()
            )

            stored_date = data.get("date")
            stored_schema_version = int(
                data.get("schema_version", 1)
            )
            today = datetime.now().strftime("%Y-%m-%d")

            self.yesterday_energy_kwh = float(
                data.get(
                    "yesterday_energy_kwh",
                    0.0,
                )
            )

            self.pending_day_finalizations = (
                self._load_pending_day_finalizations(
                    data.get("pending_day_finalizations", {})
                )
            )

            if (
                stored_date == today
                and stored_schema_version != SCHEMA_VERSION
            ):
                self.date = today
                self._reset_today()

                log(
                    "Grid import data migrated to schema "
                    f"v{SCHEMA_VERSION}: "
                    "old current-day estimate discarded; "
                    "today starts from 0 kWh"
                )

                self.save()

            elif stored_date == today:
                self.date = stored_date

                if "house_energy_kwh" in data:
                    self.house_energy_kwh = float(
                        data.get("house_energy_kwh", 0.0)
                    )
                    self.battery_energy_kwh = float(
                        data.get("battery_energy_kwh", 0.0)
                    )
                else:
                    # Migration from the older single-total format.
                    self.house_energy_kwh = float(
                        data.get("daily_energy_kwh", 0.0)
                    )
                    self.battery_energy_kwh = 0.0

                self.current_power_w = float(
                    data.get("current_power_w", 0.0)
                )

                self.sub_active = bool(
                    data.get("sub_active", False)
                )
                self.sub_start_soc = self._optional_float(
                    data.get("sub_start_soc")
                )
                self.sub_max_soc = self._optional_float(
                    data.get("sub_max_soc")
                )
                self.sub_battery_accounted_kwh = float(
                    data.get(
                        "sub_battery_accounted_kwh",
                        0.0,
                    )
                )

                self.last_save_monotonic = time.monotonic()

                log(
                    "Grid import loaded: "
                    f"today={self.daily_energy_kwh:.3f} kWh, "
                    f"yesterday="
                    f"{self.yesterday_energy_kwh:.3f} kWh"
                )

            else:
                completed_total = float(
                    data.get(
                        "house_energy_kwh",
                        data.get("daily_energy_kwh", 0.0),
                    )
                ) + float(
                    data.get("battery_energy_kwh", 0.0)
                )

                if stored_date:
                    self.yesterday_energy_kwh = completed_total
                    self._queue_day_finalization(
                        stored_date,
                        completed_total,
                    )

                self.date = today
                self._reset_today()

                log(
                    "Grid import started for new day: "
                    f"{self.date}; "
                    f"yesterday="
                    f"{self.yesterday_energy_kwh:.3f} kWh"
                )

                self.save()

        except Exception as e:
            log(
                "Failed to load grid import: "
                f"{e}"
            )

    def save(self):
        data = {
            "schema_version": SCHEMA_VERSION,
            "date": self.date,
            "house_energy_kwh": round(
                self.house_energy_kwh,
                6,
            ),
            "battery_energy_kwh": round(
                self.battery_energy_kwh,
                6,
            ),
            "daily_energy_kwh": round(
                self.daily_energy_kwh,
                6,
            ),
            "current_power_w": round(
                self.current_power_w,
                1,
            ),
            "yesterday_energy_kwh": round(
                self.yesterday_energy_kwh,
                6,
            ),
            "sub_active": self.sub_active,
            "sub_start_soc": self.sub_start_soc,
            "sub_max_soc": self.sub_max_soc,
            "sub_battery_accounted_kwh": round(
                self.sub_battery_accounted_kwh,
                6,
            ),
            "pending_day_finalizations": {
                date: round(value, 6)
                for date, value in sorted(
                    self.pending_day_finalizations.items()
                )
            },
            "timestamp": int(time.time()),
        }

        try:
            atomic_write_json(
                GRID_IMPORT_FILE,
                data,
                ensure_ascii=False,
                indent=2,
            )
            self.last_save_monotonic = time.monotonic()

        except Exception as e:
            log(
                "Failed to save grid import: "
                f"{e}"
            )

    def update(
        self,
        *,
        operating_mode,
        output_power_w,
        battery_soc,
    ):
        if not self._valid_number(output_power_w):
            self.current_power_w = 0.0
            self.last_update_monotonic = None
            return False

        if not self._valid_number(battery_soc):
            self.current_power_w = 0.0
            self.last_update_monotonic = None
            return False

        output_power_w = max(
            0.0,
            float(output_power_w),
        )
        battery_soc = float(battery_soc)

        is_sub = operating_mode in SUB_OPERATING_MODES

        self._check_new_day(
            battery_soc=battery_soc,
            is_sub=is_sub,
        )

        # During startup/transition, do not destroy a persisted
        # active SUB interval until the operating mode is known.
        if operating_mode in {
            "unknown",
            "transitioning",
        }:
            self.current_power_w = 0.0
            self.last_update_monotonic = None
            return True

        if not is_sub:
            was_sub_active = self.sub_active

            if was_sub_active:
                log(
                    "Grid import accounting stopped: "
                    f"mode={operating_mode}, "
                    f"today={self.daily_energy_kwh:.3f} kWh"
                )

            self._stop_sub_interval()
            self.current_power_w = 0.0
            self.last_update_monotonic = None

            if was_sub_active:
                self._save_if_needed(force=True)

            return True

        if not self.sub_active:
            self._start_sub_interval(battery_soc)

        self.current_power_w = round(
            output_power_w,
            1,
        )

        self._update_battery_energy(battery_soc)
        self._integrate_house_energy()
        self._save_if_needed()

        return True

    def _start_sub_interval(self, battery_soc):
        self.sub_active = True
        self.sub_start_soc = battery_soc
        self.sub_max_soc = battery_soc
        self.sub_battery_accounted_kwh = 0.0
        self.last_update_monotonic = None

        log(
            "Grid import accounting started: "
            f"SUB interval, SOC={battery_soc:.1f}%"
        )

        self.save()

    def _stop_sub_interval(self):
        self.sub_active = False
        self.sub_start_soc = None
        self.sub_max_soc = None
        self.sub_battery_accounted_kwh = 0.0
        self.last_update_monotonic = None

    def _update_battery_energy(self, battery_soc):
        if self.sub_start_soc is None:
            self.sub_start_soc = battery_soc

        if (
            self.sub_max_soc is None
            or battery_soc > self.sub_max_soc
        ):
            self.sub_max_soc = battery_soc

        soc_gain = max(
            0.0,
            self.sub_max_soc - self.sub_start_soc,
        )

        interval_battery_energy_kwh = (
            BATTERY_CAPACITY_KWH
            * soc_gain
            / 100.0
        )

        new_battery_energy_kwh = max(
            0.0,
            interval_battery_energy_kwh
            - self.sub_battery_accounted_kwh,
        )

        if new_battery_energy_kwh <= 0:
            return

        self.battery_energy_kwh += new_battery_energy_kwh
        self.sub_battery_accounted_kwh = (
            interval_battery_energy_kwh
        )

        log(
            "Grid import battery contribution: "
            f"SOC gain={soc_gain:.1f}%, "
            f"energy="
            f"{interval_battery_energy_kwh:.3f} kWh"
        )

    def _integrate_house_energy(self):
        now_monotonic = time.monotonic()

        if self.last_update_monotonic is None:
            self.last_update_monotonic = now_monotonic
            return

        elapsed_seconds = (
            now_monotonic
            - self.last_update_monotonic
        )

        self.last_update_monotonic = now_monotonic

        if elapsed_seconds <= 0 or elapsed_seconds > 60:
            return

        energy_increment_kwh = (
            self.current_power_w
            * elapsed_seconds
            / 3_600_000
        )

        self.house_energy_kwh += energy_increment_kwh

    def _check_new_day(
        self,
        *,
        battery_soc,
        is_sub,
    ):
        today = datetime.now().strftime("%Y-%m-%d")

        if today == self.date:
            return

        completed_total = self.daily_energy_kwh

        log(
            "Grid import day completed: "
            f"{self.date}={completed_total:.3f} kWh"
        )

        self._queue_day_finalization(
            self.date,
            completed_total,
        )

        self.yesterday_energy_kwh = completed_total
        self.date = today
        self._reset_today()

        if is_sub:
            self._start_sub_interval(battery_soc)
        else:
            self.save()

    def _reset_today(self):
        self.house_energy_kwh = 0.0
        self.battery_energy_kwh = 0.0
        self.current_power_w = 0.0

        self.sub_active = False
        self.sub_start_soc = None
        self.sub_max_soc = None
        self.sub_battery_accounted_kwh = 0.0

        self.last_update_monotonic = None
        self.last_save_monotonic = None

    def _save_if_needed(self, force=False):
        now_monotonic = time.monotonic()

        if (
            force
            or self.last_save_monotonic is None
            or (
                now_monotonic - self.last_save_monotonic
                >= PERSIST_INTERVAL_SECONDS
            )
        ):
            self.save()

    def mqtt_values(self):
        return {
            "grid_import_power_estimated": round(
                self.current_power_w,
                0,
            ),
            "daily_grid_import_estimated": round(
                self.daily_energy_kwh,
                3,
            ),
            "grid_import_yesterday_estimated": round(
                self.yesterday_energy_kwh,
                3,
            ),
        }

    def get_pending_day_finalizations(self):
        return tuple(
            sorted(
                self.pending_day_finalizations.items()
            )
        )

    def mark_day_finalization_handled(self, completed_date):
        if completed_date not in self.pending_day_finalizations:
            return False

        self.pending_day_finalizations.pop(completed_date, None)
        self.save()

        log(
            "Grid import day finalization handled: "
            f"{completed_date}"
        )
        return True

    def _queue_day_finalization(
        self,
        completed_date,
        completed_total,
    ):
        if not completed_date:
            return

        try:
            datetime.strptime(completed_date, "%Y-%m-%d")
            numeric_total = max(0.0, float(completed_total))
        except (TypeError, ValueError):
            log(
                "Grid import ignored invalid completed day: "
                f"date={completed_date}, total={completed_total}"
            )
            return

        self.pending_day_finalizations[completed_date] = (
            numeric_total
        )

        log(
            "Grid import queued Daily Summary finalization: "
            f"{completed_date}={numeric_total:.3f} kWh"
        )

    @staticmethod
    def _load_pending_day_finalizations(raw_pending):
        if not isinstance(raw_pending, dict):
            return {}

        pending = {}

        for completed_date, completed_total in raw_pending.items():
            try:
                datetime.strptime(completed_date, "%Y-%m-%d")
                numeric_total = max(
                    0.0,
                    float(completed_total),
                )
            except (TypeError, ValueError):
                continue

            pending[completed_date] = numeric_total

        return pending

    @staticmethod
    def _valid_number(value):
        if value is None:
            return False

        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _optional_float(value):
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None
