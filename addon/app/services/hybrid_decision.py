from datetime import datetime


class HybridDecisionEngine:
    """Plan the cheap-rate night around tomorrow's useful solar start."""

    OVERNIGHT_DROP_SOC = 15.0
    MORNING_SOC_PER_HOUR = 10.0
    DEFAULT_MINIMUM_SOC = 20.0
    MINIMUM_SOC_LOWER_BOUND = 20.0
    MINIMUM_SOC_UPPER_BOUND = 50.0
    MAX_TARGET_SOC = 95.0
    FALLBACK_MORNING_HOURS = 5.0
    BATTERY_CAPACITY_KWH = 16.0
    CONSERVATIVE_BATTERY_EFFICIENCY = 0.90
    POST_07_HOURS = 17.0
    HOURS_PER_DAY = 24.0

    def __init__(self, retained_target_soc=None):
        self.status = "not_evaluated"
        if self._valid_number(retained_target_soc):
            self.reason = (
                "Detailed night plan is unavailable after EnergyHub "
                f"restart; retained target {float(retained_target_soc):.1f}%; "
                "next evaluation is 23:50"
            )
        else:
            self.reason = (
                "No Adaptive Hybrid evaluation has been received since "
                "EnergyHub started; next scheduled evaluation is 23:50"
            )
        self.summary = self.reason

        self.evaluated_soc = None
        self.evaluated_consumption = None
        self.evaluated_forecast = None
        self.evaluated_at = None
        self.calculation = None
        self.projected_soc_at_07 = None
        self.minimum_soc = None
        self.raw_morning_hours = None
        self.morning_hours = None
        self.useful_solar_start = None
        self.effective_solar_start = None
        self.ramp_confirmed = False
        self.ramp_credit_hours = 0.0
        self.ramp_start_power_w = None
        self.ramp_next_power_w = None
        self.morning_reserve_soc = None
        self.morning_model_source = "verified_ramp_fallback"
        self.morning_model_reason = None
        self.morning_model_samples = 0
        self.morning_expected_load_kwh = None
        self.morning_forecast_solar_kwh = None
        self.morning_net_deficit_kwh = None
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
        minimum_soc=None,
        raw_morning_hours=None,
        effective_solar_start=None,
        ramp_confirmed=False,
        ramp_credit_hours=0,
        ramp_start_power_w=None,
        ramp_next_power_w=None,
        flexible_morning_plan=None,
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
        minimum_soc_fallback = not self._valid_number(minimum_soc)
        if minimum_soc_fallback:
            minimum_soc = self.DEFAULT_MINIMUM_SOC
        else:
            minimum_soc = min(
                self.MINIMUM_SOC_UPPER_BOUND,
                max(
                    self.MINIMUM_SOC_LOWER_BOUND,
                    float(minimum_soc),
                ),
            )

        morning_fallback = (
            not self._valid_number(raw_morning_hours)
            and not self._valid_number(morning_hours)
        )
        self.used_fallback = morning_fallback or minimum_soc_fallback

        if morning_fallback:
            raw_morning_hours = self.FALLBACK_MORNING_HOURS
            useful_solar_start = "fallback 12:00"
            effective_solar_start = "fallback 12:00"
        else:
            raw_morning_hours = max(
                0.0,
                float(
                    raw_morning_hours
                    if self._valid_number(raw_morning_hours)
                    else morning_hours
                ),
            )

        ramp_start_power_w = self._optional_round(
            ramp_start_power_w
        )
        ramp_next_power_w = self._optional_round(
            ramp_next_power_w
        )
        ramp_confirmed = bool(
            ramp_confirmed
            and ramp_start_power_w is not None
            and ramp_start_power_w >= 300
            and ramp_next_power_w is not None
            and ramp_next_power_w >= 600
            and raw_morning_hours >= 1
        )
        ramp_credit_hours = 1.0 if ramp_confirmed else 0.0
        morning_hours = max(
            0.0,
            raw_morning_hours - ramp_credit_hours,
        )

        projected_soc = max(
            0.0,
            battery_soc - self.OVERNIGHT_DROP_SOC,
        )
        flexible_available = bool(
            isinstance(flexible_morning_plan, dict)
            and flexible_morning_plan.get("available") is True
            and self._valid_number(
                flexible_morning_plan.get("deficit_kwh")
            )
        )
        if flexible_available:
            morning_deficit_kwh = max(
                0.0,
                float(flexible_morning_plan["deficit_kwh"]),
            )
            morning_reserve_soc = (
                morning_deficit_kwh
                / (
                    self.BATTERY_CAPACITY_KWH
                    * self.CONSERVATIVE_BATTERY_EFFICIENCY
                )
                * 100.0
            )
            self.morning_model_source = "learned_net_energy"
            self.morning_model_reason = str(
                flexible_morning_plan.get("reason") or "available"
            )
            self.morning_model_samples = int(
                flexible_morning_plan.get("sample_count", 0)
            )
            self.morning_expected_load_kwh = self._optional_round(
                flexible_morning_plan.get("expected_load_kwh")
            )
            self.morning_forecast_solar_kwh = self._optional_round(
                flexible_morning_plan.get("forecast_solar_kwh")
            )
            self.morning_net_deficit_kwh = self._optional_round(
                morning_deficit_kwh
            )
            flexible_support = flexible_morning_plan.get(
                "support_time"
            )
            if flexible_support:
                effective_solar_start = str(flexible_support)
        else:
            morning_reserve_soc = (
                morning_hours * self.MORNING_SOC_PER_HOUR
            )
            self.morning_model_source = "verified_ramp_fallback"
            self.morning_model_reason = str(
                (
                    flexible_morning_plan or {}
                ).get("reason")
                or "learned morning profile unavailable"
            )
            self.morning_model_samples = int(
                (flexible_morning_plan or {}).get("sample_count", 0)
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
            minimum_soc
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
        self.minimum_soc = round(minimum_soc, 2)
        self.raw_morning_hours = round(raw_morning_hours, 2)
        self.morning_hours = round(morning_hours, 2)
        self.useful_solar_start = (
            str(useful_solar_start)
            if useful_solar_start
            else "unknown"
        )
        self.effective_solar_start = (
            str(effective_solar_start)
            if (flexible_available or ramp_confirmed)
            and effective_solar_start
            else self.useful_solar_start
        )
        self.ramp_confirmed = ramp_confirmed
        self.ramp_credit_hours = round(ramp_credit_hours, 2)
        self.ramp_start_power_w = ramp_start_power_w
        self.ramp_next_power_w = ramp_next_power_w
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
            f"{minimum_soc:.0f}% selected minimum + max("
            f"{morning_reserve_soc:.1f}% morning, "
            f"{daytime_deficit_soc:.1f}% daytime deficit)"
        )

        if flexible_available:
            self.calculation += (
                f"; learned morning net deficit "
                f"{self.morning_net_deficit_kwh:.2f} kWh across "
                f"hourly net deficits; "
                f"{self.morning_expected_load_kwh:.2f} kWh expected "
                f"essential load and "
                f"{self.morning_forecast_solar_kwh:.2f} kWh forecast "
                f"solar across evaluated intervals; "
                f"{self.morning_model_samples} samples/hour"
            )
        else:
            self.calculation += (
                f"; legacy ramp fallback: {self.morning_model_reason}"
            )

        if self.ramp_confirmed:
            self.calculation += (
                f"; confirmed solar ramp "
                f"{self.ramp_start_power_w:.0f} W → "
                f"{self.ramp_next_power_w:.0f} W gives "
                f"{self.ramp_credit_hours:.1f} h credit; effective "
                f"support {self.effective_solar_start}"
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
            f"effective support {self.effective_solar_start}, "
            f"morning gap {morning_hours:.1f} h after "
            f"{self.ramp_credit_hours:.1f} h ramp credit; "
            f"selected minimum {minimum_soc:.1f}%; target "
            f"{target_soc:.1f}%"
        )

        plan += (
            f"; morning model {self.morning_model_source}"
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
                    f"{plan}; projected 07:00 SOC already meets the "
                    "adaptive target, so night-grid support is not "
                    "required"
                ),
                request=(
                    None
                    if operating_mode == "solar"
                    else "solar"
                ),
                summary=(
                    f"Projected 07:00 SOC {projected_soc:.1f}% meets "
                    f"target {target_soc:.1f}%; remain Solar"
                ),
            )

        if battery_soc >= target_soc:
            return self._result(
                status="hybrid_grid_hold",
                reason=(
                    f"{plan}; SOC is currently at or above target but "
                    "would fall below it by 07:00, so preserve the "
                    "overnight floor in Hybrid Grid Hold now"
                ),
                request="hybrid_grid_hold",
                summary=(
                    f"Projected 07:00 SOC {projected_soc:.1f}% is below "
                    f"target {target_soc:.1f}%; enter Hybrid Grid Hold"
                ),
            )

        return self._result(
            status="hybrid_charging",
            reason=f"{plan}; charge to the adaptive target now",
            request="hybrid",
            summary=(
                f"Current SOC {battery_soc:.1f}% is below target "
                f"{target_soc:.1f}%; enter Hybrid Charging"
            ),
        )

    def mqtt_values(self):
        values = {
            "hybrid_decision": self.status,
            "hybrid_decision_reason": self.summary,
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
            "hybrid_minimum_soc": self.minimum_soc,
            "hybrid_raw_morning_hours": self.raw_morning_hours,
            "hybrid_morning_hours": self.morning_hours,
            "hybrid_useful_solar_start": self.useful_solar_start,
            "hybrid_effective_solar_start": (
                self.effective_solar_start
            ),
            "hybrid_ramp_confirmed": str(
                self.ramp_confirmed
            ).lower(),
            "hybrid_ramp_credit_hours": self.ramp_credit_hours,
            "hybrid_ramp_start_power_w": self.ramp_start_power_w,
            "hybrid_ramp_next_power_w": self.ramp_next_power_w,
            "hybrid_morning_reserve_soc": self.morning_reserve_soc,
            "hybrid_morning_model_source": self.morning_model_source,
            "hybrid_morning_model_reason": self.morning_model_reason,
            "hybrid_morning_model_samples": self.morning_model_samples,
            "hybrid_morning_expected_load_kwh": (
                self.morning_expected_load_kwh
            ),
            "hybrid_morning_forecast_solar_kwh": (
                self.morning_forecast_solar_kwh
            ),
            "hybrid_morning_net_deficit_kwh": (
                self.morning_net_deficit_kwh
            ),
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

    def _result(self, status, reason, request=None, summary=None):
        self.status = status
        self.reason = reason
        self.summary = summary or reason

        return {
            "status": status,
            "reason": reason,
            "request": request,
            "projected_soc_at_07": self.projected_soc_at_07,
            "minimum_soc": self.minimum_soc,
            "raw_morning_hours": self.raw_morning_hours,
            "morning_hours": self.morning_hours,
            "useful_solar_start": self.useful_solar_start,
            "effective_solar_start": self.effective_solar_start,
            "ramp_confirmed": self.ramp_confirmed,
            "ramp_credit_hours": self.ramp_credit_hours,
            "ramp_start_power_w": self.ramp_start_power_w,
            "ramp_next_power_w": self.ramp_next_power_w,
            "morning_reserve_soc": self.morning_reserve_soc,
            "morning_model_source": self.morning_model_source,
            "morning_model_reason": self.morning_model_reason,
            "morning_model_samples": self.morning_model_samples,
            "morning_expected_load_kwh": self.morning_expected_load_kwh,
            "morning_forecast_solar_kwh": (
                self.morning_forecast_solar_kwh
            ),
            "morning_net_deficit_kwh": self.morning_net_deficit_kwh,
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
