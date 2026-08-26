import json
import math
from datetime import datetime
from pathlib import Path

from app.utils.json_store import atomic_write_json
from app.utils.logger import log


SOC_ANOMALY_JOURNAL_FILE = Path("/data/soc_anomaly_journal.json")
SOC_ANOMALY_THRESHOLD_PERCENT = 5.0
SOC_ANOMALY_MAX_INTERVAL_SECONDS = 5 * 60
SOC_ANOMALY_HISTORY_LIMIT = 100
SOC_BASELINE_SAVE_INTERVAL_SECONDS = 60


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rounded(value, digits=2):
    number = _number(value)
    return None if number is None else round(number, digits)


class SocAnomalyJournal:
    """Bounded, read-only evidence journal for suspicious SOC steps."""

    def __init__(self, path=SOC_ANOMALY_JOURNAL_FILE, clock=None):
        self.path = Path(path) if path else None
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.started_at = self.clock()
        self.events = []
        self.total_event_count = 0
        self.last_sample = None
        self.last_saved_at = None
        self.first_valid_observation = True
        self._load()

    def _load(self):
        if not self.path or not self.path.exists():
            return

        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as error:
            log(f"Failed to load SOC anomaly journal: {error}")
            return

        if not isinstance(data, dict):
            log("Failed to load SOC anomaly journal: JSON object required")
            return

        events = data.get("events", [])
        if isinstance(events, list):
            self.events = events[-SOC_ANOMALY_HISTORY_LIMIT:]

        try:
            total_event_count = int(
                data.get("total_event_count", len(self.events))
            )
        except (TypeError, ValueError):
            total_event_count = len(self.events)
            log(
                "SOC anomaly journal has an invalid total event count; "
                "retained history was preserved"
            )
        self.total_event_count = max(
            len(self.events),
            total_event_count,
        )

        sample = data.get("last_sample")
        if isinstance(sample, dict):
            try:
                timestamp = datetime.fromisoformat(sample["timestamp"])
                soc = _number(sample.get("soc"))
                if soc is not None and 0 <= soc <= 100:
                    self.last_sample = {
                        "timestamp": timestamp.isoformat(),
                        "soc": soc,
                    }
            except (KeyError, TypeError, ValueError):
                log(
                    "SOC anomaly journal has an invalid last sample; "
                    "retained event history was preserved"
                )

        saved_at = data.get("saved_at")
        if saved_at:
            try:
                self.last_saved_at = datetime.fromisoformat(saved_at)
            except (TypeError, ValueError):
                log(
                    "SOC anomaly journal has an invalid saved_at value; "
                    "retained event history was preserved"
                )

        log(
            "SOC anomaly journal loaded: "
            f"{len(self.events)} retained events, "
            f"{self.total_event_count} total"
        )

    def _save(self, now):
        if not self.path:
            return

        try:
            atomic_write_json(
                self.path,
                {
                    "schema_version": 1,
                    "saved_at": now.isoformat(),
                    "total_event_count": self.total_event_count,
                    "history_limit": SOC_ANOMALY_HISTORY_LIMIT,
                    "last_sample": self.last_sample,
                    "events": self.events,
                },
                ensure_ascii=False,
                indent=2,
            )
            self.last_saved_at = now
        except Exception as error:
            # The journal is diagnostic only. Persistence failure must never
            # propagate into telemetry acceptance or inverter control.
            log(f"Failed to save SOC anomaly journal: {error}")

    def observe(
        self,
        *,
        valid,
        soc,
        battery_voltage=None,
        charging_current=None,
        discharging_current=None,
        pv1_power=None,
        pv2_power=None,
        total_pv_power=None,
        house_load=None,
        grid_available=None,
        grid_voltage=None,
        operating_mode=None,
        telemetry_freshness=None,
        communication_recovered=False,
    ):
        if not valid:
            return False

        current_soc = _number(soc)
        if current_soc is None or not 0 <= current_soc <= 100:
            return False

        now = self.clock()
        previous = self.last_sample
        energyhub_restarted = self.first_valid_observation
        self.first_valid_observation = False
        event_created = False

        if previous is not None:
            try:
                previous_time = datetime.fromisoformat(previous["timestamp"])
                elapsed_seconds = (now - previous_time).total_seconds()
            except (KeyError, TypeError, ValueError):
                elapsed_seconds = None

            previous_soc = _number(previous.get("soc"))
            if previous_soc is not None and elapsed_seconds is not None:
                delta = current_soc - previous_soc
                if (
                    0 < elapsed_seconds <= SOC_ANOMALY_MAX_INTERVAL_SECONDS
                    and abs(delta) >= SOC_ANOMALY_THRESHOLD_PERCENT
                ):
                    event = {
                        "timestamp": now.isoformat(),
                        "previous_timestamp": previous["timestamp"],
                        "previous_soc": round(previous_soc, 2),
                        "current_soc": round(current_soc, 2),
                        "delta_percent": round(delta, 2),
                        "elapsed_seconds": round(elapsed_seconds, 1),
                        "battery_voltage_v": _rounded(battery_voltage),
                        "charging_current_a": _rounded(charging_current),
                        "discharging_current_a": _rounded(
                            discharging_current
                        ),
                        "pv1_power_w": _rounded(pv1_power, 1),
                        "pv2_power_w": _rounded(pv2_power, 1),
                        "total_pv_power_w": _rounded(
                            total_pv_power,
                            1,
                        ),
                        "house_load_w": _rounded(house_load, 1),
                        "grid_available": (
                            bool(grid_available)
                            if grid_available is not None
                            else None
                        ),
                        "grid_voltage_v": _rounded(grid_voltage),
                        "operating_mode": str(
                            operating_mode or "unknown"
                        ),
                        "telemetry_freshness": str(
                            telemetry_freshness or "unknown"
                        ),
                        "energyhub_restarted": energyhub_restarted,
                        "energyhub_started_at": self.started_at.isoformat(),
                        "energyhub_uptime_seconds": round(
                            max(
                                0,
                                (now - self.started_at).total_seconds(),
                            ),
                            1,
                        ),
                        "communication_recovered": bool(
                            communication_recovered
                        ),
                        "soc_region": (
                            "top_of_charge"
                            if max(previous_soc, current_soc) > 95
                            else "low_soc"
                            if min(previous_soc, current_soc) < 15
                            else "mid_range"
                        ),
                        "trigger": (
                            f"absolute SOC delta >= "
                            f"{SOC_ANOMALY_THRESHOLD_PERCENT:g}% within "
                            f"{SOC_ANOMALY_MAX_INTERVAL_SECONDS:g}s"
                        ),
                    }
                    self.events.append(event)
                    self.events = self.events[-SOC_ANOMALY_HISTORY_LIMIT:]
                    self.total_event_count += 1
                    event_created = True
                    log(
                        "SOC anomaly recorded: "
                        f"{previous_soc:g}% -> {current_soc:g}% "
                        f"in {elapsed_seconds:.1f}s"
                    )

        self.last_sample = {
            "timestamp": now.isoformat(),
            "soc": current_soc,
        }

        seconds_since_save = (
            None
            if self.last_saved_at is None
            else (now - self.last_saved_at).total_seconds()
        )
        save_due = (
            seconds_since_save is None
            or seconds_since_save < 0
            or seconds_since_save >= SOC_BASELINE_SAVE_INTERVAL_SECONDS
        )
        if event_created or save_due:
            self._save(now)

        return event_created

    def mqtt_values(self):
        latest = self.events[-1] if self.events else None
        return {
            "soc_anomaly_event_count": self.total_event_count,
            "soc_anomaly_latest": (
                latest["timestamp"] if latest else "unknown"
            ),
        }

    def latest_attributes(self):
        latest = self.events[-1] if self.events else None
        return {
            "event_count": self.total_event_count,
            "retained_event_count": len(self.events),
            "history_limit": SOC_ANOMALY_HISTORY_LIMIT,
            "threshold_percent": SOC_ANOMALY_THRESHOLD_PERCENT,
            "max_interval_seconds": SOC_ANOMALY_MAX_INTERVAL_SECONDS,
            "latest_event": latest,
        }
