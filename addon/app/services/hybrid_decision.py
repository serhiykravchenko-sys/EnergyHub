from datetime import datetime


class HybridDecisionEngine:
    """Plan the cheap-rate night around tomorrow's useful solar start."""

    OVERNIGHT_DROP_SOC = 15.0
    MORNING_SOC_PER_HOUR = 10.0
    PROTECTED_RESERVE_SOC = 20.0
    SOLAR_RAMP_MARGIN_SOC = 10.0
    MAX_TARGET_SOC = 95.0
    FALLBACK_MORNING_HOURS = 5.0
    BATTERY_CAPACITY_KWH = 16.0
    CONSERVATIVE_BATTERY_EFFICIENCY = 0.90
    POST_07_HOURS = 17.0
    HOURS_PER_DAY = 24.0

    def __init__(self):
        self.status = "not_evaluated"
        self.reason = "Adaptive Hybrid has not been evaluated yet"

        self.evaluated_soc = None
        self.evaluated_consumption = None
        self.evaluated_forecast = None
        self.evaluated_at = None
        self.calculation = None
        self.projected_soc_at_07 = None
        self.morning_hours = None
        self.useful_solar_start = None
        self.morning_reserve_soc = None
        self.expected_consumption_after_07 = None
        self.solar_forecast_after_07 = None
        self.daytime_deficit_kwh = None
        self.daytime_deficit_soc = None
        self.energy_balance_available = False
        self.target_soc = None
        self.target_capped = False
        self.used_fallback = False

    def evaluate(
        self,
        autopilot_enabled,
        operating_mode,
        battery_soc,
        morning_hours,
        useful_solar_start=None,
        forecast_tomorrow=None,
        consumption_today=None,
        solar_forecast_after_07=None,
    ):
        if not autopilot_enabled:
            return self._result(
                status="skipped",
                reason="Autopilot is disabled",
            )

        if operating_mode not in {
            "solar",
            "unknown",
            "panic",
            "panic_grid_hold",
        }:
            return self._result(
                status="skipped",
                reason=(
                    f"Operating mode is {operating_mode}; "
                    "Adaptive Hybrid was not evaluated"
                ),
            )

        if not self._valid_number(battery_soc):
            return self._result(
                status="skipped",
                reason="Battery SOC is unavailable",
            )

        battery_soc = float(battery_soc)
        morning_fallback = not self._valid_number(morning_hours)
        self.used_fallback = morning_fallback

        if morning_fallback:
            morning_hours = self.FALLBACK_MORNING_HOURS
            useful_solar_start = "fallback 12:00"
        else:
            morning_hours = max(0.0, float(morning_hours))

        projected_soc = max(
            0.0,
            battery_soc - self.OVERNIGHT_DROP_SOC,
        )
        morning_reserve_soc = (
            morning_hours * self.MORNING_SOC_PER_HOUR
        )

        expected_consumption_after_07 = None
        daytime_solar = None
        daytime_deficit_kwh = None
        daytime_deficit_soc = 0.0

        if self._valid_number(consumption_today):
            expected_consumption_after_07 = (
                float(consumption_today)
                * self.POST_07_HOURS
                / self.HOURS_PER_DAY
            )

        if self._valid_number(solar_forecast_after_07):
            daytime_solar = float(solar_forecast_after_07)
        elif self._valid_number(forecast_tomorrow):
            # Almost all production is after 07:00. The total forecast is a
            # safe compatibility fallback until the aligned hourly sum is
            # available from Home Assistant.
            daytime_solar = float(forecast_tomorrow)
            self.used_fallback = True

        self.energy_balance_available = (
            expected_consumption_after_07 is not None
            and daytime_solar is not None
        )

        if self.energy_balance_available:
            daytime_deficit_kwh = max(
                0.0,
                expected_consumption_after_07 - daytime_solar,
            )
            daytime_deficit_soc = (
                daytime_deficit_kwh
                / (
                    self.BATTERY_CAPACITY_KWH
                    * self.CONSERVATIVE_BATTERY_EFFICIENCY
                )
                * 100.0
            )
        else:
            self.used_fallback = True

        resilience_need_soc = max(
            morning_reserve_soc,
            daytime_deficit_soc,
        )
        raw_target_soc = (
            self.PROTECTED_RESERVE_SOC
            + self.SOLAR_RAMP_MARGIN_SOC
            + resilience_need_soc
        )
        target_soc = min(self.MAX_TARGET_SOC, raw_target_soc)

        self.evaluated_soc = round(battery_soc, 2)
        self.evaluated_consumption = self._optional_round(
            consumption_today
        )
        self.evaluated_forecast = self._optional_round(
            forecast_tomorrow
        )
        self.projected_soc_at_07 = round(projected_soc, 2)
        self.morning_hours = round(morning_hours, 2)
        self.useful_solar_start = (
            str(useful_solar_start)
            if useful_solar_start
            else "unknown"
        )
        self.morning_reserve_soc = round(
            morning_reserve_soc,
            2,
        )
        self.expected_consumption_after_07 = self._optional_round(
            expected_consumption_after_07
        )
        self.solar_forecast_after_07 = self._optional_round(
            daytime_solar
        )
        self.daytime_deficit_kwh = self._optional_round(
            daytime_deficit_kwh
        )
        self.daytime_deficit_soc = round(
            daytime_deficit_soc,
            2,
        )
        self.target_soc = round(target_soc, 2)
        self.target_capped = raw_target_soc > self.MAX_TARGET_SOC
        self.evaluated_at = (
            datetime.now()
            .astimezone()
            .strftime("%Y-%m-%d %H:%M")
        )
        self.calculation = (
            f"Projected {projected_soc:.1f}% = "
            f"{battery_soc:.1f}% SOC - "
            f"{self.OVERNIGHT_DROP_SOC:.0f}% overnight; "
            f"target {target_soc:.1f}% = "
            f"{self.PROTECTED_RESERVE_SOC:.0f}% reserve + "
            f"{self.SOLAR_RAMP_MARGIN_SOC:.0f}% margin + max("
            f"{morning_reserve_soc:.1f}% morning, "
            f"{daytime_deficit_soc:.1f}% daytime deficit)"
        )

        if self.energy_balance_available:
            self.calculation += (
                f"; daytime deficit {daytime_deficit_kwh:.2f} kWh = "
                f"{expected_consumption_after_07:.2f} kWh expected "
                f"after 07:00 - {daytime_solar:.2f} kWh solar"
            )
        else:
            self.calculation += (
                "; aligned daytime energy unavailable, morning-only "
                "fallback used"
            )

        if self.target_capped:
            self.calculation += (
                f"; raw target {raw_target_soc:.1f}% capped at "
                f"{self.MAX_TARGET_SOC:.0f}%"
            )

        plan = (
            f"SOC now {battery_soc:.1f}%, projected 07:00 "
            f"{projected_soc:.1f}% after {self.OVERNIGHT_DROP_SOC:.0f}% "
            f"night allowance; useful solar {self.useful_solar_start}, "
            f"morning gap {morning_hours:.1f} h; target "
            f"{target_soc:.1f}%"
        )

        if self.energy_balance_available:
            plan += (
                f"; post-07 deficit {daytime_deficit_kwh:.2f} kWh "
                f"({daytime_deficit_soc:.1f}% SOC)"
            )

        if self.target_capped:
            plan += (
                f" (capped from {raw_target_soc:.1f}% at "
                f"{self.MAX_TARGET_SOC:.0f}%)"
            )

        if self.used_fallback:
            plan += (
                "; one or more planning inputs unavailable, "
                "conservative fallback used"
            )

        if projected_soc >= target_soc:
            return self._result(
                status="solar",
                reason=(
                    f"{plan}; "
                    + (
                        "end Panic and restore Solar"
                        if operating_mode in {"panic", "panic_grid_hold"}
                        else "remain in Solar"
                    )
                ),
                request=(
                    "solar"
                    if operating_mode in {"panic", "panic_grid_hold"}
                    else None
                ),
            )

        if battery_soc >= target_soc:
            return self._result(
                status="hybrid_grid_hold",
                reason=f"{plan}; enter Hybrid Grid Hold now",
                request="hybrid_grid_hold",
            )

        return self._result(
            status="hybrid_charging",
            reason=f"{plan}; charge to the adaptive target now",
            request="hybrid",
        )

    def mqtt_values(self):
        values = {
            "hybrid_decision": self.status,
            "hybrid_decision_reason": self.reason,
            "hybrid_battery_refill_required": "",
            "hybrid_total_energy_required": "",
        }

        optional_values = {
            "hybrid_evaluated_soc": self.evaluated_soc,
            "hybrid_evaluated_consumption": self.evaluated_consumption,
            "hybrid_evaluated_forecast": self.evaluated_forecast,
            "hybrid_evaluated_at": self.evaluated_at,
            "hybrid_calculation": self.calculation,
            "hybrid_projected_soc_at_07": self.projected_soc_at_07,
            "hybrid_morning_hours": self.morning_hours,
            "hybrid_useful_solar_start": self.useful_solar_start,
            "hybrid_morning_reserve_soc": self.morning_reserve_soc,
            "hybrid_expected_consumption_after_07": (
                self.expected_consumption_after_07
            ),
            "hybrid_solar_forecast_after_07": (
                self.solar_forecast_after_07
            ),
            "hybrid_daytime_deficit_kwh": self.daytime_deficit_kwh,
            "hybrid_daytime_deficit_soc": self.daytime_deficit_soc,
            "hybrid_energy_balance_available": str(
                self.energy_balance_available
            ).lower(),
            "hybrid_target_soc": self.target_soc,
            "hybrid_target_capped": str(self.target_capped).lower(),
            "hybrid_forecast_fallback": str(self.used_fallback).lower(),
        }

        for key, value in optional_values.items():
            if value is not None:
                values[key] = value

        return values

    def _result(self, status, reason, request=None):
        self.status = status
        self.reason = reason

        return {
            "status": status,
            "reason": reason,
            "request": request,
            "projected_soc_at_07": self.projected_soc_at_07,
            "morning_hours": self.morning_hours,
            "useful_solar_start": self.useful_solar_start,
            "morning_reserve_soc": self.morning_reserve_soc,
            "expected_consumption_after_07": (
                self.expected_consumption_after_07
            ),
            "solar_forecast_after_07": self.solar_forecast_after_07,
            "daytime_deficit_kwh": self.daytime_deficit_kwh,
            "daytime_deficit_soc": self.daytime_deficit_soc,
            "energy_balance_available": self.energy_balance_available,
            "target_soc": self.target_soc,
            "target_capped": self.target_capped,
            "used_fallback": self.used_fallback,
        }

    @staticmethod
    def _valid_number(value):
        if value is None:
            return False

        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False

    @classmethod
    def _optional_round(cls, value):
        if not cls._valid_number(value):
            return None
        return round(float(value), 2)
