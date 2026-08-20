from datetime import datetime, timedelta


NIGHT_START_TIME = (23, 50)
NIGHT_END_TIME = (7, 0)


class HybridNightEnforcement:
    """Keep the evaluated AHM target authoritative until Solar handover."""

    @staticmethod
    def enforcement_date(now=None):
        current = now or datetime.now().astimezone()
        minutes = current.hour * 60 + current.minute
        start = NIGHT_START_TIME[0] * 60 + NIGHT_START_TIME[1]
        end = NIGHT_END_TIME[0] * 60 + NIGHT_END_TIME[1]

        if minutes >= start:
            return (current.date() + timedelta(days=1)).isoformat()
        if minutes < end:
            return current.date().isoformat()
        return None

    def evaluate(
        self,
        *,
        autopilot_enabled,
        enforcement_until_date,
        operating_mode,
        battery_soc,
        target_soc,
        grid_available,
        telemetry_freshness,
        now=None,
    ):
        active_date = self.enforcement_date(now)

        if not autopilot_enabled:
            return self._result("skipped", "Autopilot is disabled")
        if active_date is None:
            return self._result("outside_window", "Outside the AHM night window")
        if enforcement_until_date != active_date:
            return self._result(
                "inactive",
                "No current AHM night plan is armed",
            )
        if telemetry_freshness != "fresh":
            return self._result(
                "waiting_for_telemetry",
                "Battery telemetry is not fresh",
            )
        if not self._valid_number(battery_soc):
            return self._result("waiting_for_telemetry", "Battery SOC is unavailable")
        if not self._valid_number(target_soc):
            return self._result("inactive", "AHM target is unavailable")
        if operating_mode not in {
            "solar",
            "hybrid_charging",
            "hybrid_grid_hold",
            "transitioning",
        }:
            return self._result(
                "waiting_for_owner",
                f"Operating mode {operating_mode} is not owned by AHM",
            )

        soc = float(battery_soc)
        target = float(target_soc)

        if operating_mode == "transitioning":
            return self._result("transitioning", "An inverter transition is in progress")
        if operating_mode == "hybrid_charging":
            return self._result("charging", "Hybrid Charging is recovering the AHM target")
        if operating_mode == "solar" and soc < target:
            if not grid_available:
                return self._result(
                    "waiting_for_grid",
                    f"SOC {soc:.1f}% is below target {target:.1f}%, but grid is offline",
                )
            return self._result(
                "trigger_charging",
                f"SOC {soc:.1f}% fell below AHM target {target:.1f}% during the night",
                request="hybrid",
            )
        if operating_mode == "solar" and soc == target:
            if not grid_available:
                return self._result(
                    "waiting_for_grid",
                    f"SOC {soc:.1f}% reached target {target:.1f}%, but grid is offline",
                )
            return self._result(
                "trigger_grid_hold",
                f"SOC {soc:.1f}% reached AHM target {target:.1f}% during the night",
                request="hybrid_grid_hold",
            )
        if operating_mode == "hybrid_grid_hold" and soc < target:
            if not grid_available:
                return self._result(
                    "waiting_for_grid",
                    f"SOC {soc:.1f}% fell below target {target:.1f}%, but grid is offline",
                )
            return self._result(
                "resume_charging",
                f"SOC {soc:.1f}% fell below held AHM target {target:.1f}%",
                request="hybrid",
            )

        return self._result(
            "monitoring",
            f"SOC {soc:.1f}% remains above AHM target {target:.1f}%",
        )

    @staticmethod
    def _result(status, reason, request=None):
        return {
            "status": status,
            "reason": reason,
            "request": request,
        }

    @staticmethod
    def _valid_number(value):
        if value is None:
            return False
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        return numeric == numeric
