import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from app.utils.logger import log


MORNING_LOAD_FILE = Path("/data/morning_load_profile.json")


class MorningLoadProfileService:
    """Learn essential 07:00-12:00 load after removing heat pumps."""

    START_HOUR = 7
    END_HOUR = 12
    RETENTION_DAYS = 21
    MINIMUM_SAMPLES = 3
    PERCENTILE = 0.75

    def __init__(self, path=None):
        self.path = Path(path) if path else MORNING_LOAD_FILE
        self.snapshots = {}
        self.samples = {}
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.snapshots = dict(data.get("snapshots", {}))
            self.samples = dict(data.get("samples", {}))
            log(
                "Morning load profile loaded: "
                f"{sum(len(values) for values in self.samples.values())} "
                "hourly samples"
            )
        except (OSError, ValueError, TypeError) as exc:
            log(f"Failed to load morning load profile: {exc}")
            self.snapshots = {}
            self.samples = {}

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "snapshots": self.snapshots,
                        "samples": self.samples,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            log(f"Failed to save morning load profile: {exc}")

    def record_snapshot(self, payload):
        try:
            captured_at = datetime.fromisoformat(
                str(payload["captured_at"])
            )
            date_key = str(payload.get("date") or captured_at.date())
            hour = int(payload.get("hour", captured_at.hour))
            house_kwh = float(payload["house_kwh"])
            heat_pump_kwh = float(payload["heat_pump_kwh"])
        except (KeyError, TypeError, ValueError):
            return {
                "accepted": False,
                "reason": "invalid snapshot payload",
            }

        if not self.START_HOUR <= hour <= self.END_HOUR:
            return {
                "accepted": False,
                "reason": "outside 07:00-12:00 learning window",
            }
        if (
            not math.isfinite(house_kwh)
            or not math.isfinite(heat_pump_kwh)
        ):
            return {
                "accepted": False,
                "reason": "non-finite cumulative energy",
            }
        if house_kwh < 0 or heat_pump_kwh < 0:
            return {
                "accepted": False,
                "reason": "negative cumulative energy",
            }

        key = f"{date_key}:{hour:02d}"
        snapshot = {
            "date": date_key,
            "hour": hour,
            "captured_at": captured_at.isoformat(),
            "house_kwh": round(house_kwh, 4),
            "heat_pump_kwh": round(heat_pump_kwh, 4),
        }
        self.snapshots[key] = snapshot

        sample = None
        if hour > self.START_HOUR:
            previous = self.snapshots.get(
                f"{date_key}:{hour - 1:02d}"
            )
            if previous is not None:
                house_delta = house_kwh - float(previous["house_kwh"])
                heat_delta = (
                    heat_pump_kwh
                    - float(previous["heat_pump_kwh"])
                )
                if house_delta >= 0 and heat_delta >= 0:
                    essential_kwh = max(0.0, house_delta - heat_delta)
                    interval_hour = hour - 1
                    sample = round(essential_kwh, 4)
                    self.samples.setdefault(
                        str(interval_hour), {}
                    )[date_key] = sample

        self._prune(captured_at.date())
        self.save()
        return {
            "accepted": True,
            "sample_kwh": sample,
            "sample_hour": hour - 1 if sample is not None else None,
        }

    def profile(self):
        result = {}
        for hour in range(self.START_HOUR, self.END_HOUR):
            values = [
                float(value)
                for value in self.samples.get(str(hour), {}).values()
                if self._valid_number(value)
            ]
            values.sort()
            if values:
                rank = max(1, math.ceil(len(values) * self.PERCENTILE))
                expected = values[rank - 1]
            else:
                expected = None
            result[hour] = {
                "expected_kwh": (
                    round(expected, 4)
                    if expected is not None
                    else None
                ),
                "sample_count": len(values),
            }
        return result

    def flexible_plan(self, hourly_solar):
        profile = self.profile()
        minimum_count = min(
            item["sample_count"] for item in profile.values()
        )
        if minimum_count < self.MINIMUM_SAMPLES:
            return self._unavailable(
                f"learning {minimum_count}/{self.MINIMUM_SAMPLES} samples",
                minimum_count,
            )

        solar = {}
        try:
            for item in hourly_solar or []:
                hour = int(item["hour"])
                if self.START_HOUR <= hour < self.END_HOUR:
                    solar[hour] = max(
                        0.0,
                        float(item["power_w"]) / 1000.0,
                    )
        except (KeyError, TypeError, ValueError):
            return self._unavailable(
                "invalid hourly solar forecast",
                minimum_count,
            )

        required = set(range(self.START_HOUR, self.END_HOUR))
        if set(solar) != required:
            return self._unavailable(
                "incomplete 07:00-12:00 solar forecast",
                minimum_count,
            )

        support_hour = None
        for hour in range(self.START_HOUR, self.END_HOUR - 1):
            current_load = profile[hour]["expected_kwh"]
            next_load = profile[hour + 1]["expected_kwh"]
            if (
                solar[hour] >= current_load
                and solar[hour + 1] >= next_load
            ):
                support_hour = hour
                break

        final_hour = (
            min(self.END_HOUR - 1, support_hour + 1)
            if support_hour is not None
            else self.END_HOUR - 1
        )
        considered = range(self.START_HOUR, final_hour + 1)
        expected_kwh = sum(
            profile[hour]["expected_kwh"] for hour in considered
        )
        solar_kwh = sum(solar[hour] for hour in considered)
        deficit_kwh = sum(
            max(
                0.0,
                profile[hour]["expected_kwh"] - solar[hour],
            )
            for hour in considered
        )

        return {
            "available": True,
            "source": "learned_net_energy",
            "reason": "learned essential load and complete solar forecast",
            "sample_count": minimum_count,
            "expected_load_kwh": round(expected_kwh, 3),
            "forecast_solar_kwh": round(solar_kwh, 3),
            "deficit_kwh": round(deficit_kwh, 3),
            "support_time": (
                f"{support_hour:02d}:00"
                if support_hour is not None
                else "not confirmed by 12:00"
            ),
            "profile": profile,
        }

    def _unavailable(self, reason, sample_count):
        return {
            "available": False,
            "source": "verified_ramp_fallback",
            "reason": reason,
            "sample_count": sample_count,
            "expected_load_kwh": None,
            "forecast_solar_kwh": None,
            "deficit_kwh": None,
            "support_time": None,
            "profile": self.profile(),
        }

    def _prune(self, today):
        cutoff = (today - timedelta(days=self.RETENTION_DAYS)).isoformat()
        self.snapshots = {
            key: value
            for key, value in self.snapshots.items()
            if str(value.get("date", "")) >= cutoff
        }
        for hour in list(self.samples):
            self.samples[hour] = {
                date_key: value
                for date_key, value in self.samples[hour].items()
                if date_key >= cutoff
            }

    @staticmethod
    def _valid_number(value):
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
