import json
import math
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.utils.json_store import atomic_write_json
from app.utils.logger import log


DAILY_SUMMARY_FILE = Path("/data/daily_summary.json")

REQUIRED_SNAPSHOT_INPUTS = (
    "daily_house_consumption",
    "solar_forecast_today",
    "daily_solar_surplus_estimated",
)


class DailySummaryService:
    def __init__(self, grid_history, grid_import, timezone_name="Europe/Kyiv"):
        self.grid_history = grid_history
        self.grid_import = grid_import
        self.timezone = ZoneInfo(timezone_name)
        self.inputs = {}
        self.last_snapshot = None
        self.history = {}
        self.load()

    def load(self):
        if not DAILY_SUMMARY_FILE.exists():
            return

        try:
            data = json.loads(
                DAILY_SUMMARY_FILE.read_text()
            )
            self.history = data.get("history", {})
            self.last_snapshot = data.get("last_snapshot")

            log(
                "Daily summary loaded: "
                f"{len(self.history)} days"
            )

        except Exception as e:
            log(
                "Failed to load daily summary: "
                f"{e}"
            )

    def save(self):
        data = {
            "last_snapshot": self.last_snapshot,
            "history": self.history,
        }

        try:
            atomic_write_json(
                DAILY_SUMMARY_FILE,
                data,
                ensure_ascii=False,
                indent=2,
            )

        except Exception as e:
            log(
                "Failed to save daily summary: "
                f"{e}"
            )

    def update_input(self, key, value):
        numeric_value = self._numeric_value(value)

        if numeric_value is None:
            log(
                "Daily summary ignored invalid input "
                f"{key}: {value}"
            )
            return False

        self.inputs[key] = numeric_value

        log(
            "Daily summary input updated: "
            f"{key}={numeric_value}"
        )

        # Input updates are intentionally not snapshots. Home Assistant
        # publishes the inputs one MQTT message at a time, so snapshotting
        # here could combine values from different publication cycles.
        return True

    def update_snapshot(self, payload):
        try:
            data = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            log(
                "Daily summary ignored invalid snapshot payload: "
                f"{e}"
            )
            return False

        if not isinstance(data, dict):
            log(
                "Daily summary ignored snapshot payload: "
                "JSON object required"
            )
            return False

        snapshot_date = str(data.get("date", "")).strip()

        try:
            datetime.strptime(snapshot_date, "%Y-%m-%d")
        except ValueError:
            log(
                "Daily summary ignored snapshot with invalid date: "
                f"{snapshot_date}"
            )
            return False

        today = datetime.now().strftime("%Y-%m-%d")

        if snapshot_date != today:
            log(
                "Daily summary ignored stale snapshot: "
                f"date={snapshot_date}, today={today}"
            )
            return False

        source_timestamp = data.get("timestamp")

        if source_timestamp in (None, ""):
            log(
                "Daily summary ignored snapshot without timestamp"
            )
            return False

        snapshot_inputs = {}

        for key in REQUIRED_SNAPSHOT_INPUTS:
            numeric_value = self._numeric_value(data.get(key))

            if numeric_value is None:
                log(
                    "Daily summary ignored incomplete snapshot: "
                    f"invalid {key}={data.get(key)}"
                )
                return False

            snapshot_inputs[key] = numeric_value

        forecast_tomorrow = self._numeric_value(
            data.get("solar_forecast_tomorrow")
        )
        solar_actual_today = self._numeric_value(
            data.get("solar_actual_today")
        )
        battery_full_today = data.get("battery_full_today")

        self.inputs.update(snapshot_inputs)

        if forecast_tomorrow is not None:
            self.inputs[
                "solar_forecast_tomorrow"
            ] = forecast_tomorrow

        snapshot_inputs["solar_actual_today"] = solar_actual_today
        snapshot_inputs["battery_full_today"] = (
            battery_full_today is True
        )

        return self.snapshot(
            snapshot_date=snapshot_date,
            snapshot_inputs=snapshot_inputs,
            source_timestamp=str(source_timestamp),
        )

    def ready(self, inputs=None):
        values = self.inputs if inputs is None else inputs

        return all(
            key in values
            for key in REQUIRED_SNAPSHOT_INPUTS
        )

    def snapshot(
        self,
        *,
        snapshot_date=None,
        snapshot_inputs=None,
        source_timestamp=None,
    ):
        values = (
            self.inputs
            if snapshot_inputs is None
            else snapshot_inputs
        )

        if not self.ready(values):
            missing = [
                key
                for key in REQUIRED_SNAPSHOT_INPUTS
                if key not in values
            ]

            log(
                "Daily summary snapshot skipped: "
                f"missing inputs={','.join(missing)}"
            )
            return False

        today = datetime.now().strftime("%Y-%m-%d")
        snapshot_date = snapshot_date or today

        if snapshot_date != today:
            log(
                "Daily summary snapshot skipped: "
                f"date={snapshot_date}, today={today}"
            )
            return False

        existing = self.history.get(snapshot_date)

        if (
            existing
            and source_timestamp is not None
            and existing.get("source_timestamp")
            == source_timestamp
        ):
            self.last_snapshot = existing

            log(
                "Daily summary snapshot already processed "
                f"for {snapshot_date}"
            )
            return True

        snapshot = {
            "date": snapshot_date,
            "timestamp": int(time.time()),
            "source_timestamp": source_timestamp,
            "house_consumption_kwh": (
                values["daily_house_consumption"]
            ),
            "solar_forecast_kwh": (
                values["solar_forecast_today"]
            ),
            "solar_surplus_estimated_kwh": (
                values[
                    "daily_solar_surplus_estimated"
                ]
            ),
            "solar_actual_kwh": values.get("solar_actual_today"),
            "battery_full": bool(values.get("battery_full_today", False)),
            "grid_import_estimated_kwh": round(
                self.grid_import.daily_energy_kwh,
                3,
            ),
            "grid_availability_24h_percent": (
                self.grid_history
                .availability_percent(24)
            ),
        }

        if existing:
            same_values = (
                existing.get("house_consumption_kwh")
                == snapshot["house_consumption_kwh"]
                and existing.get("solar_forecast_kwh")
                == snapshot["solar_forecast_kwh"]
                and existing.get(
                    "solar_surplus_estimated_kwh"
                )
                == snapshot[
                    "solar_surplus_estimated_kwh"
                ]
                and existing.get(
                    "grid_import_estimated_kwh"
                )
                == snapshot[
                    "grid_import_estimated_kwh"
                ]
                and existing.get("solar_actual_kwh")
                == snapshot["solar_actual_kwh"]
                and bool(existing.get("battery_full", False))
                == snapshot["battery_full"]
            )

            if same_values:
                self.last_snapshot = existing

                log(
                    "Daily summary snapshot unchanged "
                    f"for {snapshot_date}"
                )
                return True

        self.history[snapshot_date] = snapshot
        self.last_snapshot = snapshot
        self.save()

        log(
            "Daily summary atomic snapshot stored "
            f"for {snapshot_date}"
        )
        return True

    def mqtt_values(self):
        if not self.last_snapshot:
            return {}

        return {
            "daily_house_consumption": (
                self.last_snapshot[
                    "house_consumption_kwh"
                ]
            ),
            "daily_solar_forecast": (
                self.last_snapshot[
                    "solar_forecast_kwh"
                ]
            ),
            "daily_solar_surplus_estimated": (
                self.last_snapshot[
                    "solar_surplus_estimated_kwh"
                ]
            ),
            "daily_solar_actual": self._mqtt_optional(
                self.last_snapshot.get("solar_actual_kwh")
            ),
            "daily_solar_forecast_error_percent": (
                self._forecast_error_percent(self.last_snapshot)
            ),
            "daily_battery_reached_full": (
                "on" if self.last_snapshot.get("battery_full") else "off"
            ),
            "daily_grid_availability": (
                self.last_snapshot[
                    "grid_availability_24h_percent"
                ]
            ),
        }

    def recent_consumption(self, before_date, limit=3, require_final=False):
        """Return the newest valid completed daily-consumption samples.

        Zero and non-finite values are excluded because they represent the
        incomplete/unavailable snapshots seen in live Home Assistant evidence.
        The current day is never used in its own 05:00 reserve evaluation.
        """
        try:
            boundary = (
                before_date
                if isinstance(before_date, date)
                else date.fromisoformat(str(before_date))
            )
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            return []

        samples = []
        for day, snapshot in sorted(self.history.items(), reverse=True):
            try:
                sample_date = date.fromisoformat(str(day))
            except (TypeError, ValueError):
                continue
            if sample_date >= boundary or not isinstance(snapshot, dict):
                continue
            if (boundary - sample_date).days > 7:
                continue
            if require_final:
                try:
                    source_timestamp = snapshot.get("source_timestamp")
                    try:
                        captured = datetime.fromtimestamp(
                            float(source_timestamp),
                            tz=getattr(self, "timezone", ZoneInfo("Europe/Kyiv")),
                        )
                    except (TypeError, ValueError, OverflowError):
                        captured = datetime.fromisoformat(str(source_timestamp))
                        if captured.tzinfo is not None:
                            captured = captured.astimezone(
                                getattr(self, "timezone", ZoneInfo("Europe/Kyiv"))
                            )
                    if captured.date() != sample_date or (captured.hour, captured.minute) < (23, 50):
                        continue
                except (TypeError, ValueError, OverflowError):
                    continue
            value = self._numeric_value(snapshot.get("house_consumption_kwh"))
            if value is None or value <= 0:
                continue
            sample = {"date": sample_date.isoformat(), "kwh": value}
            if require_final:
                sample["complete"] = True
            samples.append(sample)
            if len(samples) >= limit:
                break
        return samples

    def finalize_grid_import(
        self,
        summary_date,
        final_energy_kwh,
    ):
        try:
            datetime.strptime(summary_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            log(
                "Daily summary ignored Grid Import finalization "
                f"with invalid date: {summary_date}"
            )
            return "invalid"

        try:
            final_energy_kwh = float(final_energy_kwh)
        except (TypeError, ValueError):
            final_energy_kwh = float("nan")

        if (
            not math.isfinite(final_energy_kwh)
            or final_energy_kwh < 0
        ):
            log(
                "Daily summary ignored Grid Import finalization "
                f"with invalid value: {final_energy_kwh}"
            )
            return "invalid"

        existing = self.history.get(summary_date)

        if not existing:
            log(
                "Daily summary cannot reconcile finalized Grid Import: "
                f"no snapshot for {summary_date}; "
                f"final value={final_energy_kwh:.3f} kWh remains "
                "available in Grid Import history"
            )
            return "missing"

        final_energy_kwh = round(final_energy_kwh, 3)

        try:
            existing_energy_kwh = round(
                float(
                    existing.get(
                        "grid_import_estimated_kwh",
                        0.0,
                    )
                ),
                3,
            )
        except (TypeError, ValueError):
            existing_energy_kwh = None

        if existing_energy_kwh == final_energy_kwh:
            if (
                self.last_snapshot
                and self.last_snapshot.get("date")
                == summary_date
            ):
                self.last_snapshot = existing

            log(
                "Daily summary Grid Import already finalized: "
                f"{summary_date}={final_energy_kwh:.3f} kWh"
            )
            return "unchanged"

        updated = dict(existing)
        updated["grid_import_estimated_kwh"] = final_energy_kwh
        updated["grid_import_finalized_at"] = int(time.time())

        self.history[summary_date] = updated

        if (
            self.last_snapshot
            and self.last_snapshot.get("date") == summary_date
        ):
            self.last_snapshot = updated

        self.save()

        log(
            "Daily summary Grid Import finalized: "
            f"{summary_date} "
            f"{existing_energy_kwh} -> {final_energy_kwh:.3f} kWh"
        )
        return "updated"

    @staticmethod
    def _numeric_value(value):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(numeric_value):
            return None

        return round(numeric_value, 2)

    @staticmethod
    def _mqtt_optional(value):
        return "unknown" if value is None else value

    @classmethod
    def _forecast_error_percent(cls, snapshot):
        if snapshot.get("battery_full"):
            return "unknown"
        actual = cls._numeric_value(snapshot.get("solar_actual_kwh"))
        forecast = cls._numeric_value(snapshot.get("solar_forecast_kwh"))
        if actual is None or forecast is None or forecast <= 0:
            return "unknown"
        return round((actual - forecast) / forecast * 100, 1)
