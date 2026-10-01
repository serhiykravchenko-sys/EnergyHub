from __future__ import annotations

import json
import math
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import WEATHER_BUFFER_FILE
from app.utils.json_store import atomic_write_json
from app.utils.logger import log


FORECAST_DEFICIT_PERCENT = 20.0
WEATHER_RISK_PERCENT = 20.0
SMART_HEATING_PERCENT = 20.0
MAX_RECOMMENDED_SOC = 95.0
POLICY_BASE_SOC = 20.0
SOURCE_MAX_AGE_SECONDS = 30 * 60
WEATHER_SOURCE_MAX_AGE_SECONDS = 75 * 60
SAMPLE_MAX_AGE_DAYS = 7
GRID_MODIFIERS = {
    "normal": 0.0,
    "unstable": 20.0,
    "risk": 40.0,
    "panic": 60.0,
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_datetime(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return result if result.tzinfo is not None else None


class WeatherBufferDryRun:
    """Persisted Battery Reserve recommendation and authority state.

    The historical class and MQTT names remain for compatibility. The policy
    combines up to three completed consumption days, forecast deficit, Grid
    Confidence and normalized official UHMC warnings. Home Assistant owns the
    guarded application path when Automatic authority is selected.
    """

    def __init__(
        self,
        path: Path | None = WEATHER_BUFFER_FILE,
        timezone_name: str = "Europe/Kyiv",
        clock=None,
    ):
        self.path = path
        self.timezone = ZoneInfo(timezone_name)
        self.clock = clock or (lambda: datetime.now(self.timezone))
        self.lock = threading.RLock()
        self.daily_input: dict[str, Any] | None = None
        self.weather_snapshot: dict[str, Any] | None = None
        self.grid_confidence = "unknown"
        self.grid_observed_at: datetime | None = None
        self.decision: dict[str, Any] | None = None
        self._load()

    def update(
        self,
        payload: str | dict[str, Any],
        consumption_samples: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Compatibility entry point for the daily reserve evaluation."""
        return self.update_daily(payload, consumption_samples or [])

    def update_daily(
        self,
        payload: str | dict[str, Any],
        consumption_samples: list[dict[str, Any]],
    ) -> bool:
        try:
            document = json.loads(payload) if isinstance(payload, str) else payload
            evaluation_date = date.fromisoformat(str(document["date"]))
            observed_at = _parse_datetime(document["observed_at"])
            baseline = POLICY_BASE_SOC
            solar_forecast = _number(document.get("solar_forecast_kwh"))
            applied_minimum = _number(document.get("applied_minimum_soc", document.get("baseline_soc")))
            smart_heating_enabled = document.get("smart_heating_enabled", False)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return False
        if observed_at is None or baseline is None or not 0 <= baseline <= 95:
            return False
        if applied_minimum is None or not 20 <= applied_minimum <= 95 or applied_minimum % 5:
            return False
        if type(smart_heating_enabled) is not bool:
            return False
        now = self.clock().astimezone(self.timezone)
        requested_stage = str(document.get("forecast_plan_stage") or "refresh").strip().lower()
        if requested_stage not in {"preliminary", "morning", "refresh"}:
            return False
        preliminary_window = (
            requested_stage in {"preliminary", "refresh"}
            and evaluation_date == now.date() + timedelta(days=1)
            and now.time() >= time(23, 50)
        )
        current_day_window = evaluation_date == now.date()
        if ((not preliminary_window and not current_day_window)
                or (requested_stage == "morning" and now.time() < time(5, 0))
                or not -5 <= (now - observed_at).total_seconds() <= SOURCE_MAX_AGE_SECONDS):
            return False
        if solar_forecast is not None and solar_forecast < 0:
            solar_forecast = None

        mode_text = str(document.get("mode") or "Manual").strip().lower()
        mode_text = mode_text.replace("/", " ").replace("-", " ").replace("_", " ")
        mode = ("automatic" if "automatic" in mode_text or mode_text == "auto"
                else "dry_run" if "dry" in mode_text or "advisory" in mode_text
                else "manual")

        valid_samples = []
        for sample in consumption_samples:
            if not isinstance(sample, dict):
                continue
            value = _number(sample.get("kwh"))
            try:
                sample_date = date.fromisoformat(str(sample.get("date")))
            except (TypeError, ValueError):
                continue
            if (value is None or value <= 0 or sample_date >= evaluation_date
                    or sample_date < evaluation_date - timedelta(days=SAMPLE_MAX_AGE_DAYS)
                    or sample.get("complete") is False):
                continue
            valid_samples.append({"date": sample_date.isoformat(), "kwh": round(value, 2)})
        valid_samples = sorted(valid_samples, key=lambda item: item["date"], reverse=True)[:3]

        with self.lock:
            previous_daily = self.daily_input or {}
            same_day = previous_daily.get("date") == evaluation_date.isoformat()
            captured_at = previous_daily.get("forecast_captured_at") if same_day else None
            stored_stage = previous_daily.get("forecast_plan_stage") if same_day else None
            revision_status = "captured" if solar_forecast is not None else "unavailable"

            if requested_stage == "morning" and solar_forecast is None and captured_at:
                # The safe preliminary allowance remains in force when the
                # morning refresh is unavailable; it is never added twice.
                solar_forecast = previous_daily.get("solar_forecast_kwh")
                valid_samples = previous_daily.get("consumption_samples") or valid_samples
                revision_status = "morning_unavailable_preliminary_retained"
                stored_stage = stored_stage or "preliminary"
            elif requested_stage == "morning" and solar_forecast is not None:
                captured_at = now.isoformat()
                stored_stage = "morning"
                revision_status = "morning_captured"
            elif requested_stage == "preliminary":
                captured_at = now.isoformat() if solar_forecast is not None else None
                stored_stage = "preliminary"
                revision_status = "preliminary_captured" if solar_forecast is not None else "preliminary_unavailable"
            elif captured_at:
                # Settings and intraday forecast changes update authority and
                # the applied value without replacing the dated forecast.
                solar_forecast = previous_daily.get("solar_forecast_kwh")
                valid_samples = previous_daily.get("consumption_samples") or valid_samples
                stored_stage = stored_stage or "morning"
                revision_status = previous_daily.get("forecast_revision_status") or "captured"
            elif solar_forecast is not None:
                # Recovery when no 23:52 preliminary plan exists. Before 05:00
                # it is preliminary; at/after 05:00 it is the morning plan.
                captured_at = now.isoformat()
                stored_stage = "preliminary" if now.time() < time(5, 0) else "morning"
                revision_status = f"{stored_stage}_recovery_captured"
            self.daily_input = {
                "date": evaluation_date.isoformat(),
                "observed_at": observed_at.astimezone(self.timezone).isoformat(),
                "mode": mode,
                "baseline_soc": round(baseline, 1),
                "applied_minimum_soc": applied_minimum,
                "smart_heating_enabled": smart_heating_enabled,
                "forecast_captured_at": captured_at,
                "forecast_plan_stage": stored_stage,
                "forecast_revision_status": revision_status,
                "solar_forecast_kwh": None if solar_forecast is None else round(solar_forecast, 2),
                "consumption_samples": valid_samples,
                "source_entity": str(document.get("source_entity") or ""),
            }
            self._evaluate(now)
            self._save()
        return True

    def update_weather(self, payload: str | dict[str, Any]) -> bool:
        try:
            document = json.loads(payload) if isinstance(payload, str) else payload
            observed_at = _parse_datetime(document["observed_at"])
            source_status = str(document["source_status"]).strip().lower()
            warnings = document.get("warnings")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return False
        if observed_at is None or source_status not in {"fresh", "unknown"}:
            return False
        if not isinstance(warnings, list):
            return False
        now = self.clock().astimezone(self.timezone)
        if not -5 <= (now - observed_at).total_seconds() <= WEATHER_SOURCE_MAX_AGE_SECONDS:
            return False

        normalized = []
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            event_id = str(warning.get("event_id") or "").strip()
            published_at = _parse_datetime(warning.get("published_at"))
            valid_from = _parse_datetime(warning.get("valid_from"))
            valid_until = _parse_datetime(warning.get("valid_until"))
            severity = _number(warning.get("severity"))
            hazards = warning.get("hazards")
            if (
                not event_id
                or published_at is None
                or valid_from is None
                or valid_until is None
                or severity is None
                or severity not in {1, 2, 3}
                or not isinstance(hazards, list)
                or valid_until < valid_from
            ):
                continue
            normalized.append({
                "event_id": event_id,
                "published_at": published_at.astimezone(self.timezone).isoformat(),
                "valid_from": valid_from.astimezone(self.timezone).isoformat(),
                "valid_until": valid_until.astimezone(self.timezone).isoformat(),
                "severity": int(severity),
                "severity_color": str(warning.get("severity_color") or ""),
                "region": str(warning.get("region") or "Kyiv/Kyiv region"),
                "region_match": bool(warning.get("region_match")),
                "grid_relevant": bool(warning.get("grid_relevant")),
                "hazards": sorted({str(item) for item in hazards if str(item)}),
                "summary": str(warning.get("summary") or "")[:500],
                "url": str(warning.get("url") or ""),
            })
        normalized.sort(key=lambda item: item["published_at"])
        if len(normalized) != len(warnings):
            source_status = "unknown"

        with self.lock:
            previous = self.weather_snapshot or {}
            if source_status == "unknown":
                combined = {item["event_id"]: item for item in previous.get("warnings") or []}
                combined.update({item["event_id"]: item for item in normalized})
                normalized = sorted(combined.values(), key=lambda item: item["published_at"])
            self.weather_snapshot = {
                "observed_at": observed_at.astimezone(self.timezone).isoformat(),
                "source_status": source_status,
                "source": str(document.get("source") or "uhmc1921"),
                "warnings": normalized[-20:],
            }
            self._evaluate(now)
            self._save()
        return True

    def update_grid_confidence(self, value: Any, observed_at: datetime | None = None) -> bool:
        normalized = str(value or "").strip().lower()
        if normalized not in GRID_MODIFIERS:
            return False
        with self.lock:
            changed = normalized != self.grid_confidence
            self.grid_confidence = normalized
            self.grid_observed_at = observed_at or self.clock()
            if changed:
                self._evaluate(observed_at or self.clock())
                self._save()
            return changed

    def refresh(self, observed_at: datetime | None = None) -> bool:
        with self.lock:
            previous = dict(self.decision or {})
            before_document = dict(previous)
            before_document.pop("evaluated_at", None)
            before_document.pop("control_evidence_at", None)
            before = json.dumps(before_document, sort_keys=True)
            self._evaluate(observed_at or self.clock())
            after_document = dict(self.decision or {})
            after_document.pop("evaluated_at", None)
            after_document.pop("control_evidence_at", None)
            after = json.dumps(after_document, sort_keys=True)
            if before != after:
                self._save()
                return True
            if self.decision is not None and previous.get("evaluated_at"):
                self.decision["evaluated_at"] = previous["evaluated_at"]
            return False

    def _evaluate(self, now: datetime) -> None:
        now = now.astimezone(self.timezone)
        previous = self.decision or {}
        daily = self.daily_input
        if not daily:
            return

        baseline = POLICY_BASE_SOC
        samples = list(daily.get("consumption_samples") or [])
        average = (
            round(sum(float(item["kwh"]) for item in samples) / len(samples), 2)
            if samples
            else None
        )
        solar_forecast = _number(daily.get("solar_forecast_kwh"))
        try:
            plan_date = date.fromisoformat(str(daily.get("date")))
        except (TypeError, ValueError):
            plan_date = None
        daily_fresh = (
            plan_date == now.date()
            or (
                plan_date == now.date() + timedelta(days=1)
                and daily.get("forecast_plan_stage") == "preliminary"
                and now.time() >= time(23, 50)
            )
        )
        evidence_issues = []
        if not daily_fresh:
            evidence_issues.append("daily_plan_stale")
        if solar_forecast is None:
            evidence_issues.append("forecast_unknown")
        if not samples:
            evidence_issues.append("consumption_history_incomplete")
        forecast_deficit = (
            solar_forecast < average
            if daily_fresh and solar_forecast is not None and average is not None
            else None
        )
        mode = daily["mode"]
        grid_modifier = GRID_MODIFIERS.get(self.grid_confidence, 0.0)
        grid_fresh = (self.grid_observed_at is not None and
                      -5 <= (now - self.grid_observed_at).total_seconds() <= SOURCE_MAX_AGE_SECONDS)
        if not grid_fresh:
            evidence_issues.append("grid_confidence_unknown")
            grid_modifier = _number(previous.get("grid_modifier_percent")) or 0.0

        warning_events = self._warnings_for_date(
            plan_date or now.date(),
            now,
        )
        qualifying = [
            warning for warning in warning_events
            if warning["region_match"]
            and warning["grid_relevant"]
            and int(warning["severity"]) >= 2
        ]
        weather_modifier = (
            WEATHER_RISK_PERCENT
            if grid_fresh and self.grid_confidence in GRID_MODIFIERS and qualifying
            else 0.0
        )
        severe_forecast_deficit = (
            solar_forecast * 2 < average
            if daily_fresh and solar_forecast is not None and average is not None
            else None
        )
        generation_modifier = FORECAST_DEFICIT_PERCENT if forecast_deficit else 0.0
        smart_heating_enabled = daily.get("smart_heating_enabled") is True
        smart_heating_modifier = SMART_HEATING_PERCENT if smart_heating_enabled else 0.0
        snapshot = self.weather_snapshot or {}
        weather_at = _parse_datetime(snapshot.get("observed_at"))
        weather_fresh = (snapshot.get("source_status") == "fresh" and weather_at is not None
                         and -5 <= (now - weather_at).total_seconds() <= WEATHER_SOURCE_MAX_AGE_SECONDS)
        if not weather_fresh:
            evidence_issues.append("weather_source_unknown")
        # Unknown evidence never authorizes releasing an already advised buffer.
        if forecast_deficit is None:
            generation_modifier = _number(previous.get("generation_modifier_percent")) or 0.0
        if not weather_fresh or not grid_fresh:
            weather_modifier = max(weather_modifier, _number(previous.get("weather_modifier_percent")) or 0.0)

        recommended = min(
            MAX_RECOMMENDED_SOC,
            baseline + generation_modifier + grid_modifier + weather_modifier
            + smart_heating_modifier,
        )
        previous_recommended = _number(previous.get("recommended_soc"))
        evaluation_signature = json.dumps(
            {
                "date": daily["date"],
                "forecast_plan_stage": daily.get("forecast_plan_stage"),
                "mode": mode,
                "baseline": baseline,
                "solar": solar_forecast,
                "average": average,
                "grid": self.grid_confidence,
                "warning_ids": [item["event_id"] for item in warning_events],
                "recommended": recommended,
                "smart_heating": smart_heating_enabled,
            },
            sort_keys=True,
        )
        if mode == "manual":
            transition = "manual"
        elif previous.get("evaluation_signature") == evaluation_signature:
            transition = str(previous.get("transition") or "unchanged")
        elif previous_recommended is None:
            transition = "initial"
        elif recommended > previous_recommended:
            transition = "increase"
        elif recommended < previous_recommended:
            transition = "decrease"
        else:
            transition = "unchanged"

        reasons = []
        if generation_modifier:
            reasons.append("severe_forecast_deficit" if severe_forecast_deficit else "forecast_deficit")
        if grid_modifier:
            reasons.append(f"grid_{self.grid_confidence}")
        if weather_modifier:
            reasons.append("uhmc_weather_risk")
        if smart_heating_modifier:
            reasons.append("smart_heating")

        latest_event = warning_events[-1] if warning_events else None
        source_warnings = self._unexpired_warnings(now)
        automatic_enabled = mode == "automatic"
        automatic_available = automatic_enabled and not evidence_issues
        applied = _number(daily.get("applied_minimum_soc"))
        control_applied = (automatic_available and applied is not None
                           and abs(applied - recommended) < 0.01)
        previous_applied = _number(previous.get("applied_minimum_soc"))
        applied_change_confirmed = (control_applied and previous_applied is not None
                                    and abs(previous_applied - applied) >= 0.01)
        applied_change_id = (
            f"{daily['date']}:{previous_applied:g}:{applied:g}:{evaluation_signature}"
            if applied_change_confirmed else None
        )
        self.decision = {
            "schema_version": 2,
            "advice_only": not automatic_enabled,
            "reserve_owner": "energyhub" if automatic_enabled else "family",
            "policy_base_soc": POLICY_BASE_SOC,
            "date": daily["date"],
            "evaluated_at": now.isoformat(),
            "mode": mode,
            "management_mode": mode,
            "dry_run": mode == "dry_run",
            "baseline_soc": round(baseline, 1),
            "applied_minimum_soc": daily.get("applied_minimum_soc"),
            "automatic_control_enabled": automatic_enabled,
            "automatic_control_available": automatic_available,
            "control_evidence_at": now.isoformat() if automatic_available else None,
            "forecast_captured_at": daily.get("forecast_captured_at"),
            "forecast_plan_stage": daily.get("forecast_plan_stage"),
            "forecast_revision_status": daily.get("forecast_revision_status"),
            "daily_plan_fresh": daily_fresh,
            "evidence_issues": evidence_issues,
            "recommendation_status": "provisional" if evidence_issues else "ready",
            "solar_forecast_kwh": solar_forecast,
            "consumption_average_kwh": average,
            "consumption_sample_count": len(samples),
            "consumption_samples": samples,
            "forecast_deficit": forecast_deficit,
            "severe_forecast_deficit": severe_forecast_deficit,
            "generation_modifier_percent": generation_modifier,
            "grid_confidence": self.grid_confidence,
            "grid_confidence_fresh": grid_fresh,
            "grid_modifier_percent": grid_modifier,
            "weather_source_status": (
                "fresh" if weather_fresh else "unknown"
            ),
            "weather_modifier_percent": weather_modifier,
            "smart_heating_enabled": smart_heating_enabled,
            "smart_heating_modifier_percent": smart_heating_modifier,
            "qualifying_weather_warning_count": len(qualifying),
            "weather_warnings": warning_events,
            "weather_source_warnings": source_warnings,
            "latest_weather_event": latest_event,
            "recommended_soc": round(recommended, 1),
            "previous_recommended_soc": previous_recommended,
            "transition": transition,
            "evaluation_signature": evaluation_signature,
            "reason_codes": reasons,
            "cap_soc": MAX_RECOMMENDED_SOC,
            "control_applied": control_applied,
            "previous_applied_soc": previous_applied,
            "applied_change_confirmed": applied_change_confirmed,
            "applied_change_id": applied_change_id,
            "source_entity": daily.get("source_entity", ""),
        }

    def _warnings_for_date(
        self,
        evaluation_date: date,
        now: datetime,
    ) -> list[dict[str, Any]]:
        result = []
        day_start = datetime.combine(evaluation_date, time.min, self.timezone)
        day_end = datetime.combine(evaluation_date, time.max, self.timezone)
        for warning in (self.weather_snapshot or {}).get("warnings") or []:
            valid_from = _parse_datetime(warning.get("valid_from"))
            valid_until = _parse_datetime(warning.get("valid_until"))
            if valid_from is None or valid_until is None:
                continue
            if (
                valid_from.astimezone(self.timezone) <= day_end
                and valid_until.astimezone(self.timezone) >= day_start
                and valid_until.astimezone(self.timezone) >= now
            ):
                result.append(dict(warning))
        result.sort(key=lambda item: item["published_at"])
        return result

    def _unexpired_warnings(self, now: datetime) -> list[dict[str, Any]]:
        result = []
        for warning in (self.weather_snapshot or {}).get("warnings") or []:
            valid_until = _parse_datetime(warning.get("valid_until"))
            if valid_until is not None and valid_until.astimezone(self.timezone) >= now:
                result.append(dict(warning))
        result.sort(key=lambda item: item["published_at"])
        return result

    def status_state(self) -> str:
        with self.lock:
            if not self.decision:
                return "Waiting for forecast plan inputs"
            if self.decision.get("advice_only"):
                return ("Manual reserve: evidence incomplete" if self.decision.get("evidence_issues")
                        else "Manual reserve: conditions observed")
            transition = self.decision.get("transition")
            if transition == "manual":
                return "Manual"
            if self.decision.get("evidence_issues"):
                return "Reserve evidence incomplete"
            if transition == "increase":
                return "Reserve increase recommended"
            if transition == "decrease":
                return "Reserve decrease recommended"
            return "Reserve recommendation ready"

    def status_attributes(self) -> dict[str, Any]:
        with self.lock:
            attributes = dict(self.decision or {"dry_run": True, "decision": None})
            return attributes

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log("Reserve Policy state is unavailable; waiting for inputs")
            return
        if not isinstance(document, dict):
            return
        if document.get("schema_version") == 2 and "decision" in document:
            daily = document.get("daily_input")
            weather = document.get("weather_snapshot")
            decision = document.get("decision")
            if (daily is not None and not isinstance(daily, dict)
                    or weather is not None and not isinstance(weather, dict)
                    or decision is not None and not isinstance(decision, dict)):
                log("Reserve Policy persisted state is malformed; waiting for inputs")
                return
            try:
                self.daily_input = daily
                self.weather_snapshot = weather
                self.grid_confidence = str(document.get("grid_confidence") or "unknown")
                self.decision = decision
                # Rebuild old persisted presentation before publishing it.
                if self.daily_input:
                    self._evaluate(self.clock())
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                log(f"Reserve Policy persisted state is malformed: {error}")
                self.daily_input = None
                self.weather_snapshot = None
                self.grid_confidence = "unknown"
                self.decision = None
        else:
            self.decision = document

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            atomic_write_json(
                self.path,
                {
                    "schema_version": 2,
                    "daily_input": self.daily_input,
                    "weather_snapshot": self.weather_snapshot,
                    "grid_confidence": self.grid_confidence,
                    "decision": self.decision,
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as exc:
            log(f"Reserve Policy state save failed: {exc}")
