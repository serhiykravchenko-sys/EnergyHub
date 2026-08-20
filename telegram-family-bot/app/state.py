from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_STATE = {
    "soc_snapshots": {},
    "night_baselines": {},
    "night_imports": {},
    "last_report_date": None,
    "test_message_version": None,
    "initialized_at": None,
    "grid_online": None,
    "grid_candidate": None,
    "grid_candidate_since": None,
    "outage_started_at": None,
    "grid_confidence": None,
    "pending_notifications": [],
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
            state.setdefault(key, value.copy() if isinstance(value, dict) else value)
        return state

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.path)
