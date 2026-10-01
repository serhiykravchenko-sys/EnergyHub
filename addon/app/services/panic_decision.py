from math import isfinite


GRID_CONFIDENCE_LEVELS = {"normal", "unstable", "risk", "panic"}

PANIC_MODES = {
    "panic",
    "panic_grid_hold",
}

HYBRID_MODES = {
    "hybrid_charging",
    "hybrid_grid_hold",
}


class PanicDecisionEngine:
    """Conservative 24/7 control of the applied Battery Reserve."""

    def __init__(self):
        self.status = "not_evaluated"
        self.reason = "Automatic Panic has not been evaluated yet"
        self.target_soc = None
        self.target_source = None
        self.release_soc = None
        self.phase = "inactive"

    def evaluate(
        self,
        *,
        autopilot_enabled,
        operating_mode,
        grid_confidence,
        battery_soc,
        grid_available,
        manual_reserve_soc=20,
        now=None,
    ):
        if not autopilot_enabled:
            return self._result(
                status="skipped",
                reason="Autopilot is disabled",
                phase="inactive",
            )

        if operating_mode == "transitioning":
            return self._result(
                status="skipped",
                reason="Inverter transition is in progress",
                phase="transitioning",
            )

        if operating_mode not in {
            "solar",
            *HYBRID_MODES,
            *PANIC_MODES,
        }:
            return self._result(
                status="skipped",
                reason=(
                    f"Operating mode is {operating_mode}; "
                    "Panic cannot take ownership"
                ),
                phase="inactive",
            )

        if not self._valid_number(battery_soc):
            return self._result(
                status="skipped",
                reason="Battery SOC is unavailable",
                phase="unknown",
            )

        if grid_confidence not in GRID_CONFIDENCE_LEVELS:
            return self._result(
                status="skipped",
                reason=(
                    f"Grid Confidence is unsupported: {grid_confidence}"
                ),
                phase="unknown",
            )

        battery_soc = float(battery_soc)
        if not self._valid_reserve(manual_reserve_soc):
            return self._result(status="skipped", reason="Manual Battery Reserve is unavailable", phase="unknown")
        manual_reserve_soc = float(manual_reserve_soc)
        # Grid and forecast/weather allowances are already folded into the
        # applied Battery Reserve. Never apply a second confidence ladder or
        # inherited overnight target here.
        target_soc = manual_reserve_soc
        normal_reserve_cycle = target_soc < 95
        release_soc = (
            min(100, target_soc + 10)
            if normal_reserve_cycle
            else None
        )

        target_sources = [f"applied Battery Reserve={manual_reserve_soc:g}%"]
        target_source = "; ".join(target_sources)

        self.target_soc = round(target_soc, 2)
        self.target_source = target_source
        self.release_soc = release_soc

        if operating_mode in HYBRID_MODES:
            if battery_soc < target_soc:
                phase = (
                    "charging"
                    if grid_available
                    else "waiting_for_grid"
                )
                return self._result(
                    status="handoff_to_charging",
                    reason=(
                        f"Daytime Panic took ownership at SOC="
                        f"{battery_soc:.1f}% below target="
                        f"{target_soc:.1f}%; {target_source}"
                    ),
                    request="panic",
                    target_soc=target_soc,
                    phase=phase,
                )

            if (
                normal_reserve_cycle
                and grid_available
                and battery_soc >= release_soc
            ):
                return self._result(
                    status="handoff_to_solar",
                    reason=(
                        f"Daytime Panic took ownership at SOC="
                        f"{battery_soc:.1f}%, which meets the Normal-grid "
                        f"Solar release threshold {release_soc}%"
                    ),
                    request="solar",
                    target_soc=target_soc,
                    phase="solar",
                )

            return self._result(
                status="handoff_to_grid_hold",
                reason=(
                    f"Daytime Panic took ownership at SOC="
                    f"{battery_soc:.1f}%; preserve the {target_soc:.1f}% "
                    + (
                        f"floor until SOC reaches the {release_soc}% "
                        "Normal-grid Solar release threshold"
                        if normal_reserve_cycle
                        else "target in Panic Grid Hold"
                    )
                ),
                request="panic_grid_hold",
                target_soc=target_soc,
                phase=(
                    "grid_hold"
                    if grid_available
                    else "reserve_support"
                ),
            )

        if battery_soc < target_soc:
            phase = "charging" if grid_available else "waiting_for_grid"
            reason = (
                f"SOC={battery_soc:.1f}% < target={target_soc:.1f}%; "
                f"{target_source}; "
                + (
                    "grid is online, charge now"
                    if grid_available
                    else "grid is offline, remain armed and wait"
                )
            )

            if (
                normal_reserve_cycle
                and operating_mode == "solar"
                and not grid_available
            ):
                return self._result(
                    status="waiting_for_grid",
                    reason=reason,
                    target_soc=target_soc,
                    phase="waiting_for_grid",
                )

            if operating_mode == "panic":
                return self._result(
                    status=phase,
                    reason=reason,
                    phase=phase,
                )

            return self._result(
                status="trigger_charge",
                reason=reason,
                request="panic",
                target_soc=target_soc,
                phase=phase,
            )

        if operating_mode == "solar" and battery_soc <= target_soc:
            if not grid_available:
                return self._result(
                    status="waiting_for_grid",
                    reason=(
                        f"SOC={battery_soc:.1f}% reached the Normal-grid "
                        f"reserve floor={target_soc:.1f}%, but grid power "
                        "is absent; remain in Solar and reevaluate when "
                        "the grid returns"
                    ),
                    target_soc=target_soc,
                    phase="waiting_for_grid",
                )

            return self._result(
                status="trigger_grid_hold",
                reason=(
                    f"SOC={battery_soc:.1f}% reached the Normal-grid "
                    f"reserve floor={target_soc:.1f}%; "
                    + (f"hold until SOC reaches {release_soc}%"
                       if release_soc is not None else "hold at the 95% cap")
                ),
                request="panic_grid_hold",
                target_soc=target_soc,
                phase=(
                    "grid_hold"
                    if grid_available
                    else "reserve_support"
                ),
            )

        if operating_mode == "panic":
            return self._result(
                status="target_reached",
                reason=(
                    f"SOC={battery_soc:.1f}% >= target={target_soc:.1f}%; "
                    f"{target_source}; enter Panic Grid Hold"
                ),
                request="panic_grid_hold",
                target_soc=target_soc,
                phase="grid_hold" if grid_available else "reserve_support",
            )

        if operating_mode == "panic_grid_hold":
            if (
                normal_reserve_cycle
                and grid_available
                and battery_soc >= release_soc
            ):
                return self._result(
                    status="release_solar",
                    reason=(
                        f"SOC={battery_soc:.1f}% reached the Normal-grid "
                        f"Solar release threshold={release_soc}%; "
                        "return to Solar"
                    ),
                    request="solar",
                    target_soc=target_soc,
                    phase="solar",
                )

            return self._result(
                status="grid_hold",
                reason=(
                    f"SOC={battery_soc:.1f}% >= target={target_soc:.1f}%; "
                    f"{target_source}; "
                    + (
                        f"preserve reserve until SOC reaches the "
                        f"{release_soc}% Normal-grid Solar release threshold"
                        if normal_reserve_cycle
                        else "preserve the capped Battery Reserve"
                    )
                ),
                phase="grid_hold" if grid_available else "reserve_support",
            )

        return self._result(
            status="no_action",
            reason=(
                f"SOC={battery_soc:.1f}% >= target={target_soc:.1f}%; "
                f"{target_source}; Panic is not required"
            ),
            phase="inactive",
        )

    def mqtt_values(self):
        values = {
            "panic_decision": self.status,
            "panic_decision_reason": self.reason,
            "panic_phase": self.phase,
        }

        optional_values = {
            "panic_target_soc": self.target_soc,
            "panic_target_source": self.target_source,
        }

        for key, value in optional_values.items():
            if value is not None:
                values[key] = value

        return values

    def requires_immediate_evaluation(
        self,
        *,
        operating_mode,
        grid_confidence,
        battery_soc,
        grid_available,
        manual_reserve_soc=20,
        now=None,
    ):
        """Wake the Normal-grid hysteresis at its exact SOC boundaries."""
        if grid_confidence not in GRID_CONFIDENCE_LEVELS:
            return False
        if not self._valid_number(battery_soc):
            return False
        if not self._valid_reserve(manual_reserve_soc):
            return False

        soc = float(battery_soc)
        floor = float(manual_reserve_soc)
        if (
            operating_mode == "solar"
            and grid_available
            and soc <= floor
        ):
            return True
        return (
            operating_mode == "panic_grid_hold"
            and grid_available
            and (soc >= min(100, floor + 10) or soc < floor)
        )

    def _result(
        self,
        *,
        status,
        reason,
        request=None,
        target_soc=None,
        phase=None,
    ):
        self.status = status
        self.reason = reason
        if target_soc is not None:
            self.target_soc = round(float(target_soc), 2)
        if phase is not None:
            self.phase = phase

        return {
            "status": status,
            "reason": reason,
            "request": request,
            "target_soc": self.target_soc,
            "target_source": self.target_source,
            "release_soc": self.release_soc,
            "phase": self.phase,
        }

    @staticmethod
    def _valid_reserve(value):
        return (PanicDecisionEngine._valid_number(value)
                and 20 <= float(value) <= 95 and float(value) % 5 == 0)

    @staticmethod
    def _valid_number(value):
        if value is None:
            return False

        try:
            return isfinite(float(value))
        except (TypeError, ValueError):
            return False
