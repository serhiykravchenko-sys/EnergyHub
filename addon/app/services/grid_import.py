import json
import os
import time
from datetime import datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.json_store import atomic_write_json
from app.utils.logger import log


GRID_IMPORT_FILE = Path("/data/grid_import.json")
SCHEMA_VERSION = 3
BATTERY_CAPACITY_KWH = 16.0
PERSIST_INTERVAL_SECONDS = 60
HISTORY_RETENTION_DAYS = 400
NIGHT_PRICE_UAH_PER_KWH = 2.5
NORMAL_PRICE_UAH_PER_KWH = 5.0

SUB_OPERATING_MODES = {
    "hybrid_charging",
    "hybrid_grid_hold",
    "panic",
    "panic_grid_hold",
}


class GridImportService:
    """Estimate Grid Import and split it into local calendar-day tariffs."""

    def __init__(self, path=GRID_IMPORT_FILE, clock=None, timezone_name=None):
        self.path = Path(path)
        self.timezone = self._load_timezone(
            timezone_name or os.environ.get("TZ") or "Europe/Kyiv"
        )
        self.clock = clock or (lambda: datetime.now(self.timezone))
        now = self._now()

        self.date = now.date().isoformat()
        self.house_energy_kwh = 0.0
        self.battery_energy_kwh = 0.0
        self.current_power_w = 0.0
        self.yesterday_energy_kwh = 0.0

        self.night_house_energy_kwh = 0.0
        self.night_battery_energy_kwh = 0.0
        self.normal_house_energy_kwh = 0.0
        self.normal_battery_energy_kwh = 0.0
        self.night_cost_uah = 0.0
        self.normal_cost_uah = 0.0
        self.total_night_energy_kwh = 0.0
        self.total_normal_energy_kwh = 0.0

        self.yesterday_night_energy_kwh = None
        self.yesterday_normal_energy_kwh = None
        self.yesterday_cost_uah = None
        self.yesterday_tariff_complete = False
        self.daily_tariff_history = {}
        self.tariff_accounting_started_at = now.isoformat()

        self.sub_active = False
        self.sub_start_soc = None
        self.sub_max_soc = None
        self.sub_battery_accounted_kwh = 0.0

        self.last_update_monotonic = None
        self.last_update_at = None
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

    @property
    def night_energy_kwh(self):
        return self.night_house_energy_kwh + self.night_battery_energy_kwh

    @property
    def normal_energy_kwh(self):
        return self.normal_house_energy_kwh + self.normal_battery_energy_kwh

    @property
    def daily_cost_uah(self):
        return self.night_cost_uah + self.normal_cost_uah

    def load(self):
        if not self.path.exists():
            log("Grid import history not found. Starting from 0 kWh.")
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            stored_date = data.get("date")
            stored_schema_version = int(data.get("schema_version", 1))
            today = self._now().date().isoformat()

            self.yesterday_energy_kwh = self._nonnegative(
                data.get("yesterday_energy_kwh", 0.0)
            )
            self.pending_day_finalizations = self._load_pending_day_finalizations(
                data.get("pending_day_finalizations", {})
            )

            if stored_schema_version < SCHEMA_VERSION:
                self._load_legacy_current_day(data, stored_date, today)
                log(
                    "Grid import data migrated to schema v3: existing total "
                    "import was preserved; tariff accounting starts at migration"
                )
                self.save()
                return

            self.daily_tariff_history = self._load_tariff_history(
                data.get("daily_tariff_history", {})
            )
            self.total_night_energy_kwh = self._nonnegative(
                data.get("total_night_energy_kwh", 0.0)
            )
            self.total_normal_energy_kwh = self._nonnegative(
                data.get("total_normal_energy_kwh", 0.0)
            )
            self.tariff_accounting_started_at = str(
                data.get("tariff_accounting_started_at")
                or self.tariff_accounting_started_at
            )
            self.yesterday_night_energy_kwh = self._optional_nonnegative(
                data.get("yesterday_night_energy_kwh")
            )
            self.yesterday_normal_energy_kwh = self._optional_nonnegative(
                data.get("yesterday_normal_energy_kwh")
            )
            self.yesterday_cost_uah = self._optional_nonnegative(
                data.get("yesterday_cost_uah")
            )
            self.yesterday_tariff_complete = bool(
                data.get("yesterday_tariff_complete", False)
            )

            if stored_date == today:
                self._load_current_day(data)
                log(
                    "Grid import loaded: "
                    f"today={self.daily_energy_kwh:.3f} kWh, "
                    f"night={self.night_energy_kwh:.3f} kWh, "
                    f"normal={self.normal_energy_kwh:.3f} kWh"
                )
                return

            if stored_date:
                completed_total = self._stored_total(data)
                self._load_current_day(data)
                self._complete_day(stored_date, completed_total)

            self.date = today
            self._reset_today()
            log(
                "Grid import started for new day: "
                f"{self.date}; yesterday={self.yesterday_energy_kwh:.3f} kWh"
            )
            self.save()

        except Exception as e:
            log(f"Failed to load grid import: {e}")

    def _load_legacy_current_day(self, data, stored_date, today):
        completed_total = self._stored_total(data)
        self.tariff_accounting_started_at = self._now().isoformat()
        self.daily_tariff_history = {}
        self.total_night_energy_kwh = 0.0
        self.total_normal_energy_kwh = 0.0
        self.yesterday_night_energy_kwh = None
        self.yesterday_normal_energy_kwh = None
        self.yesterday_cost_uah = None
        self.yesterday_tariff_complete = False

        if stored_date == today:
            self.date = today
            self.house_energy_kwh = self._nonnegative(
                data.get("house_energy_kwh", data.get("daily_energy_kwh", 0.0))
            )
            self.battery_energy_kwh = self._nonnegative(
                data.get("battery_energy_kwh", 0.0)
            )
            self.current_power_w = self._nonnegative(
                data.get("current_power_w", 0.0)
            )
            self.sub_active = bool(data.get("sub_active", False))
            self.sub_start_soc = self._optional_float(data.get("sub_start_soc"))
            self.sub_max_soc = self._optional_float(data.get("sub_max_soc"))
            self.sub_battery_accounted_kwh = self._nonnegative(
                data.get("sub_battery_accounted_kwh", 0.0)
            )
            self.last_save_monotonic = time.monotonic()
            return

        if stored_date:
            self.yesterday_energy_kwh = completed_total
            self._queue_day_finalization(stored_date, completed_total)
        self.date = today
        self._reset_today()

    def _load_current_day(self, data):
        self.date = str(data.get("date") or self.date)
        self.house_energy_kwh = self._nonnegative(
            data.get("house_energy_kwh", data.get("daily_energy_kwh", 0.0))
        )
        self.battery_energy_kwh = self._nonnegative(
            data.get("battery_energy_kwh", 0.0)
        )
        self.current_power_w = self._nonnegative(data.get("current_power_w", 0.0))
        for name in (
            "night_house_energy_kwh",
            "night_battery_energy_kwh",
            "normal_house_energy_kwh",
            "normal_battery_energy_kwh",
            "night_cost_uah",
            "normal_cost_uah",
        ):
            setattr(self, name, self._nonnegative(data.get(name, 0.0)))
        self.sub_active = bool(data.get("sub_active", False))
        self.sub_start_soc = self._optional_float(data.get("sub_start_soc"))
        self.sub_max_soc = self._optional_float(data.get("sub_max_soc"))
        self.sub_battery_accounted_kwh = self._nonnegative(
            data.get("sub_battery_accounted_kwh", 0.0)
        )
        self.last_save_monotonic = time.monotonic()

    def save(self):
        data = {
            "schema_version": SCHEMA_VERSION,
            "date": self.date,
            "house_energy_kwh": round(self.house_energy_kwh, 6),
            "battery_energy_kwh": round(self.battery_energy_kwh, 6),
            "daily_energy_kwh": round(self.daily_energy_kwh, 6),
            "current_power_w": round(self.current_power_w, 1),
            "yesterday_energy_kwh": round(self.yesterday_energy_kwh, 6),
            "night_house_energy_kwh": round(self.night_house_energy_kwh, 6),
            "night_battery_energy_kwh": round(self.night_battery_energy_kwh, 6),
            "normal_house_energy_kwh": round(self.normal_house_energy_kwh, 6),
            "normal_battery_energy_kwh": round(self.normal_battery_energy_kwh, 6),
            "night_cost_uah": round(self.night_cost_uah, 6),
            "normal_cost_uah": round(self.normal_cost_uah, 6),
            "total_night_energy_kwh": round(self.total_night_energy_kwh, 6),
            "total_normal_energy_kwh": round(self.total_normal_energy_kwh, 6),
            "yesterday_night_energy_kwh": self.yesterday_night_energy_kwh,
            "yesterday_normal_energy_kwh": self.yesterday_normal_energy_kwh,
            "yesterday_cost_uah": self.yesterday_cost_uah,
            "yesterday_tariff_complete": self.yesterday_tariff_complete,
            "night_price_uah_per_kwh": NIGHT_PRICE_UAH_PER_KWH,
            "normal_price_uah_per_kwh": NORMAL_PRICE_UAH_PER_KWH,
            "tariff_accounting_started_at": self.tariff_accounting_started_at,
            "daily_tariff_history": self.daily_tariff_history,
            "sub_active": self.sub_active,
            "sub_start_soc": self.sub_start_soc,
            "sub_max_soc": self.sub_max_soc,
            "sub_battery_accounted_kwh": round(
                self.sub_battery_accounted_kwh, 6
            ),
            "pending_day_finalizations": {
                date: round(value, 6)
                for date, value in sorted(self.pending_day_finalizations.items())
            },
            "timestamp": int(time.time()),
        }

        try:
            atomic_write_json(self.path, data, ensure_ascii=False, indent=2)
            self.last_save_monotonic = time.monotonic()
        except Exception as e:
            log(f"Failed to save grid import: {e}")

    def update(self, *, operating_mode, output_power_w, battery_soc, now=None):
        current_time = self._normalize_time(now or self._now())

        if not self._valid_number(output_power_w) or not self._valid_number(
            battery_soc
        ):
            self.current_power_w = 0.0
            self.last_update_monotonic = None
            self.last_update_at = None
            return False

        output_power_w = max(0.0, float(output_power_w))
        battery_soc = float(battery_soc)
        is_sub = operating_mode in SUB_OPERATING_MODES

        # During startup/transition, do not destroy a persisted active SUB
        # interval until the operating mode is known.
        if operating_mode in {"unknown", "transitioning"}:
            self._check_new_day(current_time, battery_soc, self.sub_active)
            self.current_power_w = 0.0
            self.last_update_monotonic = None
            self.last_update_at = None
            return True

        if not is_sub:
            self._check_new_day(current_time, battery_soc, False)
            was_sub_active = self.sub_active
            if was_sub_active:
                log(
                    "Grid import accounting stopped: "
                    f"mode={operating_mode}, today={self.daily_energy_kwh:.3f} kWh"
                )
            self._stop_sub_interval()
            self.current_power_w = 0.0
            if was_sub_active:
                self._save_if_needed(force=True)
            return True

        if not self.sub_active:
            self._check_new_day(current_time, battery_soc, True)
            self._start_sub_interval(battery_soc, current_time)

        self.current_power_w = round(output_power_w, 1)
        self._integrate_house_energy(current_time, battery_soc)
        self._update_battery_energy(battery_soc, current_time)
        self._save_if_needed()
        return True

    def _start_sub_interval(self, battery_soc, current_time=None):
        self.sub_active = True
        self.sub_start_soc = battery_soc
        self.sub_max_soc = battery_soc
        self.sub_battery_accounted_kwh = 0.0
        self.last_update_monotonic = None
        self.last_update_at = current_time
        log(f"Grid import accounting started: SUB interval, SOC={battery_soc:.1f}%")
        self.save()

    def _stop_sub_interval(self):
        self.sub_active = False
        self.sub_start_soc = None
        self.sub_max_soc = None
        self.sub_battery_accounted_kwh = 0.0
        self.last_update_monotonic = None
        self.last_update_at = None

    def _update_battery_energy(self, battery_soc, current_time):
        if self.sub_start_soc is None:
            self.sub_start_soc = battery_soc
        if self.sub_max_soc is None or battery_soc > self.sub_max_soc:
            self.sub_max_soc = battery_soc

        soc_gain = max(0.0, self.sub_max_soc - self.sub_start_soc)
        interval_battery_energy_kwh = BATTERY_CAPACITY_KWH * soc_gain / 100.0
        new_battery_energy_kwh = max(
            0.0,
            interval_battery_energy_kwh - self.sub_battery_accounted_kwh,
        )
        if new_battery_energy_kwh <= 0:
            return

        self.battery_energy_kwh += new_battery_energy_kwh
        self.sub_battery_accounted_kwh = interval_battery_energy_kwh
        self._add_tariff_energy(
            self._tariff_for(current_time), "battery", new_battery_energy_kwh
        )
        log(
            "Grid import battery contribution: "
            f"SOC gain={soc_gain:.1f}%, energy={interval_battery_energy_kwh:.3f} kWh"
        )

    def _integrate_house_energy(self, current_time, battery_soc):
        now_monotonic = time.monotonic()
        if self.last_update_monotonic is None:
            self.last_update_monotonic = now_monotonic
            self.last_update_at = current_time
            return

        elapsed_seconds = now_monotonic - self.last_update_monotonic
        self.last_update_monotonic = now_monotonic
        if elapsed_seconds <= 0 or elapsed_seconds > 60:
            self._check_new_day(current_time, battery_soc, True)
            self.last_update_at = current_time
            return

        start = current_time - timedelta(seconds=elapsed_seconds)
        if self.last_update_at is not None:
            observed_elapsed = (current_time - self.last_update_at).total_seconds()
            if 0 < observed_elapsed <= 60:
                start = self.last_update_at

        cursor = start
        while cursor < current_time:
            if cursor.date().isoformat() != self.date:
                self._roll_day(cursor.date().isoformat(), battery_soc, True)
            boundary = min(self._next_tariff_boundary(cursor), current_time)
            seconds = max(0.0, (boundary - cursor).total_seconds())
            energy_increment_kwh = self.current_power_w * seconds / 3_600_000
            if energy_increment_kwh > 0:
                self.house_energy_kwh += energy_increment_kwh
                self._add_tariff_energy(
                    self._tariff_for(cursor), "house", energy_increment_kwh
                )
            cursor = boundary

        if current_time.date().isoformat() != self.date:
            self._roll_day(current_time.date().isoformat(), battery_soc, True)
        self.last_update_monotonic = now_monotonic
        self.last_update_at = current_time

    def _add_tariff_energy(self, tariff, contribution, energy_kwh):
        if tariff == "night":
            attribute = f"night_{contribution}_energy_kwh"
            self.night_cost_uah += energy_kwh * NIGHT_PRICE_UAH_PER_KWH
            self.total_night_energy_kwh += energy_kwh
        else:
            attribute = f"normal_{contribution}_energy_kwh"
            self.normal_cost_uah += energy_kwh * NORMAL_PRICE_UAH_PER_KWH
            self.total_normal_energy_kwh += energy_kwh
        setattr(self, attribute, getattr(self, attribute) + energy_kwh)

    def _check_new_day(self, current_time, battery_soc, is_sub):
        today = current_time.date().isoformat()
        if today != self.date:
            self._roll_day(today, battery_soc, is_sub)

    def _roll_day(self, new_date, battery_soc, is_sub):
        completed_date = self.date
        completed_total = self.daily_energy_kwh
        active_power_w = self.current_power_w if is_sub else 0.0
        self._complete_day(completed_date, completed_total)
        log(f"Grid import day completed: {completed_date}={completed_total:.3f} kWh")
        self.date = new_date
        self._reset_today()
        if is_sub:
            self.current_power_w = active_power_w
            self.sub_active = True
            self.sub_start_soc = battery_soc
            self.sub_max_soc = battery_soc
            self.sub_battery_accounted_kwh = 0.0
        self.save()

    def _complete_day(self, completed_date, completed_total):
        tariff_complete = self._tariff_day_complete(completed_date)
        self.yesterday_energy_kwh = max(0.0, float(completed_total))
        self.yesterday_tariff_complete = tariff_complete
        self.yesterday_night_energy_kwh = (
            self.night_energy_kwh if tariff_complete else None
        )
        self.yesterday_normal_energy_kwh = (
            self.normal_energy_kwh if tariff_complete else None
        )
        self.yesterday_cost_uah = self.daily_cost_uah if tariff_complete else None
        self.daily_tariff_history[completed_date] = {
            "night_kwh": round(self.night_energy_kwh, 6),
            "normal_kwh": round(self.normal_energy_kwh, 6),
            "night_cost_uah": round(self.night_cost_uah, 6),
            "normal_cost_uah": round(self.normal_cost_uah, 6),
            "night_price_uah_per_kwh": NIGHT_PRICE_UAH_PER_KWH,
            "normal_price_uah_per_kwh": NORMAL_PRICE_UAH_PER_KWH,
            "estimated": True,
            "complete": tariff_complete,
        }
        self._prune_tariff_history()
        self._queue_day_finalization(completed_date, completed_total)

    def _reset_today(self):
        self.house_energy_kwh = 0.0
        self.battery_energy_kwh = 0.0
        self.current_power_w = 0.0
        self.night_house_energy_kwh = 0.0
        self.night_battery_energy_kwh = 0.0
        self.normal_house_energy_kwh = 0.0
        self.normal_battery_energy_kwh = 0.0
        self.night_cost_uah = 0.0
        self.normal_cost_uah = 0.0
        self.sub_active = False
        self.sub_start_soc = None
        self.sub_max_soc = None
        self.sub_battery_accounted_kwh = 0.0
        self.last_update_monotonic = None
        self.last_update_at = None
        self.last_save_monotonic = None

    def _save_if_needed(self, force=False):
        now_monotonic = time.monotonic()
        if (
            force
            or self.last_save_monotonic is None
            or now_monotonic - self.last_save_monotonic >= PERSIST_INTERVAL_SECONDS
        ):
            self.save()

    def mqtt_values(self):
        month = self.month_to_date()
        return {
            "grid_import_power_estimated": round(self.current_power_w, 0),
            "daily_grid_import_estimated": round(self.daily_energy_kwh, 3),
            "grid_import_yesterday_estimated": round(self.yesterday_energy_kwh, 3),
            "grid_import_night_today_estimated": round(self.night_energy_kwh, 3),
            "grid_import_normal_today_estimated": round(self.normal_energy_kwh, 3),
            "grid_import_night_yesterday_estimated": self._mqtt_optional(
                self.yesterday_night_energy_kwh
            ),
            "grid_import_normal_yesterday_estimated": self._mqtt_optional(
                self.yesterday_normal_energy_kwh
            ),
            "grid_import_cost_yesterday_estimated": self._mqtt_optional(
                self.yesterday_cost_uah
            ),
            "grid_import_night_total_estimated": round(
                self.total_night_energy_kwh, 3
            ),
            "grid_import_normal_total_estimated": round(
                self.total_normal_energy_kwh, 3
            ),
            "grid_import_night_month_estimated": round(month["night_kwh"], 3),
            "grid_import_normal_month_estimated": round(month["normal_kwh"], 3),
            "grid_import_month_estimated": round(month["total_kwh"], 3),
            "grid_import_cost_month_estimated": round(month["cost_uah"], 2),
            "grid_import_night_price": NIGHT_PRICE_UAH_PER_KWH,
            "grid_import_normal_price": NORMAL_PRICE_UAH_PER_KWH,
        }

    def month_to_date(self, month=None):
        selected_month = month or self.date[:7]
        night_kwh = 0.0
        normal_kwh = 0.0
        cost_uah = 0.0
        for completed_date, record in self.daily_tariff_history.items():
            if (
                completed_date.startswith(f"{selected_month}-")
                and completed_date != self.date
            ):
                night_kwh += self._nonnegative(record.get("night_kwh", 0.0))
                normal_kwh += self._nonnegative(record.get("normal_kwh", 0.0))
                cost_uah += self._nonnegative(record.get("night_cost_uah", 0.0))
                cost_uah += self._nonnegative(record.get("normal_cost_uah", 0.0))
        if self.date.startswith(f"{selected_month}-"):
            night_kwh += self.night_energy_kwh
            normal_kwh += self.normal_energy_kwh
            cost_uah += self.daily_cost_uah
        return {
            "night_kwh": night_kwh,
            "normal_kwh": normal_kwh,
            "total_kwh": night_kwh + normal_kwh,
            "cost_uah": cost_uah,
        }

    def get_pending_day_finalizations(self):
        return tuple(sorted(self.pending_day_finalizations.items()))

    def mark_day_finalization_handled(self, completed_date):
        if completed_date not in self.pending_day_finalizations:
            return False
        self.pending_day_finalizations.pop(completed_date, None)
        self.save()
        log(f"Grid import day finalization handled: {completed_date}")
        return True

    def _queue_day_finalization(self, completed_date, completed_total):
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
        self.pending_day_finalizations[completed_date] = numeric_total
        log(
            "Grid import queued Daily Summary finalization: "
            f"{completed_date}={numeric_total:.3f} kWh"
        )

    def _prune_tariff_history(self):
        if len(self.daily_tariff_history) <= HISTORY_RETENTION_DAYS:
            return
        retained_dates = sorted(self.daily_tariff_history)[-HISTORY_RETENTION_DAYS:]
        self.daily_tariff_history = {
            date: self.daily_tariff_history[date] for date in retained_dates
        }

    def _tariff_day_complete(self, completed_date):
        try:
            started = datetime.fromisoformat(self.tariff_accounting_started_at)
            started = self._normalize_time(started)
            completed = datetime.strptime(completed_date, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return False
        if completed > started.date():
            return True
        return completed == started.date() and started.time() == datetime_time(0, 0)

    def _next_tariff_boundary(self, value):
        local = value.astimezone(self.timezone)
        if local.hour < 7:
            boundary_time = datetime_time(7, 0)
            boundary_date = local.date()
        elif local.hour < 23:
            boundary_time = datetime_time(23, 0)
            boundary_date = local.date()
        else:
            boundary_time = datetime_time(0, 0)
            boundary_date = local.date() + timedelta(days=1)
        return datetime.combine(boundary_date, boundary_time, tzinfo=self.timezone)

    @staticmethod
    def _tariff_for(value):
        return "night" if value.hour < 7 or value.hour >= 23 else "normal"

    def _normalize_time(self, value):
        if value.tzinfo is None:
            return value.replace(tzinfo=self.timezone)
        return value.astimezone(self.timezone)

    def _now(self):
        return self._normalize_time(self.clock())

    @staticmethod
    def _load_timezone(name):
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            log(f"Grid import timezone {name!r} unavailable; using Europe/Kyiv")
            return ZoneInfo("Europe/Kyiv")

    @staticmethod
    def _stored_total(data):
        return GridImportService._nonnegative(
            data.get("house_energy_kwh", data.get("daily_energy_kwh", 0.0))
        ) + GridImportService._nonnegative(data.get("battery_energy_kwh", 0.0))

    @staticmethod
    def _load_pending_day_finalizations(raw_pending):
        if not isinstance(raw_pending, dict):
            return {}
        pending = {}
        for completed_date, completed_total in raw_pending.items():
            try:
                datetime.strptime(completed_date, "%Y-%m-%d")
                pending[completed_date] = max(0.0, float(completed_total))
            except (TypeError, ValueError):
                continue
        return pending

    @staticmethod
    def _load_tariff_history(raw_history):
        if not isinstance(raw_history, dict):
            return {}
        history = {}
        for completed_date, record in raw_history.items():
            try:
                datetime.strptime(completed_date, "%Y-%m-%d")
            except (TypeError, ValueError):
                continue
            if isinstance(record, dict):
                history[completed_date] = record
        return history

    @staticmethod
    def _valid_number(value):
        if value is None:
            return False
        try:
            numeric = float(value)
            return numeric == numeric and numeric not in (float("inf"), float("-inf"))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _nonnegative(value):
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _optional_nonnegative(value):
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_float(value):
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _mqtt_optional(value):
        return "unknown" if value is None else round(value, 3)
