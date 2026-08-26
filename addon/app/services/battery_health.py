import math


class BatteryHealthMonitor:
    def __init__(self):
        self.previous_soc = None
        self.status = "normal"
        self.reason = "ok"

    def update(self, state):
        soc = state.battery_soc

        if soc is None:
            self.status = "warning"
            self.reason = "soc_unavailable"
            return

        try:
            soc = float(soc)
        except (TypeError, ValueError):
            self.status = "warning"
            self.reason = "soc_invalid"
            return

        if not math.isfinite(soc) or not 0 <= soc <= 100:
            self.status = "warning"
            self.reason = "soc_invalid"
            return

        if soc < 15:
            self.status = "warning"
            self.reason = "low_soc"
            self.previous_soc = soc
            return

        if self.previous_soc is None:
            self.status = "normal"
            self.reason = "ok"
            self.previous_soc = soc
            return

        if soc <= 95 and self.previous_soc <= 95:
            delta = soc - self.previous_soc

            if abs(delta) >= 2:
                self.status = "warning"
                self.reason = f"soc_jump_{self.previous_soc:g}_to_{soc:g}"
                self.previous_soc = soc
                return

        self.status = "normal"
        self.reason = "ok"
        self.previous_soc = soc

    def mqtt_values(self):
        return {
            "battery_health": self.status,
            "battery_health_reason": self.reason,
        }
