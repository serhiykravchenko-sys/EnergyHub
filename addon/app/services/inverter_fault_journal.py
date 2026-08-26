import json
import math
from collections import deque
from datetime import datetime
from pathlib import Path

from app.utils.json_store import atomic_write_json
from app.utils.logger import log


INVERTER_FAULT_JOURNAL_FILE = Path("/data/inverter_fault_journal.json")
INVERTER_FAULT_HISTORY_LIMIT = 100
INVERTER_PREFAULT_MINUTES = 5
INVERTER_TELEMETRY_INTERVAL_SECONDS = 10
INVERTER_PREFAULT_SAMPLE_LIMIT = (
    INVERTER_PREFAULT_MINUTES * 60 // INVERTER_TELEMETRY_INTERVAL_SECONDS
)
IGNORED_QPIWS_KEYS = {"_command", "_command_description", "reserved"}
DASHBOARD_IGNORED_MESSAGES = {"pv_loss_warning"}


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _rounded(value, digits=1):
    value = _number(value)
    return None if value is None else round(value, digits)


def active_qpiws_messages(data):
    if not isinstance(data, dict):
        return []
    return sorted(
        key
        for key, value in data.items()
        if key not in IGNORED_QPIWS_KEYS and str(value) == "1"
    )


def display_name(value):
    return str(value or "unknown").replace("_", " ").strip().title()


class InverterFaultJournal:
    """Persistent QPIWS transition history with bounded pre-event evidence."""

    def __init__(self, path=INVERTER_FAULT_JOURNAL_FILE, clock=None):
        self.path = Path(path) if path else None
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.events = []
        self.total_event_count = 0
        self.active_messages = []
        self.telemetry = deque(maxlen=INVERTER_PREFAULT_SAMPLE_LIMIT)
        self._load()

    def _load(self):
        if not self.path or not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            events = data.get("events", [])
            if isinstance(events, list):
                self.events = events[-INVERTER_FAULT_HISTORY_LIMIT:]
            try:
                total_event_count = int(
                    data.get("total_event_count", len(self.events))
                )
            except (TypeError, ValueError):
                total_event_count = len(self.events)
                log(
                    "Inverter fault journal has an invalid total event "
                    "count; retained history was preserved"
                )
            self.total_event_count = max(
                len(self.events),
                total_event_count,
            )
            active = data.get("active_messages", [])
            if isinstance(active, list):
                self.active_messages = sorted(str(item) for item in active)
            log(
                "Inverter fault journal loaded: "
                f"{len(self.events)} retained incidents, "
                f"{self.total_event_count} total"
            )
        except Exception as error:
            log(f"Failed to load inverter fault journal: {error}")
            self.events = []
            self.total_event_count = 0
            self.active_messages = []

    def _save(self, now):
        if not self.path:
            return
        try:
            atomic_write_json(
                self.path,
                {
                    "schema_version": 1,
                    "saved_at": now.isoformat(),
                    "history_limit": INVERTER_FAULT_HISTORY_LIMIT,
                    "total_event_count": self.total_event_count,
                    "active_messages": self.active_messages,
                    "events": self.events,
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as error:
            log(f"Failed to save inverter fault journal: {error}")

    def observe_telemetry(
        self,
        *,
        valid,
        load_w=None,
        load_percent=None,
        battery_soc=None,
        battery_voltage=None,
        battery_charging_current=None,
        battery_discharging_current=None,
        pv1_power=None,
        pv2_power=None,
        total_pv_power=None,
        grid_available=None,
        grid_voltage=None,
        operating_mode=None,
        telemetry_freshness=None,
    ):
        if not valid:
            return
        self.telemetry.append({
            "timestamp": self.clock().isoformat(),
            "load_w": _rounded(load_w),
            "load_percent": _rounded(load_percent),
            "battery_soc": _rounded(battery_soc),
            "battery_voltage_v": _rounded(battery_voltage, 2),
            "battery_charging_current_a": _rounded(
                battery_charging_current, 2
            ),
            "battery_discharging_current_a": _rounded(
                battery_discharging_current, 2
            ),
            "pv1_power_w": _rounded(pv1_power),
            "pv2_power_w": _rounded(pv2_power),
            "total_pv_power_w": _rounded(total_pv_power),
            "grid_available": (
                bool(grid_available) if grid_available is not None else None
            ),
            "grid_voltage_v": _rounded(grid_voltage, 2),
            "operating_mode": str(operating_mode or "unknown"),
            "telemetry_freshness": str(telemetry_freshness or "unknown"),
        })

    def observe_qpiws(self, data):
        if not isinstance(data, dict) or not data:
            return False
        messages = active_qpiws_messages(data)
        if messages == self.active_messages:
            return False

        now = self.clock()
        if self.active_messages and self.events:
            latest = self.events[-1]
            if latest.get("cleared_at") is None:
                latest["cleared_at"] = now.isoformat()
                try:
                    started = datetime.fromisoformat(latest["started_at"])
                    latest["duration_seconds"] = round(
                        max(0, (now - started).total_seconds()), 1
                    )
                except (KeyError, TypeError, ValueError):
                    latest["duration_seconds"] = None
                latest["recovery"] = (
                    "superseded" if messages else "warning_cleared"
                )

        self.active_messages = messages
        if messages:
            event = {
                "started_at": now.isoformat(),
                "cleared_at": None,
                "duration_seconds": None,
                "messages": messages,
                "display_messages": [display_name(item) for item in messages],
                "pre_fault_minutes": INVERTER_PREFAULT_MINUTES,
                "pre_fault_samples": list(self.telemetry),
                "latest_conditions": (
                    dict(self.telemetry[-1]) if self.telemetry else None
                ),
                "recovery": "active",
            }
            self.events.append(event)
            self.events = self.events[-INVERTER_FAULT_HISTORY_LIMIT:]
            self.total_event_count += 1
            log("Inverter incident recorded: " + ", ".join(messages))
        elif self.events:
            log("Inverter incident cleared")

        self._save(now)
        return True

    def current_state(self):
        messages = self._dashboard_messages(self.active_messages)
        return (
            ", ".join(display_name(item) for item in messages)
            if messages
            else "Normal"
        )

    @staticmethod
    def _dashboard_messages(messages):
        return [
            str(item)
            for item in messages or []
            if str(item).strip().lower() not in DASHBOARD_IGNORED_MESSAGES
        ]

    def dashboard_events(self):
        result = []
        for event in reversed(self.events):
            messages = self._dashboard_messages(event.get("messages"))
            if not messages:
                continue
            exposed = dict(event)
            exposed["messages"] = messages
            exposed["display_messages"] = [
                display_name(item) for item in messages
            ]
            result.append(exposed)
        return result

    def recent_event(self, position):
        events = self.dashboard_events()
        if position < 1 or position > len(events):
            return None
        return events[position - 1]

    def event_state(self, position):
        event = self.recent_event(position)
        if not event:
            return "No incident"
        return ", ".join(event.get("display_messages") or ["Unknown"])

    def event_attributes(self, position):
        event = self.recent_event(position)
        visible_event_count = len(self.dashboard_events())
        return {
            "position": position,
            "event_count": self.total_event_count,
            "retained_event_count": len(self.events),
            "visible_event_count": visible_event_count,
            "history_limit": INVERTER_FAULT_HISTORY_LIMIT,
            "event": event,
        }
