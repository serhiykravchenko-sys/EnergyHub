from datetime import datetime


PANIC_START_TIME = (7, 0)
PANIC_END_TIME = (23, 50)

PANIC_TARGETS = {
    "normal": 20,
    "unstable": 60,
    "risk": 80,
    "panic": 95,
}

NORMAL_GRID_RELEASE_SOC = 30

PANIC_MODES = {
    "panic",
    "panic_grid_hold",
}

HYBRID_MODES = {
    "hybrid_charging",
    "hybrid_grid_hold",
}


class PanicDecisionEngine:
    """Conservative daytime reserve recovery driven by Grid Confidence."""

    def __init__(self):
        self.status = "not_evaluated"
        self.reason = "Automatic Panic has not been evaluated yet"
        self.target_soc = None
        self.grid_target_soc = None
        self.ahm_target_soc = None
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
        ahm_target_soc=None,
        now=None,
    ):
        current_time = now or datetime.now()

        if not autopilot_enabled:
            return self._result(
                status="skipped",
                reason="Autopilot is disabled",
                phase="inactive",
            )

        if not self._inside_evaluation_window(current_time):
            return self._result(
                status="skipped",
                reason=(
                    "Outside Panic evaluation window "
                    f"{self._format_time(PANIC_START_TIME)}–"
                    f"{self._format_time(PANIC_END_TIME)}"
                ),
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

        if grid_confidence not in PANIC_TARGETS:
            return self._result(
                status="skipped",
                reason=(
                    f"Grid Confidence is unsupported: {grid_confidence}"
                ),
                phase="unknown",
            )

        battery_soc = float(battery_soc)
        grid_target_soc = PANIC_TARGETS[grid_confidence]
        valid_ahm_target = (
            float(ahm_target_soc)
            if self._valid_number(ahm_target_soc)
            else None
        )
        target_soc = max(
            grid_target_soc,
            valid_ahm_target or 0,
        )
        normal_reserve_cycle = (
            grid_confidence == "normal"
            and valid_ahm_target is None
        )
        release_soc = (
            NORMAL_GRID_RELEASE_SOC
            if normal_reserve_cycle
            else None
        )

        target_sources = [
            f"Grid Confidence {grid_confidence}={grid_target_soc}%"
        ]
        if (
            valid_ahm_target is not None
            and valid_ahm_target > grid_target_soc
        ):
            target_sources.append(
                f"unmet AHM target={valid_ahm_target:.1f}%"
            )
        target_source = "; ".join(target_sources)

        self.grid_target_soc = grid_target_soc
        self.ahm_target_soc = valid_ahm_target
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

        if (
            normal_reserve_cycle
            and operating_mode == "solar"
            and battery_soc <= target_soc
        ):
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
                    f"reserve floor={target_soc:.1f}%; hold until "
                    f"SOC reaches {release_soc}%"
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
                        else (
                            "preserve reserve until AHM takes ownership "
                            "at 23:50"
                        )
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
            "panic_grid_target_soc": self.grid_target_soc,
            "panic_ahm_target_soc": (
                self.ahm_target_soc
                if self.ahm_target_soc is not None
                else "None"
            ),
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
        ahm_target_soc=None,
        now=None,
    ):
        """Wake the Normal-grid hysteresis at its exact SOC boundaries."""
        current_time = now or datetime.now()
        if not self._inside_evaluation_window(current_time):
            return False
        if grid_confidence != "normal" or self._valid_number(ahm_target_soc):
            return False
        if not self._valid_number(battery_soc):
            return False

        soc = float(battery_soc)
        if (
            operating_mode == "solar"
            and grid_available
            and soc <= PANIC_TARGETS["normal"]
        ):
            return True
        return (
            operating_mode == "panic_grid_hold"
            and grid_available
            and soc >= NORMAL_GRID_RELEASE_SOC
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
            "grid_target_soc": self.grid_target_soc,
            "ahm_target_soc": self.ahm_target_soc,
            "target_source": self.target_source,
            "release_soc": self.release_soc,
            "phase": self.phase,
        }

    def _inside_evaluation_window(self, current_time):
        minutes_now = current_time.hour * 60 + current_time.minute
        start_minutes = PANIC_START_TIME[0] * 60 + PANIC_START_TIME[1]
        end_minutes = PANIC_END_TIME[0] * 60 + PANIC_END_TIME[1]
        return start_minutes <= minutes_now < end_minutes

    @staticmethod
    def _format_time(value):
        return f"{value[0]:02d}:{value[1]:02d}"

    @staticmethod
    def _valid_number(value):
        if value is None:
            return False

        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False
