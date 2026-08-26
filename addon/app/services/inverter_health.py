from app.services.inverter_fault_journal import active_qpiws_messages


class InverterHealthMonitor:

    def __init__(self):
        self.status = "unknown"
        self.reason = "not_checked"

    def update(self, data):
        if not data:
            self.status = "warning"
            self.reason = "warning_read_failed"
            return

        active = active_qpiws_messages(data)

        if active:
            self.status = "warning"
            self.reason = ",".join(active)
        else:
            self.status = "normal"
            self.reason = "ok"

    def failure(self):
        self.status = "warning"
        self.reason = "warning_read_failed"

    def mqtt_values(self):
        return {
            "inverter_health": self.status,
            "inverter_health_reason": self.reason,
        }
