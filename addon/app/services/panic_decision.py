from datetime import datetime


PANIC_START_TIME = (7, 0)
PANIC_END_TIME = (23, 50)

PANIC_TARGETS = {
    "normal": 20,
    "unstable": 60,
    "risk": 80,
    "panic": 95,
}

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

        if operating_mode in HYBRID_MODES:
            return self._result(
                status="skipped",
                reason="AHM night strategy is active",
                phase="inactive",
            )

        if operating_mode == "transitioning":
            return self._result(
                status="skipped",
                reason="Inverter transition is in progress",
                phase="transitioning",
            )

        if operating_mode not in {"solar", *PANIC_MODES}:
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
            return self._result(
                status="grid_hold",
                reason=(
                    f"SOC={battery_soc:.1f}% >= target={target_soc:.1f}%; "
                    f"{target_source}; preserve reserve until AHM takes "
                    "ownership at 23:50"
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
            "panic_ahm_target_soc": self.ahm_target_soc,
            "panic_target_source": self.target_source,
        }

        for key, value in optional_values.items():
            if value is not None:
                values[key] = value

        return values

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
