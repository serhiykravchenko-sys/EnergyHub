from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_STATE = {
    "last_report_date": None,
    "morning_report_outbox": None,
    "initialized_at": None,
    "grid_online": None,
    "grid_candidate": None,
    "grid_candidate_since": None,
    "outage_started_at": None,
    "grid_confidence": None,
    "grid_confidence_pending": None,
    "grid_confidence_reserve_soc": None,
    "soc_anomaly_initialized": False,
    "soc_anomaly_last_event_id": None,
    "soc_anomaly_last_event_count": None,
    "soc_anomaly_report_events": [],
    "peak_load_guard_last_event_id": None,
    "weather_warning_seen_event_ids": [],
    "weather_warning_report_events": [],
    "weather_reserve_modifier": None,
    "weather_reserve_recommended_soc": None,
    "weather_reserve_restoration_events": [],
    "uhmc_active_warnings": [],
    "uhmc_snapshot_signature": None,
    "uhmc_last_published_at": None,
    "uhmc_next_check_at": None,
    "uhmc_retry_pending": False,
    "uhmc_source_warning_active": False,
    "pending_notifications": [],
    "environment_last_check": None,
    "environment_candidates": {},
    "environment_active": {},
    "environment_recoveries": [],
    "environment_changes_in_report": [],
    "environment_hourly_snapshots": {},
}


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_STATE)
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_STATE)
        for key, value in DEFAULT_STATE.items():
            state.setdefault(
                key,
                value.copy() if isinstance(value, (dict, list)) else value,
            )
        return state

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.path)
