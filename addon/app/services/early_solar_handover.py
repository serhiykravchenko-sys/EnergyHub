from datetime import datetime
import math


class EarlySolarHandoverEngine:
    """Decide whether Hybrid Grid Hold can safely end before 07:00."""

    LIVE_SOLAR_MIN_W = 300.0
    FORECAST_ENERGY_MIN_KWH = 1.6
    START_MINUTE = 6 * 60
    END_MINUTE = 7 * 60

    def __init__(self):
        self.status = "not_checked"
        self.reason = (
            "Early Solar has not been checked since EnergyHub started"
        )
        self.evaluated_at = None
        self.live_solar_w = None
        self.forecast_energy_kwh = None
        self.battery_soc = None
        self.target_soc = None

    def evaluate(
        self,
        *,
        autopilot_enabled,
        operating_mode,
        battery_soc,
        hybrid_target_soc,
        telemetry_freshness,
        total_solar_fresh,
        total_solar_power_w,
        forecast_energy_kwh,
        grid_available,
        request_date=None,
        now=None,
    ):
        current_time = now or datetime.now().astimezone()
        self.evaluated_at = current_time.isoformat(timespec="seconds")
        self.battery_soc = self._optional_round(battery_soc)
        self.target_soc = self._optional_round(hybrid_target_soc)
        self.live_solar_w = self._optional_round(
            total_solar_power_w,
            digits=1,
        )
        self.forecast_energy_kwh = self._optional_round(
            forecast_energy_kwh,
        )

        if not autopilot_enabled:
            return self._result(
                status="not_applicable",
                reason="Autopilot is disabled",
            )

        current_minute = current_time.hour * 60 + current_time.minute
        if not self.START_MINUTE <= current_minute < self.END_MINUTE:
            return self._result(
                status="not_applicable",
                reason="Outside the 06:00–07:00 early Solar window",
            )

        if operating_mode != "hybrid_grid_hold":
            return self._result(
                status="not_applicable",
                reason=(
                    f"Current strategy is {operating_mode}; "
                    "early Solar requires Hybrid Grid Hold"
                ),
            )

        if request_date != current_time.date().isoformat():
            return self._result(
                status="held",
                reason="The 06:00–07:00 forecast is missing or stale",
            )

        if not self._valid_number(hybrid_target_soc):
            return self._result(
                status="held",
                reason="The persisted Adaptive Hybrid target is unavailable",
            )

        if not self._valid_number(battery_soc):
            return self._result(
                status="held",
                reason="Battery SOC is unavailable",
            )

        if telemetry_freshness != "fresh":
            return self._result(
                status="held",
                reason="Inverter telemetry is not fresh",
            )

        if not grid_available:
            return self._result(
                status="held",
                reason="Grid is offline; preserve the current strategy",
            )

        if not total_solar_fresh:
            return self._result(
                status="held",
                reason="Total Solar telemetry is not fresh",
            )

        if not self._valid_number(total_solar_power_w):
            return self._result(
                status="held",
                reason="Live Total Solar is unavailable",
            )

        if not self._valid_number(forecast_energy_kwh):
            return self._result(
                status="held",
                reason="The 06:00–07:00 solar forecast is unavailable",
            )

        battery_soc = float(battery_soc)
        target_soc = float(hybrid_target_soc)
        live_solar_w = float(total_solar_power_w)
        forecast_energy_kwh = float(forecast_energy_kwh)

        if battery_soc < target_soc:
            return self._result(
                status="held",
                reason=(
                    f"SOC {battery_soc:.1f}% is below the Adaptive Hybrid "
                    f"target {target_soc:.1f}%"
                ),
            )

        if live_solar_w < self.LIVE_SOLAR_MIN_W:
            return self._result(
                status="held",
                reason=(
                    f"Live Total Solar {live_solar_w:.0f} W is below "
                    f"{self.LIVE_SOLAR_MIN_W:.0f} W"
                ),
            )

        if forecast_energy_kwh < self.FORECAST_ENERGY_MIN_KWH:
            return self._result(
                status="held",
                reason=(
                    "Forecast solar 06:00–07:00 "
                    f"{forecast_energy_kwh:.2f} kWh is below "
                    f"{self.FORECAST_ENERGY_MIN_KWH:.2f} kWh"
                ),
            )

        return self._result(
            status="release_requested",
            reason=(
                f"SOC {battery_soc:.1f}% meets target {target_soc:.1f}%; "
                f"live solar {live_solar_w:.0f} W and 06:00–07:00 forecast "
                f"{forecast_energy_kwh:.2f} kWh meet the early Solar gates"
            ),
            request="solar",
        )

    def confirm_transition(self, succeeded, error=None):
        if succeeded:
            self.status = "released"
            self.reason = (
                f"{self.reason}; Solar transition confirmed"
            )
        else:
            self.status = "transition_failed"
            self.reason = (
                f"{self.reason}; Solar transition failed: "
                f"{error or 'confirmation unavailable'}"
            )

        return {
            "status": self.status,
            "reason": self.reason,
        }

    def mqtt_values(self):
        values = {
            "hybrid_early_solar_check": self.status,
            "hybrid_early_solar_reason": self.reason,
        }

        optional_values = {
            "hybrid_early_solar_evaluated_at": self.evaluated_at,
            "hybrid_early_solar_live_power_w": self.live_solar_w,
            "hybrid_early_solar_forecast_kwh": self.forecast_energy_kwh,
        }

        for key, value in optional_values.items():
            if value is not None:
                values[key] = value

        return values

    def _result(self, *, status, reason, request=None):
        self.status = status
        self.reason = reason

        return {
            "status": status,
            "reason": reason,
            "request": request,
            "evaluated_at": self.evaluated_at,
            "live_solar_w": self.live_solar_w,
            "forecast_energy_kwh": self.forecast_energy_kwh,
            "battery_soc": self.battery_soc,
            "target_soc": self.target_soc,
        }

    @staticmethod
    def _valid_number(value):
        if isinstance(value, bool):
            return False

        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    @classmethod
    def _optional_round(cls, value, digits=2):
        if not cls._valid_number(value):
            return None
        return round(float(value), digits)
